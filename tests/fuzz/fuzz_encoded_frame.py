#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes the encoded frames of a connection: script transforms rewriting them, and SFrame set and keyed mid-stream.

The workers of the senders and receivers rewrite frames with arbitrary data (empty, garbage, large), drop, reorder,
copy and write foreign frames, which libwebrtc packetizes, depacketizes and decodes. Transforms are replaced, removed
and swapped for SFrame encryptors and decryptors with fuzzed keys between slices of media. Only the documented
errors are expected, and the metadata of frames read stays in the ranges of RTP.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import math
import pathlib
import sys
from typing import Callable, Union

import atheris

with atheris.instrument_imports():
    from inputs import EDGES, FLOATS, Input

    import webrtc

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from tests.helpers import connect, copy_frame, mistyped

EXPECTED = (
    TypeError,
    ValueError,
    webrtc.DataCloneError,
    webrtc.InvalidStateError,
    webrtc.NotAllowedError,
    webrtc.NotFoundError,
    webrtc.InvalidRangeError,
    webrtc.InvalidModificationError,
)
SUITES = list(webrtc.SFrameCipherSuite)
SLICE = 0.25
LARGE = [1 << 10, 1 << 14, 1 << 16, 1 << 18, 1 << 20]
RIDS = [None, 'a', 'hi', '', 'not valid', 'x' * 256, '0']
MEMBERS: list[Callable[[Input], object]] = [
    lambda inp: inp.choice(EDGES),
    lambda inp: -inp.unsigned(1 << 16) - 1,
    lambda inp: inp.choice(FLOATS),
    lambda inp: inp.choice(['', 'video/VP8', 'audio/opus', 'x' * 1000, b'1', [], [1, -1, 2**64], {}, True]),
    lambda inp: [inp.unsigned(1 << 16) for _ in range(inp.small(4))],
    lambda inp: inp.maybe(lambda: inp.unsigned(1 << 16)),
]

Frame = Union[webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame]
Metadata = Union[webrtc.RTCEncodedVideoFrameMetadata, webrtc.RTCEncodedAudioFrameMetadata]
SFrameTransform = Union[webrtc.RTCRtpSFrameEncryptor, webrtc.RTCRtpSFrameDecryptor]
SFrameStream = Union[webrtc.SFrameEncryptorStream, webrtc.SFrameDecryptorStream]
Transform = Union[webrtc.RTCRtpScriptTransform, SFrameTransform, None]
Transformer = webrtc.RTCRtpScriptTransformer
Writer = webrtc.WritableStreamDefaultWriter[Frame]
Slot = Union[webrtc.RTCRtpSender, webrtc.RTCRtpReceiver]

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


def metadata(inp: Input, *, video: bool) -> Metadata:
    cls = webrtc.RTCEncodedVideoFrameMetadata if video else webrtc.RTCEncodedAudioFrameMetadata
    fields = [name for name in cls.__dataclass_fields__ if inp.flag()]
    return cls(**{name: mistyped(inp.choice(MEMBERS)(inp)) for name in fields})


def same(got: object, member: object) -> bool:
    return got == member or (isinstance(member, float) and math.isnan(member))


def check_metadata(frame: Frame) -> None:
    """What libwebrtc gives is in the ranges of RTP."""
    meta = frame.get_metadata()
    for member in (meta.synchronization_source, meta.rtp_timestamp):
        assert member is None or 0 <= member < 2**32
    assert meta.payload_type is None or 0 <= meta.payload_type < 128
    csrcs = meta.contributing_sources
    assert csrcs is None or all(0 <= csrc < 2**32 for csrc in csrcs)
    kind = 'video/' if isinstance(frame, webrtc.RTCEncodedVideoFrame) else 'audio/'
    assert meta.mime_type is None or meta.mime_type == '' or meta.mime_type.startswith(kind)
    if isinstance(meta, webrtc.RTCEncodedVideoFrameMetadata):
        for member in (meta.width, meta.height, meta.spatial_index, meta.temporal_index):
            assert member is None or 0 <= member < 2**32
    else:
        assert meta.audio_level is None or 0 <= meta.audio_level <= 1


class Session:
    """A connected pair sending audio and video through transforms that the fuzz data drives."""

    caller: webrtc.RTCPeerConnection
    callee: webrtc.RTCPeerConnection
    senders: list[webrtc.RTCRtpSender]
    receivers: list[webrtc.RTCRtpReceiver]

    def __init__(self) -> None:
        self.inp = Input(b'')
        self.failures: list[BaseException] = []
        self.history: list[Frame] = []
        self.keys: list[bytes] = [bytes(16)]

    async def start(self) -> None:
        self.caller, self.callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        receivers: list[webrtc.RTCRtpReceiver] = []
        self.callee.on('track', lambda event: receivers.append(event.receiver))
        stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
        self.senders = [self.caller.add_track(track) for track in stream.get_tracks()]
        await connect(self.caller, self.callee)
        self.receivers = receivers

    def stop(self) -> None:
        self.caller.close()
        self.callee.close()

    def fail(self, error: BaseException) -> None:
        if not isinstance(error, EXPECTED):
            self.failures.append(error)

    def key(self) -> bytes:
        if self.inp.flag():
            self.keys = [*self.keys[-7:], bytes(self.inp.contiguous(self.inp.small(48)))]
        return self.inp.choice(self.keys)

    def key_id(self) -> int:
        return self.inp.choice([0, 1, 2**64 - 1]) if self.inp.small(7) < 7 else mistyped(self.inp.integer(16))

    async def keyed(self, transform: SFrameTransform) -> None:
        for _ in range(self.inp.small(3)):
            if isinstance(transform, webrtc.RTCRtpSFrameEncryptor):
                await transform.set_encryption_key(self.key(), self.key_id())
            elif self.inp.flag():
                await transform.add_decryption_key(self.key(), self.key_id())
            else:
                await transform.remove_decryption_key(self.key_id())

    def on_error(self, event: webrtc.SFrameTransformErrorEvent) -> None:
        if not (
            isinstance(event.error_type, webrtc.SFrameTransformErrorEventType)
            and (event.key_id is not None) == (event.error_type == webrtc.SFrameTransformErrorEventType.key_id)
            and isinstance(event.frame, (webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame))
        ):
            self.failures.append(AssertionError(f'a wrong error event: {vars(event)}'))

    async def sframe_transform(self, *, sending: bool) -> SFrameTransform:
        suite = self.inp.choice(SUITES)
        transform: SFrameTransform
        if sending:
            transform = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(suite))
        else:
            transform = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(suite))
            transform.on('error', self.on_error)
        await self.keyed(transform)
        return transform

    def script_transform(self, *, sending: bool) -> webrtc.RTCRtpScriptTransform:
        worker: Callable[[webrtc.RTCTransformEvent], object] = Worker(self)
        if self.inp.flag():
            worker = functools.partial(self.piped, stream=self.sframe_stream(sending=sending))
        if self.inp.flag():
            return webrtc.RTCRtpScriptTransform(worker, self.inp.maybe(lambda: self.inp.small(4)))
        parameters = webrtc.WorkerAndParameters(worker, mistyped(self.inp.choice([None, 'sframe', 'other'])))
        return webrtc.RTCRtpScriptTransform(parameters)

    async def transform_of(self, *, sending: bool) -> Transform:
        mode = self.inp.small(3)
        if mode == 0:
            return None
        if mode == 1:
            return await self.sframe_transform(sending=sending)
        return self.script_transform(sending=sending)

    def sframe_stream(self, *, sending: bool) -> SFrameStream:
        options = webrtc.SFrameTransformOptions(self.inp.choice(SUITES))
        if sending:
            return webrtc.SFrameEncryptorStream(options)
        decryptor = webrtc.SFrameDecryptorStream(options)
        decryptor.on('error', self.on_error)
        return decryptor

    async def piped(self, event: webrtc.RTCTransformEvent, stream: SFrameStream) -> None:
        try:
            await self.pipe(event.transformer, stream)
        except Exception as e:  # ruff: ignore[blind-except] # checked by the session
            self.fail(e)

    async def pipe(self, transformer: webrtc.RTCRtpScriptTransformer, stream: SFrameStream) -> None:
        if isinstance(stream, webrtc.SFrameEncryptorStream):
            await stream.set_encryption_key(self.key(), 1)
        else:
            await stream.add_decryption_key(self.key(), 1)
        piped = transformer.readable.pipe_through(stream)
        await piped.pipe_to(transformer.writable)

    async def configure(self) -> None:
        slots: list[Slot] = [*self.senders, *self.receivers]
        for _ in range(self.inp.small(4)):
            with contextlib.suppress(*EXPECTED):
                await self.reconfigure(self.inp.choice(slots), slots)

    async def reconfigure(self, slot: Slot, slots: list[Slot]) -> None:
        mode = self.inp.small(3)
        current = slot.transform
        if mode == 0 and isinstance(current, (webrtc.RTCRtpSFrameEncryptor, webrtc.RTCRtpSFrameDecryptor)):
            await self.keyed(current)
        elif mode == 1:
            slot.transform = mistyped(self.inp.choice(slots).transform)
        else:
            sending = isinstance(slot, webrtc.RTCRtpSender) != (self.inp.small(7) == 7)
            slot.transform = mistyped(await self.transform_of(sending=sending))

    async def run(self, inp: Input) -> None:
        if any(pc.connection_state != webrtc.RTCPeerConnectionState.connected for pc in (self.caller, self.callee)):
            self.stop()
            await self.start()
        self.inp = inp
        await self.configure()
        await asyncio.sleep(SLICE)
        failures = self.failures
        self.failures = []
        if len(failures) > 0:
            raise failures[0]


class Worker:
    """Reads the frames of a transformer and does what the fuzz data says with each."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.held: list[Frame] = []
        self.actions: list[Callable[[Frame, webrtc.RTCRtpScriptTransformer], Frame | None]] = [
            self.drop,
            self.replace,
            self.enlarge,
            self.edit,
            self.mistype,
            self.copied,
            self.foreign,
            self.reorder,
            self.request_key_frame,
        ]

    async def __call__(self, event: webrtc.RTCTransformEvent) -> None:
        try:
            await self.work(event.transformer)
        except Exception as e:  # ruff: ignore[blind-except] # checked by the session
            self.session.fail(e)

    async def work(self, transformer: Transformer) -> None:
        reader = transformer.readable.get_reader()
        writer = transformer.writable.get_writer()
        while True:
            result = await reader.read()
            if result.done:
                return
            frame = result.value
            assert frame is not None
            check_metadata(frame)
            history = self.session.history
            history.append(frame)
            del history[:-16]
            await self.handle(frame, transformer, writer)

    async def handle(self, frame: Frame, transformer: Transformer, writer: Writer) -> None:
        inp = self.session.inp
        try:
            written = frame if inp.exhausted() else inp.choice(self.actions)(frame, transformer)
        except EXPECTED:
            written = frame
        if written is None:
            return
        # a frame of a previous transform of the sender or receiver is written as its own, as the specification says,
        # which drops the frames read after it until their counters catch up
        fresh = written is frame and frame._counter > transformer._last_received
        await writer.write(written)
        if fresh:
            assert len(frame.data) == 0
            copied = False
            with contextlib.suppress(webrtc.DataCloneError):
                _ = copy_frame(frame)
                copied = True
            assert not copied
        if inp.small(63) == 63:
            # errors the stream, which ends the worker
            await writer.write(mistyped(b'not a frame'))

    @staticmethod
    def drop(_frame: Frame, _transformer: Transformer) -> Frame | None:
        return None

    def replace(self, frame: Frame, _transformer: Transformer) -> Frame | None:
        frame.data = self.session.inp.contiguous(self.session.inp.small(2048))
        return frame

    def enlarge(self, frame: Frame, _transformer: Transformer) -> Frame | None:
        inp = self.session.inp
        frame.data = (b'\0' + bytes(inp.contiguous(inp.small(64)))) * (inp.choice(LARGE) // 64 + 1)
        return frame

    def edit(self, frame: Frame, _transformer: Transformer) -> Frame | None:
        inp = self.session.inp
        data = frame.data
        del data[inp.small(len(data)) :]
        data.extend(inp.contiguous(inp.small(32)))
        if len(data) > 0:
            data[inp.small(len(data) - 1)] ^= inp.small(255)
        return frame

    def mistype(self, frame: Frame, _transformer: Transformer) -> Frame | None:
        """Data of another type, or strided: TypeError."""
        frame.data = mistyped(self.session.inp.choice([None, 1, 'data', memoryview(b'abcd')[::2], memoryview(b'ab')]))
        return frame

    def copied(self, frame: Frame, _transformer: Transformer) -> Frame | None:
        """A copy with other metadata, which has it and the data of the frame; written, it's dropped."""
        inp = self.session.inp
        meta = metadata(inp, video=isinstance(frame, webrtc.RTCEncodedVideoFrame)) if inp.flag() else None
        if isinstance(frame, webrtc.RTCEncodedVideoFrame):
            copy: Frame = webrtc.RTCEncodedVideoFrame(frame, webrtc.RTCEncodedVideoFrameOptions(mistyped(meta)))
        else:
            copy = webrtc.RTCEncodedAudioFrame(frame, webrtc.RTCEncodedAudioFrameOptions(mistyped(meta)))
        assert copy.data == frame.data
        if meta is not None:
            got = copy.get_metadata()
            for name in type(meta).__dataclass_fields__:
                member = getattr(meta, name)
                assert member is None or same(getattr(got, name), member)
        self.session.history.append(copy)
        return copy if inp.flag() else frame

    def foreign(self, frame: Frame, _transformer: Transformer) -> Frame | None:
        """A frame read before, maybe written, or by another worker: dropped."""
        return self.session.inp.choice(self.session.history) if self.session.inp.flag() else frame

    def reorder(self, frame: Frame, _transformer: Transformer) -> Frame | None:
        """Held, and one held written later: older than the last written, it's dropped."""
        inp = self.session.inp
        self.held.append(frame)
        del self.held[:-8]
        if inp.flag():
            return None
        return self.held.pop(inp.small(len(self.held) - 1))

    def request_key_frame(self, frame: Frame, transformer: Transformer) -> Frame | None:
        inp = self.session.inp
        if inp.flag():
            request = asyncio.ensure_future(transformer.generate_key_frame(inp.choice(RIDS)))
        else:
            request = asyncio.ensure_future(transformer.send_key_frame_request())
        request.add_done_callback(self.requested)
        return frame

    def requested(self, request: asyncio.Future[None]) -> None:
        error = None if request.cancelled() else request.exception()
        if error is not None:
            self.session.fail(error)


session = Session()


def on_loop_exception(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
    """An exception of a callback or handler, which the fuzzer would miss: only the documented ones are expected."""
    error = context.get('exception')
    if isinstance(error, BaseException):
        session.fail(error)


loop.set_exception_handler(on_loop_exception)
loop.run_until_complete(session.start())


def test_one_input(data: bytes) -> None:
    loop.run_until_complete(session.run(Input(data)))


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
