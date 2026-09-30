#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStreamTrackProcessor, VideoTrackGenerator and MediaStreamTrackGenerator on local tracks."""

from __future__ import annotations

import array
import asyncio

import pytest

import webrtc
from tests.helpers import QUIET_PERIOD, wait_for_event, wait_until

TIMEOUT = 10


def i420(width: int, height: int) -> bytes:
    chroma = ((width + 1) // 2) * ((height + 1) // 2)
    return bytes([81] * (width * height) + [90] * chroma + [240] * chroma)


def video_frame(timestamp: int, width: int = 4, height: int = 2) -> webrtc.VideoFrame:
    return webrtc.VideoFrame(
        i420(width, height), format='I420', coded_width=width, coded_height=height, timestamp=timestamp
    )


async def read(reader: webrtc.ReadableStreamDefaultReader) -> webrtc.ReadableStreamReadResult:
    return await asyncio.wait_for(reader.read(), TIMEOUT)


@pytest.mark.asyncio
async def test_video_frames_of_a_camera(video_stream: webrtc.MediaStream) -> None:
    """A processor of a video track reads its frames, and closes when the track stops."""
    track = video_stream.get_tracks()[0]
    processor = webrtc.MediaStreamTrackProcessor(track)
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
    reader = webrtc.MediaStreamTrackProcessor(track=track).readable.get_reader()
    audio = (await read(reader)).value
    assert isinstance(audio, webrtc.AudioData)
    assert audio.format == webrtc.AudioSampleFormat.s16
    assert (audio.sample_rate, audio.number_of_channels, audio.number_of_frames) == (48000, 1, 480)
    audio.close()
    track.stop()
    await asyncio.wait_for(reader.closed, TIMEOUT)


def test_init_forms() -> None:
    """The processor takes a track, an init or a dictionary, and rejects anything else."""
    generator = webrtc.VideoTrackGenerator()
    track = generator.track
    for processor in (
        webrtc.MediaStreamTrackProcessor(track, max_buffer_size=3),
        webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, 3)),
        webrtc.MediaStreamTrackProcessor({'track': track, 'maxBufferSize': 3}),
    ):
        assert isinstance(processor.readable, webrtc.ReadableStream)
    with pytest.raises(TypeError):
        webrtc.MediaStreamTrackProcessor(generator)
    with pytest.raises(TypeError):
        webrtc.MediaStreamTrackProcessor(track, max_buffer_size=70000)
    track.stop()


@pytest.mark.asyncio
async def test_full_buffer_drops_the_oldest_frames(video_stream: webrtc.MediaStream) -> None:
    """Frames nobody reads are dropped once the buffer is full, oldest first, and counted."""
    track = video_stream.get_tracks()[0]
    processor = webrtc.MediaStreamTrackProcessor(track, max_buffer_size=2)
    reader = processor.readable.get_reader()
    await wait_until(lambda: processor.total_frames >= 5, 'frames to arrive')
    # the total first: frames keep arriving, and the discarded ones are the total less the 2 queued at any time
    total = processor.total_frames
    assert processor.discarded_frames >= total - 2
    first, second = (await read(reader)).value, (await read(reader)).value
    assert first.timestamp < second.timestamp
    first.close()
    second.close()


@pytest.mark.asyncio
async def test_cancel_stops_reading(video_stream: webrtc.MediaStream) -> None:
    """Canceling the stream detaches the processor from the track."""
    processor = webrtc.MediaStreamTrackProcessor(video_stream.get_tracks()[0])
    reader = processor.readable.get_reader()
    (await read(reader)).value.close()
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
    reader = webrtc.MediaStreamTrackProcessor(track).readable.get_reader()
    assert (await read(reader)).done


@pytest.mark.asyncio
async def test_generator_forwards_frames_with_their_timestamps() -> None:
    """A frame written to a generator reaches a processor of its track, with its size and timestamp, and is closed."""
    generator = webrtc.VideoTrackGenerator()
    track = generator.track
    reader = webrtc.MediaStreamTrackProcessor(track, max_buffer_size=10).readable.get_reader()
    writer = generator.writable.get_writer()

    # reads issued before the frames arrive are settled in order
    reads = [reader.read() for _ in range(4)]
    for timestamp in range(4):
        frame = video_frame(timestamp * 1000)
        await writer.write(frame)
        assert frame.format is None, 'written frames are closed'
    frames = [r.value for r in await asyncio.wait_for(asyncio.gather(*reads), TIMEOUT)]
    assert [f.timestamp for f in frames] == [0, 1000, 2000, 3000]
    out = bytearray(12)
    await frames[0].copy_to(out)
    assert bytes(out) == i420(4, 2)
    for f in frames:
        f.close()
    track.stop()


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
    reader = webrtc.MediaStreamTrackProcessor(track).readable.get_reader()
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

    processor = webrtc.MediaStreamTrackProcessor(track, max_buffer_size=10)
    reader = processor.readable.get_reader()
    writer = generator.writable.get_writer()
    await writer.write(video_frame(1))
    unmuted = wait_for_event(track, 'unmute')
    generator.muted = False
    await unmuted
    await writer.write(video_frame(2))
    frame = (await read(reader)).value
    assert frame.timestamp == 2
    frame.close()
    track.stop()


@pytest.mark.asyncio
async def test_audio_generator_sends_10_ms_frames() -> None:
    """An audio generator is a track: it sends what's written in 10 ms frames, converted to 16 bits."""
    generator = webrtc.MediaStreamTrackGenerator('audio')
    assert isinstance(generator, webrtc.MediaStreamTrack)
    assert generator.kind == webrtc.MediaType.audio
    reader = webrtc.MediaStreamTrackProcessor(generator, max_buffer_size=100).readable.get_reader()
    writer = generator.writable.get_writer()

    # 25 ms of f32 at 48 kHz: two frames now, the rest with the next samples
    samples = array.array('f', [0.5] * 1200).tobytes()
    data = webrtc.AudioData(
        format='f32', sample_rate=48000, number_of_frames=1200, number_of_channels=1, timestamp=0, data=samples
    )
    await writer.write(data)
    assert data.format is None, 'written data is closed'
    received = [(await read(reader)).value for _ in range(2)]
    for audio in received:
        assert (audio.number_of_frames, audio.sample_rate) == (480, 48000)
        out = array.array('h', [0] * 480)
        audio.copy_to(memoryview(out).cast('B'), {'plane_index': 0})
        assert set(out) == {16384}
        audio.close()

    with pytest.raises(TypeError):
        await writer.write(video_frame(0))
    generator.stop()


def test_generator_kinds() -> None:
    """A MediaStreamTrackGenerator is created for a kind, as a string, an init or a dictionary."""
    assert webrtc.MediaStreamTrackGenerator('video').kind == webrtc.MediaType.video
    assert webrtc.MediaStreamTrackGenerator({'kind': 'audio'}).kind == webrtc.MediaType.audio
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
    reader = webrtc.MediaStreamTrackProcessor(generator.track).readable.get_reader()

    class Stamp:
        @staticmethod
        def transform(frame: webrtc.VideoFrame, controller: webrtc.TransformStreamDefaultController) -> None:
            controller.enqueue(webrtc.VideoFrame(frame, timestamp=42))
            frame.close()

    source = webrtc.MediaStreamTrackProcessor(video_stream.get_tracks()[0]).readable
    pipe = asyncio.ensure_future(source.pipe_through(webrtc.TransformStream(Stamp())).pipe_to(generator.writable))
    frame = (await read(reader)).value
    assert frame.timestamp == 42
    assert frame.coded_width == 640
    frame.close()

    video_stream.get_tracks()[0].stop()
    await asyncio.wait_for(pipe, TIMEOUT)
    await wait_until(lambda: generator.track.ready_state == webrtc.MediaStreamTrackState.ended, 'the generator to end')


@pytest.mark.asyncio
async def test_frames_wait_in_the_native_queue_only(video_stream: webrtc.MediaStream) -> None:
    """Frames are taken from the processor for pending reads only: the rest stays in its buffer, where it's dropped."""
    processor = webrtc.MediaStreamTrackProcessor(video_stream.get_tracks()[0], max_buffer_size=2)
    reader = processor.readable.get_reader()
    frames = await asyncio.wait_for(asyncio.gather(*(reader.read() for _ in range(4))), TIMEOUT)
    for result in frames:
        result.value.close()
    await wait_until(lambda: processor.discarded_frames > 0, 'frames to be dropped')
    assert not processor.readable._controller._queue
