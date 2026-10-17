#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Sockets under churn: connections coming and going, ICE restarts, TCP connections that fail."""

from __future__ import annotations

import asyncio
import pathlib
import socket
import sys
import time
from itertools import starmap
from typing import TYPE_CHECKING

import pytest

import webrtc
import wrtc
from tests.helpers import connect, exchange_offer_answer, wait_for_event, wait_for_ice_gathering_complete, wait_until
from tests.timing import seconds

if TYPE_CHECKING:
    from tests.helpers import CreatePC


def _descriptors() -> int:
    return sum(1 for _ in pathlib.Path('/dev/fd').iterdir())


async def _round(count: int) -> None:
    pairs = [(webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()) for _ in range(count)]
    for caller, _ in pairs:
        caller.create_data_channel('round')
    await asyncio.gather(*starmap(connect, pairs))
    for caller, callee in pairs:
        caller.close()
        callee.close()


@pytest.mark.skipif(sys.platform == 'win32', reason='counts the descriptors in /dev/fd')
@pytest.mark.asyncio
async def test_rounds_of_connections_give_their_sockets_back() -> None:
    """After rounds of connections set up at once and closed, the process has the sockets it had after the first."""
    await _round(5)
    after_first = _descriptors()
    for _ in range(4):
        await _round(5)

    await wait_until(lambda: _descriptors() <= after_first, 'the sockets of closed connections to close')


@pytest.mark.asyncio
async def test_messages_flow_across_ice_restarts(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Each restart gathers again on the connection's own networks and keeps the channel working."""
    channel = caller.create_data_channel('restarts')
    announced = wait_for_event(callee, 'datachannel')
    await connect(caller, callee)
    event = await announced
    assert isinstance(event, webrtc.RTCDataChannelEvent)
    remote = event.channel
    await wait_until(lambda: channel.ready_state == webrtc.RTCDataChannelState.open, 'the channel to open')

    for restart in range(3):
        caller.restart_ice()
        await exchange_offer_answer(caller, callee)
        await wait_until(
            lambda: caller.ice_gathering_state == webrtc.RTCIceGatheringState.complete, 'gathering after the restart'
        )
        received = wait_for_event(remote, 'message')
        channel.send(f'after restart {restart}')
        message = await received
        assert isinstance(message, webrtc.MessageEvent)
        assert message.data == f'after restart {restart}'


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        port: int = probe.getsockname()[1]
        return port


def _to_closed_tcp_port(sdp: str, port: int) -> str:
    """Keeps the TCP candidates on 127.0.0.1, made passive on a port nothing listens on."""
    lines: list[str] = []
    for line in sdp.split('\r\n'):
        if line.startswith('a=candidate:'):
            parts = line.split()
            if parts[2].lower() != 'tcp' or parts[4] != '127.0.0.1':
                continue
            parts[5] = str(port)
            parts[parts.index('tcptype') + 1] = 'passive'
            lines.append(' '.join(parts))
        else:
            lines.append(line)
    return '\r\n'.join(lines)


@pytest.mark.skipif(sys.platform == 'win32', reason='counts the descriptors in /dev/fd')
@pytest.mark.asyncio
async def test_refused_tcp_connects_neither_spin_nor_leak(create_pc: CreatePC) -> None:
    """Retrying a TCP candidate nothing listens on leaves the network thread idle and keeps no socket open."""
    caller, callee = create_pc(), create_pc()
    caller.create_data_channel('refused')
    await caller.set_local_description()
    await wait_for_ice_gathering_complete(caller)
    assert caller.local_description is not None
    offer = webrtc.RTCSessionDescriptionInit(
        type='offer', sdp=_to_closed_tcp_port(caller.local_description.sdp, _closed_port())
    )
    await callee.set_remote_description(offer)
    await callee.set_local_description()
    await wait_for_ice_gathering_complete(callee)
    await asyncio.sleep(1)
    descriptors = _descriptors()

    started = time.process_time()
    await asyncio.sleep(1)

    assert time.process_time() - started < seconds(0.5)
    assert _descriptors() <= descriptors


async def _selected_pair(pc: webrtc.RTCPeerConnection) -> webrtc.RTCIceCandidatePairStats:
    report = await pc.get_stats()
    selected = next(
        s.selected_candidate_pair_id
        for s in report.values()
        if isinstance(s, webrtc.RTCTransportStats) and s.selected_candidate_pair_id is not None
    )
    pair = report[selected]
    assert isinstance(pair, webrtc.RTCIceCandidatePairStats)
    return pair


def _skip_unless_a_flood_fits(pytestconfig: pytest.Config) -> None:
    if pytestconfig.getoption('--gc-on-emit'):
        pytest.skip('a flood of events, and --gc-on-emit collects garbage on every event')
    # the library's floor: below it the kernel overflows here and SCTP stalls on recovery
    if wrtc._testing.udp_receive_buffer() < 8 << 20:
        pytest.skip('the system caps the UDP receive buffer below 8 MB (on Linux, net.core.rmem_max)')


@pytest.mark.asyncio
async def test_a_flood_between_connections_of_one_thread_loses_no_datagram(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, pytestconfig: pytest.Config
) -> None:
    """The network thread reads what it sends to its own sockets before their kernel buffers overflow."""
    _skip_unless_a_flood_fits(pytestconfig)
    channel = caller.create_data_channel('flood')
    announced = wait_for_event(callee, 'datachannel')
    await connect(caller, callee)
    event = await announced
    assert isinstance(event, webrtc.RTCDataChannelEvent)
    remote = event.channel
    await wait_until(lambda: channel.ready_state == webrtc.RTCDataChannelState.open, 'the channel to open')

    count = 20000
    received = 0
    all_received = asyncio.Event()

    def on_message(_event: webrtc.MessageEvent) -> None:
        nonlocal received
        received += 1
        if received == count:
            all_received.set()

    remote.on('message', on_message)
    channel.buffered_amount_low_threshold = 256 << 10
    payload = b'x' * 1024
    for _ in range(count):
        # as a sender keeping under a high watermark does
        if channel.buffered_amount > 1 << 20:
            await wait_for_event(channel, 'bufferedamountlow')
        channel.send(payload)
    await all_received.wait()

    sent = (await _selected_pair(caller)).packets_sent
    delivered = (await _selected_pair(callee)).packets_received
    # SCTP retransmits what the kernel dropped, so only these counts show the loss
    assert sent is not None
    assert delivered is not None
    assert sent - delivered <= 16, f'{sent - delivered} of {sent} datagrams dropped'
