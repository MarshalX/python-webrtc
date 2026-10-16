#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""WebRTC Encoded Transform: RTCRtpScriptTransform on senders and receivers of a real connection."""

from __future__ import annotations

import asyncio
import gc
import threading
import time
from typing import TYPE_CHECKING, Callable, Union

import pytest

import webrtc
import wrtc
from tests.helpers import (
    connect,
    delivered,
    exchange_ice_candidates,
    exchange_offer,
    mistyped,
    settled_alive,
    undelivered,
    wait_progressing,
    wait_until,
    wait_until_unmuted,
)
from tests.timing import seconds

if TYPE_CHECKING:
    from collections.abc import Iterator

TIMEOUT = seconds(15)
MARK = 0xAB
KEPT = 3

Frame = Union[webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame]


class Recorder:
    """A worker that records the frames it reads, writing back all but the first ``keep``, after ``change``."""

    def __init__(self, change: Callable[[Frame], None] | None = None, *, write: bool = True, keep: int = 0) -> None:
        self.change = change
        self.write = write
        self.keep = keep
        self.frames: list[Frame] = []
        self.transformer: webrtc.RTCRtpScriptTransformer | None = None
        self.started = asyncio.get_running_loop().create_future()
        self.done = asyncio.get_running_loop().create_future()

    async def __call__(self, event: webrtc.RTCTransformEvent) -> None:
        self.transformer = event.transformer
        self.started.set_result(event)
        reader = event.transformer.readable.get_reader()
        writer = event.transformer.writable.get_writer() if self.write else None
        while True:
            result = await reader.read()
            if result.done:
                break
            frame = result.value
            assert frame is not None
            self.frames.append(frame)
            if self.change is not None:
                self.change(frame)
            if writer is not None and len(self.frames) > self.keep:
                _ = writer.write(frame)
        self.done.set_result(None)

    async def wait_frames(self, count: int) -> None:
        try:
            await wait_progressing(
                lambda: min(len(self.frames), count),
                lambda: len(self.frames) >= count,
                f'{count} frames',
                stall=TIMEOUT,
            )
        except TimeoutError as e:
            msg = f'{e}: {self.describe()}'
            raise TimeoutError(msg) from None

    def describe(self) -> str:
        """What the worker saw, for failure messages."""
        if self.transformer is None:
            return 'not started'
        transformer = self.transformer
        return f'{len(self.frames)} frames, ended {transformer._ended}, native state {transformer._native_obj.state}'


def key_frames(recorder: Recorder) -> int:
    return sum(1 for frame in recorder.frames if getattr(frame, 'type', None) == webrtc.EncodedVideoChunkType.key)


def mark(frame: Frame) -> None:
    frame.data.append(MARK)


def unmark(frame: Frame) -> None:
    if len(frame.data) > 0 and frame.data[-1] == MARK:
        del frame.data[-1]


@pytest.fixture
def pair() -> Iterator[tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]]:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    yield caller, callee
    caller.close()
    callee.close()


async def local_track(kind: str) -> webrtc.MediaStreamTrack:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(**{kind: True}))
    return stream.get_tracks()[0]


async def transformed_call(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    kind: str,
    *,
    sender_worker: Recorder | None = None,
    receiver_worker: Recorder | None = None,
) -> tuple[webrtc.RTCRtpSender, webrtc.RTCRtpReceiver]:
    """Sends a track with transforms set before negotiation, and connects."""
    sender = caller.add_track(await local_track(kind))
    if sender_worker is not None:
        sender.transform = webrtc.RTCRtpScriptTransform(sender_worker)

    receivers: list[webrtc.RTCRtpReceiver] = []

    def on_track(event: webrtc.RTCTrackEvent) -> None:
        receivers.append(event.receiver)
        if receiver_worker is not None:
            event.receiver.transform = webrtc.RTCRtpScriptTransform(receiver_worker)

    callee.on('track', on_track)
    await connect(caller, callee)
    assert len(receivers) == 1
    return sender, receivers[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['video', 'audio'])
async def test_frames_pass_through_transforms(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection], kind: str
) -> None:
    """The receiver's transform sees what the sender's transform changed, and removes it before decoding."""
    caller, callee = pair
    sending, receiving = Recorder(mark), Recorder(unmark)
    marked: list[bool] = []

    def check(frame: Frame) -> None:
        # the padding-only packets of audio arrive as empty frames
        if len(frame.data) > 0:
            marked.append(frame.data[-1] == MARK)
        unmark(frame)

    receiving.change = check
    _, receiver = await transformed_call(caller, callee, kind, sender_worker=sending, receiver_worker=receiving)
    await wait_progressing(lambda: min(len(marked), 20), lambda: len(marked) >= 20, 'frames with data', stall=TIMEOUT)
    assert sum(marked) >= 15

    frame_class = webrtc.RTCEncodedVideoFrame if kind == 'video' else webrtc.RTCEncodedAudioFrame
    assert all(isinstance(frame, frame_class) for frame in sending.frames + receiving.frames)
    await wait_until_unmuted(receiver.track)


@pytest.mark.asyncio
async def test_video_metadata(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    sending, receiving = Recorder(), Recorder()
    await transformed_call(caller, callee, 'video', sender_worker=sending, receiver_worker=receiving)
    await receiving.wait_frames(5)

    first = sending.frames[0]
    assert isinstance(first, webrtc.RTCEncodedVideoFrame)
    assert first.type == webrtc.EncodedVideoChunkType.key
    sent = first.get_metadata()
    assert isinstance(sent, webrtc.RTCEncodedVideoFrameMetadata)
    assert sent.mime_type is not None
    assert sent.mime_type.startswith('video/')
    assert sent.width == 640
    assert sent.height == 480
    assert sent.synchronization_source is not None
    assert sent.payload_type is not None
    assert sent.rtp_timestamp is not None
    assert sent.receive_time is None
    assert sent.capture_time is not None
    assert abs(sent.capture_time - time.time() * 1000) < 60_000
    assert sent.synchronizationSource == sent.synchronization_source

    received = receiving.frames[0].get_metadata()
    assert isinstance(received, webrtc.RTCEncodedVideoFrameMetadata)
    assert received.synchronization_source == sent.synchronization_source
    assert received.receive_time is not None
    assert abs(received.receive_time - time.time() * 1000) < 60_000
    received.width = 1
    again = receiving.frames[0].get_metadata()
    assert isinstance(again, webrtc.RTCEncodedVideoFrameMetadata)
    assert again.width != 1


@pytest.mark.asyncio
async def test_audio_metadata(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    receiving = Recorder()
    await transformed_call(caller, callee, 'audio', receiver_worker=receiving)
    await receiving.wait_frames(5)

    metadata = receiving.frames[-1].get_metadata()
    assert isinstance(metadata, webrtc.RTCEncodedAudioFrameMetadata)
    assert metadata.mime_type == 'audio/opus'
    assert metadata.sequence_number is not None
    assert metadata.contributing_sources == []
    assert metadata.audio_level is None or 0 <= metadata.audio_level <= 1
    assert not hasattr(receiving.frames[-1], 'type')


ABS_CAPTURE_TIME = 'http://www.webrtc.org/experiments/rtp-hdrext/abs-capture-time'


def negotiate_abs_capture_time(transceiver: webrtc.RTCRtpTransceiver) -> None:
    extensions = transceiver.get_header_extensions_to_negotiate()
    for extension in extensions:
        if extension.uri == ABS_CAPTURE_TIME:
            extension.direction = webrtc.RTCRtpTransceiverDirection.sendrecv
    transceiver.set_header_extensions_to_negotiate(extensions)


@pytest.mark.asyncio
async def test_metadata_of_the_absolute_capture_time(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    """A received frame has the sender's capture time and clock offset."""
    caller, callee = pair
    sending, receiving = Recorder(), Recorder()
    sender = caller.add_track(await local_track('video'))
    sender.transform = webrtc.RTCRtpScriptTransform(sending)
    negotiate_abs_capture_time(caller.get_transceivers()[0])

    def on_track(event: webrtc.RTCTrackEvent) -> None:
        negotiate_abs_capture_time(event.transceiver)
        event.receiver.transform = webrtc.RTCRtpScriptTransform(receiving)

    callee.on('track', on_track)
    await connect(caller, callee)
    await receiving.wait_frames(5)

    received = receiving.frames[-1].get_metadata()
    sent = next(f.get_metadata() for f in sending.frames if f.get_metadata().rtp_timestamp == received.rtp_timestamp)
    assert received.sender_capture_time_offset is not None
    assert received.capture_time is not None
    assert sent.capture_time is not None
    # both in milliseconds since the Unix epoch, on one machine
    assert abs(received.capture_time - sent.capture_time) < 1000


@pytest.mark.asyncio
async def test_copy_construction(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    sending = Recorder(write=False)
    await transformed_call(caller, callee, 'video', sender_worker=sending)
    await sending.wait_frames(1)
    frame = sending.frames[0]
    assert isinstance(frame, webrtc.RTCEncodedVideoFrame)

    clone = webrtc.RTCEncodedVideoFrame(frame)
    assert repr(clone).startswith('<webrtc.RTCEncodedVideoFrame object at 0x')
    assert clone.type == frame.type
    assert clone.data == frame.data
    assert clone.data is not frame.data
    assert clone.get_metadata() == frame.get_metadata()

    options = webrtc.RTCEncodedVideoFrameOptions(webrtc.RTCEncodedVideoFrameMetadata(width=7, dependencies=[1, 2]))
    changed = webrtc.RTCEncodedVideoFrame(frame, options)
    expected = frame.get_metadata()
    expected.width, expected.dependencies = 7, [1, 2]
    assert changed.get_metadata() == expected

    with pytest.raises(TypeError):
        webrtc.RTCEncodedAudioFrame(mistyped(frame))


@pytest.mark.asyncio
async def test_frame_data(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    sending = Recorder(write=False)
    await transformed_call(caller, callee, 'audio', sender_worker=sending)
    await sending.wait_frames(1)
    frame = sending.frames[0]

    data = frame.data
    assert isinstance(data, bytearray)
    assert frame.data is data
    frame.data = b'\x01\x02'
    assert frame.data == bytearray(b'\x01\x02')
    shared = bytearray(b'\x03')
    frame.data = shared
    assert frame.data is shared
    frame.data = memoryview(b'\x04\x05')[::1]
    assert frame.data == bytearray(b'\x04\x05')
    with pytest.raises(TypeError):
        frame.data = mistyped('text')
    with pytest.raises(TypeError):
        frame.data = memoryview(b'abcd')[::2]


@pytest.mark.asyncio
async def test_changed_data_is_received(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    """Data changed in place, or replaced by bytes or a memoryview, is what the receiver's transform reads."""
    caller, callee = pair
    written = 0

    def change(frame: Frame) -> None:
        nonlocal written
        written += 1
        if written % 3 == 0:
            frame.data[:] = b'in place'
        elif written % 3 == 1:
            frame.data = b'bytes'
        else:
            frame.data = memoryview(b'a memoryview')

    payloads: set[bytes] = set()
    receiving = Recorder(lambda frame: payloads.add(bytes(frame.data)))
    await transformed_call(caller, callee, 'audio', sender_worker=Recorder(change), receiver_worker=receiving)
    await wait_until(lambda: {b'in place', b'bytes', b'a memoryview'} <= payloads, 'each changed payload', TIMEOUT)


@pytest.mark.asyncio
async def test_written_frame_is_detached(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    sending = Recorder()
    await transformed_call(caller, callee, 'audio', sender_worker=sending)
    await sending.wait_frames(2)
    frame = sending.frames[0]
    assert frame.data == bytearray()
    assert frame.get_metadata().mime_type == 'audio/opus'
    with pytest.raises(webrtc.DataCloneError):
        webrtc.RTCEncodedAudioFrame(mistyped(frame))


@pytest.mark.asyncio
async def test_write_rules(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    """Copies, frames written twice or out of order, and frames of another transformer are dropped."""
    caller, callee = pair
    payloads: list[bytes] = []
    receiving = Recorder(lambda frame: payloads.append(bytes(frame.data)))
    sending = Recorder(write=False)
    await transformed_call(caller, callee, 'audio', sender_worker=sending, receiver_worker=receiving)
    await sending.wait_frames(3)
    assert sending.transformer is not None
    writer = sending.transformer.writable.get_writer()
    first, second, third = sending.frames[:3]

    copy = webrtc.RTCEncodedAudioFrame(mistyped(first))
    copy.data = bytearray(b'copy')
    await writer.write(copy)
    second.data = bytearray(b'accepted')
    await writer.write(second)
    second.data = bytearray(b'twice')
    await writer.write(second)
    first.data = bytearray(b'reordered')
    await writer.write(first)
    assert third.get_metadata().mime_type == 'audio/opus'
    # frames arrive in order: the dropped ones would come before this one
    third.data = bytearray(b'after')
    await writer.write(third)
    await wait_until(lambda: b'after' in payloads, 'the frame written last', TIMEOUT)
    assert b'accepted' in payloads
    assert {b'copy', b'twice', b'reordered'}.isdisjoint(payloads)

    with pytest.raises(TypeError):
        await writer.write(mistyped(None))


@pytest.mark.asyncio
async def test_generate_key_frame(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    sending, receiving = Recorder(), Recorder()
    await transformed_call(caller, callee, 'video', sender_worker=sending, receiver_worker=receiving)
    await receiving.wait_frames(5)
    assert sending.transformer is not None
    assert receiving.transformer is not None

    keys = key_frames(sending)
    await asyncio.wait_for(sending.transformer.generate_key_frame(), TIMEOUT)
    await wait_until(lambda: key_frames(sending) > keys, 'the key frame recorded', TIMEOUT)
    await asyncio.wait_for(sending.transformer.generateKeyFrame(), TIMEOUT)

    with pytest.raises(webrtc.NotFoundError):
        await sending.transformer.generate_key_frame('foo')
    for rid in ('', 'foo-bar', 'foo_bar', '!?', 'a' * 256):
        with pytest.raises(webrtc.NotAllowedError):
            await sending.transformer.generate_key_frame(rid)
    with pytest.raises(webrtc.InvalidStateError):
        await receiving.transformer.generate_key_frame()


@pytest.mark.asyncio
async def test_generate_key_frame_of_a_simulcast_layer(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    """A rid the sender doesn't send is NotFoundError."""
    caller, callee = pair
    sending = Recorder()
    encodings = [webrtc.RTCRtpEncodingParameters(rid='hi'), webrtc.RTCRtpEncodingParameters(rid='lo')]
    init = webrtc.RTCRtpTransceiverInit(direction='sendonly', send_encodings=encodings)
    sender = caller.add_transceiver(await local_track('video'), init).sender
    sender.transform = webrtc.RTCRtpScriptTransform(sending)
    exchange_ice_candidates(caller, callee)
    await exchange_offer(caller, callee)
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    # libwebrtc doesn't announce receiving both layers by itself
    simulcast = 'a=rid:hi recv\r\na=rid:lo recv\r\na=simulcast:recv hi;lo\r\n'
    await caller.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', answer.sdp + simulcast))
    assert [encoding.rid for encoding in sender.get_parameters().encodings] == ['hi', 'lo']
    await sending.wait_frames(1)
    assert sending.transformer is not None

    await asyncio.wait_for(sending.transformer.generate_key_frame('lo'), TIMEOUT)
    with pytest.raises(webrtc.NotFoundError):
        await sending.transformer.generate_key_frame('mid')

    # each request waits for a key frame of its own layer
    await asyncio.wait_for(
        asyncio.gather(sending.transformer.generate_key_frame('hi'), sending.transformer.generate_key_frame('lo')),
        TIMEOUT,
    )


@pytest.mark.asyncio
async def test_cancelled_generate_key_frame_leaves_the_next_one(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    """A cancelled request is skipped when the key frame comes."""
    caller, callee = pair
    sending = Recorder()
    await transformed_call(caller, callee, 'video', sender_worker=sending)
    await sending.wait_frames(1)
    assert sending.transformer is not None

    cancelled = asyncio.ensure_future(sending.transformer.generate_key_frame())
    await asyncio.sleep(0)
    cancelled.cancel()
    await asyncio.wait_for(sending.transformer.generate_key_frame(), TIMEOUT)
    assert cancelled.cancelled()


@pytest.mark.asyncio
async def test_generate_key_frame_of_audio(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    sending = Recorder()
    await transformed_call(caller, callee, 'audio', sender_worker=sending)
    await sending.wait_frames(1)
    assert sending.transformer is not None
    with pytest.raises(webrtc.InvalidStateError):
        await sending.transformer.generate_key_frame()


@pytest.mark.asyncio
async def test_send_key_frame_request(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    caller, callee = pair
    sending, receiving = Recorder(), Recorder()
    await transformed_call(caller, callee, 'video', sender_worker=sending, receiver_worker=receiving)
    await receiving.wait_frames(5)
    assert sending.transformer is not None
    assert receiving.transformer is not None

    keys = key_frames(sending)
    await receiving.transformer.send_key_frame_request()
    await receiving.transformer.sendKeyFrameRequest()

    await wait_until(lambda: key_frames(sending) > keys, 'a key frame', TIMEOUT)
    with pytest.raises(webrtc.InvalidStateError):
        await sending.transformer.send_key_frame_request()


@pytest.mark.asyncio
async def test_removing_a_transform(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    """The streams of a removed transform end, and frames flow without it."""
    caller, callee = pair
    sending, receiving = Recorder(mark), Recorder(unmark)
    sender, receiver = await transformed_call(caller, callee, 'video', sender_worker=sending, receiver_worker=receiving)
    await receiving.wait_frames(5)
    transform = sender.transform
    assert isinstance(transform, webrtc.RTCRtpScriptTransform)

    sender.transform = None
    assert sender.transform is None
    await asyncio.wait_for(sending.done, TIMEOUT)
    count = len(receiving.frames)
    await receiving.wait_frames(count + 10)
    assert receiving.frames[-1].data[-1:] != bytes([MARK])

    replacement = Recorder()
    sender.transform = webrtc.RTCRtpScriptTransform(replacement)
    await replacement.wait_frames(5)
    assert receiver.transform is not None


@pytest.mark.asyncio
async def test_a_transform_has_one_sender_or_receiver(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    caller, _ = pair
    first = caller.add_transceiver(webrtc.MediaType.video).sender
    second = caller.add_transceiver(webrtc.MediaType.video).sender
    recorder = Recorder()
    transform = webrtc.RTCRtpScriptTransform(recorder)
    first.transform = transform
    assert first.transform is transform
    await asyncio.wait_for(recorder.started, TIMEOUT)
    # set again on the same sender, as browsers allow
    first.transform = transform
    with pytest.raises(webrtc.InvalidStateError):
        second.transform = transform
    with pytest.raises(webrtc.InvalidStateError):
        caller.get_transceivers()[1].receiver.transform = transform
    first.transform = None
    with pytest.raises(webrtc.InvalidStateError):
        first.transform = transform
    assert second.transform is None
    with pytest.raises(TypeError):
        second.transform = mistyped(object())


@pytest.mark.asyncio
async def test_rtctransform_event() -> None:
    events: list[webrtc.RTCTransformEvent] = []
    options = {'name': 'sender'}
    transform = webrtc.RTCRtpScriptTransform(events.append, options, [options])
    assert events == []
    await asyncio.sleep(0)
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, webrtc.RTCTransformEvent)
    assert event.type == 'rtctransform'
    assert event.transformer.options is options
    assert isinstance(event.transformer.readable, webrtc.ReadableStream)
    assert isinstance(event.transformer.writable, webrtc.WritableStream)
    assert transform is not None

    parameters = webrtc.WorkerAndParameters(events.append, 'sframe')
    assert parameters.type == webrtc.RTCRtpScriptTransformType.sframe
    with pytest.raises(webrtc.NotSupportedError):
        webrtc.RTCRtpScriptTransform(parameters)
    webrtc.RTCRtpScriptTransform(webrtc.WorkerAndParameters(events.append))
    with pytest.raises(ValueError, match='other'):
        webrtc.WorkerAndParameters(events.append, mistyped('other'))
    with pytest.raises(TypeError, match='worker must be callable'):
        webrtc.WorkerAndParameters(mistyped(None))
    with pytest.raises(TypeError):
        webrtc.RTCRtpScriptTransform(mistyped(None))
    with pytest.raises(TypeError):
        webrtc.RTCRtpScriptTransform(events.append, None, mistyped('transfer'))
    with pytest.raises(webrtc.DataCloneError):
        webrtc.RTCRtpScriptTransform(events.append, options, [options, options])


def test_transformer_reads_in_a_second_loop() -> None:
    """Reads keep working in a later loop."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    started: list[webrtc.RTCTransformEvent] = []

    async def setup() -> None:
        sender = caller.add_track(await local_track('video'))
        sender.transform = webrtc.RTCRtpScriptTransform(started.append)
        await connect(caller, callee)
        await wait_until(lambda: len(started) == 1, 'the transform event')
        await read_frames(3)

    async def read_frames(count: int) -> None:
        reader = started[0].transformer.readable.get_reader()
        for _ in range(count):
            result = await asyncio.wait_for(reader.read(), TIMEOUT)
            assert not result.done
        reader.release_lock()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(setup())
        time.sleep(0.3)
    finally:
        loop.close()
    try:
        asyncio.run(read_frames(200))
    finally:
        caller.close()
        callee.close()


def test_a_transform_needs_a_loop() -> None:
    with pytest.raises(RuntimeError):
        webrtc.RTCRtpScriptTransform(lambda _event: None)


def test_key_frame_request_event() -> None:
    event = webrtc.KeyFrameRequestEvent('keyframerequest')
    assert event.type == 'keyframerequest'
    assert event.rid is None
    assert webrtc.KeyFrameRequestEvent('keyframerequest', 'hi').rid == 'hi'


@pytest.mark.asyncio
async def test_nobody_reading(pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]) -> None:
    """Frames of a transformer that isn't read are dropped, nothing blocks."""
    caller, callee = pair
    started: list[webrtc.RTCTransformEvent] = []
    sender = caller.add_track(await local_track('video'))
    sender.transform = webrtc.RTCRtpScriptTransform(started.append)
    await connect(caller, callee)

    encoded = 0

    async def frames_encoded() -> int:
        nonlocal encoded
        stats = (await sender.get_stats()).values()
        outbound = [s.frames_encoded for s in stats if isinstance(s, webrtc.RTCOutboundRtpStreamStats)]
        encoded = max((frames for frames in outbound if frames is not None), default=0)
        return encoded

    # past the 60 frames a transformer queues, the oldest are dropped; slow cores encode slower, not never
    await wait_progressing(frames_encoded, lambda: encoded > 70, 'more frames than the queue keeps')
    assert len(started) == 1
    caller.close()
    callee.close()


def released_to(baseline: dict[str, int]) -> bool:
    """Whether the native objects are back to the baseline, polled without blocking the loop."""
    gc.collect()
    return all(count <= baseline.get(name, 0) for name, count in wrtc._alive().items())


def left_over(baseline: dict[str, int]) -> int:
    """The native objects alive past the baseline."""
    return sum(max(0, count - baseline.get(name, 0)) for name, count in wrtc._alive().items())


def alive_objects() -> dict[str, int]:
    """The native objects of transforms alive, once releases on helper threads are done."""
    alive = settled_alive()[0]
    return {name: alive[name] for name in ('RTCRtpScriptTransform', 'RTCEncodedFrame', 'FrameTransformerBridge')}


@pytest.mark.asyncio
async def test_closing_releases_transforms() -> None:
    baseline = alive_objects()

    async def session() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        sending, receiving = Recorder(mark), Recorder(unmark)
        await transformed_call(caller, callee, 'video', sender_worker=sending, receiver_worker=receiving)
        await receiving.wait_frames(5)
        caller.add_track(await local_track('audio')).transform = webrtc.RTCRtpScriptTransform(lambda _event: None)
        caller.close()
        callee.close()
        try:
            await asyncio.wait_for(asyncio.gather(sending.done, receiving.done), TIMEOUT)
        except asyncio.TimeoutError:
            ends = f'sender: {sending.describe()}; receiver: {receiving.describe()}'
            msg = f'Timed out waiting for the workers to end ({ends})'
            raise TimeoutError(msg) from None

    await session()
    try:
        await wait_progressing(
            lambda: -left_over(baseline), lambda: released_to(baseline), 'the transforms released', stall=TIMEOUT
        )
    except TimeoutError:
        left = {name: count for name, count in wrtc._alive().items() if count > baseline.get(name, 0)}
        msg = f'Timed out waiting for the transforms released, still alive: {left}'
        raise TimeoutError(msg) from None


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['video', 'audio'])
async def test_frames_are_released_where_dropped(kind: str) -> None:
    """Frames kept past their connection are destroyed on the thread dropping them, while the Dispatcher is held."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    sending, receiving = Recorder(keep=KEPT), Recorder(keep=KEPT)
    await transformed_call(caller, callee, kind, sender_worker=sending, receiver_worker=receiving)
    await receiving.wait_frames(KEPT)
    caller.close()
    callee.close()
    await asyncio.wait_for(asyncio.gather(sending.done, receiving.done), TIMEOUT)

    # the frames each side kept
    kept = [frame for frame in sending.frames + receiving.frames if frame._native is not None]
    assert len(kept) == 2 * KEPT
    sending.frames.clear()
    receiving.frames.clear()
    alive = settled_alive()[0]['RTCEncodedFrame']

    def drop() -> None:
        kept.clear()
        gc.collect()

    with undelivered():
        dropping = threading.Thread(target=drop)
        dropping.start()
        dropping.join()
        assert wrtc._testing.alive_counts()['RTCEncodedFrame'] == alive - 2 * KEPT


@pytest.mark.asyncio
async def test_async_worker_exception_goes_to_the_loop() -> None:
    """An async worker's exception reaches the loop's exception handler."""
    loop = asyncio.get_running_loop()
    reported = loop.create_future()
    loop.set_exception_handler(lambda _loop, context: reported.done() or reported.set_result(context))
    try:

        async def worker(_event: webrtc.RTCTransformEvent) -> None:
            await asyncio.sleep(0)
            msg = 'worker'
            raise ValueError(msg)

        transform = webrtc.RTCRtpScriptTransform(worker)
        context = await asyncio.wait_for(reported, seconds(5))
        assert context['message'] == 'Exception in the worker of an RTCRtpScriptTransform'
        assert isinstance(context['exception'], ValueError)
        assert transform is not None
    finally:
        loop.set_exception_handler(None)


@pytest.mark.asyncio
async def test_generate_key_frame_settles_when_the_transform_is_removed(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    """A pending key frame request rejects on removal."""
    caller, callee = pair
    started: asyncio.Future[webrtc.RTCRtpScriptTransformer] = asyncio.get_running_loop().create_future()
    sender, _ = await transformed_call(caller, callee, 'video')
    sender.transform = webrtc.RTCRtpScriptTransform(lambda event: started.set_result(event.transformer))
    transformer = await asyncio.wait_for(started, TIMEOUT)
    await wait_until(lambda: transformer._native_obj.sourceKind is not None, 'a source', TIMEOUT)
    request = asyncio.ensure_future(transformer.generate_key_frame())
    # only a read key frame fulfills it, and nothing reads
    await delivered()
    assert not request.done()
    sender.transform = None
    with pytest.raises(webrtc.InvalidStateError):
        await asyncio.wait_for(request, TIMEOUT)


@pytest.mark.asyncio
async def test_cancelled_generate_key_frame_is_left_on_removal(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    """Removal rejects pending requests and leaves a cancelled one as is."""
    caller, callee = pair
    started: asyncio.Future[webrtc.RTCRtpScriptTransformer] = asyncio.get_running_loop().create_future()
    sender, _ = await transformed_call(caller, callee, 'video')
    sender.transform = webrtc.RTCRtpScriptTransform(lambda event: started.set_result(event.transformer))
    transformer = await asyncio.wait_for(started, TIMEOUT)
    await wait_until(lambda: transformer._native_obj.sourceKind is not None, 'a source', TIMEOUT)
    cancelled = asyncio.ensure_future(transformer.generate_key_frame())
    pending = asyncio.ensure_future(transformer.generate_key_frame())
    await delivered()
    cancelled.cancel()
    await asyncio.gather(cancelled, return_exceptions=True)
    sender.transform = None
    with pytest.raises(webrtc.InvalidStateError):
        await asyncio.wait_for(pending, TIMEOUT)
    assert cancelled.cancelled()


@pytest.mark.asyncio
async def test_key_frames_of_a_removed_transform(
    pair: tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection],
) -> None:
    """Key frame calls reject instead of hanging."""
    caller, callee = pair
    sending, receiving = Recorder(), Recorder()
    sender, receiver = await transformed_call(caller, callee, 'video', sender_worker=sending, receiver_worker=receiving)
    await receiving.wait_frames(1)
    assert sending.transformer is not None
    assert receiving.transformer is not None
    sender.transform = None
    receiver.transform = None
    await asyncio.wait_for(asyncio.gather(sending.done, receiving.done), TIMEOUT)

    with pytest.raises(webrtc.InvalidStateError, match='was removed'):
        await asyncio.wait_for(sending.transformer.generate_key_frame(), TIMEOUT)
    with pytest.raises(webrtc.InvalidStateError, match='was removed'):
        await receiving.transformer.send_key_frame_request()


@pytest.mark.asyncio
async def test_key_frames_of_an_unused_transform() -> None:
    """A transform of no sender or receiver can't ask for key frames."""
    started: asyncio.Future[webrtc.RTCRtpScriptTransformer] = asyncio.get_running_loop().create_future()
    transform = webrtc.RTCRtpScriptTransform(lambda event: started.set_result(event.transformer))
    transformer = await asyncio.wait_for(started, TIMEOUT)
    with pytest.raises(webrtc.InvalidStateError):
        await transformer.generate_key_frame()
    with pytest.raises(webrtc.InvalidStateError):
        await transformer.send_key_frame_request()
    assert transform is not None
