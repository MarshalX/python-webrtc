#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Ownership and lifetime of the native wrappers: no leaks, no use-after-free, stable identity and state."""

from __future__ import annotations

import asyncio
import gc
import pathlib
import subprocess
import sys
import textwrap
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

import webrtc
import wrtc
from tests.helpers import QUIET_PERIOD, connect, exchange_offer_answer, wait_for_event

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator


def collect() -> None:
    gc.collect()
    gc.collect()


async def received_track_event(event: Awaitable[webrtc.Event]) -> webrtc.RTCTrackEvent:
    received = await event
    assert isinstance(received, webrtc.RTCTrackEvent)
    return received


def alive_factories() -> int:
    """Factories constructed and not destroyed yet, once the count settles."""
    # the last reference to one may be released on a helper thread (see CreateSessionDescriptionObserver)
    collect()
    count = wrtc._alive_factories()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        time.sleep(0.05)
        current = wrtc._alive_factories()
        if current == count:
            break
        count = current
    return count


def peer_connection_cycle() -> None:
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.add_transceiver(webrtc.MediaType.video)
    pc.get_transceivers()
    pc.close()
    del pc
    collect()


@pytest.fixture
def isolated() -> Iterator[None]:
    """Nothing created by earlier tests may keep the default factory alive."""
    collect()
    yield
    collect()


pytestmark = pytest.mark.usefixtures('isolated')


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
    stream = webrtc.get_user_media()
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
    stream = webrtc.get_user_media()
    source_track = webrtc.MediaStreamTrackGenerator('audio')
    before = alive_factories()

    connections = [webrtc.RTCPeerConnection() for _ in range(5)]
    assert alive_factories() == before

    for pc in connections:
        pc.add_track(stream.get_tracks()[0])
        pc.add_track(source_track)
        pc.close()


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
    streams = [webrtc.get_user_media() for _ in range(50)]
    tracks = [stream.get_tracks()[0] for stream in streams]
    del tracks
    collect()

    for i in range(10):
        for stream in streams:
            stream.get_tracks()[0].enabled = bool(i % 2)


def test_destroyed_track_wrapper_is_not_notified() -> None:
    """A track wrapper dies while libwebrtc keeps the track alive in a sender."""
    pc = webrtc.RTCPeerConnection()
    stream = webrtc.get_user_media()
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
    stream = webrtc.get_user_media()
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

    assert transport.state == webrtc.DtlsTransportState.closed
    assert ice_transport.state == webrtc.RTCIceTransportState.closed


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


@pytest.mark.asyncio
async def test_handlers_referencing_their_connection_do_not_keep_it_alive() -> None:
    """The garbage collector sees the handlers while Python alone owns the connection."""
    baseline = alive_factories()
    delivered = asyncio.get_running_loop().create_future()

    def create() -> weakref.ref[webrtc.RTCPeerConnection]:
        pc = webrtc.RTCPeerConnection()

        @pc.on('negotiationneeded')
        def on_negotiation(_event: webrtc.Event) -> None:
            pc.get_transceivers()
            if not delivered.done():
                delivered.set_result(None)

        pc.add_transceiver(webrtc.MediaType.audio)
        return weakref.ref(pc)

    ref = create()
    await asyncio.wait_for(delivered, 5)
    collect()

    assert ref() is None
    assert alive_factories() == baseline


@pytest.mark.asyncio
async def test_channel_handlers_do_not_dangle_after_close_and_gc() -> None:
    """Handlers of a channel collected with echoed messages in flight are never called again, and nothing crashes."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    channel = caller.create_data_channel('lifetime')
    received: list[str] = []

    def on_close(_event: webrtc.Event) -> None:
        received.append('close')

    channel.on('message', lambda event: received.append(event.data))
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


def test_collected_on_libwebrtc_thread() -> None:
    """The garbage collector running on a libwebrtc thread (to emit an event) releases a connection elsewhere."""
    script = textwrap.dedent(
        """
        import asyncio
        import gc
        import threading
        import webrtc
        from webrtc.utils import events

        async def main():
            gc.disable()
            # garbage: a connection in a cycle with its handlers, left for the collector
            pc = webrtc.RTCPeerConnection()
            pc.add_transceiver(webrtc.MediaType.audio)
            pc.on('connectionstatechange', lambda event, pc=pc: None)
            del pc

            emit = events._Listeners.__call__
            def collecting(self, name, *args):
                if threading.current_thread() is not threading.main_thread():
                    gc.collect()
                emit(self, name, *args)
            events._Listeners.__call__ = collecting

            transport = webrtc.RTCIceTransport()
            done = asyncio.get_running_loop().create_future()
            transport.on('icecandidate', lambda event: event.candidate or done.done() or done.set_result(None))
            transport.gather()
            await asyncio.wait_for(done, 10)
            transport.stop()
            print('collected')

        asyncio.run(main())
        """
    )
    root = pathlib.Path(pathlib.Path(pathlib.Path(__file__).resolve()).parent).parent
    result = subprocess.run(
        [sys.executable, '-c', script], capture_output=True, text=True, timeout=60, cwd=root, check=False
    )
    assert 'collected' in result.stdout, result.stderr[-2000:]


@pytest.mark.asyncio
async def test_generators_are_collected() -> None:
    """An audio generator is its own track: its handlers mustn't keep it alive."""
    baseline = alive_factories()

    def create() -> tuple[weakref.ref[object], ...]:
        audio = webrtc.MediaStreamTrackGenerator('audio')
        video = webrtc.VideoTrackGenerator()
        audio.on('ended', lambda _: audio.kind)
        video.track.on('ended', lambda _: video.track)
        return weakref.ref(audio), weakref.ref(video), weakref.ref(video.track)

    refs = [ref for _ in range(10) for ref in create()]
    await asyncio.sleep(QUIET_PERIOD)
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


def processor_with_handler_on_its_track() -> webrtc.MediaStreamTrackProcessor:
    track = webrtc.get_user_media(audio=False, video=True).get_tracks()[0]
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
    track.on('ended', lambda _: processor.readable)
    track.stop()
    return processor


def stream_with_handler_on_its_track() -> webrtc.MediaStream:
    stream = webrtc.get_user_media(audio=True, video=False)
    stream.get_tracks()[0].on('ended', lambda _: stream.id)
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
    """Handlers of a track referencing its processor or stream don't keep them alive."""
    baseline = alive_factories()
    refs = [weakref.ref(create()) for _ in range(5)]
    await asyncio.sleep(QUIET_PERIOD)
    collect()

    assert [ref for ref in refs if ref() is not None] == []
    assert alive_factories() == baseline


def test_stream_keeps_the_state_of_its_tracks() -> None:
    """The native stream keeps its tracks weakly, the Python one keeps them: a stopped track stays stopped."""
    stream = webrtc.MediaStream(webrtc.get_user_media(audio=True, video=True).get_tracks())
    for track in stream.get_tracks():
        track.stop()
    del track
    collect()

    assert all(track.ready_state == webrtc.MediaStreamTrackState.ended for track in stream.get_tracks())
    assert len(stream.get_audio_tracks()) == len(stream.get_video_tracks()) == 1


@pytest.mark.xfail(
    strict=True,
    reason='known leak: the native sender and receiver keep the wrappers of their tracks, whose state (like the id of '
    'a remote track) is theirs, so handlers of the track referencing its sender or receiver are a cycle through C++',
)
@pytest.mark.asyncio
@pytest.mark.parametrize('part', ['sender', 'receiver'])
async def test_handler_of_a_track_referencing_its_sender_or_receiver(part: str) -> None:
    baseline = alive_factories()

    def create() -> weakref.ref[webrtc.RTCRtpSender | webrtc.RTCRtpReceiver]:
        pc = webrtc.RTCPeerConnection()
        if part == 'sender':
            owner = pc.add_track(webrtc.get_user_media(audio=True, video=False).get_tracks()[0])
        else:
            owner = pc.add_transceiver(webrtc.MediaType.audio).receiver
        track = owner.track
        assert track is not None

        def on_ended(_event: webrtc.Event) -> webrtc.MediaStreamTrack | None:
            return owner.track

        track.on('ended', on_ended)
        pc.close()
        return weakref.ref(owner)

    ref = create()
    await asyncio.sleep(QUIET_PERIOD)
    collect()

    assert ref() is None
    assert alive_factories() == baseline


def alive_objects() -> dict[str, int]:
    """The native objects alive by type, once releases on helper threads are done."""
    collect()
    alive = wrtc._alive()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        time.sleep(0.05)
        collect()
        current = wrtc._alive()
        if current == alive:
            break
        alive = current
    return alive


@pytest.mark.asyncio
async def test_a_session_releases_every_native_object() -> None:
    """Connections with media, channels, processors and generators, closed and dropped: nothing native is left."""
    baseline = alive_objects()

    async def session() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        stream = webrtc.get_user_media(audio=True, video=True)
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
