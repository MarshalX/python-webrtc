#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The same objects used from many Python threads at once: no crash, no deadlock, no corruption."""

from __future__ import annotations

import asyncio
import concurrent.futures
import gc
import os
import subprocess
import sys
import threading
import time
from typing import Callable
from unittest import mock

import pytest

import webrtc
import wrtc
from tests.helpers import ROOT, connect, exchange_offer_answer, wait_for_event
from tests.isolation import isolated
from webrtc.utils import events


def _join(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(20)
        assert not thread.is_alive(), 'stuck'


def _start(*targets: Callable[[], None]) -> list[threading.Thread]:
    threads = [threading.Thread(target=target, daemon=True) for target in targets]
    for thread in threads:
        thread.start()
    return threads


async def _open_channel(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> webrtc.RTCDataChannel:
    channel = caller.create_data_channel('busy')
    opened = wait_for_event(channel, 'open')
    callee.on('datachannel', lambda event: event.channel.on('message', lambda _message: None))
    await connect(caller, callee)
    await opened
    return channel


@isolated(timeout=90)
def test_constructors_from_many_threads() -> None:
    """Constructors register their Python object with the GIL: pybind11's registry was corrupted."""
    track = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=True))).get_tracks()[0]
    stop = threading.Event()

    def construct() -> None:
        while not stop.is_set():
            webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
            webrtc.RTCPeerConnection().close()
            webrtc.RTCIceTransport().stop()
            gc.collect()

    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        constructing = [pool.submit(construct) for _ in range(6)]
        time.sleep(3)
        stop.set()
        for future in constructing:
            future.result(30)
    track.stop()


async def _release_while_the_signaling_thread_waits(kind: str) -> None:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    channel = await _open_channel(caller, callee)
    released: object
    if kind == 'video generator':
        released = webrtc.VideoTrackGenerator()._native
    elif kind == 'audio generator':
        released = webrtc.MediaStreamTrackGenerator('audio')
    else:
        released = webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(webrtc.VideoTrackGenerator().track)
        )
    gc.collect()
    # the signaling thread delivers the messages, waiting for the GIL this thread keeps
    sys.setswitchinterval(1000)
    for _ in range(200):
        channel.send(b'busy')
    end = time.perf_counter() + 0.3
    while time.perf_counter() < end:
        pass
    del released
    gc.collect()
    sys.setswitchinterval(0.005)
    caller.close()
    callee.close()


@pytest.mark.parametrize('kind', ['video generator', 'audio generator', 'processor'])
@isolated(timeout=30)
def test_released_while_libwebrtc_threads_wait_for_the_gil(kind: str) -> None:
    """A track's proxy released with the GIL deadlocked with the signaling thread."""
    asyncio.run(_release_while_the_signaling_thread_waits(kind))


async def _create_and_release_tracks_while_messages_arrive() -> None:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    channel = await _open_channel(caller, callee)
    stop = threading.Event()

    def create() -> None:
        while not stop.is_set():
            constraints = webrtc.MediaStreamConstraints(audio=True, video=True)
            for track in asyncio.run(webrtc.media_devices.get_user_media(constraints)).get_tracks():
                track.stop()

    def release() -> None:
        while not stop.is_set():
            constraints = webrtc.MediaStreamConstraints(audio=True)
            tracks = [asyncio.run(webrtc.media_devices.get_user_media(constraints)).get_tracks()[0] for _ in range(5)]
            del tracks

    threads = _start(create, create, release, release)
    end = time.monotonic() + 4
    while time.monotonic() < end:
        for _ in range(100):
            channel.send(b'busy')
        await asyncio.sleep(0.001)
    stop.set()
    _join(threads)
    caller.close()
    callee.close()


@isolated
def test_wrappers_created_and_released_on_many_threads() -> None:
    """Releasing a wrapper with the GIL waited for a holder lock held across a BlockingCall."""
    asyncio.run(_create_and_release_tracks_while_messages_arrive())


async def _negotiate_while_transceivers_are_wrapped() -> None:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    stop = threading.Event()

    def create() -> None:
        # new transceivers, wrapped on this thread
        while not stop.is_set():
            pc = webrtc.RTCPeerConnection()
            for track in stream.get_tracks():
                pc.add_transceiver(track)
            pc.get_transceivers()
            pc.close()

    threads = _start(create, create, create)
    end = time.monotonic() + 4
    while time.monotonic() < end:
        # new transceivers of the callee, wrapped on the signaling thread by its track events
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        for track in stream.get_tracks():
            caller.add_transceiver(track)
        await asyncio.wait_for(exchange_offer_answer(caller, callee), 10)
        caller.close()
        callee.close()
    stop.set()
    _join(threads)


@isolated
def test_wrappers_created_while_a_description_wraps_them() -> None:
    """A thread creating a wrapper held the holder's lock waiting for the signaling thread, which waited for it."""
    asyncio.run(_negotiate_while_transceivers_are_wrapped())


async def _read_connections_while_they_connect() -> None:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    connections: list[webrtc.RTCPeerConnection] = []
    stop = threading.Event()

    def read() -> None:
        while not stop.is_set():
            for pc in connections.copy():
                _ = pc.sctp, pc.get_transceivers(), pc.get_senders()
                for receiver in pc.get_receivers():
                    _ = receiver.transport, receiver.track.ready_state
            stream.get_tracks()

    threads = _start(read, read, read)
    end = time.monotonic() + 4
    while time.monotonic() < end:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        connections[:] = [caller, callee]
        for track in stream.get_tracks():
            caller.add_track(track, stream)
        caller.create_data_channel('read')
        await connect(caller, callee)
        caller.close()
        callee.close()
    stop.set()
    _join(threads)


@isolated
def test_objects_of_connections_read_while_they_connect() -> None:
    """Wrapping under a lock of the connection (its SCTP transport, its tracks) waited for the signaling thread."""
    asyncio.run(_read_connections_while_they_connect())


@isolated
def test_callback_argument_that_cannot_be_converted() -> None:
    """An unconvertible callback argument is reported, not fatal."""
    reported: list[str] = []

    def callback(_argument: object) -> None:
        pass

    sys.unraisablehook = lambda unraisable: reported.append(type(unraisable.exc_value).__name__)
    wrtc._callback_unconvertible(callback)

    assert reported == ['RuntimeError']


@pytest.mark.skipif(not wrtc._sanitized, reason='checked in sanitizer builds only')
def test_held_events_with_the_gil_abort() -> None:
    """Held events taken with the GIL held abort."""
    result = subprocess.run(
        [sys.executable, '-c', 'import wrtc; wrtc._held_events_with_gil()'],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode != 0
    assert 'HeldEvents' in result.stderr, result.stderr


class _Parking:
    def __init__(self) -> None:
        self.park_signaling, self.signaling_parked, self.release_signaling = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        self.park_worker, self.worker_parked = threading.Event(), threading.Event()

    def park(self, listeners: events._Listeners, name: str) -> None:
        if name == 'negotiationneeded' and self.park_signaling.is_set():
            self.park_signaling.clear()
            self.signaling_parked.set()
            self.release_signaling.wait(5)
        elif (
            name == 'icecandidate'
            and self.park_worker.is_set()
            and isinstance(listeners.target, webrtc.RTCIceTransport)
        ):
            self.park_worker.clear()
            self.worker_parked.set()
            time.sleep(0.5)
            gc.collect()


def _create_channel(pc: webrtc.RTCPeerConnection) -> None:
    pc.create_data_channel('x')


def _watched() -> tuple[webrtc.RTCPeerConnection, webrtc.RTCIceTransport]:
    garbage = webrtc.RTCIceTransport()
    garbage.stop()
    cycle: list[object] = [garbage]
    cycle.append(cycle)
    pc = webrtc.RTCPeerConnection()
    pc.on('negotiationneeded', lambda _event: None)
    gatherer = webrtc.RTCIceTransport()
    gatherer.on('icecandidate', lambda _event: None)
    return pc, gatherer


@isolated(timeout=30)
def test_wrapper_released_on_the_worker_while_a_constructor_waits_for_it() -> None:
    """Worker GC while a constructor waits for the worker."""
    parking = _Parking()
    original = events._Listeners.__call__
    created = threading.Event()

    def emit(listeners: events._Listeners, name: str, *args: object) -> None:
        parking.park(listeners, name)
        original(listeners, name, *args)

    def create() -> None:
        webrtc.RTCIceTransport()
        created.set()

    with mock.patch.object(events._Listeners, '__call__', emit):
        gc.disable()
        loop = asyncio.new_event_loop()
        _start(loop.run_forever)
        # handlers are registered on a running loop
        watched: concurrent.futures.Future[tuple[webrtc.RTCPeerConnection, webrtc.RTCIceTransport]] = (
            concurrent.futures.Future()
        )
        loop.call_soon_threadsafe(lambda: watched.set_result(_watched()))
        pc, gatherer = watched.result(10)
        parking.park_signaling.set()
        _start(lambda: _create_channel(pc))
        assert parking.signaling_parked.wait(5)
        _start(create)
        time.sleep(0.3)
        parking.park_worker.set()
        _start(gatherer.gather)
        assert parking.worker_parked.wait(5)
        parking.release_signaling.set()
        assert created.wait(5), 'stuck'
    # the parked threads would keep the interpreter from exiting
    os._exit(0)
