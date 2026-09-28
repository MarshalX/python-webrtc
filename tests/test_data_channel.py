#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio

import pytest

import webrtc
from tests.helpers import connect, exchange_ice_candidates, wait_for_event


async def open_pair(caller, callee, **options):
    channel = caller.create_data_channel('chat', **options)
    if options.get('negotiated'):
        remote = callee.create_data_channel('chat', **options)
        opened = [wait_for_event(channel, 'open'), wait_for_event(remote, 'open')]
        await connect(caller, callee)
        await asyncio.gather(*opened)
        return channel, remote

    opened = wait_for_event(channel, 'open')
    announced = wait_for_event(callee, 'datachannel')
    await connect(caller, callee)
    remote = (await announced).channel
    await opened
    return channel, remote


@pytest.mark.asyncio
@pytest.mark.parametrize('negotiated', [False, True])
async def test_messages_both_ways(caller, callee, negotiated):
    options = {'negotiated': True, 'id': 3} if negotiated else {}
    channel, remote = await open_pair(caller, callee, protocol='proto', **options)

    assert remote.label == 'chat' and remote.protocol == 'proto'
    assert channel.ready_state == remote.ready_state == webrtc.RTCDataChannelState.open
    assert channel.id == remote.id

    received = []
    remote.on('message', lambda event: received.append(event.data))
    got_all = asyncio.get_running_loop().create_future()
    remote.on('message', lambda event: len(received) == 3 and not got_all.done() and got_all.set_result(None))

    channel.send('text')
    channel.send(b'\x00\x01')
    channel.send(bytearray(b'\x02'))
    await asyncio.wait_for(got_all, 5)
    assert received == ['text', b'\x00\x01', b'\x02']


@pytest.mark.asyncio
async def test_buffered_amount_and_low_event(caller, callee):
    channel, _ = await open_pair(caller, callee)
    channel.buffered_amount_low_threshold = 0

    channel.send('hello')
    assert channel.buffered_amount == 5
    await wait_for_event(channel, 'bufferedamountlow')
    assert channel.buffered_amount == 0


@pytest.mark.asyncio
async def test_close_states_and_events(caller, callee):
    channel, remote = await open_pair(caller, callee)
    remote_events = []
    remote.on('closing', lambda event: remote_events.append(('closing', remote.ready_state)))
    remote_closed = wait_for_event(remote, 'close')
    local_closing = []
    channel.on('closing', lambda event: local_closing.append(event))

    channel.close()
    assert channel.ready_state == webrtc.RTCDataChannelState.closing
    await remote_closed

    assert remote_events == [('closing', webrtc.RTCDataChannelState.closing)]
    assert remote.ready_state == webrtc.RTCDataChannelState.closed
    # closing locally fires no closing event
    assert local_closing == []
    with pytest.raises(webrtc.InvalidStateError):
        channel.send('late')


def test_create_data_channel_validation(pc):
    with pytest.raises(ValueError):
        pc.create_data_channel('x', max_packet_life_time=1, max_retransmits=1)
    with pytest.raises(ValueError):
        pc.create_data_channel('x', negotiated=True)
    with pytest.raises(ValueError):
        pc.create_data_channel('x', negotiated=True, id=65535)
    # an id is ignored unless negotiated
    assert pc.create_data_channel('x', id=65535).id is None

    pc.create_data_channel('taken', negotiated=True, id=1)
    with pytest.raises(webrtc.OperationError):
        pc.create_data_channel('again', negotiated=True, id=1)

    channel = pc.create_data_channel('x', priority=webrtc.RTCPriorityType.high, ordered=False)
    assert channel.priority == webrtc.RTCPriorityType.high
    assert channel.ordered is False
    assert channel.ready_state == webrtc.RTCDataChannelState.connecting
    with pytest.raises(TypeError):
        channel.send(42)


def test_create_data_channel_on_closed_connection():
    pc = webrtc.RTCPeerConnection()
    pc.close()
    with pytest.raises(webrtc.InvalidStateError):
        pc.create_data_channel('x')


@pytest.mark.asyncio
async def test_max_message_size(caller, callee):
    caller.create_data_channel('size')
    await caller.set_local_description()
    # 65536 until an answer negotiates the max-message-size of the remote peer
    assert caller.sctp.max_message_size == 65536
    caller.close()


@pytest.mark.asyncio
async def test_send_larger_than_max_message_size(caller, callee):
    channel, _ = await open_pair(caller, callee)
    size = caller.sctp.max_message_size
    assert size > 65536

    with pytest.raises(ValueError):
        channel.send(bytes(int(size) + 1))
    assert channel.buffered_amount == 0
    assert channel.ready_state == webrtc.RTCDataChannelState.open


@pytest.mark.asyncio
async def test_stats_are_current(caller, callee):
    channel, remote = await open_pair(caller, callee)
    before = (await callee.get_stats()).of_type('data-channel')[0].bytes_received
    received = wait_for_event(remote, 'message')
    channel.send('hello')
    await received
    # libwebrtc reuses a report for 50 ms: the stats right after a message count it
    after = (await callee.get_stats()).of_type('data-channel')[0].bytes_received
    assert after == before + 5


@pytest.mark.asyncio
async def test_max_channels_once_connected(caller, callee):
    caller.create_data_channel('channels')
    await caller.set_local_description()
    assert caller.sctp.max_channels is None
    await callee.set_remote_description(caller.local_description)
    await callee.set_local_description()
    await caller.set_remote_description(callee.local_description)
    exchange_ice_candidates(caller, callee)
    for _ in range(100):
        if callee.sctp.state == webrtc.SctpTransportState.connected:
            break
        await asyncio.sleep(0.05)
    assert callee.sctp.max_channels > 0
