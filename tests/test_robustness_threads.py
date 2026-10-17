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
import sys
import threading
import time
from typing import Callable

import pytest

import webrtc
import wrtc
from tests.helpers import connect, delivered, exchange_offer_answer, settled_alive, wait_for_event, wait_until
from tests.isolation import isolated
from tests.timing import seconds
from webrtc.utils.loops import LoopState


def _join(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(seconds(20))
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


@isolated(timeout=seconds(90))
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
@isolated(timeout=seconds(30))
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
        await asyncio.wait_for(exchange_offer_answer(caller, callee), seconds(10))
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


def _garbage_connection() -> None:
    """Closed connection in a cycle with its handler."""
    pc = webrtc.RTCPeerConnection()
    pc.on('negotiationneeded', lambda _event, _pc=pc: None)
    pc.close()


def _watched() -> tuple[webrtc.RTCPeerConnection, webrtc.RTCIceTransport]:
    pc = webrtc.RTCPeerConnection()
    pc.on('negotiationneeded', lambda _event: None)
    gatherer = webrtc.RTCIceTransport()
    gatherer.on('icecandidate', lambda _event: None)
    return pc, gatherer


def _watched_on_a_loop() -> tuple[asyncio.AbstractEventLoop, webrtc.RTCPeerConnection, webrtc.RTCIceTransport]:
    """Objects with handlers, plus garbage, on a thread's loop."""
    loop = asyncio.new_event_loop()
    _start(loop.run_forever)
    watched: concurrent.futures.Future[tuple[webrtc.RTCPeerConnection, webrtc.RTCIceTransport]] = (
        concurrent.futures.Future()
    )
    loop.call_soon_threadsafe(lambda: watched.set_result(_watched()))
    loop.call_soon_threadsafe(_garbage_connection)
    pc, gatherer = watched.result(10)
    return loop, pc, gatherer


@isolated(timeout=seconds(60))
def test_wrappers_made_and_collected_while_a_libwebrtc_thread_posts() -> None:
    """GC while signaling is parked mid-post."""
    gc.disable()
    loop, pc, gatherer = _watched_on_a_loop()
    created = threading.Event()

    def create() -> None:
        # unparked once the constructor is known to return
        transport = webrtc.RTCIceTransport()
        created.set()
        del transport

    def create_channel() -> None:
        _ = pc.create_data_channel('x')

    wrtc._testing.park('mailbox.post')
    try:
        _start(create_channel)
        assert wrtc._testing.parked('mailbox.post', seconds(5))
        _start(create)
        _start(gatherer.gather)
        time.sleep(0.3)
        assert not created.is_set()
        gc.collect()
    finally:
        wrtc._testing.release('mailbox.post')
    assert created.wait(seconds(10)), 'stuck'
    gatherer.stop()
    pc.close()
    loop.call_soon_threadsafe(loop.stop)
    wrtc._testing.dispatcher_idle()


@isolated(timeout=seconds(60))
def test_dispatcher_parked_while_objects_go_and_their_loop_closes() -> None:
    """Loop closes while the Dispatcher is parked."""
    baseline = settled_alive()

    async def scenario() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        caller.on('connectionstatechange', lambda _event: None)
        callee.on('connectionstatechange', lambda _event: None)
        channel = await _open_channel(caller, callee)
        wrtc._testing.park('dispatcher.wake')
        # a parked wake makes later events queue behind it
        wrtc._testing.post(wrtc.Mailbox(), 'event', 1)
        assert wrtc._testing.parked('dispatcher.wake', seconds(5))
        channel.send(b'parked')
        callee.close()

    try:
        asyncio.run(scenario())
        gc.collect()
    finally:
        wrtc._testing.release('dispatcher.wake')
    assert settled_alive() == baseline


async def _read_while_the_signaling_thread_is_parked() -> None:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    [track] = (await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))).get_tracks()
    sender = caller.add_track(track)
    await _open_channel(caller, callee)
    [transceiver] = caller.get_transceivers()
    sctp = caller.sctp
    assert sctp is not None
    await wait_until(lambda: sctp.transport.ice_transport.get_selected_candidate_pair() is not None, 'the pair')
    # bound, and never negotiated
    fresh = webrtc.RTCPeerConnection()
    remote = callee.get_transceivers()[0].receiver.track

    def read() -> tuple[object, ...]:
        pair = sctp.transport.ice_transport.get_selected_candidate_pair()
        return (
            fresh.ice_gathering_state,
            remote.ready_state,
            transceiver.mid,
            transceiver.current_direction,
            transceiver.stopped,
            sender.track,
            pair is not None,
            sctp.max_channels,
        )

    expected = read()
    wrtc._testing.park('connection.datachannel')
    try:
        # off the loop: creating it waits for the parked signaling thread too
        creating = asyncio.ensure_future(asyncio.to_thread(caller.create_data_channel, 'parked'))
        assert await asyncio.to_thread(wrtc._testing.parked, 'connection.datachannel', seconds(5))
        assert await asyncio.wait_for(asyncio.to_thread(read), seconds(5)) == expected
    finally:
        wrtc._testing.release('connection.datachannel')
    await creating
    track.stop()
    fresh.close()
    caller.close()
    callee.close()


@isolated(timeout=seconds(60))
def test_getters_do_not_wait_for_the_signaling_thread() -> None:
    """Transceiver, sender, track, ICE and SCTP getters return what Python was shown while signaling is busy."""
    asyncio.run(_read_while_the_signaling_thread_is_parked())


async def _start_while_the_previous_operation_releases() -> list[str]:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    caller.add_transceiver(webrtc.MediaType.audio)
    order: list[str] = []
    callee.on('icegatheringstatechange', lambda _event: order.append(callee.ice_gathering_state.value))
    await caller.set_local_description()
    offer = caller.local_description
    assert offer is not None

    pending = LoopState.of(asyncio.get_running_loop()).pending
    # the offer's completion is still on the signaling thread, before the point the park would stop it at
    await delivered()
    wrtc._testing.park('description.completed')
    try:
        # resolved, while its signaling task is parked before it releases what it held
        await callee.set_remote_description(offer)
        assert await asyncio.to_thread(wrtc._testing.parked, 'description.completed', seconds(5))
        answering = asyncio.ensure_future(callee.set_local_description())
        # pending once its signaling task is posted, behind the parked one
        await wait_until(lambda: len(pending) > 0, 'the next operation')
    finally:
        wrtc._testing.release('description.completed')
    await answering
    order.append('answered')
    await wait_until(lambda: 'gathering' in order, 'gathering')
    caller.close()
    callee.close()
    return order


@isolated(timeout=seconds(60))
def test_operation_holds_its_events_after_the_previous_one_releases() -> None:
    """The next operation starts as the one before releases its hold on events, and still holds its own."""
    order = asyncio.run(_start_while_the_previous_operation_releases())
    assert order.index('answered') < order.index('gathering'), order
