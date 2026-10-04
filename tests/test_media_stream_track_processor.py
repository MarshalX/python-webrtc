#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStreamTrackProcessor, VideoTrackGenerator and MediaStreamTrackGenerator on local tracks."""

from __future__ import annotations

import array
import asyncio
import time
from typing import TypeVar

import pytest

import webrtc
from tests.helpers import QUIET_PERIOD, wait_for_event, wait_until

TIMEOUT = 10
I420_4X2 = bytes(range(1, 13))


def i420(width: int, height: int) -> bytes:
    chroma = ((width + 1) // 2) * ((height + 1) // 2)
    return bytes([81] * (width * height) + [90] * chroma + [240] * chroma)


def video_frame(timestamp: int, width: int = 4, height: int = 2) -> webrtc.VideoFrame:
    return webrtc.VideoFrame(
        i420(width, height),
        webrtc.VideoFrameBufferInit(format='I420', coded_width=width, coded_height=height, timestamp=timestamp),
    )


_T = TypeVar('_T')


async def read(reader: webrtc.ReadableStreamDefaultReader[_T]) -> webrtc.ReadableStreamReadResult[_T]:
    return await asyncio.wait_for(reader.read(), TIMEOUT)


def as_video_frame(value: object) -> webrtc.VideoFrame:
    assert isinstance(value, webrtc.VideoFrame)
    return value


def as_audio_data(value: object) -> webrtc.AudioData:
    assert isinstance(value, webrtc.AudioData)
    return value


@pytest.mark.asyncio
async def test_video_frames_of_a_camera(video_stream: webrtc.MediaStream) -> None:
    """A processor of a video track reads its frames, and closes when the track stops."""
    track = video_stream.get_tracks()[0]
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
    reader = processor.readable.get_reader()
    result = await read(reader)
    assert not result.done
    frame = result.value
    assert isinstance(frame, webrtc.VideoFrame)
    assert frame.format == webrtc.VideoPixelFormat.I420
    assert (frame.coded_width, frame.coded_height) == (640, 480)
    frame.close()

    track.stop()
    await asyncio.wait_for(reader.closed, TIMEOUT)
    assert (await reader.read()).done


@pytest.mark.asyncio
async def test_audio_data_of_a_microphone(audio_stream: webrtc.MediaStream) -> None:
    """A processor of an audio track reads its samples, 10 ms at a time."""
    track = audio_stream.get_tracks()[0]
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
    audio = (await read(reader)).value
    assert isinstance(audio, webrtc.AudioData)
    assert audio.format == webrtc.AudioSampleFormat.s16
    assert (audio.sample_rate, audio.number_of_channels, audio.number_of_frames) == (48000, 1, 480)
    audio.close()
    track.stop()
    await asyncio.wait_for(reader.closed, TIMEOUT)


@pytest.mark.asyncio
async def test_wakeup_sent_before_the_listeners_is_not_lost(
    audio_stream: webrtc.MediaStream, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Media comes as soon as the sink is attached, before the listeners are: the wakeup it sends is dropped."""
    attach = webrtc.MediaStreamTrackProcessor._attach

    def attach_once_media_came(processor: webrtc.MediaStreamTrackProcessor) -> None:
        deadline = time.monotonic() + 5
        while processor._native_obj.totalFrames == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        attach(processor)

    monkeypatch.setattr(webrtc.MediaStreamTrackProcessor, '_attach', attach_once_media_came)
    init = webrtc.MediaStreamTrackProcessorInit(audio_stream.get_tracks()[0], max_buffer_size=1)
    reader = webrtc.MediaStreamTrackProcessor(init).readable.get_reader()
    for _ in range(5):
        chunk = (await asyncio.wait_for(reader.read(), 5)).value
        assert isinstance(chunk, webrtc.AudioData)
        chunk.close()
    await reader.cancel()


def test_init_forms() -> None:
    """The processor takes its init, also from its JSON form, with a buffer size in range."""
    generator = webrtc.VideoTrackGenerator()
    track = generator.track
    for processor in (
        webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=3)),
        webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit.from_json({'track': track, 'maxBufferSize': 3})
        ),
    ):
        assert isinstance(processor.readable, webrtc.ReadableStream)
    with pytest.raises(TypeError):
        webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=70000))
    track.stop()


@pytest.mark.asyncio
async def test_full_buffer_drops_the_oldest_frames(video_stream: webrtc.MediaStream) -> None:
    """Frames nobody reads are dropped once the buffer is full, oldest first, and counted."""
    track = video_stream.get_tracks()[0]
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=2))
    reader = processor.readable.get_reader()
    await wait_until(lambda: processor.total_frames >= 5, 'frames to arrive')
    # the total first: frames keep arriving, and the discarded ones are the total less the 2 queued at any time
    total = processor.total_frames
    assert processor.discarded_frames >= total - 2
    first, second = as_video_frame((await read(reader)).value), as_video_frame((await read(reader)).value)
    assert first.timestamp < second.timestamp
    first.close()
    second.close()


@pytest.mark.asyncio
async def test_cancel_stops_reading(video_stream: webrtc.MediaStream) -> None:
    """Canceling the stream detaches the processor from the track."""
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(video_stream.get_tracks()[0]))
    reader = processor.readable.get_reader()
    as_video_frame((await read(reader)).value).close()
    await reader.cancel()
    total = processor.total_frames
    await asyncio.sleep(QUIET_PERIOD)
    assert processor.total_frames == total
    assert (await reader.read()).done


@pytest.mark.asyncio
async def test_processor_of_an_ended_track(video_stream: webrtc.MediaStream) -> None:
    """The stream of an ended track is closed."""
    track = video_stream.get_tracks()[0]
    track.stop()
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
    assert (await read(reader)).done


@pytest.mark.asyncio
async def test_generator_forwards_frames_with_their_timestamps() -> None:
    """A frame written to a generator reaches a processor of its track, with its size and timestamp, and is closed."""
    generator = webrtc.VideoTrackGenerator()
    track = generator.track
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=10)
    ).readable.get_reader()
    writer = generator.writable.get_writer()

    # reads issued before the frames arrive are settled in order
    reads = [reader.read() for _ in range(4)]
    for timestamp in range(4):
        frame = video_frame(timestamp * 1000)
        await writer.write(frame)
        assert frame.format is None, 'written frames are closed'
    frames = [as_video_frame(r.value) for r in await asyncio.wait_for(asyncio.gather(*reads), TIMEOUT)]
    assert [f.timestamp for f in frames] == [0, 1000, 2000, 3000]
    out = bytearray(12)
    await frames[0].copy_to(out)
    assert bytes(out) == i420(4, 2)
    for f in frames:
        f.close()
    track.stop()


@pytest.mark.asyncio
async def test_generator_sends_the_visible_rect() -> None:
    """A generator sends the visible rect of a frame, not its whole coded buffer."""
    generator = webrtc.VideoTrackGenerator()
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(generator.track)
    ).readable.get_reader()
    rect = webrtc.DOMRectInit(x=2, y=0, width=2, height=2)
    init = webrtc.VideoFrameBufferInit(format='I420', coded_width=4, coded_height=2, timestamp=0)
    with webrtc.VideoFrame(I420_4X2, init) as source:
        cropped = webrtc.VideoFrame(source, webrtc.VideoFrameInit(visible_rect=rect))
    init.visible_rect = rect
    for frame in (webrtc.VideoFrame(I420_4X2, init), cropped):
        expected = bytearray(frame.allocation_size())
        await frame.copy_to(expected)
        writer = generator.writable.get_writer()
        await writer.write(frame)
        writer.release_lock()
        with as_video_frame((await read(reader)).value) as received:
            assert (received.coded_width, received.coded_height) == (2, 2)
            out = bytearray(received.allocation_size())
            await received.copy_to(out)
            assert out == expected
    generator.track.stop()


@pytest.mark.asyncio
async def test_generator_rejects_what_it_cant_send() -> None:
    """A video generator takes open VideoFrames only."""
    generator = webrtc.VideoTrackGenerator()
    writer = generator.writable.get_writer()
    closed = video_frame(0)
    closed.close()
    with pytest.raises(TypeError):
        await writer.write(closed)
    with pytest.raises(TypeError):
        await webrtc.VideoTrackGenerator().writable.get_writer().write(b'frame')
    generator.track.stop()


@pytest.mark.asyncio
async def test_closing_the_generator_ends_its_track() -> None:
    """Closing the writable ends the track, which closes the processor."""
    generator = webrtc.VideoTrackGenerator()
    track = generator.track
    ended = wait_for_event(track, 'ended')
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
    await generator.writable.get_writer().close()
    await ended
    assert track.ready_state == webrtc.MediaStreamTrackState.ended
    await asyncio.wait_for(reader.closed, TIMEOUT)


@pytest.mark.asyncio
async def test_muted_generator_drops_frames() -> None:
    """A muted generator mutes its track and drops the frames written."""
    generator = webrtc.VideoTrackGenerator()
    track = generator.track
    muted = wait_for_event(track, 'mute')
    generator.muted = True
    await muted
    assert generator.muted
    assert track.muted

    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=10))
    reader = processor.readable.get_reader()
    writer = generator.writable.get_writer()
    await writer.write(video_frame(1))
    unmuted = wait_for_event(track, 'unmute')
    generator.muted = False
    await unmuted
    await writer.write(video_frame(2))
    frame = as_video_frame((await read(reader)).value)
    assert frame.timestamp == 2
    frame.close()
    track.stop()


@pytest.mark.asyncio
async def test_audio_generator_sends_10_ms_frames() -> None:
    """An audio generator is a track: it sends what's written in 10 ms frames, converted to 16 bits."""
    generator = webrtc.MediaStreamTrackGenerator('audio')
    assert isinstance(generator, webrtc.MediaStreamTrack)
    assert generator.kind == webrtc.MediaType.audio
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(generator, max_buffer_size=100)
    ).readable.get_reader()
    writer = generator.writable.get_writer()

    # 25 ms of f32 at 48 kHz: two frames now, the rest with the next samples
    samples = array.array('f', [0.5] * 1200).tobytes()
    data = webrtc.AudioData(
        webrtc.AudioDataInit(
            format='f32', sample_rate=48000, number_of_frames=1200, number_of_channels=1, timestamp=0, data=samples
        )
    )
    await writer.write(data)
    assert data.format is None, 'written data is closed'
    received = [as_audio_data((await read(reader)).value) for _ in range(2)]
    for audio in received:
        assert (audio.number_of_frames, audio.sample_rate) == (480, 48000)
        out = array.array('h', [0] * 480)
        audio.copy_to(memoryview(out).cast('B'), webrtc.AudioDataCopyToOptions(plane_index=0))
        assert set(out) == {16384}
        audio.close()

    with pytest.raises(TypeError):
        await writer.write(video_frame(0))
    generator.stop()


def test_generator_kinds() -> None:
    """A MediaStreamTrackGenerator is created for a kind, as a string or an init."""
    assert webrtc.MediaStreamTrackGenerator('video').kind == webrtc.MediaType.video
    init = webrtc.MediaStreamTrackGeneratorInit.from_json({'kind': 'audio'})
    assert webrtc.MediaStreamTrackGenerator(init).kind == webrtc.MediaType.audio
    assert (
        webrtc.MediaStreamTrackGenerator(webrtc.MediaStreamTrackGeneratorInit(webrtc.MediaType.video)).kind
        == webrtc.MediaType.video
    )
    with pytest.raises(TypeError):
        webrtc.MediaStreamTrackGenerator('data')


@pytest.mark.asyncio
async def test_pipe_processor_to_generator(video_stream: webrtc.MediaStream) -> None:
    """The frames of a track are piped through a transform to a generator, as in a browser."""
    generator = webrtc.VideoTrackGenerator()
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(generator.track)
    ).readable.get_reader()

    class Stamp:
        @staticmethod
        def transform(frame: webrtc.VideoFrame, controller: webrtc.TransformStreamDefaultController) -> None:
            controller.enqueue(webrtc.VideoFrame(frame, webrtc.VideoFrameInit(timestamp=42)))
            frame.close()

    source = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(video_stream.get_tracks()[0])
    ).readable
    pipe = asyncio.ensure_future(source.pipe_through(webrtc.TransformStream(Stamp())).pipe_to(generator.writable))
    frame = as_video_frame((await read(reader)).value)
    assert frame.timestamp == 42
    assert frame.coded_width == 640
    frame.close()

    video_stream.get_tracks()[0].stop()
    await asyncio.wait_for(pipe, TIMEOUT)
    await wait_until(lambda: generator.track.ready_state == webrtc.MediaStreamTrackState.ended, 'the generator to end')


@pytest.mark.asyncio
async def test_frames_wait_in_the_native_queue_only(video_stream: webrtc.MediaStream) -> None:
    """Frames are taken from the processor for pending reads only: the rest stays in its buffer, where it's dropped."""
    processor = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(video_stream.get_tracks()[0], max_buffer_size=2)
    )
    reader = processor.readable.get_reader()
    frames = await asyncio.wait_for(asyncio.gather(*(reader.read() for _ in range(4))), TIMEOUT)
    for result in frames:
        as_video_frame(result.value).close()
    await wait_until(lambda: processor.discarded_frames > 0, 'frames to be dropped')
    assert len(processor.readable._controller._queue) == 0


def test_processor_reads_in_a_second_loop(video_stream: webrtc.MediaStream) -> None:
    """Reads keep working in a later loop."""
    track = video_stream.get_tracks()[0]

    async def create() -> webrtc.MediaStreamTrackProcessor:  # ruff: ignore[unused-async]
        return webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))

    async def read_frames(processor: webrtc.MediaStreamTrackProcessor, count: int) -> None:
        reader = processor.readable.get_reader()
        for _ in range(count):
            as_video_frame((await read(reader)).value).close()
        reader.release_lock()

    loop = asyncio.new_event_loop()
    try:
        processor = loop.run_until_complete(create())
        loop.run_until_complete(read_frames(processor, 3))
        time.sleep(0.3)
    finally:
        loop.close()
    asyncio.run(read_frames(processor, 5))


@pytest.mark.asyncio
async def test_clone_of_a_stopped_generator_track_gets_frames() -> None:
    """A live clone keeps receiving frames."""
    generator = webrtc.VideoTrackGenerator()
    clone = generator.track.clone()
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(clone)).readable.get_reader()
    generator.track.stop()
    assert clone.ready_state == webrtc.MediaStreamTrackState.live
    writer = generator.writable.get_writer()
    for timestamp in range(3):
        await writer.write(video_frame(timestamp))
    as_video_frame((await asyncio.wait_for(reader.read(), 5)).value).close()
    clone.stop()
