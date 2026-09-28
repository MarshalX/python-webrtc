#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Data channels: opening, messages, closing, and their limits."""

import asyncio

import pytest

import webrtc
from tests.helpers import connect, wait_for_event, wait_until


async def open_pair(caller, callee, **options):
    """Opens a channel of the caller and returns it with its remote end"""
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
    """Both ends of an announced or negotiated channel have its options and id, and messages arrive in order"""
    options = {'negotiated': True, 'id': 3} if negotiated else {}
    channel, remote = await open_pair(caller, callee, protocol='proto', **options)

    assert remote.label == 'chat' and remote.protocol == 'proto'
    assert channel.ready_state == remote.ready_state == webrtc.RTCDataChannelState.open
    assert channel.id == remote.id

    received = []
    got_all = asyncio.get_running_loop().create_future()

    @remote.on('message')
    def on_message(event):
        received.append(event.data)
        if len(received) == 3 and not got_all.done():
            got_all.set_result(None)

    channel.send('text')
    channel.send(b'\x00\x01')
    channel.send(bytearray(b'\x02'))
    await asyncio.wait_for(got_all, 5)
    assert received == ['text', b'\x00\x01', b'\x02']


@pytest.mark.asyncio
async def test_buffered_amount_and_low_event(caller, callee):
    """A message sent is buffered until it's handed to SCTP, then bufferedamountlow is fired"""
    channel, _ = await open_pair(caller, callee)
    channel.buffered_amount_low_threshold = 0

    channel.send('hello')
    assert channel.buffered_amount == 5
    await wait_for_event(channel, 'bufferedamountlow')
    assert channel.buffered_amount == 0


@pytest.mark.asyncio
async def test_close_states_and_events(caller, callee):
    """Closing a channel makes it closing at once; the remote end fires closing then close, the local end nothing"""
    channel, remote = await open_pair(caller, callee)
    remote_events = []

    def on_remote_closing(event):
        remote_events.append(('closing', remote.ready_state))

    remote.on('closing', on_remote_closing)
    remote_closed = wait_for_event(remote, 'close')
    local_closing = []
    channel.on('closing', local_closing.append)

    channel.close()
    assert channel.ready_state == webrtc.RTCDataChannelState.closing
    await remote_closed

    assert remote_events == [('closing', webrtc.RTCDataChannelState.closing)]
    assert remote.ready_state == webrtc.RTCDataChannelState.closed
    assert local_closing == []
    with pytest.raises(webrtc.InvalidStateError):
        channel.send('late')


@pytest.mark.parametrize(
    'init',
    [
        {'max_packet_life_time': 1, 'max_retransmits': 1},
        {'negotiated': True},
        {'negotiated': True, 'id': 65535},
    ],
    ids=['both limits', 'negotiated without id', 'id out of range'],
)
def test_invalid_data_channel_init(pc, init):
    """A channel has at most one of the limits, and a negotiated one an id in range"""
    with pytest.raises(ValueError):
        pc.create_data_channel('x', **init)


def test_id_is_ignored_unless_negotiated(pc):
    """The id of a channel that isn't negotiated is chosen once SCTP is up"""
    assert pc.create_data_channel('x', id=65535).id is None


def test_id_taken(pc):
    """Two negotiated channels can't have the same id"""
    pc.create_data_channel('taken', negotiated=True, id=1)
    with pytest.raises(webrtc.OperationError):
        pc.create_data_channel('again', negotiated=True, id=1)


def test_data_channel_options(pc):
    """A new channel has its options and is connecting, and only sends text and bytes"""
    channel = pc.create_data_channel('x', priority=webrtc.RTCPriorityType.high, ordered=False)
    assert channel.priority == webrtc.RTCPriorityType.high
    assert channel.ordered is False
    assert channel.ready_state == webrtc.RTCDataChannelState.connecting
    with pytest.raises(TypeError):
        channel.send(42)


def test_create_data_channel_on_closed_connection(pc):
    """A closed connection can't create channels"""
    pc.close()
    with pytest.raises(webrtc.InvalidStateError):
        pc.create_data_channel('x')


@pytest.mark.asyncio
async def test_max_message_size_before_an_answer(pc):
    """The max message size is 65536 until an answer negotiates the max-message-size of the remote peer"""
    pc.create_data_channel('size')
    await pc.set_local_description()
    assert pc.sctp.max_message_size == 65536


@pytest.mark.asyncio
async def test_send_larger_than_max_message_size(caller, callee):
    """A message larger than the negotiated max message size isn't sent, and the channel stays open"""
    channel, _ = await open_pair(caller, callee)
    size = caller.sctp.max_message_size
    assert size > 65536

    with pytest.raises(ValueError):
        channel.send(bytes(int(size) + 1))
    assert channel.buffered_amount == 0
    assert channel.ready_state == webrtc.RTCDataChannelState.open


@pytest.mark.asyncio
async def test_stats_are_current(caller, callee):
    """The stats of a channel count a message right after it's received"""
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
    """The max number of channels is known once SCTP is connected"""
    caller.create_data_channel('channels')
    await caller.set_local_description()
    assert caller.sctp.max_channels is None

    await connect(caller, callee)
    await wait_until(lambda: callee.sctp.state == webrtc.SctpTransportState.connected, 'SCTP to connect')
    assert callee.sctp.max_channels > 0
