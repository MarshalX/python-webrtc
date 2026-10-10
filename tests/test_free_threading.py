#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Free-threaded use: a loop per thread over shared objects."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import gc
import sys
import threading
import time
from typing import TYPE_CHECKING, Callable, cast

import pytest

import webrtc
from tests.helpers import NamedEvents, connect, settled_alive, wait_for_event

if TYPE_CHECKING:
    from collections.abc import Generator

GIL_ENABLED: bool = getattr(sys, '_is_gil_enabled', lambda: True)()
pytestmark = pytest.mark.skipif(GIL_ENABLED, reason='the GIL is enabled: needs a free-threaded build')

THREADS = 8
CONNECTIONS = 20
ROUNDS = 300
#: longer is a deadlock
TIMEOUT = 60
#: each collection stops every thread; back to back they'd starve the others
COLLECT_INTERVAL = 0.01


@contextlib.contextmanager
def collecting() -> Generator[None, None, None]:
    """Collects garbage on a thread for the block."""
    stop = threading.Event()

    def collect() -> None:
        while not stop.is_set():
            gc.collect()
            time.sleep(COLLECT_INTERVAL)

    thread = threading.Thread(target=collect, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(TIMEOUT)
        assert not thread.is_alive(), 'the collecting thread is stuck'


def run_threads(*targets: Callable[[], object]) -> None:
    """Runs targets on threads with gc running; re-raises the first error."""
    with collecting(), concurrent.futures.ThreadPoolExecutor(len(targets)) as pool:
        runs = [pool.submit(target) for target in targets]
        for run in runs:
            _ = run.result(TIMEOUT)


async def connected_pair() -> None:
    """Connect, message, close."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    channel = caller.create_data_channel('free-threading')
    received: asyncio.Future[object] = asyncio.get_running_loop().create_future()

    def on_datachannel(event: webrtc.RTCDataChannelEvent) -> None:
        event.channel.on('message', lambda message: received.set_result(message.data))

    callee.on('datachannel', on_datachannel)
    opened = wait_for_event(channel, 'open')
    await connect(caller, callee, timeout=TIMEOUT)
    await opened
    channel.send('hello')
    assert await asyncio.wait_for(received, TIMEOUT) == 'hello'
    caller.close()
    callee.close()


def test_a_loop_per_thread_with_a_connected_pair_each() -> None:
    """Eight concurrent pairs leave nothing alive."""
    baseline = settled_alive()
    run_threads(*(lambda: asyncio.run(connected_pair()) for _ in range(THREADS)))
    assert settled_alive() == baseline


def test_handlers_from_two_loops_while_a_third_thread_closes() -> None:
    """Handler churn from two loops during close."""
    pc = webrtc.RTCPeerConnection()
    events = cast('NamedEvents', pc)
    started = threading.Barrier(3)

    async def register(name: str) -> None:
        def handler(_event: webrtc.Event) -> None:
            pass

        started.wait(TIMEOUT)
        for _ in range(ROUNDS):
            events.on(name, handler)
            assert name in pc.event_names()
            events.off(name, handler)
            await asyncio.sleep(0)

    def close() -> None:
        started.wait(TIMEOUT)
        pc.close()

    run_threads(
        lambda: asyncio.run(register('connectionstatechange')),
        lambda: asyncio.run(register('negotiationneeded')),
        close,
    )
    assert pc.signaling_state == webrtc.RTCSignalingState.closed
    assert pc.event_names() == set()


def test_close_races_create_offer() -> None:
    """Close races pending offers."""
    connections = [webrtc.RTCPeerConnection() for _ in range(CONNECTIONS)]
    started = threading.Barrier(2)

    async def offers() -> None:
        started.wait(TIMEOUT)
        for pc in connections:
            offer = asyncio.ensure_future(pc.create_offer())
            _ = await asyncio.wait({offer})
            if not offer.cancelled():
                exception = offer.exception()
                assert exception is None or isinstance(exception, webrtc.InvalidStateError), exception

    def close() -> None:
        started.wait(TIMEOUT)
        for pc in connections:
            pc.close()

    run_threads(lambda: asyncio.run(offers()), close)
    assert all(pc.signaling_state == webrtc.RTCSignalingState.closed for pc in connections)
