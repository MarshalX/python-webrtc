#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The sockets of connections: how many there are, TCP, and the network thread's waits."""

from __future__ import annotations

import asyncio
import pathlib
import sys
import time
from typing import TYPE_CHECKING

import pytest

import webrtc
from tests.helpers import connect, wait_for_event, wait_for_ice_gathering_complete, wait_until

if TYPE_CHECKING:
    from tests.helpers import CreatePC

posix_only = pytest.mark.skipif(sys.platform == 'win32', reason='counts the descriptors in /dev/fd')


def _descriptors() -> int:
    return sum(1 for _ in pathlib.Path('/dev/fd').iterdir())


async def _connected_pair(create_pc: CreatePC) -> tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]:
    caller, callee = create_pc(), create_pc()
    caller.create_data_channel('pair')
    await connect(caller, callee)
    return caller, callee


@posix_only
@pytest.mark.asyncio
async def test_connections_set_up_at_once_open_as_many_sockets_as_one_at_a_time(create_pc: CreatePC) -> None:
    """A connection gathering doesn't allocate its ports again when another one starts."""
    before = _descriptors()
    await _connected_pair(create_pc)
    one = _descriptors() - before

    before = _descriptors()
    await asyncio.gather(*(_connected_pair(create_pc) for _ in range(10)))
    at_once = _descriptors() - before

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

    assert time.process_time() - started < 0.5


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
    assert time.perf_counter() - started < 0.1
