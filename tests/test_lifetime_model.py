#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The activity table: what keeps an unreferenced object alive, and until when."""

from __future__ import annotations

import asyncio
import functools
import weakref
from typing import TYPE_CHECKING, Callable, Literal, NamedTuple, Protocol

import pytest

import webrtc
import wrtc
from tests.helpers import (
    SETTLE_INTERVAL,
    SETTLE_TIMEOUT,
    called,
    collect,
    connect,
    exchange_offer_answer,
    release_stranded_candidates,
    settled_alive,
    wait_for_event,
    wait_until,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence

TIMEOUT = 10
SUITE = webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128
KEY = bytes(range(16))
OTHER_KEY = bytes(range(1, 17))

Alive = dict[str, int]
Pair = tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]


class Wrapped(Protocol):
    """A wrapper or a transformer."""

    @property
    def _native_obj(self) -> object: ...


class Tracked(NamedTuple):
    """A weak reference and its ``wrtc._alive()`` type."""

    ref: weakref.ref[object]
    native: str


class Scene(NamedTuple):
    """What a row builds."""

    dropped: list[Tracked]
    kept: list[object]
    end: Callable[[], object]
    #: activity ends on its own, so kept is checked before the loop runs
    ends_by_itself: bool = False


Builder = Callable[[], 'Scene | Awaitable[Scene]']


def track(obj: Wrapped) -> Tracked:
    return Tracked(weakref.ref(obj), type(obj._native_obj).__name__)


def baseline() -> Alive:
    """Settled native counts before the test's objects."""
    return settled_alive()[0]


def above(alive: Alive, base: Alive, dropped: Sequence[Tracked]) -> bool:
    return all(alive.get(t.native, 0) > base.get(t.native, 0) for t in dropped)


def dead(dropped: Sequence[Tracked]) -> bool:
    return all(t.ref() is None for t in dropped)


def kept_now(dropped: Sequence[Tracked], base: Alive) -> bool:
    """Whether the objects survive a collection."""
    collect()
    return not any(t.ref() is None for t in dropped) and above(wrtc._alive(), base, dropped)


async def kept(dropped: Sequence[Tracked], base: Alive) -> bool:
    """Whether the objects survive while the loop runs."""
    loop = asyncio.get_running_loop()
    collect()
    alive = wrtc._alive()
    deadline = loop.time() + SETTLE_TIMEOUT
    while loop.time() < deadline:
        await asyncio.sleep(SETTLE_INTERVAL)
        collect()
        current = wrtc._alive()
        if current == alive:
            break
        alive = current
    return kept_now(dropped, base)


async def collected(dropped: Sequence[Tracked]) -> bool:
    """Whether the wrappers die within the settle wait."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SETTLE_TIMEOUT
    while True:
        collect()
        if dead(dropped):
            return True
        if loop.time() > deadline:
            return False
        await asyncio.sleep(SETTLE_INTERVAL)


def released_after_loop_close(dropped: Sequence[Tracked], base: Alive) -> bool:
    """Whether everything died with the loop."""
    release_stranded_candidates()

    def released(alive: Alive, _factories: int) -> bool:
        return dead(dropped) and all(count <= base.get(name, 0) for name, count in alive.items())

    alive, factories = settled_alive(released)
    return released(alive, factories)


def describe(dropped: Sequence[Tracked], base: Alive) -> str:
    """Survivors and counts off the baseline."""
    alive = [t.native for t in dropped if t.ref() is not None]
    counts = {name: (count, base.get(name, 0)) for name, count in wrtc._alive().items() if count != base.get(name, 0)}
    return f'wrappers alive: {alive}, native counts (now, baseline): {counts}'


def close(tracked: Tracked) -> None:
    """Closes or stops the object."""
    obj = tracked.ref()
    assert obj is not None
    if isinstance(obj, webrtc.MediaStreamTrack):
        obj.stop()
    else:
        assert isinstance(obj, (webrtc.RTCPeerConnection, webrtc.RTCDataChannel))
        obj.close()


def closing(*connections: webrtc.RTCPeerConnection) -> Callable[[], None]:
    """Closes the connection."""

    def end() -> None:
        for pc in connections:
            pc.close()

    return end


def finish(scene: Scene) -> None:
    """Closes what a row kept."""
    for obj in scene.kept:
        if isinstance(obj, webrtc.RTCPeerConnection):
            obj.close()
        elif isinstance(obj, webrtc.MediaStream):
            for item in obj.get_tracks():
                item.stop()


def pair() -> Pair:
    return webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()


async def audio_stream() -> webrtc.MediaStream:
    return await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))


async def negotiated_receiver(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> webrtc.RTCRtpReceiver:
    """A negotiated, unconnected audio receiver."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer_answer(caller, callee)
    return callee.get_receivers()[0]


def connection_with_a_handler() -> Scene:
    """Connection with a handler: kept until close()."""
    pc = webrtc.RTCPeerConnection()
    pc.on('connectionstatechange', lambda _event: pc)
    tracked = track(pc)
    return Scene([tracked], [], functools.partial(close, tracked))


def connection_with_a_pending_operation() -> Scene:
    """Pending operation: kept until it settles."""
    pc = webrtc.RTCPeerConnection()
    settled = asyncio.get_running_loop().create_future()
    asyncio.ensure_future(pc.get_stats()).add_done_callback(lambda _task: settled.set_result(None))
    return Scene([track(pc)], [], functools.partial(asyncio.wait_for, settled, TIMEOUT), ends_by_itself=True)


async def connection_with_an_active_child() -> Scene:
    """Connection kept by its handled channel."""
    caller, callee = pair()
    channel = caller.create_data_channel('child')
    channel.on('message', lambda _event: channel)
    opened = wait_for_event(channel, 'open', TIMEOUT)
    await connect(caller, callee)
    await opened
    # drop connect()'s handlers so only the channel keeps it
    caller.off()
    callee.off()
    tracked = track(caller)
    return Scene([tracked, track(channel)], [callee], functools.partial(close, tracked))


def channel_connecting_with_an_open_handler() -> Scene:
    """Connecting channel with an open handler."""
    caller, callee = pair()
    channel = caller.create_data_channel('connecting')
    channel.on('open', lambda _event: channel)
    return Scene([track(channel)], [caller, callee], closing(caller, callee))


async def channel_open_with_a_message_handler() -> Scene:
    """Open channel with a message handler."""
    caller, callee = pair()
    channel = caller.create_data_channel('open')
    channel.on('message', lambda _event: channel)
    opened = wait_for_event(channel, 'open', TIMEOUT)
    await connect(caller, callee)
    await opened
    return Scene([track(channel)], [caller, callee], closing(caller, callee))


async def channel_closed_after_its_close_handler_ran() -> Scene:
    """Remote channel with a close handler."""
    caller, callee = pair()
    channel = caller.create_data_channel('closing')
    closed = asyncio.get_running_loop().create_future()
    remotes: list[webrtc.RTCDataChannel] = []

    @callee.on('datachannel')
    def on_channel(event: webrtc.RTCDataChannelEvent) -> None:
        remote = event.channel
        remote.on('close', lambda _event: (remote, closed.set_result(None)))
        remotes.append(remote)

    await connect(caller, callee)
    await wait_until(lambda: len(remotes) == 1, 'the remote channel', TIMEOUT)
    tracked = track(remotes.pop())

    async def end() -> None:
        # only the remote end gets closing, then close
        channel.close()
        await asyncio.wait_for(closed, TIMEOUT)

    return Scene([tracked], [caller, callee, channel], end)


async def channel_with_data_buffered_and_no_handlers() -> Scene:
    """Channel kept until its buffer drains."""
    caller, callee = pair()
    channel = caller.create_data_channel('buffered')
    opened = wait_for_event(channel, 'open', TIMEOUT)
    await connect(caller, callee)
    await opened
    channel.send(bytes(200_000))
    assert channel.buffered_amount > 0
    tracked = track(channel)

    async def end() -> None:
        def drained() -> bool:
            item = tracked.ref()
            return item is None or not isinstance(item, webrtc.RTCDataChannel) or item.buffered_amount == 0

        await wait_until(drained, 'the buffer to drain', TIMEOUT)

    return Scene([tracked], [caller, callee], end, ends_by_itself=True)


async def remote_track_with_an_ended_handler() -> Scene:
    """Remote track with an ended handler."""
    caller, callee = pair()
    received = wait_for_event(callee, 'track', TIMEOUT)
    await negotiated_receiver(caller, callee)
    event = await received
    assert isinstance(event, webrtc.RTCTrackEvent)
    remote = event.track
    ended = asyncio.get_running_loop().create_future()
    remote.on('ended', lambda _event: (remote, ended.set_result(None)))

    async def end() -> None:
        # close fires ended; the track goes after its handler
        callee.close()
        caller.close()
        await asyncio.wait_for(ended, TIMEOUT)

    return Scene([track(remote)], [caller, callee], end)


def generator_track_with_an_ended_handler(kind: Literal['audio', 'video']) -> Builder:
    def build() -> Scene:
        """Generator track: kept until stop()."""
        generator = webrtc.MediaStreamTrackGenerator(kind) if kind == 'audio' else webrtc.VideoTrackGenerator()
        item = generator if isinstance(generator, webrtc.MediaStreamTrack) else generator.track
        item.on('ended', lambda _event: item)
        tracked = track(item)
        return Scene([tracked], [], functools.partial(close, tracked))

    build.__name__ = f'{kind}_generator_track_with_an_ended_handler'
    return build


async def local_track_with_an_ended_handler() -> Scene:
    """get_user_media track: kept until stop()."""
    item = (await audio_stream()).get_tracks()[0]
    item.on('ended', lambda _event: item)
    tracked = track(item)
    return Scene([tracked], [], functools.partial(close, tracked))


async def transports_with_statechange_handlers() -> Scene:
    """Transports with statechange handlers."""
    caller, callee = pair()
    channel = caller.create_data_channel('transports')
    await connect(caller, callee)
    sctp = caller.sctp
    assert sctp is not None
    dtls = sctp.transport
    ice = dtls.ice_transport
    sctp.on('statechange', lambda _event: sctp)
    dtls.on('statechange', lambda _event: dtls)
    ice.on('statechange', lambda _event: ice)
    return Scene([track(ice), track(dtls), track(sctp)], [caller, callee, channel], closing(caller, callee))


async def dtmf_sender_with_tones_buffered() -> Scene:
    """DTMF sender kept until its tones play."""
    caller, callee = pair()
    stream = await audio_stream()
    sender = caller.add_track(stream.get_tracks()[0], stream)
    await connect(caller, callee)
    dtmf = sender.dtmf
    assert dtmf is not None
    emptied = asyncio.get_running_loop().create_future()

    def on_tone(event: webrtc.RTCDTMFToneChangeEvent) -> None:
        if event.tone == '' and not emptied.done():
            emptied.set_result(dtmf.tone_buffer)

    dtmf.on('tonechange', on_tone)
    dtmf.insert_dtmf('12', duration=40, inter_tone_gap=30)
    assert dtmf.tone_buffer == '12'
    end = functools.partial(asyncio.wait_for, emptied, TIMEOUT)
    return Scene([track(dtmf)], [caller, callee, stream], end, ends_by_itself=True)


async def remote_stream_with_an_addtrack_handler() -> Scene:
    """Remote stream with an addtrack handler."""
    caller, callee = pair()
    stream = await audio_stream()
    caller.add_track(stream.get_tracks()[0], stream)
    received = wait_for_event(callee, 'track', TIMEOUT)
    await exchange_offer_answer(caller, callee)
    event = await received
    assert isinstance(event, webrtc.RTCTrackEvent)
    remote = event.streams[0]
    remote.on('addtrack', lambda _event: remote)
    return Scene([track(remote)], [caller, callee, stream], closing(caller, callee))


async def script_transformer_with_a_keyframerequest_handler() -> Scene:
    """Receiver transformer with a handler."""
    caller, callee = pair()
    receiver = await negotiated_receiver(caller, callee)
    transformers: list[webrtc.RTCRtpScriptTransformer] = []

    def worker(event: webrtc.RTCTransformEvent) -> None:
        transformer = event.transformer
        transformer.on('keyframerequest', lambda _event: transformer)
        transformers.append(transformer)

    receiver.transform = webrtc.RTCRtpScriptTransform(worker)
    await wait_until(lambda: len(transformers) == 1, 'the transformer', TIMEOUT)
    return Scene([track(transformers.pop())], [caller, callee], closing(caller, callee))


async def sframe_decryptor_with_an_error_handler() -> Scene:
    """Receiver decryptor with an error handler."""
    caller, callee = pair()
    receiver = await negotiated_receiver(caller, callee)
    decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(SUITE))
    await decryptor.add_decryption_key(KEY, 1)
    decryptor.on('error', lambda _event: decryptor)
    receiver.transform = decryptor
    return Scene([track(decryptor)], [caller, callee], closing(caller, callee))


async def sframe_decryptor_with_errors_coming() -> Scene:
    """Wrong-key decryptor on flowing media."""
    caller, callee = pair()
    stream = await audio_stream()
    encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(SUITE))
    await encryptor.set_encryption_key(KEY, 1)
    caller.add_track(stream.get_tracks()[0]).transform = encryptor
    await connect(caller, callee)
    decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(SUITE))
    await decryptor.add_decryption_key(OTHER_KEY, 1)
    errors: list[webrtc.SFrameTransformErrorEvent] = []
    decryptor.on('error', lambda event: (decryptor, errors.append(event)))
    callee.get_receivers()[0].transform = decryptor
    await wait_until(lambda: len(errors) > 5, 'errors', TIMEOUT)
    errors.clear()
    return Scene([track(decryptor)], [caller, callee, stream], closing(caller, callee))


def idle_connection() -> Scene:
    """Idle connection: collected while open."""
    return Scene([track(webrtc.RTCPeerConnection())], [], lambda: None)


async def idle_open_channel() -> Scene:
    """Idle channel: collected while open."""
    caller, callee = pair()
    channel = caller.create_data_channel('idle')
    opened = wait_for_event(channel, 'open', TIMEOUT)
    await connect(caller, callee)
    await opened
    return Scene([track(channel)], [caller, callee], lambda: None)


def processor_and_generator_with_pending_operations() -> Scene:
    """Pending stream reads/writes never root."""
    generator = webrtc.VideoTrackGenerator()
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(generator.track))
    # tasks unreferenced and nothing written: the read never settles
    asyncio.ensure_future(processor.readable.get_reader().read()).add_done_callback(lambda _task: None)
    frame = webrtc.VideoFrame(
        bytes(4 * 4 * 4), webrtc.VideoFrameBufferInit(format='RGBA', coded_width=4, coded_height=4, timestamp=0)
    )
    asyncio.ensure_future(generator.writable.get_writer().write(frame)).add_done_callback(lambda _task: None)
    return Scene([track(processor), track(generator.track)], [], lambda: None)


ROWS: list[Builder] = [
    connection_with_a_handler,
    connection_with_a_pending_operation,
    connection_with_an_active_child,
    channel_connecting_with_an_open_handler,
    channel_open_with_a_message_handler,
    channel_closed_after_its_close_handler_ran,
    channel_with_data_buffered_and_no_handlers,
    remote_track_with_an_ended_handler,
    generator_track_with_an_ended_handler('audio'),
    generator_track_with_an_ended_handler('video'),
    local_track_with_an_ended_handler,
    transports_with_statechange_handlers,
    dtmf_sender_with_tones_buffered,
    remote_stream_with_an_addtrack_handler,
    script_transformer_with_a_keyframerequest_handler,
    sframe_decryptor_with_an_error_handler,
    sframe_decryptor_with_errors_coming,
]

NEVER_KEPT: list[Builder] = [idle_connection, idle_open_channel, processor_and_generator_with_pending_operations]


def rows(builders: list[Builder]) -> list[object]:
    """Rows as parameters."""
    return [pytest.param(build, id=build.__name__) for build in builders]


@pytest.mark.parametrize('build', rows(ROWS))
def test_kept_while_active_then_collected(build: Builder) -> None:
    """Kept while active, collected after."""
    base = baseline()

    async def scenario() -> list[Tracked]:
        scene = await called(build)
        if scene.ends_by_itself:
            assert kept_now(scene.dropped, base), describe(scene.dropped, base)
        else:
            assert await kept(scene.dropped, base), describe(scene.dropped, base)
        await called(scene.end)
        assert await collected(scene.dropped), describe(scene.dropped, base)
        finish(scene)
        return scene.dropped

    dropped = asyncio.run(scenario())
    assert released_after_loop_close(dropped, base), describe(dropped, base)


@pytest.mark.parametrize('build', rows(ROWS))
def test_collected_after_its_loop_closed(build: Builder) -> None:
    """Collected when the loop closes."""
    base = baseline()

    async def scenario() -> list[Tracked]:
        return (await called(build)).dropped

    dropped = asyncio.run(scenario())
    assert released_after_loop_close(dropped, base), describe(dropped, base)


@pytest.mark.parametrize('build', rows(NEVER_KEPT))
def test_collected_while_active(build: Builder) -> None:
    """Inactive objects are collected right away."""
    base = baseline()

    async def scenario() -> list[Tracked]:
        scene = await called(build)
        assert await collected(scene.dropped), describe(scene.dropped, base)
        finish(scene)
        return scene.dropped

    dropped = asyncio.run(scenario())
    assert released_after_loop_close(dropped, base), describe(dropped, base)
