#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The sockets of connections: how many there are, TCP, and the network thread's waits."""

from __future__ import annotations

import asyncio
import sys
import time
from typing import TYPE_CHECKING

import pytest

import webrtc
from tests.helpers import (
    connect,
    exchange_ice_candidates,
    exchange_offer_answer,
    open_descriptors,
    wait_for_event,
    wait_for_ice_gathering_complete,
    wait_until,
)
from tests.timing import seconds

if TYPE_CHECKING:
    from tests.helpers import CreatePC

posix_only = pytest.mark.skipif(sys.platform == 'win32', reason='counts the descriptors in /dev/fd')


async def _connected_pair(create_pc: CreatePC) -> tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]:
    caller, callee = create_pc(), create_pc()
    caller.create_data_channel('pair')
    await connect(caller, callee)
    return caller, callee


@posix_only
@pytest.mark.asyncio
async def test_connections_set_up_at_once_open_as_many_sockets_as_one_at_a_time(create_pc: CreatePC) -> None:
    """A connection gathering doesn't allocate its ports again when another one starts."""
    before = open_descriptors()
    await _connected_pair(create_pc)
    one = open_descriptors() - before

    before = open_descriptors()
    await asyncio.gather(*(_connected_pair(create_pc) for _ in range(10)))
    at_once = open_descriptors() - before

    assert at_once <= 10 * one


def _tcp_candidates(sdp: str) -> list[str]:
    return [line for line in sdp.split('\r\n') if line.startswith('a=candidate:') and ' tcp ' in line.lower()]


@pytest.mark.asyncio
async def test_tcp_candidates_are_active_and_listen_nowhere(create_pc: CreatePC) -> None:
    """TCP candidates connect out to a remote passive one, so connections hold no TCP pair per network."""
    pc = create_pc()
    pc.create_data_channel('tcp')

    await pc.set_local_description()
    await wait_for_ice_gathering_complete(pc)

    assert pc.local_description is not None
    candidates = _tcp_candidates(pc.local_description.sdp)
    assert len(candidates) > 0
    assert all('tcptype active' in candidate for candidate in candidates)


#: ports no other test gathers on
TCP_LISTEN_PORT_RANGE = (40100, 40199)


async def _gathered_tcp_candidates(pc: webrtc.RTCPeerConnection) -> list[webrtc.RTCIceCandidate]:
    pc.create_data_channel('tcp')
    await pc.set_local_description()
    await wait_for_ice_gathering_complete(pc)

    assert pc.local_description is not None
    lines = _tcp_candidates(pc.local_description.sdp)
    return [webrtc.RTCIceCandidate(line, sdp_m_line_index=0) for line in lines]


@pytest.mark.asyncio
async def test_tcp_listen_offers_passive_candidates_in_the_port_range(create_pc: CreatePC) -> None:
    low, high = TCP_LISTEN_PORT_RANGE
    listening = create_pc(webrtc.RTCConfiguration(tcp_listen=True, port_range=TCP_LISTEN_PORT_RANGE))
    default = create_pc()

    passive = await _gathered_tcp_candidates(listening)
    active = await _gathered_tcp_candidates(default)

    assert len(passive) > 0
    assert all(candidate.tcp_type == webrtc.RTCIceTcpCandidateType.passive for candidate in passive)
    assert all(candidate.port is not None and low <= candidate.port <= high for candidate in passive)
    assert all(candidate.tcp_type == webrtc.RTCIceTcpCandidateType.active for candidate in active)


def _is_tcp(candidate: webrtc.RTCIceCandidate) -> bool:
    return candidate.protocol == webrtc.RTCIceProtocol.tcp


@pytest.mark.asyncio
async def test_tcp_listen_connects_without_udp(create_pc: CreatePC) -> None:
    caller = create_pc()
    callee = create_pc(webrtc.RTCConfiguration(tcp_listen=True))
    caller.create_data_channel('tcp')
    exchange_ice_candidates(caller, callee, admits=_is_tcp)

    await exchange_offer_answer(caller, callee)

    def connected() -> bool:
        return all(pc.connection_state == webrtc.RTCPeerConnectionState.connected for pc in (caller, callee))

    await wait_until(connected, 'both connections to connect over TCP')
    assert caller.sctp is not None
    pair = caller.sctp.transport.ice_transport.get_selected_candidate_pair()
    assert pair is not None
    assert pair.local.protocol == webrtc.RTCIceProtocol.tcp


@pytest.mark.asyncio
async def test_closing_during_a_flood(create_pc: CreatePC) -> None:
    """Closing both ends while messages are in flight in both directions."""
    caller, callee = create_pc(), create_pc()
    channel = caller.create_data_channel('flood')
    announced = wait_for_event(callee, 'datachannel')
    await connect(caller, callee)
    event = await announced
    assert isinstance(event, webrtc.RTCDataChannelEvent)
    remote = event.channel
    await wait_until(lambda: channel.ready_state == webrtc.RTCDataChannelState.open, 'the channel to open')

    message = bytes(64 * 1024)
    for _ in range(16):
        channel.send(message)
        remote.send(message)

    caller.close()
    callee.close()

    assert caller.connection_state == webrtc.RTCPeerConnectionState.closed


@pytest.mark.asyncio
async def test_idle_connections_leave_the_process_idle(create_pc: CreatePC) -> None:
    """The network thread sleeps while nothing happens, rather than waking for sockets that are always ready."""
    for _ in range(5):
        await _connected_pair(create_pc)
    await asyncio.sleep(1)

    started = time.process_time()
    await asyncio.sleep(1)

    assert time.process_time() - started < seconds(0.5)


@pytest.mark.asyncio
async def test_connections_set_up_and_closed_repeatedly(create_pc: CreatePC) -> None:
    """Sockets come and go with their connections, while others are being set up."""
    for _ in range(5):
        pairs = await asyncio.gather(*(_connected_pair(create_pc) for _ in range(5)))
        for caller, callee in pairs:
            caller.close()
            callee.close()


@pytest.mark.asyncio
async def test_gathering_runs_its_phases_without_waiting_between_them(
    create_pc: CreatePC, pytestconfig: pytest.Config
) -> None:
    """A description sent without trickle doesn't wait for the empty relay and TCP phases."""
    if pytestconfig.getoption('--gc-on-emit'):
        pytest.skip('a wall-clock limit, and --gc-on-emit collects garbage on every event')
    pc = create_pc()
    pc.create_data_channel('gather')

    started = time.perf_counter()
    await pc.set_local_description()
    await wait_for_ice_gathering_complete(pc)

    # libwebrtc's default waits 50 ms between its three phases
    assert time.perf_counter() - started < seconds(0.1)


@pytest.mark.asyncio
async def test_a_candidate_pool_runs_its_phases_without_waiting_between_them(
    create_pc: CreatePC, pytestconfig: pytest.Config
) -> None:
    """The pool, gathered as the connection is created, doesn't wait before its first phase either."""
    if pytestconfig.getoption('--gc-on-emit'):
        pytest.skip('a wall-clock limit, and --gc-on-emit collects garbage on every event')
    pc = create_pc(webrtc.RTCConfiguration(ice_candidate_pool_size=1))
    pc.create_data_channel('gather')

    started = time.perf_counter()
    # not polled: a poll's interval would hide the wait
    complete = wait_for_event(
        pc,
        'icegatheringstatechange',
        predicate=lambda _: pc.ice_gathering_state == webrtc.RTCIceGatheringState.complete,
    )
    await pc.set_local_description()
    await complete

    # libwebrtc's default waits 50 ms before the pool's first phase
    assert time.perf_counter() - started < seconds(0.04)
