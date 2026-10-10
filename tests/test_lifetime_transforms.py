#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Lifetime of encoded transforms, SFrame transforms and encoded frames: no leaks, no use after free."""

from __future__ import annotations

import asyncio
import contextlib
import weakref
from typing import TYPE_CHECKING, Union

import pytest

import webrtc
import wrtc
from tests.helpers import QUIET_PERIOD, collect, connect, copy_frame, settled_alive, wait_until
from tests.test_lifetime import alive_factories, alive_objects

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

TIMEOUT = 15
KEY = bytes(range(16))
OTHER_KEY = bytes(range(1, 17))
SUITE = webrtc.SFrameCipherSuite.AES_128_GCM_SHA256_128

Frame = Union[webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame]


class Worker:
    """Passes frames through, keeping the first ``hold`` ones; references ``owner`` (like its connection)."""

    def __init__(self, *, hold: int = 0, write: bool = True, owner: object = None) -> None:
        loop = asyncio.get_running_loop()
        self.hold = hold
        self.write = write
        self.owner = owner
        self.held: list[Frame] = []
        self.count = 0
        self.transformer: webrtc.RTCRtpScriptTransformer | None = None
        self.writer: webrtc.WritableStreamDefaultWriter[Frame] | None = None
        self.flowing: asyncio.Future[None] = loop.create_future()
        self.ended: asyncio.Future[None] = loop.create_future()

    async def __call__(self, event: webrtc.RTCTransformEvent) -> None:
        self.transformer = event.transformer
        reader = event.transformer.readable.get_reader()
        writer = self.writer = event.transformer.writable.get_writer()
        try:
            while True:
                result = await reader.read()
                if result.done:
                    break
                frame = result.value
                assert frame is not None
                self.count += 1
                if self.count >= 5 and not self.flowing.done():
                    self.flowing.set_result(None)
                if len(self.held) < self.hold:
                    self.held.append(frame)
                elif self.write:
                    # rejected once the transform is removed
                    writer.write(frame).add_done_callback(lambda f: f.cancelled() or f.exception())
        finally:
            self.ended.set_result(None)


@pytest.fixture
def isolated() -> Iterator[None]:
    collect()
    yield
    collect()


pytestmark = pytest.mark.usefixtures('isolated')


async def media() -> list[webrtc.MediaStreamTrack]:
    constraints = webrtc.MediaStreamConstraints(audio=True, video=True)
    return (await webrtc.media_devices.get_user_media(constraints)).get_tracks()


async def script_call(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    hold: int = 0,
    owner: object = None,
) -> list[Worker]:
    """Sends audio and video through script transforms on both ends, and waits for frames to flow."""
    workers: list[Worker] = []
    for track in await media():
        sending = Worker(hold=hold, owner=owner)
        caller.add_track(track).transform = webrtc.RTCRtpScriptTransform(sending)
        workers.append(sending)

    def on_track(event: webrtc.RTCTrackEvent) -> None:
        receiving = Worker(hold=hold, owner=owner)
        event.receiver.transform = webrtc.RTCRtpScriptTransform(receiving)
        workers.append(receiving)

    callee.on('track', on_track)
    await connect(caller, callee)
    await wait_until(lambda: len(workers) == 4, 'the transforms of the receivers', TIMEOUT)
    await asyncio.wait_for(asyncio.gather(*(w.flowing for w in workers)), TIMEOUT)
    return workers


async def sframe_call(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, *, decryption_key: bytes = KEY
) -> list[webrtc.RTCRtpSFrameDecryptor]:
    """Sends audio and video encrypted with SFrame, decrypted with a key (the wrong one makes errors)."""
    for track in await media():
        encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(SUITE))
        await encryptor.set_encryption_key(KEY, 1)
        caller.add_track(track).transform = encryptor
    decryptors: list[webrtc.RTCRtpSFrameDecryptor] = []

    async def on_track(event: webrtc.RTCTrackEvent) -> None:
        decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(SUITE))
        event.receiver.transform = decryptor
        decryptors.append(decryptor)
        await decryptor.add_decryption_key(decryption_key, 1)

    callee.on('track', on_track)
    await connect(caller, callee)
    await wait_until(lambda: len(decryptors) == 2, 'the decryptors', TIMEOUT)
    return decryptors


async def settled(baseline: dict[str, int]) -> dict[str, int]:
    """What's alive once back to the baseline, or after a while: cycles are collectable once helper threads let go."""
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        await asyncio.sleep(QUIET_PERIOD)
        collect()
        alive = wrtc._alive()
        if alive == baseline or asyncio.get_running_loop().time() > deadline:
            return alive


def released_with_the_loop(refs: Sequence[weakref.ref[object]], baseline: dict[str, int], factories: int) -> bool:
    """Whether everything died with the loop."""

    def released(alive: dict[str, int], alive_factories: int) -> bool:
        within = all(count <= baseline.get(name, 0) for name, count in alive.items())
        return within and alive_factories <= factories and all(ref() is None for ref in refs)

    return released(*settled_alive(released))


def test_transforms_of_connections_dropped_without_close() -> None:
    """Dropped connections live until the loop closes."""
    baseline, factories = alive_objects(), alive_factories()

    async def session() -> list[weakref.ref[object]]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        workers = await script_call(caller, callee)
        transforms = [part.transform for part in (*caller.get_senders(), *callee.get_receivers())]
        refs: list[weakref.ref[object]] = [weakref.ref(item) for item in (caller, callee, *transforms)]
        del caller, callee, transforms
        collect()
        await asyncio.sleep(QUIET_PERIOD)
        # both connections have handlers (connect()'s candidates, the callee's track)
        assert all(ref() is not None for ref in refs)
        assert all(not w.ended.done() for w in workers)
        return refs

    refs = asyncio.run(session())
    assert released_with_the_loop(refs, baseline, factories)


def handle_errors(decryptors: list[webrtc.RTCRtpSFrameDecryptor]) -> list[webrtc.SFrameTransformErrorEvent]:
    errors: list[webrtc.SFrameTransformErrorEvent] = []
    for decryptor in decryptors:
        decryptor.on('error', errors.append)
    return errors


async def stop_errors(refs: list[weakref.ref[object]]) -> None:
    """Stops per-frame errors, each a collection under --gc-on-emit."""
    for ref in refs:
        decryptor = ref()
        if isinstance(decryptor, webrtc.RTCRtpSFrameDecryptor):
            await decryptor.add_decryption_key(KEY, 1)


def test_sframe_transforms_of_connections_dropped_without_close() -> None:
    """Dropped connections keep decryptors until the loop closes."""
    baseline, factories = alive_objects(), alive_factories()

    async def session() -> list[weakref.ref[object]]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        decryptors = await sframe_call(caller, callee, decryption_key=OTHER_KEY)
        errors = handle_errors(decryptors)
        refs: list[weakref.ref[object]] = [weakref.ref(item) for item in (caller, callee, *decryptors)]
        del caller, callee, decryptors
        collect()
        errors.clear()
        await wait_until(lambda: len(errors) > 5, 'errors after the drop', TIMEOUT)
        assert all(ref() is not None for ref in refs)
        await stop_errors(refs)
        return refs

    refs = asyncio.run(session())
    assert released_with_the_loop(refs, baseline, factories)


@pytest.mark.parametrize('dropped', [False, True])
def test_worker_referencing_its_connection_with_a_pending_read(*, dropped: bool) -> None:
    """Waiting worker ends on close() or loop close."""
    baseline, factories = alive_objects(), alive_factories()

    async def session() -> list[weakref.ref[object]]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        workers = await script_call(caller, callee, owner=None if dropped else (caller, callee))
        refs: list[weakref.ref[object]] = [weakref.ref(worker) for worker in workers]
        if dropped:
            del caller, callee
            collect()
            await asyncio.sleep(QUIET_PERIOD)
            assert all(not w.ended.done() for w in workers)
            return refs
        caller.close()
        callee.close()
        await asyncio.wait_for(asyncio.gather(*(w.ended for w in workers)), TIMEOUT)
        return refs

    async def scenario() -> list[weakref.ref[object]]:
        refs = await session()
        if not dropped:
            assert await settled(baseline) == baseline
            assert [ref for ref in refs if ref() is not None] == []
        return refs

    refs = asyncio.run(scenario())
    assert released_with_the_loop(refs, baseline, factories)


def use_frame(frame: Frame) -> None:
    assert len(frame.data) > 0
    assert frame.get_metadata().synchronization_source is not None
    assert copy_frame(frame).data == frame.data


async def use_frames_after_close(worker: Worker) -> None:
    assert worker.transformer is not None
    native = worker.transformer._native_obj
    for frame in worker.held:
        use_frame(frame)
        assert frame._native is not None
        assert not native.write(frame._native, None)
        assert not native.write(frame._native, b'\x00')
    assert worker.writer is not None
    with pytest.raises(webrtc.InvalidStateError):
        await worker.writer.write(worker.held[-1])


@pytest.mark.asyncio
async def test_frames_used_after_their_connection_is_gone() -> None:
    """Frames kept past close and collection still read, copy, and are dropped when written."""
    baseline = alive_objects()

    async def session() -> list[Worker]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        workers = await script_call(caller, callee, hold=3)
        caller.close()
        callee.close()
        return workers

    workers = await session()
    await asyncio.wait_for(asyncio.gather(*(w.ended for w in workers)), TIMEOUT)
    collect()
    await asyncio.gather(*(use_frames_after_close(worker) for worker in workers))
    del workers
    assert await settled(baseline) == baseline


@pytest.mark.asyncio
async def test_native_frames_are_written_to_their_sender_or_receiver_only() -> None:
    """A frame of another sender or receiver (another kind, direction) written natively is dropped, not sent."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    try:
        workers = await script_call(caller, callee, hold=2)
        for target in workers:
            assert target.transformer is not None
            native = target.transformer._native_obj
            for frame in (source.held[-1] for source in workers if source is not target):
                assert frame._native is not None
                assert not native.write(frame._native, None)
                assert frame._native.getData() == bytes(frame.data)
        own = workers[0].held[0]
        assert workers[0].transformer is not None
        assert own._native is not None
        assert workers[0].transformer._native_obj.write(own._native, None)
        assert own._native.getData() == b''
        await asyncio.sleep(QUIET_PERIOD)
        assert all(not w.ended.done() for w in workers)
    finally:
        caller.close()
        callee.close()


async def replace_transform(
    part: webrtc.RTCRtpSender | webrtc.RTCRtpReceiver, index: int, workers: list[Worker]
) -> None:
    """Sets a script transform, none or SFrame, by the index."""
    choice = index % 4
    if choice == 0:
        worker = Worker(hold=1, write=index % 3 != 0)
        workers.append(worker)
        part.transform = webrtc.RTCRtpScriptTransform(worker)
    elif choice == 1:
        part.transform = None
    elif choice == 2 and isinstance(part, webrtc.RTCRtpSender):
        encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(SUITE))
        await encryptor.set_encryption_key(KEY, index)
        part.transform = encryptor
    elif choice == 2 and isinstance(part, webrtc.RTCRtpReceiver):
        decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(SUITE))
        await decryptor.add_decryption_key(KEY, index - 2)
        decryptor.on('error', lambda _event: None)
        part.transform = decryptor


@pytest.mark.asyncio
async def test_transforms_replaced_while_media_flows() -> None:
    """Transforms set, replaced and removed many times while frames flow are all released."""
    baseline = alive_objects()

    async def session() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        workers = await script_call(caller, callee, hold=1)
        senders, receivers = caller.get_senders(), callee.get_receivers()
        for index in range(30):
            for part in (*senders, *receivers):
                await replace_transform(part, index, workers)
            await asyncio.sleep(0.02)
        final = [Worker() for _ in (*senders, *receivers)]
        for part, worker in zip((*senders, *receivers), final):
            part.transform = webrtc.RTCRtpScriptTransform(worker)
        await asyncio.wait_for(asyncio.gather(*(w.flowing for w in final)), TIMEOUT)
        await asyncio.wait_for(asyncio.gather(*(w.ended for w in workers)), TIMEOUT)
        caller.close()
        callee.close()
        await asyncio.wait_for(asyncio.gather(*(w.ended for w in final)), TIMEOUT)

    await session()
    assert await settled(baseline) == baseline


@pytest.mark.asyncio
async def test_decryptor_handler_referencing_the_decryptor() -> None:
    """An error handler referencing its decryptor (a cycle through C++) doesn't keep it alive."""
    baseline, factories = alive_objects(), alive_factories()

    async def session() -> list[weakref.ref[object]]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        decryptors = await sframe_call(caller, callee, decryption_key=OTHER_KEY)
        seen: list[object] = []
        for decryptor in decryptors:
            decryptor.on('error', lambda event, decryptor=decryptor: seen.append((decryptor, event.frame)))
        await wait_until(lambda: len(seen) > 5, 'errors', TIMEOUT)
        caller.close()
        callee.close()
        return [weakref.ref(decryptor) for decryptor in decryptors]

    refs = await session()
    assert await settled(baseline) == baseline
    assert [ref for ref in refs if ref() is not None] == []
    assert alive_factories() == factories


@pytest.mark.asyncio
async def test_error_frames_used_after_close() -> None:
    """The frames of error events, kept past close and collection, are still frames."""
    baseline = alive_objects()

    async def session() -> list[webrtc.SFrameTransformErrorEvent]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        decryptors = await sframe_call(caller, callee, decryption_key=OTHER_KEY)
        errors: list[webrtc.SFrameTransformErrorEvent] = []
        for decryptor in decryptors:
            decryptor.on('error', errors.append)
        await wait_until(lambda: len(errors) > 20, 'errors', TIMEOUT)
        caller.close()
        callee.close()
        return errors

    errors = await session()
    collect()
    frames = [event.frame for event in errors]
    del errors
    encoded = [
        frame for frame in frames if isinstance(frame, (webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame))
    ]
    assert len(encoded) == len(frames)
    list(map(use_frame, encoded))
    del frames, encoded
    assert await settled(baseline) == baseline


class Piped:
    """A worker piping its frames through SFrame streams, which the test drops midway."""

    def __init__(self) -> None:
        self.encryptor = webrtc.SFrameEncryptorStream(webrtc.SFrameTransformOptions(SUITE))
        self.decryptor = webrtc.SFrameDecryptorStream(webrtc.SFrameTransformOptions(SUITE))
        self.decryptor.on('error', lambda _event: None)
        self.started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.ended: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def __call__(self, event: webrtc.RTCTransformEvent) -> None:
        await self.encryptor.set_encryption_key(KEY, 3)
        await self.decryptor.add_decryption_key(KEY, 3)
        transformer = event.transformer
        self.started.set_result(None)
        with contextlib.suppress(Exception):
            through = transformer.readable.pipe_through(self.encryptor)
            through = through.pipe_through(self.decryptor)
            await through.pipe_to(transformer.writable)
        self.ended.set_result(None)


@pytest.mark.asyncio
async def test_sframe_streams_dropped_mid_pipe() -> None:
    baseline = alive_objects()

    async def session() -> list[weakref.ref[object]]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        workers: list[Piped] = []
        for track in await media():
            worker = Piped()
            caller.add_track(track).transform = webrtc.RTCRtpScriptTransform(worker)
            workers.append(worker)
        await connect(caller, callee)
        await asyncio.wait_for(asyncio.gather(*(w.started for w in workers)), TIMEOUT)
        await asyncio.sleep(0.5)
        refs: list[weakref.ref[object]] = [weakref.ref(w.encryptor) for w in workers]
        for worker in workers:
            del worker.encryptor, worker.decryptor
        collect()
        await asyncio.sleep(0.2)
        caller.close()
        callee.close()
        await asyncio.wait_for(asyncio.gather(*(w.ended for w in workers)), TIMEOUT)
        return refs

    refs = await session()
    assert await settled(baseline) == baseline
    assert [ref for ref in refs if ref() is not None] == []


@pytest.mark.asyncio
async def test_senders_and_receivers_collected_while_transforms_are_set() -> None:
    """The transform attribute outlives the wrappers of senders and receivers dropped by Python."""
    baseline = alive_objects()

    async def session() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        workers = await script_call(caller, callee)
        collect()
        counts = [w.count for w in workers]
        await wait_until(lambda: all(w.count > c + 5 for w, c in zip(workers, counts)), 'more frames', TIMEOUT)
        for pc, parts in ((caller, caller.get_senders), (callee, callee.get_receivers)):
            for part in parts():
                assert isinstance(part.transform, webrtc.RTCRtpScriptTransform)
            assert pc.connection_state == webrtc.RTCPeerConnectionState.connected
        caller.close()
        callee.close()
        await asyncio.wait_for(asyncio.gather(*(w.ended for w in workers)), TIMEOUT)

    await session()
    assert await settled(baseline) == baseline


async def referencing_sframe(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Decryptors whose error handlers reference the connection and its receivers."""
    decryptors = await sframe_call(caller, callee, decryption_key=OTHER_KEY)
    seen: list[object] = []
    receivers = callee.get_receivers()
    for decryptor in decryptors:
        decryptor.on('error', lambda event: seen.append((callee, receivers, event.frame)))
    await wait_until(lambda: len(seen) > 5, 'errors', TIMEOUT)


async def referencing_script(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Script transforms whose options and handlers reference the connections, senders and receivers."""
    workers = await script_call(caller, callee)
    for part in (*caller.get_senders(), *callee.get_receivers()):
        transform = part.transform
        assert isinstance(transform, webrtc.RTCRtpScriptTransform)
        transformer = transform._transformer
        assert transformer is not None
        transformer._options = (caller, callee, part)
        transformer.on('keyframerequest', lambda _event: (caller, callee))
    await wait_until(lambda: all(w.count > 10 for w in workers), 'frames', TIMEOUT)


@pytest.mark.parametrize('kind', ['sframe', 'script'])
@pytest.mark.parametrize('closed', [True, False])
def test_handlers_referencing_their_connection(kind: str, *, closed: bool) -> None:
    """Transform references keep the connection until close."""
    baseline, factories = alive_objects(), alive_factories()

    async def session() -> list[weakref.ref[object]]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        await (referencing_sframe if kind == 'sframe' else referencing_script)(caller, callee)
        if closed:
            caller.close()
            callee.close()
        return [weakref.ref(caller), weakref.ref(callee)]

    async def scenario() -> list[weakref.ref[object]]:
        refs = await session()
        if closed:
            assert await settled(baseline) == baseline
            assert [ref for ref in refs if ref() is not None] == []
        else:
            collect()
            await asyncio.sleep(QUIET_PERIOD)
            # handlers and associated transforms keep them while open
            assert all(ref() is not None for ref in refs)
        return refs

    refs = asyncio.run(scenario())
    try:
        assert released_with_the_loop(refs, baseline, factories)
    finally:
        for ref in refs:
            pc = ref()
            if isinstance(pc, webrtc.RTCPeerConnection):
                pc.close()


class Handler:
    """A handler referencing a connection and its receivers, which the test sees collected."""

    def __init__(self, pc: webrtc.RTCPeerConnection, receivers: list[webrtc.RTCRtpReceiver]) -> None:
        self.pc = pc
        self.receivers = receivers

    def __call__(self, _event: webrtc.Event) -> None:
        _ = self.pc, self.receivers


@pytest.mark.asyncio
async def test_handlers_registered_once_detached_are_not_kept() -> None:
    """A detached transform never dispatches again: handlers registered on it then are dropped, not kept in a cycle."""
    baseline, factories = alive_objects(), alive_factories()

    async def session() -> list[weakref.ref[object]]:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        decryptors = await sframe_call(caller, callee, decryption_key=OTHER_KEY)
        transform = webrtc.RTCRtpScriptTransform(Worker())
        receivers = callee.get_receivers()
        receivers[0].transform = transform
        caller.close()
        callee.close()
        await asyncio.sleep(QUIET_PERIOD)
        handlers = [Handler(callee, receivers) for _ in range(4)]
        decryptors[1].on('error', handlers[0])
        decryptors[1].once('error', handlers[1])
        transformer = transform._transformer
        assert transformer is not None
        transformer.on('keyframerequest', handlers[2])
        transformer.once('keyframerequest', handlers[3])
        decryptors[1].off('error', handlers[0])
        assert receivers[1].transform is not None
        return [weakref.ref(item) for item in (caller, callee, *handlers)]

    refs = await session()
    try:
        assert await settled(baseline) == baseline
        assert [ref for ref in refs if ref() is not None] == []
        assert alive_factories() == factories
    finally:
        for ref in refs:
            pc = ref()
            if isinstance(pc, webrtc.RTCPeerConnection):
                pc.close()
