#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The audio and video between generated tracks and the frames of a pipeline, without a connection."""

from __future__ import annotations

import array
import asyncio
import contextlib
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from pipecat.frames.frames import InputAudioRawFrame, OutputImageRawFrame

import webrtc
from tests.helpers import QUIET_PERIOD, reader_of, wait_until
from tests.pipecat._audio import SILENCE, dominant_frequency, sine
from tests.timing import seconds
from webrtc.pipecat._media import (  # ruff: ignore[import-private-name]
    _SILENCE_SLACK_SECS,
    AudioPacer,
    AudioReader,
    VideoWriter,
    video_image,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

RATE = 16000
FRAME_BYTES = RATE // 50 * 2
#: the rate the engine delivers a microphone at
TRACK_RATE = 48000
SIZE = (64, 48)
FRAME_SECS = 0.01
STALL_SECS = 0.3


class Received:
    """The audio a track carries, as it arrives."""

    def __init__(self, track: webrtc.MediaStreamTrack) -> None:
        self.samples: list[int] = []
        self.chunks = 0
        self._reader = reader_of(track, max_buffer_size=100)
        self._task = asyncio.ensure_future(self._read())

    async def _read(self) -> None:
        while True:
            audio = (await self._reader.read()).value
            if audio is None:
                return
            assert isinstance(audio, webrtc.AudioData)
            with audio:
                plane = array.array('h', bytes(audio.number_of_frames * 2))
                audio.copy_to(memoryview(plane).cast('B'), webrtc.AudioDataCopyToOptions(plane_index=0))
            self.samples.extend(plane)
            self.chunks += 1

    def loud(self, start: int = 0) -> int:
        return sum(abs(sample) > SILENCE for sample in self.samples[start:])

    async def stop(self) -> None:
        _ = self._task.cancel()
        _ = await asyncio.gather(self._task, return_exceptions=True)
        _ = self._reader.cancel()


@contextlib.asynccontextmanager
async def pacing(*, auto_silence: bool = True) -> AsyncGenerator[tuple[AudioPacer, Received], None]:
    pacer = AudioPacer(RATE, auto_silence=auto_silence)
    received = Received(pacer.track)
    try:
        yield pacer, received
    finally:
        await received.stop()
        await pacer.close()


def tone(duration: float) -> bytes:
    """A 440 Hz sine at the rate, as the pipeline writes it."""
    return sine(440, RATE, count=round(duration * RATE))


def loud_samples(audio: bytes) -> int:
    return sum(abs(sample) > SILENCE for sample in array.array('h', audio))


@pytest.mark.asyncio
async def test_a_write_returns_once_it_is_sent() -> None:
    async with pacing() as (pacer, received):
        loop = asyncio.get_running_loop()
        start = loop.time()

        assert await pacer.write(tone(0.2), 1)

        elapsed = loop.time() - start
        assert 0.15 < elapsed < seconds(0.5)
        await wait_until(lambda: received.loud() > 0, 'the audio')


@pytest.mark.asyncio
async def test_short_writes_keep_the_pace_of_real_time() -> None:
    async with pacing() as (pacer, _received):
        loop = asyncio.get_running_loop()
        start = loop.time()

        for _ in range(20):
            assert await pacer.write(tone(0.01), 1)

        elapsed = loop.time() - start
        assert 0.15 < elapsed < seconds(0.35)


@pytest.mark.asyncio
async def test_silence_fills_the_gaps() -> None:
    async with pacing() as (_pacer, received):
        await asyncio.sleep(0.3)

        assert received.chunks > 10
        assert received.loud() == 0


@pytest.mark.asyncio
async def test_without_silence_the_track_pauses() -> None:
    async with pacing(auto_silence=False) as (pacer, received):
        await asyncio.sleep(0.3)
        assert received.chunks == 0

        assert await pacer.write(tone(0.1), 1)
        await wait_until(lambda: received.loud() > 0, 'the audio')


@pytest.mark.asyncio
async def test_a_writer_giving_up_drops_the_rest() -> None:
    async with pacing() as (pacer, received):
        with contextlib.suppress(TimeoutError):
            _ = await asyncio.wait_for(pacer.write(tone(2), 1), 0.2)
        await asyncio.sleep(0.1)
        mark = len(received.samples)
        await asyncio.sleep(0.3)

        assert received.loud(mark) == 0


@pytest.mark.asyncio
async def test_closing_ends_the_writes_waiting() -> None:
    pacer = AudioPacer(RATE, auto_silence=True)
    write = asyncio.ensure_future(pacer.write(tone(2), 1))
    await asyncio.sleep(0.1)

    await pacer.close()

    assert await write is False
    assert await pacer.write(tone(0.1), 1) is False
    assert pacer.track.ready_state == 'ended'


async def write_stereo_tone(generator: webrtc.MediaStreamTrackGenerator, stop: asyncio.Event) -> None:
    writer = generator.writable.get_writer()
    written = 0
    while not stop.is_set():
        mono = array.array('h', sine(440, TRACK_RATE, first=written, count=480))
        stereo = array.array('h', [sample for sample in mono for _ in range(2)])
        init = webrtc.AudioDataInit(
            format='s16',
            sample_rate=TRACK_RATE,
            number_of_frames=480,
            number_of_channels=2,
            timestamp=written * 1_000_000 // TRACK_RATE,
            data=stereo.tobytes(),
        )
        await writer.write(webrtc.AudioData(init))
        written += 480
        await asyncio.sleep(0.01)
    writer.release_lock()


@pytest.mark.asyncio
async def test_the_reader_makes_20_ms_frames_at_its_rate() -> None:
    generator = webrtc.MediaStreamTrackGenerator('audio')
    frames: list[InputAudioRawFrame] = []

    async def push(frame: InputAudioRawFrame) -> None:  # ruff: ignore[unused-async]
        frames.append(frame)

    stop = asyncio.Event()
    writing = asyncio.ensure_future(write_stereo_tone(generator, stop))
    reading = asyncio.ensure_future(AudioReader(RATE, 1).read(generator, push))
    try:
        await wait_until(lambda: len(frames) >= 25, 'half a second of frames')
    finally:
        stop.set()
        await writing
        generator.stop()
        await asyncio.wait_for(reading, seconds(5))

    assert {(len(frame.audio), frame.sample_rate, frame.num_channels) for frame in frames} == {(FRAME_BYTES, RATE, 1)}
    samples = list(array.array('h', b''.join(frame.audio for frame in frames[5:])))
    frequency = dominant_frequency(samples, RATE)
    assert frequency is not None
    assert abs(frequency - 440) < 5


def stereo_chunk(first: int) -> webrtc.AudioData:
    """10 ms of a 440 Hz stereo tone at the track's rate, from the sample at the index ``first``."""
    mono = array.array('h', sine(440, TRACK_RATE, first=first, count=480))
    stereo = array.array('h', [sample for sample in mono for _ in range(2)])
    init = webrtc.AudioDataInit(
        format='s16',
        sample_rate=TRACK_RATE,
        number_of_frames=480,
        number_of_channels=2,
        timestamp=first * 1_000_000 // TRACK_RATE,
        data=stereo.tobytes(),
    )
    return webrtc.AudioData(init)


@pytest.mark.asyncio
async def test_the_reader_resamples_to_a_rate_the_track_rate_does_not_divide() -> None:
    generator = webrtc.MediaStreamTrackGenerator('audio')
    frames: list[InputAudioRawFrame] = []

    async def push(frame: InputAudioRawFrame) -> None:  # ruff: ignore[unused-async]
        frames.append(frame)

    rate = 44100
    stop = asyncio.Event()
    writing = asyncio.ensure_future(write_stereo_tone(generator, stop))
    reading = asyncio.ensure_future(AudioReader(rate, 1).read(generator, push))
    try:
        await wait_until(lambda: len(frames) >= 25, 'half a second of frames')
    finally:
        stop.set()
        await writing
        generator.stop()
        await asyncio.wait_for(reading, seconds(5))

    assert {(len(frame.audio), frame.sample_rate) for frame in frames} == {(rate // 50 * 2, rate)}
    frequency = dominant_frequency(list(array.array('h', b''.join(frame.audio for frame in frames[5:]))), rate)
    assert frequency is not None
    assert abs(frequency - 440) < 5


@pytest.mark.asyncio
async def test_the_reader_pushes_a_frame_with_its_second_chunk() -> None:
    generator = webrtc.MediaStreamTrackGenerator('audio')
    writer = generator.writable.get_writer()
    frames: list[InputAudioRawFrame] = []

    async def push(frame: InputAudioRawFrame) -> None:  # ruff: ignore[unused-async]
        frames.append(frame)

    reading = asyncio.ensure_future(AudioReader(RATE, 1).read(generator, push))
    try:
        # the processor reads chunks from the first one written after it starts
        await asyncio.sleep(QUIET_PERIOD)
        for frame in range(3):
            await writer.write(stereo_chunk(960 * frame))
            await asyncio.sleep(QUIET_PERIOD)
            assert len(frames) == frame

            # a resampler holding audio back would push it with a later chunk
            await writer.write(stereo_chunk(960 * frame + 480))
            await wait_until(lambda frame=frame: len(frames) == frame + 1, 'the frame')
            assert len(frames[-1].audio) == FRAME_BYTES
    finally:
        writer.release_lock()
        generator.stop()
        await asyncio.wait_for(reading, seconds(5))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('image_format', 'pixel'), [('RGB', bytes([10, 200, 30])), ('RGBA', bytes([10, 200, 30, 255]))]
)
async def test_written_images_come_out_as_rgb(image_format: str, pixel: bytes) -> None:
    writer = VideoWriter()
    reader = reader_of(writer.track)
    try:
        image = OutputImageRawFrame(image=pixel * (SIZE[0] * SIZE[1]), size=SIZE, format=image_format)
        assert await writer.write(image)
        frame = (await asyncio.wait_for(reader.read(), seconds(5))).value
        assert isinstance(frame, webrtc.VideoFrame)
        with frame:
            image = video_image(frame)
    finally:
        _ = reader.cancel()
        writer.close()

    assert image.size == SIZE
    assert len(image.pixels) == SIZE[0] * SIZE[1] * 3
    assert all(abs(got - want) <= 2 for got, want in zip(image.pixels[:3], pixel[:3]))


#: an image of 4x2 pixels, black but its top-left one, which is red
MARKED_SIZE = (4, 2)
RED = bytes([255, 0, 0, 255])
MARKED = RED + bytes(4 * (MARKED_SIZE[0] * MARKED_SIZE[1] - 1))


@dataclass(frozen=True)
class Turn:
    """How a frame is shown, and where the red pixel of the marked image is then."""

    rotation: int
    flip: bool
    size: tuple[int, int]
    red_at: tuple[int, int]


TURNS = [
    Turn(0, flip=False, size=(4, 2), red_at=(0, 0)),
    Turn(90, flip=False, size=(2, 4), red_at=(1, 0)),
    Turn(180, flip=False, size=(4, 2), red_at=(3, 1)),
    Turn(270, flip=False, size=(2, 4), red_at=(0, 3)),
    Turn(0, flip=True, size=(4, 2), red_at=(3, 0)),
    Turn(90, flip=True, size=(2, 4), red_at=(1, 3)),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('turn', TURNS, ids=lambda turn: f'{turn.rotation}{" flipped" if turn.flip else ""}')
async def test_images_are_turned_as_their_frames_are_shown(turn: Turn) -> None:  # ruff: ignore[unused-async]
    width, height = MARKED_SIZE
    init = webrtc.VideoFrameBufferInit(
        format='RGBX', coded_width=width, coded_height=height, timestamp=0, rotation=turn.rotation, flip=turn.flip
    )
    with webrtc.VideoFrame(MARKED, init) as frame:
        image = video_image(frame)

    assert image.size == turn.size
    x, y = turn.red_at
    red = (y * turn.size[0] + x) * 3
    assert image.pixels[red : red + 3] == RED[:3]
    assert image.pixels.count(255) == 1


@pytest.mark.asyncio
async def test_a_stalled_loop_skips_the_silence_it_lost() -> None:
    async with pacing() as (pacer, received):
        await wait_until(lambda: received.chunks > 5, 'the pacer to run')
        loop = asyncio.get_running_loop()
        start = loop.time()
        samples = pacer._samples_sent

        # a handler blocking the loop
        loop.call_soon(time.sleep, STALL_SECS)
        await asyncio.sleep(STALL_SECS + 0.2)

        elapsed = loop.time() - start
        sent = (pacer._samples_sent - samples) / RATE
        # silence catches up only on late wakes, not on a stall
        assert sent < elapsed - STALL_SECS + _SILENCE_SLACK_SECS + 3 * FRAME_SECS


@pytest.mark.asyncio
async def test_silence_keeps_real_time_with_a_coarse_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    # Windows' 15.6 ms timer ticks make a 10 ms wait often end a tick late
    tick = 1 / 64
    loop = asyncio.get_running_loop()
    clock = loop.time
    monkeypatch.setattr(loop, 'time', lambda: math.floor(clock() / tick) * tick)
    async with pacing() as (pacer, _received):
        await asyncio.sleep(0.1)
        start = time.monotonic()
        samples = pacer._samples_sent

        await asyncio.sleep(1)

        sent = (pacer._samples_sent - samples) / RATE
        assert sent > 0.97 * (time.monotonic() - start)


async def write_through_a_stall(pacer: AudioPacer, audio: bytes) -> float:
    """Writes audio while the loop stalls once, and returns how long the write took."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    loop.call_later(0.2, time.sleep, STALL_SECS)

    assert await pacer.write(audio, 1)
    return loop.time() - start


@pytest.mark.asyncio
async def test_a_stalled_loop_catches_up_on_the_audio_waiting() -> None:
    async with pacing() as (pacer, received):
        audio = tone(1)
        elapsed = await write_through_a_stall(pacer, audio)

        # a write without the catching up would take the stall longer
        assert elapsed < 1 + STALL_SECS / 2
        await wait_until(lambda: received.loud() == loud_samples(audio), 'all of the audio')


@pytest.mark.asyncio
async def test_an_interruption_stops_the_catching_up() -> None:
    async with pacing() as (pacer, received):
        audio = tone(1)
        loop = asyncio.get_running_loop()
        start = loop.time()

        def stall_then_interrupt() -> None:
            time.sleep(STALL_SECS)
            pacer.interrupt()

        loop.call_later(0.2, stall_then_interrupt)
        assert await pacer.write(audio, 1)

        # late by the stall, and none of it dropped
        assert loop.time() - start > 1 + STALL_SECS - 2 * FRAME_SECS
        await wait_until(lambda: received.loud() == loud_samples(audio), 'all of the audio')


@pytest.mark.asyncio
async def test_catching_up_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    bound = 0.1
    monkeypatch.setattr('webrtc.pipecat._media._MAX_CATCH_UP_SECS', bound)
    async with pacing() as (pacer, received):
        audio = tone(1)
        elapsed = await write_through_a_stall(pacer, audio)

        # the stall beyond the bound is late, and none of it dropped
        assert elapsed > 1 + STALL_SECS - bound - 2 * FRAME_SECS
        await wait_until(lambda: received.loud() == loud_samples(audio), 'all of the audio')


@pytest.mark.asyncio
async def test_a_write_during_silence_waits_for_its_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    # long frames, so sending at once would show
    frame_ms = 200
    monkeypatch.setattr('webrtc.pipecat._media.SENT_AUDIO_FRAME_MS', frame_ms)
    async with pacing() as (pacer, received):
        await wait_until(lambda: received.chunks > 0, 'the first silence')
        loop = asyncio.get_running_loop()
        start = loop.time()

        assert await pacer.write(tone(frame_ms / 1000), 1)

        elapsed = loop.time() - start
        assert frame_ms / 1000 / 2 < elapsed < seconds(frame_ms / 1000 * 1.5)
        await wait_until(lambda: received.loud() > 0, 'the audio')


@pytest.mark.asyncio
async def test_a_write_within_a_frame_of_the_last_leaves_no_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    frame_ms = 200
    frame_samples = RATE * frame_ms // 1000
    monkeypatch.setattr('webrtc.pipecat._media.SENT_AUDIO_FRAME_MS', frame_ms)
    async with pacing() as (pacer, received):
        await wait_until(lambda: received.chunks > 0, 'the first silence')
        start = len(received.samples)

        audio = tone(frame_ms / 1000)
        assert await pacer.write(audio, 1)
        # a write returns as its frame starts, so the next one is due a frame later
        await asyncio.sleep(0.5 * frame_ms / 1000)
        assert await pacer.write(audio, 1)

        await wait_until(lambda: received.loud(start) == 2 * loud_samples(audio), 'both writes')
        loud = [i for i, sample in enumerate(received.samples[start:]) if abs(sample) > SILENCE]
        assert loud[-1] - loud[0] < frame_samples * 5 // 2


@pytest.mark.asyncio
async def test_an_image_of_another_format_is_not_sent() -> None:
    writer = VideoWriter()
    try:
        assert not await writer.write(OutputImageRawFrame(image=bytes(SIZE[0] * SIZE[1]), size=SIZE, format='L'))
        assert not await writer.write(OutputImageRawFrame(image=bytes(10), size=SIZE, format='RGB'))
    finally:
        writer.close()
