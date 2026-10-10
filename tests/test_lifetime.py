#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Ownership and lifetime of the native wrappers: no leaks, no use-after-free, stable identity and state."""

from __future__ import annotations

import asyncio
import gc
import inspect
import pathlib
import re
import subprocess
import sys
import textwrap
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, cast

import pytest

import webrtc
import wrtc
from tests.helpers import (
    QUIET_PERIOD,
    collect,
    connect,
    exchange_offer_answer,
    settled_alive,
    wait_for_event,
    wait_until,
)
from tests.isolation import isolated
from webrtc.utils import lifetime, loops

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator


async def received_track_event(event: Awaitable[webrtc.Event]) -> webrtc.RTCTrackEvent:
    received = await event
    assert isinstance(received, webrtc.RTCTrackEvent)
    return received


def alive_factories() -> int:
    """Factories constructed and not destroyed yet, once the count settles."""
    return settled_alive()[1]


def peer_connection_cycle() -> None:
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.add_transceiver(webrtc.MediaType.video)
    pc.get_transceivers()
    pc.close()
    del pc
    collect()


@pytest.fixture
def collected() -> Iterator[None]:
    """Nothing created by earlier tests may keep the default factory alive."""
    collect()
    yield
    collect()


pytestmark = pytest.mark.usefixtures('collected')


def test_peer_connection_cycles_do_not_leak_factories() -> None:
    """Closed and collected connections release their factory."""
    baseline = alive_factories()

    for _ in range(30):
        peer_connection_cycle()

    assert alive_factories() == baseline


def test_factories_return_to_baseline_when_everything_is_gone() -> None:
    """Everything shares one factory, which is gone with the last object using it."""
    baseline = alive_factories()

    pc = webrtc.RTCPeerConnection()
    stream = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True)))
    generator = webrtc.MediaStreamTrackGenerator('audio')
    pc.add_track(stream.get_tracks()[0])
    pc.add_track(generator)

    # one factory for everything
    assert alive_factories() == (baseline if baseline != 0 else 1)

    pc.close()
    del pc, stream, generator
    collect()

    assert alive_factories() == baseline


def test_everything_alive_shares_one_factory() -> None:
    """New connections use the factory of the media alive."""
    stream = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True)))
    source_track = webrtc.MediaStreamTrackGenerator('audio')
    before = alive_factories()

    connections = [webrtc.RTCPeerConnection() for _ in range(5)]
    assert alive_factories() == before

    for pc in connections:
        pc.add_track(stream.get_tracks()[0])
        pc.add_track(source_track)
        pc.close()


@pytest.mark.asyncio
async def test_async_with_closes_connection() -> None:
    """Leaving async with closes the connection, also on an error."""
    async with webrtc.RTCPeerConnection() as pc:
        assert pc.connection_state == webrtc.RTCPeerConnectionState.new
    assert pc.connection_state == webrtc.RTCPeerConnectionState.closed

    with pytest.raises(RuntimeError):
        async with webrtc.RTCPeerConnection() as pc:
            raise RuntimeError
    assert pc.connection_state == webrtc.RTCPeerConnectionState.closed


def test_closed_connection_keeps_its_factory_shared() -> None:
    """A closed connection and its tracks keep their factory, which new connections reuse."""
    pc = webrtc.RTCPeerConnection()
    receiver_track = pc.add_transceiver(webrtc.MediaType.audio).receiver.track
    pc.close()
    before = alive_factories()

    # the first factory is alive while the closed connection and its track are, so it must be reused
    pc2 = webrtc.RTCPeerConnection()
    assert alive_factories() == before
    pc2.close()

    assert receiver_track.ready_state == webrtc.MediaStreamTrackState.ended


def test_dropped_track_wrappers_are_not_notified() -> None:
    """Toggling a track notifies its observers, a dropped wrapper must not be one of them."""
    streams = [
        asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))) for _ in range(50)
    ]
    tracks = [stream.get_tracks()[0] for stream in streams]
    del tracks
    collect()

    for i in range(10):
        for stream in streams:
            stream.get_tracks()[0].enabled = bool(i % 2)


def test_destroyed_track_wrapper_is_not_notified() -> None:
    """A track wrapper dies while libwebrtc keeps the track alive in a sender."""
    pc = webrtc.RTCPeerConnection()
    stream = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True)))
    pc.add_track(stream.get_tracks()[0])
    del stream
    collect()

    for i in range(10):
        track = pc.get_senders()[0].track
        assert track is not None
        track.enabled = bool(i % 2)
        del track
        collect()

    pc.close()


def test_track_state_survives_gc() -> None:
    """The state of a track is kept by its native object, not by its wrapper."""
    stream = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True)))
    track = stream.get_tracks()[0]
    track.enabled = False
    track.stop()
    del track
    collect()

    track = stream.get_tracks()[0]
    assert track.ready_state == webrtc.MediaStreamTrackState.ended
    assert track.enabled is False


def test_track_state_survives_gc_of_all_python_references() -> None:
    """The state of a remote track survives when no wrapper of it is left."""
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.get_transceivers()[0].receiver.track.stop()
    collect()

    assert pc.get_transceivers()[0].receiver.track.ready_state == webrtc.MediaStreamTrackState.ended
    pc.close()


def test_transceiver_identity() -> None:
    """The same transceiver, sender, receiver and track are wrapped by the same native wrappers."""
    pc = webrtc.RTCPeerConnection()
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    collect()

    assert pc.get_transceivers()[0] == transceiver
    assert pc.get_senders()[0] == transceiver.sender
    assert pc.get_receivers()[0] == transceiver.receiver
    assert transceiver.receiver.track == transceiver.receiver.track
    pc.close()


def test_sender_identity(audio_stream: webrtc.MediaStream) -> None:
    """A sender and its track are the same objects after a collection."""
    pc = webrtc.RTCPeerConnection()
    track = audio_stream.get_tracks()[0]
    sender = pc.add_track(track)
    collect()

    assert pc.get_senders()[0] == sender
    assert sender.track == track
    pc.close()


def test_drop_and_refetch_before_negotiation() -> None:
    """Wrappers dropped and fetched again, many times, stay valid."""
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.add_transceiver(webrtc.MediaType.video)

    for _ in range(50):
        for transceiver in pc.get_transceivers():
            _ = transceiver.sender.track, transceiver.sender.transport
            _ = transceiver.receiver.track.ready_state, transceiver.receiver.transport
        for sender in pc.get_senders():
            _ = sender.track
        for receiver in pc.get_receivers():
            _ = receiver.track.enabled
        del transceiver, sender, receiver, _
        collect()

    pc.close()


@pytest.mark.asyncio
async def test_drop_and_refetch_transports(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """Transports dropped and fetched again, many times, stay valid and shared."""
    caller.add_track(audio_stream.get_tracks()[0])
    await exchange_offer_answer(caller, callee)

    transport = caller.get_senders()[0].transport
    assert transport is not None
    ice_transport = transport.ice_transport
    del transport, ice_transport

    for _ in range(50):
        for pc in (caller, callee):
            read_transports(pc)
        del pc
        collect()

    assert caller.get_senders()[0].transport == caller.get_transceivers()[0].receiver.transport
    sender_transport, receiver_transport = caller.get_senders()[0].transport, caller.get_receivers()[0].transport
    assert sender_transport is not None
    assert receiver_transport is not None
    assert sender_transport.ice_transport == receiver_transport.ice_transport


@pytest.mark.asyncio
async def test_transports_outlive_closed_connection(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """Transports kept after their connection is closed and collected report closed."""
    caller.add_track(audio_stream.get_tracks()[0])
    await exchange_offer_answer(caller, callee)

    transport = caller.get_senders()[0].transport
    assert transport is not None
    ice_transport = transport.ice_transport
    caller.close()
    callee.close()
    collect()

    assert transport.state == webrtc.RTCDtlsTransportState.closed
    assert ice_transport.state == webrtc.RTCIceTransportState.closed


@isolated(timeout=60)
def test_states_show_the_engine_once_their_loop_is_gone() -> None:
    """Loop closed with queued changes shows engine state."""

    async def scenario() -> tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection, webrtc.RTCDataChannel]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        channel = caller.create_data_channel('states')
        opened = wait_for_event(channel, 'open')
        announced = wait_for_event(callee, 'datachannel')
        await connect(caller, callee)
        await opened
        remote = cast('webrtc.RTCDataChannelEvent', await announced).channel
        wrtc._testing.park('dispatcher.wake')
        # a parked wake makes the close's state changes queue behind it
        wrtc._testing.post(wrtc.Mailbox(), 'event', 1)
        assert wrtc._testing.parked('dispatcher.wake', 5)
        remote.close()
        return caller, callee, channel

    try:
        caller, callee, channel = asyncio.run(scenario())
    finally:
        wrtc._testing.release('dispatcher.wake')
    # the closing records were dropped with the loop
    asyncio.run(wait_until(lambda: channel.ready_state == webrtc.RTCDataChannelState.closed, 'the channel to close'))
    caller.close()
    callee.close()


def read_transports(pc: webrtc.RTCPeerConnection) -> None:
    for transceiver in pc.get_transceivers():
        for transport in (transceiver.sender.transport, transceiver.receiver.transport):
            if transport is not None:
                _ = transport.state, transport.ice_transport.state, transport.ice_transport.gathering_state


def read_until_stopped(pc: webrtc.RTCPeerConnection, stop: threading.Event) -> None:
    while not stop.is_set():
        for transceiver in pc.get_transceivers():
            _ = transceiver.direction, transceiver.receiver.track.ready_state, transceiver.sender.track
        for sender in pc.get_senders():
            _ = sender.track, sender.transport
        for receiver in pc.get_receivers():
            _ = receiver.track.enabled, receiver.transport
        _ = pc.connection_state, pc.signaling_state


def test_getters_while_connection_is_closed_and_dropped(audio_stream: webrtc.MediaStream) -> None:
    """Reading from other threads while the connection is closed and dropped neither crashes nor deadlocks."""
    track = audio_stream.get_tracks()[0]

    for _ in range(20):
        pc = webrtc.RTCPeerConnection()
        pc.add_track(track)
        pc.add_transceiver(webrtc.MediaType.video)
        stop = threading.Event()
        executor = ThreadPoolExecutor(max_workers=4)
        readers = [executor.submit(read_until_stopped, pc, stop) for _ in range(4)]

        pc.close()
        del pc
        collect()
        stop.set()

        # raises what a reader raised, or TimeoutError if it's stuck
        for reader in readers:
            reader.result(timeout=10)
        executor.shutdown()
        collect()


def connection_with_a_handler_referencing_it(delivered: asyncio.Future[None]) -> weakref.ref[webrtc.RTCPeerConnection]:
    pc = webrtc.RTCPeerConnection()

    @pc.on('negotiationneeded')
    def on_negotiation(_event: webrtc.Event) -> None:
        pc.get_transceivers()
        if not delivered.done():
            delivered.set_result(None)

    pc.add_transceiver(webrtc.MediaType.audio)
    return weakref.ref(pc)


@pytest.mark.parametrize('closed', [True, False])
def test_handlers_referencing_their_connection_keep_it_until_close_or_loop_release(*, closed: bool) -> None:
    """Self-referencing handler keeps the connection until close."""
    baseline = alive_factories()

    async def scenario() -> weakref.ref[webrtc.RTCPeerConnection]:
        delivered = asyncio.get_running_loop().create_future()
        ref = connection_with_a_handler_referencing_it(delivered)
        await asyncio.wait_for(delivered, 5)
        collect()
        pc = ref()
        assert pc is not None
        if closed:
            pc.close()
            del pc
            collect()
            assert ref() is None
        return ref

    ref = asyncio.run(scenario())
    collect()

    assert ref() is None
    assert alive_factories() == baseline


def test_connection_bound_by_its_child_is_unrooted_by_a_close_from_another_thread() -> None:
    """Close from another thread unroots on the bound loop."""
    pc = webrtc.RTCPeerConnection()
    assert pc._native_obj._mailbox is None

    async def root_a_child() -> None:
        state = loops.LoopState.of(asyncio.get_running_loop())
        channel = pc.create_data_channel('rooted')
        channel.on('open', lambda _event: channel)
        assert pc._native_obj._mailbox == state.mailbox.id
        assert channel in state.active
        await asyncio.get_running_loop().run_in_executor(None, pc.close)
        assert state.active == {}

    asyncio.run(root_a_child())


@pytest.mark.asyncio
async def test_channel_handlers_do_not_dangle_after_close_and_gc() -> None:
    """Handlers of a channel collected with echoed messages in flight are never called again, and nothing crashes."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    channel = caller.create_data_channel('lifetime')
    received: list[str] = []

    def on_close(_event: webrtc.Event) -> None:
        received.append('close')

    channel.on('message', lambda event: received.append(str(event.data)))
    channel.on('close', on_close)

    @callee.on('datachannel')
    def on_channel(event: webrtc.RTCDataChannelEvent) -> None:
        remote = event.channel

        @remote.on('message')
        def echo(message: webrtc.MessageEvent) -> None:
            remote.send(message.data)

    opened = wait_for_event(channel, 'open')
    await connect(caller, callee)
    await opened

    channel.send('ping')
    caller.close()
    callee.close()
    del channel, caller, callee
    collect()
    await asyncio.sleep(QUIET_PERIOD)
    collect()
    assert 'close' not in received


@pytest.mark.asyncio
async def test_connections_dropped_while_emitting_events() -> None:
    """Events of connections that are destroyed meanwhile are dropped safely: a crash test, for sanitizers."""
    for _ in range(20):
        pc = webrtc.RTCPeerConnection()
        pc.on('icecandidate', lambda _: None)
        pc.on('icegatheringstatechange', lambda _: None)
        pc.create_data_channel('gather')
        await pc.set_local_description()
        del pc
        collect()
    # the events of the gathering that goes on
    await asyncio.sleep(QUIET_PERIOD)
    collect()


def test_process_exits_after_connecting() -> None:
    """Wrappers destroyed at exit unregister while libwebrtc threads may be wrapping objects, without deadlock."""
    script = textwrap.dedent(
        """
        import asyncio
        import webrtc
        from tests.helpers import connect, wait_for_event

        async def main():
            for _ in range(3):
                caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
                channel = caller.create_data_channel('exit')
                # the channel opens after the connection connects
                opened = wait_for_event(channel, 'open')
                await connect(caller, callee)
                await opened
                caller.sctp.transport.ice_transport.on('selectedcandidatepairchange', lambda event: None)
                channel.send('bye')
            print('connected')

        asyncio.run(main())
        """
    )
    # from the root of the project, which has the tests package (pytest may run from elsewhere, like cibuildwheel)
    root = pathlib.Path(pathlib.Path(pathlib.Path(__file__).resolve()).parent).parent
    result = subprocess.run(
        [sys.executable, '-c', script], capture_output=True, text=True, timeout=60, cwd=root, check=False
    )
    assert 'connected' in result.stdout, result.stderr[-2000:]
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.mark.asyncio
async def test_stream_tracks_read_while_they_change(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """Reading a remote stream's tracks while a description changes them doesn't deadlock with its observer."""
    audio = audio_stream.get_audio_tracks()[0]
    sender = caller.add_track(audio, audio_stream)
    track_event = wait_for_event(callee, 'track')
    await exchange_offer_answer(caller, callee)
    remote = (await received_track_event(track_event)).streams[0]

    stop = threading.Event()

    def read() -> None:
        while not stop.is_set():
            remote.get_tracks()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        for _ in range(10):
            # removing and adding the track back changes the tracks of the remote stream
            caller.remove_track(sender)
            await asyncio.wait_for(exchange_offer_answer(caller, callee), 5)
            sender = caller.add_track(audio, audio_stream)
            await asyncio.wait_for(exchange_offer_answer(caller, callee), 5)
    finally:
        stop.set()
        reader.join(5)
    assert not reader.is_alive()


def _collect_on_dispatcher_wakes() -> None:
    gc.disable()
    collections: list[threading.Thread] = []

    def wake(mailbox_id: int) -> None:
        if threading.current_thread() is not threading.main_thread():
            gc.collect()
            collections.append(threading.current_thread())
        loops._wake(mailbox_id)

    async def main() -> weakref.ref[webrtc.RTCPeerConnection]:
        # a closed connection in a cycle with its handler
        pc = webrtc.RTCPeerConnection()
        pc.add_transceiver(webrtc.MediaType.audio)
        pc.on('connectionstatechange', lambda _event, _pc=pc: None)
        pc.close()
        ref = weakref.ref(pc)
        del pc

        wrtc._set_wake(wake)
        transport = webrtc.RTCIceTransport()
        done = asyncio.get_running_loop().create_future()

        def on_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
            if event.candidate is None and not done.done():
                done.set_result(None)

        transport.on('icecandidate', on_candidate)
        transport.gather()
        await asyncio.wait_for(done, 10)
        transport.stop()
        return ref

    ref = asyncio.run(main())
    wrtc._set_wake(loops._wake)
    assert ref() is None
    assert len(collections) > 0
    assert threading.main_thread() not in collections


@isolated(timeout=60)
def test_collected_on_the_dispatcher_thread() -> None:
    """GC on the Dispatcher releases a connection."""
    _collect_on_dispatcher_wakes()


def generators_with_ended_handlers() -> tuple[weakref.ref[object], ...]:
    audio = webrtc.MediaStreamTrackGenerator('audio')
    video = webrtc.VideoTrackGenerator()
    audio.on('ended', lambda _: audio.kind)
    video.track.on('ended', lambda _: video.track)
    return weakref.ref(audio), weakref.ref(video), weakref.ref(video.track)


def stop_tracks(refs: list[weakref.ref[object]]) -> None:
    for ref in refs:
        track = ref()
        if isinstance(track, webrtc.MediaStreamTrack):
            track.stop()


@pytest.mark.parametrize('stopped', [True, False])
def test_generators_are_collected_once_stopped_or_their_loop_closes(*, stopped: bool) -> None:
    """Live track with ended handler kept until stop."""
    baseline = alive_factories()

    async def scenario() -> list[weakref.ref[object]]:
        refs = [ref for _ in range(10) for ref in generators_with_ended_handlers()]
        await asyncio.sleep(QUIET_PERIOD)
        collect()
        assert all(ref() is not None for ref in refs)
        if stopped:
            stop_tracks(refs)
            collect()
            assert [ref for ref in refs if ref() is not None] == []
        return refs

    refs = asyncio.run(scenario())
    collect()

    assert [ref for ref in refs if ref() is not None] == []
    assert alive_factories() == baseline


def test_generator_track_stays_ended_without_its_wrapper() -> None:
    """A generator whose stopped track is collected keeps dropping what's written."""
    generator = wrtc.TrackGenerator('video')
    track = generator.track
    assert generator.live
    track.stop()
    del track
    collect()

    assert not generator.live
    assert webrtc.MediaStreamTrack._wrap(generator.track).ready_state == webrtc.MediaStreamTrackState.ended


async def processor_with_handler_on_its_track() -> webrtc.MediaStreamTrackProcessor:
    track = (await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=True))).get_tracks()[0]
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
    track.on('ended', lambda _: processor.readable)
    track.stop()
    return processor


async def stream_with_handler_on_its_track() -> webrtc.MediaStream:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))
    track = stream.get_tracks()[0]
    track.on('ended', lambda _: stream.id)
    track.stop()
    return stream


def processor_of_generator_with_handler() -> webrtc.MediaStreamTrackProcessor:
    generator = webrtc.MediaStreamTrackGenerator('video')
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(generator))
    generator.on('ended', lambda _: processor.readable)
    generator.stop()
    return processor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'create',
    [processor_with_handler_on_its_track, stream_with_handler_on_its_track, processor_of_generator_with_handler],
)
async def test_handlers_of_owned_tracks_do_not_keep_owners_alive(create: Callable[[], object]) -> None:
    """Ended track handlers keep nothing alive."""
    baseline = alive_factories()
    refs: list[weakref.ref[object]] = []
    for _ in range(5):
        created = create()
        refs.append(weakref.ref(await created if inspect.isawaitable(created) else created))
    del created
    await asyncio.sleep(QUIET_PERIOD)
    collect()

    assert [ref for ref in refs if ref() is not None] == []
    assert alive_factories() == baseline


async def stream_with_a_handler_on_its_live_track() -> weakref.ref[webrtc.MediaStream]:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))
    stream.get_tracks()[0].on('ended', lambda _: stream.id)
    return weakref.ref(stream)


def test_handler_of_a_live_track_keeps_its_stream_until_its_loop_closes() -> None:
    """Live track handler keeps its stream alive."""
    baseline = alive_factories()

    async def scenario() -> weakref.ref[webrtc.MediaStream]:
        ref = await stream_with_a_handler_on_its_live_track()
        await asyncio.sleep(QUIET_PERIOD)
        collect()
        assert ref() is not None
        return ref

    ref = asyncio.run(scenario())
    collect()

    assert ref() is None
    assert alive_factories() == baseline


def test_stream_keeps_the_state_of_its_tracks() -> None:
    """The native stream keeps its tracks weakly, the Python one keeps them: a stopped track stays stopped."""
    stream = webrtc.MediaStream(
        asyncio.run(
            webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
        ).get_tracks()
    )
    for track in stream.get_tracks():
        track.stop()
    del track
    collect()

    assert all(track.ready_state == webrtc.MediaStreamTrackState.ended for track in stream.get_tracks())
    assert len(stream.get_audio_tracks()) == len(stream.get_video_tracks()) == 1


async def owner_with_handler_on_its_track(
    part: str, *, holds_track: bool
) -> tuple[webrtc.RTCPeerConnection, webrtc.RTCRtpSender | webrtc.RTCRtpReceiver]:
    pc = webrtc.RTCPeerConnection()
    owner: webrtc.RTCRtpSender | webrtc.RTCRtpReceiver
    if part == 'sender':
        stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))
        owner = pc.add_track(stream.get_tracks()[0])
    else:
        owner = pc.add_transceiver(webrtc.MediaType.audio).receiver
    track = owner.track
    assert track is not None

    def on_ended(_event: webrtc.Event) -> object:
        # like a handler holding its track event, which has both
        return (owner.track, track) if holds_track else owner.track

    track.on('ended', on_ended)
    return pc, owner


@pytest.mark.asyncio
@pytest.mark.parametrize('holds_track', [False, True])
@pytest.mark.parametrize('part', ['sender', 'receiver'])
async def test_handler_of_a_track_referencing_its_sender_or_receiver(part: str, *, holds_track: bool) -> None:
    """Handlers of a track are released once it ends, so they don't keep its sender or receiver alive."""
    baseline = alive_factories()

    async def create() -> weakref.ref[webrtc.RTCRtpSender | webrtc.RTCRtpReceiver]:
        pc, owner = await owner_with_handler_on_its_track(part, holds_track=holds_track)
        pc.close()
        if part == 'sender':
            # a local track outlives the connection
            track = owner.track
            assert track is not None
            track.stop()
        return weakref.ref(owner)

    ref = await create()
    await asyncio.sleep(QUIET_PERIOD)
    collect()

    assert ref() is None
    assert alive_factories() == baseline


@pytest.mark.asyncio
async def test_handlers_of_a_live_track_keep_its_sender_alive() -> None:
    """Like in a browser, a live track keeps the handlers that may still be called, until it's stopped."""
    baseline = alive_factories()

    async def create() -> weakref.ref[webrtc.RTCRtpSender | webrtc.RTCRtpReceiver]:
        pc, owner = await owner_with_handler_on_its_track('sender', holds_track=False)
        pc.close()
        return weakref.ref(owner)

    ref = await create()
    await asyncio.sleep(QUIET_PERIOD)
    collect()

    sender = ref()
    assert sender is not None
    track = sender.track
    assert track is not None
    track.stop()
    del sender, track
    collect()

    assert ref() is None
    assert alive_factories() == baseline


def alive_objects() -> dict[str, int]:
    """The native objects alive by type, once releases on helper threads are done."""
    return settled_alive()[0]


@pytest.mark.asyncio
async def test_a_session_releases_every_native_object() -> None:
    """Connections with media, channels, processors and generators, closed and dropped: nothing native is left."""
    baseline = alive_objects()

    async def session() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
        for track in stream.get_tracks():
            caller.add_track(track, stream)
        generator = webrtc.VideoTrackGenerator()
        caller.add_track(generator.track)
        channel = caller.create_data_channel('session')
        received = wait_for_event(callee, 'track')
        await connect(caller, callee)
        remote = (await received_track_event(received)).track
        reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(remote)).readable.get_reader()
        writer = generator.writable.get_writer()
        await writer.write(
            webrtc.VideoFrame(
                bytes(64 * 48 * 4),
                webrtc.VideoFrameBufferInit(format='RGBA', coded_width=64, coded_height=48, timestamp=0),
            )
        )
        frame = (await asyncio.wait_for(reader.read(), 5)).value
        assert frame is not None
        frame.close()
        await caller.get_stats()
        channel.send('bye')
        for track in stream.get_tracks():
            track.stop()
        caller.close()
        callee.close()

    await session()
    await asyncio.sleep(QUIET_PERIOD)

    assert alive_objects() == baseline


@pytest.mark.asyncio
async def test_operation_pending_at_close_does_not_keep_its_connection_alive() -> None:
    """A task kept until done, as asyncio recommends, doesn't keep a connection closed during its operation."""
    baseline = alive_objects()
    tasks: set[asyncio.Future[None]] = set()

    async def close_during_operation() -> weakref.ref[webrtc.RTCPeerConnection]:
        pc = webrtc.RTCPeerConnection()
        pc.add_transceiver(webrtc.MediaType.audio)
        task = asyncio.ensure_future(pc.set_local_description())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        await asyncio.sleep(0)
        pc.close()
        await asyncio.sleep(QUIET_PERIOD)
        return weakref.ref(pc)

    connection = await close_during_operation()

    assert tasks == set()
    assert alive_objects() == baseline
    assert connection() is None


def test_dispose_while_factories_are_alive() -> None:
    """dispose() refuses while factories are alive; later factories still work."""
    pc = webrtc.RTCPeerConnection()
    with pytest.raises(webrtc.InvalidStateError):
        wrtc.PeerConnectionFactory.dispose()
    pc.close()

    assert _connects_after_dispose()


async def _connect() -> bool:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    caller.create_data_channel('dispose')
    await connect(caller, callee)
    connected = caller.connection_state == webrtc.RTCPeerConnectionState.connected
    caller.close()
    callee.close()
    return connected


@isolated
def _connects_after_dispose() -> bool:
    wrtc.PeerConnectionFactory.dispose()
    return asyncio.run(_connect())


@pytest.mark.asyncio
async def test_releases_share_one_thread(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Releases all happen on the Dispatcher."""
    candidates: list[webrtc.RTCIceCandidate] = []

    @caller.on('icecandidate')
    def on_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
        if event.candidate is not None:
            candidates.append(event.candidate)

    caller.create_data_channel('release')
    await connect(caller, callee)
    for _ in range(20):
        await callee.add_ice_candidate(candidates[0])
    assert wrtc._testing.dispatcher_threads() <= 1


def test_repr(pc: webrtc.RTCPeerConnection) -> None:
    assert re.fullmatch(r'<webrtc\.RTCPeerConnection object at 0x[0-9a-f]+>', repr(pc)) is not None


@pytest.mark.asyncio
async def test_closed_channel_is_collected_while_connection_is_open() -> None:
    """A closed, dropped channel is collected."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    try:
        channel = caller.create_data_channel('collected')
        channel.on('message', lambda _event: None)
        opened = wait_for_event(channel, 'open')
        await connect(caller, callee)
        await opened
        closed = wait_for_event(channel, 'close')
        channel.close()
        await closed
        ref = weakref.ref(channel)
        del channel, opened, closed
        collect()
        await asyncio.sleep(QUIET_PERIOD)
        collect()
        assert ref() is None
    finally:
        caller.close()
        callee.close()


def test_wrappers_are_canonical() -> None:
    """One wrapper per native object, across gc."""
    pc = webrtc.RTCPeerConnection()
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    assert pc.get_transceivers()[0] is transceiver
    assert pc.get_senders()[0] is transceiver.sender
    assert transceiver.receiver.track is transceiver.receiver.track
    collect()
    assert pc.get_transceivers()[0] is transceiver
    assert pc.get_receivers()[0] is transceiver.receiver
    assert webrtc.RTCPeerConnection._wrap(pc._native_obj) is pc
    pc.close()


def test_constructed_objects_are_their_wrappers(audio_stream: webrtc.MediaStream) -> None:
    """Getters return the constructed object."""
    pc = webrtc.RTCPeerConnection()
    generator = webrtc.MediaStreamTrackGenerator('audio')
    track = audio_stream.get_tracks()[0]
    assert pc.add_track(generator).track is generator
    assert pc.add_track(track).track is track
    stream = webrtc.MediaStream([track])
    assert stream.get_tracks()[0] is track
    pc.close()


@pytest.mark.asyncio
async def test_events_carry_the_objects_of_the_getters(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """Track event objects match the getters."""
    caller.add_track(audio_stream.get_tracks()[0], audio_stream)
    received = wait_for_event(callee, 'track')
    await exchange_offer_answer(caller, callee)
    event = await received_track_event(received)
    assert event.transceiver is callee.get_transceivers()[0]
    assert event.receiver is event.transceiver.receiver
    assert event.track is event.receiver.track
    assert event.streams[0].get_tracks()[0] is event.track
    transform = webrtc.RTCRtpScriptTransform(lambda _event: None)
    event.receiver.transform = transform
    assert event.receiver.transform is transform
    decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions('AES_128_GCM_SHA256_128'))
    event.receiver.transform = decryptor
    assert event.receiver.transform is decryptor


@pytest.mark.asyncio
async def test_candidates_are_the_same_objects_each_time() -> None:
    """Candidates match the event objects."""
    transport = webrtc.RTCIceTransport()
    gathered: list[webrtc.RTCIceCandidate] = []

    def on_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
        if event.candidate is not None:
            gathered.append(event.candidate)

    def end_of_candidates(event: webrtc.Event) -> bool:
        assert isinstance(event, webrtc.RTCPeerConnectionIceEvent)
        return event.candidate is None

    transport.on('icecandidate', on_candidate)
    done = wait_for_event(transport, 'icecandidate', predicate=end_of_candidates)
    transport.gather()
    await done
    candidates = transport.get_local_candidates()
    assert len(candidates) == len(gathered) > 0
    assert all(candidate is event_candidate for candidate, event_candidate in zip(candidates, gathered))
    transport.stop()


@pytest.mark.asyncio
async def test_replace_track_runs_in_the_chain_of_its_connection(
    pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """replace_track() waits for chained operations."""
    sender = pc.add_track(audio_stream.get_tracks()[0])
    connection = wrtc.RTCPeerConnection._connectionOf(sender._native_obj)
    assert connection is not None
    assert webrtc.RTCPeerConnection._wrap(connection) is pc
    pending = asyncio.ensure_future(pc.set_local_description())
    await asyncio.sleep(0)
    await sender.replace_track(None)
    assert pending.done()


def test_the_wrapper_of_a_native_object_gets_the_class_of_its_kind() -> None:
    """Unwrapped native objects get the registered class."""
    options = webrtc.SFrameTransformOptions('AES_128_GCM_SHA256_128')
    decryptor = webrtc.RTCRtpSFrameDecryptor(options)
    assert lifetime.wrapper_of(decryptor._native_obj) is decryptor
    assert isinstance(lifetime.wrapper_of(wrtc.SFrameTransform(1, encrypting=False)), webrtc.RTCRtpSFrameDecryptor)
    assert isinstance(lifetime.wrapper_of(wrtc.SFrameTransform(1, encrypting=True)), webrtc.RTCRtpSFrameEncryptor)
    assert isinstance(lifetime.wrapper_of(wrtc.TrackGenerator('audio').track), webrtc.MediaStreamTrack)


async def _connected_objects() -> list[object]:
    """Connection-side objects."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))
    sender = caller.add_track(stream.get_tracks()[0], stream)
    channel = caller.create_data_channel('slots')
    await connect(caller, callee)
    sctp = caller.sctp
    assert sctp is not None
    return [
        caller,
        callee,
        channel,
        sctp,
        sctp.transport,
        sctp.transport.ice_transport,
        sender.dtmf,
        sender,
        *callee.get_receivers(),
        *caller.get_transceivers(),
        *stream.get_tracks(),
        stream,
    ]


async def _media_objects() -> list[object]:
    """Standalone objects."""
    generator = webrtc.MediaStreamTrackGenerator('video')
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(generator))
    transformers: list[webrtc.RTCRtpScriptTransformer] = []
    transform = webrtc.RTCRtpScriptTransform(lambda event: transformers.append(event.transformer))
    await wait_until(lambda: len(transformers) == 1, 'the transformer')
    options = webrtc.SFrameTransformOptions('AES_128_GCM_SHA256_128')
    return [
        generator,
        processor,
        transform,
        transformers[0],
        webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions('AES_128_GCM_SHA256_128')),
        webrtc.RTCRtpSFrameDecryptor(options),
        webrtc.SFrameEncryptorStream(options),
        webrtc.SFrameDecryptorStream(options),
        await webrtc.RTCPeerConnection.generate_certificate('ECDSA'),
        webrtc.RTCSessionDescription('offer'),
        webrtc.media_devices,
        webrtc.RTCIceTransport(),
    ]


@pytest.mark.asyncio
async def test_wrappers_take_no_attributes() -> None:
    """Wrappers declare slots."""
    objects = [*await _connected_objects(), *await _media_objects()]
    bases = (webrtc.WebRTCObject, webrtc.EventTarget)
    public = {
        cls for name in webrtc.__all__ if isinstance(cls := getattr(webrtc, name), type) and issubclass(cls, bases)
    }
    assert {type(obj) for obj in objects} >= public - {*bases, webrtc.UniformEventTarget}
    name = 'unknown'
    for obj in objects:
        with pytest.raises(AttributeError):
            setattr(obj, name, 1)
    for obj in objects:
        if isinstance(obj, webrtc.RTCPeerConnection):
            obj.close()
        elif isinstance(obj, webrtc.MediaStreamTrack):
            obj.stop()
