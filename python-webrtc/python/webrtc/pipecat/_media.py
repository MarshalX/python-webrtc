#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Media between the tracks of a connection and the frames of a pipeline: PCM audio and RGB images."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import InputAudioRawFrame

import webrtc

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from numpy.typing import NDArray
    from pipecat.audio.resamplers.base_audio_resampler import BaseAudioResampler
    from pipecat.frames.frames import OutputImageRawFrame

AUDIO_FRAME_MS = 20
#: The engine takes audio in 10 ms chunks
SENT_AUDIO_FRAME_MS = 10

_SAMPLE_BYTES = 2
_MICROSECONDS = 1_000_000
#: A client's jitter buffer keeps a 1 s burst, but speeds away or flushes longer ones
_MAX_CATCH_UP_SECS = 1.0
#: Three of Windows' 15.6 ms timer ticks, which wake a 10 ms wait late every other time
_SILENCE_SLACK_SECS = 0.05
#: As a share of the output's Nyquist frequency
_PASSBAND = 0.9
#: The lowest frequency that folds back into the passband
_STOPBAND = 2 - _PASSBAND
_ATTENUATION_DB = 60
#: Kaiser's estimates fall short by up to 0.4 dB here
_DESIGN_ATTENUATION_DB = _ATTENUATION_DB + 2
_S16 = webrtc.AudioDataCopyToOptions(plane_index=0, format='s16')
_RGBX = webrtc.VideoFrameCopyToOptions(format='RGBX')


@dataclass(frozen=True)
class _ImageFormat:
    pixel_bytes: int
    sent_as: webrtc.VideoPixelFormat


#: No format means RGB
_IMAGE_FORMATS: dict[str | None, _ImageFormat] = {
    None: _ImageFormat(3, webrtc.VideoPixelFormat.RGBX),
    'RGB': _ImageFormat(3, webrtc.VideoPixelFormat.RGBX),
    'RGBA': _ImageFormat(4, webrtc.VideoPixelFormat.RGBA),
}


async def read_track(
    track: webrtc.MediaStreamTrack,
    handle: Callable[[webrtc.AudioData | webrtc.VideoFrame], Awaitable[None]],
    *,
    max_buffer_size: int | None = None,
) -> None:
    """Hands each frame or audio chunk of a track to a function, closing it after, until the track ends.

    Args:
        track: The track.
        handle: The function.
        max_buffer_size: How many items wait before the oldest is dropped; the processor's default if :obj:`None`.
    """
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size))
    reader = processor.readable.get_reader()
    try:
        while True:
            result = await reader.read()
            media = result.value
            if result.done or media is None:
                return
            with media:
                await handle(media)
    finally:
        # stops the processor queuing what nobody reads
        reader.cancel().add_done_callback(_retrieved)
        reader.release_lock()


class AudioReader:
    """Turns a microphone track into 20 ms frames of 16-bit PCM at a rate and channel count.

    Args:
        sample_rate: The rate of the frames.
        channels: The channels of the frames, interleaved.
    """

    def __init__(self, sample_rate: int, channels: int) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._frame_bytes = sample_rate * AUDIO_FRAME_MS // 1000 * channels * _SAMPLE_BYTES
        self._input = bytearray()
        self._output = bytearray()
        self._input_rate: int | None = None
        self._decimators: list[Decimator] = []
        self._resamplers: list[BaseAudioResampler] = []

    async def read(self, track: webrtc.MediaStreamTrack, push: Callable[[InputAudioRawFrame], Awaitable[None]]) -> None:
        """Pushes the frames of a track until it ends.

        Args:
            track: The microphone track.
            push: Takes each frame.
        """
        self._input_rate = None

        async def handle(media: webrtc.AudioData | webrtc.VideoFrame) -> None:
            if not isinstance(media, webrtc.AudioData):
                return
            rate = int(media.sample_rate)
            if rate != self._input_rate:
                self._start_rate(rate)
            self._input += _remixed(_samples_of(media), self._channels).tobytes()

            input_bytes = rate * AUDIO_FRAME_MS // 1000 * self._channels * _SAMPLE_BYTES
            while len(self._input) >= input_bytes:
                samples = np.frombuffer(self._input[:input_bytes], np.int16).reshape(-1, self._channels)
                del self._input[:input_bytes]
                self._output += await self._converted(samples, rate)

            while len(self._output) >= self._frame_bytes:
                audio = bytes(self._output[: self._frame_bytes])
                del self._output[: self._frame_bytes]
                await push(InputAudioRawFrame(audio=audio, sample_rate=self._sample_rate, num_channels=self._channels))

        await read_track(track, handle)

    def _start_rate(self, rate: int) -> None:
        """Starts over at a new rate, as after a renegotiated codec."""
        self._input_rate = rate
        self._input.clear()
        self._output.clear()
        self._decimators = []
        self._resamplers = []
        if rate == self._sample_rate:
            return
        if rate % self._sample_rate == 0:
            self._decimators = [Decimator(rate // self._sample_rate) for _ in range(self._channels)]
        else:
            self._resamplers = [create_stream_resampler() for _ in range(self._channels)]

    async def _converted(self, samples: NDArray[np.int16], rate: int) -> bytes:
        if rate == self._sample_rate:
            return samples.tobytes()
        channels: list[NDArray[np.int16]] = []
        for channel in range(self._channels):
            if len(self._decimators) > 0:
                channels.append(self._decimators[channel].decimate(samples[:, channel]))
            else:
                resampled = await self._resamplers[channel].resample(
                    samples[:, channel].tobytes(), rate, self._sample_rate
                )
                channels.append(np.frombuffer(resampled, np.int16))
        # every channel's resampler has the same history, so gives the same count
        return np.column_stack(channels).tobytes()


class Decimator:
    """Lowers the rate of 16-bit mono audio by a whole factor, a chunk at a time, through a polyphase low-pass.

    Args:
        factor: The input's rate over the output's, more than 1.
    """

    def __init__(self, factor: int) -> None:
        taps = _low_pass(factor)
        # padding on the oldest side adds no delay
        blocks = math.ceil(len(taps) / factor)
        padded = np.zeros(blocks * factor, np.float32)
        padded[len(padded) - len(taps) :] = taps
        # by phase, then block, oldest first
        self._phases = np.ascontiguousarray(padded.reshape(blocks, factor).T)
        #: In input samples
        self.delay_samples = (len(taps) - 1) // 2
        self._signal = np.zeros(len(padded) - 1, np.float32)

    def decimate(self, samples: NDArray[np.int16]) -> NDArray[np.int16]:
        """Decimates the next chunk of the stream, of any length.

        Args:
            samples: The chunk.

        Returns:
            The output up to the chunk's last sample.
        """
        signal = np.concatenate([self._signal, samples.astype(np.float32)])
        factor, blocks = self._phases.shape
        window = blocks * factor
        count = max((len(signal) - window) // factor + 1, 0)
        self._signal = signal[count * factor :]
        if count == 0:
            return np.zeros(0, np.int16)

        phases = signal[: (count + blocks - 1) * factor].reshape(-1, factor).T.copy()
        output = np.correlate(phases[0], self._phases[0], 'valid')
        for phase in range(1, factor):
            output += np.correlate(phases[phase], self._phases[phase], 'valid')
        _ = np.clip(output, -32768, 32767, out=output)
        return np.rint(output, out=output).astype(np.int16)


def _low_pass(factor: int) -> NDArray[np.float32]:
    """The taps of a Kaiser-windowed sinc cut at the output's Nyquist frequency."""
    transition = math.pi * (_STOPBAND - _PASSBAND) / factor
    beta = 0.1102 * (_DESIGN_ATTENUATION_DB - 8.7)
    length = math.ceil((_DESIGN_ATTENUATION_DB - 7.95) / (2.285 * transition)) + 1
    # odd, for a whole-sample delay
    length += 1 - length % 2
    offsets = np.arange(length) - (length - 1) / 2
    taps = np.sinc(offsets / factor) / factor * np.kaiser(length, beta)
    return taps.astype(np.float32)


def _samples_of(data: webrtc.AudioData) -> NDArray[np.int16]:
    """One row per frame, one column per channel."""
    buffer = bytearray(data.allocation_size(_S16))
    data.copy_to(buffer, _S16)
    return np.frombuffer(buffer, np.int16).reshape(-1, data.number_of_channels)


def _remixed(samples: NDArray[np.int16], channels: int) -> NDArray[np.int16]:
    """A mono mix, or the source's channels repeated or cut."""
    source_channels = int(samples.shape[1])
    if source_channels == channels:
        return samples
    if channels == 1:
        return samples.mean(axis=1, keepdims=True).astype(np.int16)
    picked = [min(channel, source_channels - 1) for channel in range(channels)]
    return samples[:, picked]


@dataclass
class _Write:
    audio: memoryview
    channels: int
    done: asyncio.Future[bool]
    offset: int = field(default=0)


class AudioPacer:
    """Sends 16-bit PCM on a generated track in 10 ms frames at real time; a write returns once it's sent.

    Args:
        sample_rate: The rate of the audio written.
        auto_silence: Whether silence is sent while nothing is written; without it, the track pauses.
    """

    def __init__(self, sample_rate: int, *, auto_silence: bool) -> None:
        self.track = webrtc.MediaStreamTrackGenerator('audio')
        self._writer = self.track.writable.get_writer()
        self._sample_rate = sample_rate
        self._frame_samples = sample_rate * SENT_AUDIO_FRAME_MS // 1000
        self._auto_silence = auto_silence

        self._writes: collections.deque[_Write] = collections.deque()
        self._written = asyncio.Event()
        self._silence_channels = 1
        self._samples_sent = 0
        self._interrupted = False
        # also closed once sending fails; stopped only by close()
        self._closed = False
        self._stopped = False
        self._task = asyncio.ensure_future(self._run())

    async def write(self, audio: bytes, channels: int) -> bool:
        """Sends audio after the audio written before it.

        Args:
            audio: Interleaved 16-bit samples at the pacer's rate.
            channels: The channels of the samples.

        Returns:
            Whether all of it was sent; :obj:`False` if the pacer closed first.
        """
        if self._closed:
            return False

        done: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._writes.append(_Write(memoryview(audio), channels, done))
        self._written.set()
        return await done

    def interrupt(self) -> None:
        """Stops catching up on a stall, since the pipeline dropped that audio."""
        self._interrupted = True

    async def close(self) -> None:
        """Stops sending and ends the track; writes waiting return :obj:`False`."""
        if self._stopped:
            return
        self._stopped = True
        self._closed = True

        _ = self._task.cancel()
        # unlike awaiting the task, doesn't raise its cancellation here
        _ = await asyncio.wait({self._task})
        self._end_writes()
        self._writer.release_lock()
        self.track.stop()

    async def _run(self) -> None:
        try:
            await self._pace()
        except Exception:  # ruff: ignore[blind-except]
            logger.exception('Sending audio failed, the bot is silent from now on')
            self._closed = True
            self._end_writes()

    async def _pace(self) -> None:
        loop = asyncio.get_running_loop()
        frame_secs = self._frame_samples / self._sample_rate
        next_time = loop.time()
        while True:
            if await self._wait_for_audio():
                next_time = loop.time()

            self._drop_abandoned_writes()
            if len(self._writes) > 0:
                next_time += await self._send_audio() / self._sample_rate
                if self._interrupted:
                    # the client would play out what's behind
                    self._interrupted = False
                    next_time = max(next_time, loop.time())
                next_time = self._caught_up(next_time, loop.time())
                # coarse timers wake late, and the next delay is shorter for it
                await asyncio.sleep(max(next_time - loop.time(), 0))
            elif self._auto_silence:
                await self._send_silence()
                # keeps up through late wakes, but isn't caught up on after a stall
                next_time = max(next_time + frame_secs, loop.time() - _SILENCE_SLACK_SECS)
                # a write during the silence starts at once
                if await self._written_within(next_time - loop.time()):
                    next_time = loop.time()

    @staticmethod
    def _caught_up(next_time: float, now: float) -> float:
        """The time of the next frame, behind now by no more than the pacer catches up."""
        if next_time >= now - _MAX_CATCH_UP_SECS:
            return next_time
        logger.debug(
            'Audio out fell {:.0f} ms behind, catching up the last {:.0f} ms',
            (now - next_time) * 1000,
            _MAX_CATCH_UP_SECS * 1000,
        )
        return now - _MAX_CATCH_UP_SECS

    def _end_writes(self) -> None:
        for write in self._writes:
            if not write.done.done():
                write.done.set_result(False)
        self._writes.clear()

    def _drop_abandoned_writes(self) -> None:
        """Drops the writes whose writers gave up, with the rest of their audio."""
        while len(self._writes) > 0 and self._writes[0].done.done():
            _ = self._writes.popleft()

    async def _wait_for_audio(self) -> bool:
        """Waits for a write unless silence fills the gaps; returns whether it waited."""
        if self._auto_silence or len(self._writes) > 0:
            return False
        self._written.clear()
        _ = await self._written.wait()
        return True

    async def _written_within(self, timeout: float) -> bool:
        """Waits up to a time for a write; returns whether one is there."""
        self._written.clear()
        self._drop_abandoned_writes()
        if len(self._writes) == 0 and timeout > 0:
            with contextlib.suppress(asyncio.TimeoutError):
                _ = await asyncio.wait_for(self._written.wait(), timeout)
            self._drop_abandoned_writes()
        return len(self._writes) > 0

    async def _send_silence(self) -> None:
        silence = bytes(self._frame_samples * self._silence_channels * _SAMPLE_BYTES)
        _ = await self._send(silence, self._silence_channels)

    async def _send_audio(self) -> int:
        """Sends up to a frame of the oldest write; returns the samples per channel sent."""
        write = self._writes[0]
        frame_bytes = self._frame_samples * write.channels * _SAMPLE_BYTES
        chunk = write.audio[write.offset : write.offset + frame_bytes]
        write.offset += frame_bytes
        self._silence_channels = write.channels
        sent = await self._send(chunk, write.channels)

        if write.offset >= len(write.audio):
            _ = self._writes.popleft()
            if not write.done.done():
                write.done.set_result(True)
        return sent

    async def _send(self, samples: bytes | memoryview, channels: int) -> int:
        frames = len(samples) // (channels * _SAMPLE_BYTES)
        if frames == 0:
            return 0

        init = webrtc.AudioDataInit(
            format='s16',
            sample_rate=self._sample_rate,
            number_of_frames=frames,
            number_of_channels=channels,
            timestamp=self._samples_sent * _MICROSECONDS // self._sample_rate,
            data=samples,
        )
        self._samples_sent += frames
        await self._writer.write(webrtc.AudioData(init))
        return frames


@dataclass(frozen=True)
class RgbImage:
    """An image of 3 bytes a pixel, row after row, and its width and height."""

    pixels: bytes
    size: tuple[int, int]


def video_image(frame: webrtc.VideoFrame) -> RgbImage:
    """The visible pixels of a frame as RGB, turned as it's shown.

    Args:
        frame: The frame, which stays open.

    Returns:
        The image.

    Raises:
        ValueError: If the frame is closed.
    """
    rect = frame.visible_rect
    if rect is None:
        msg = 'The frame is closed'
        raise ValueError(msg)
    width = int(rect.width)
    height = int(rect.height)

    rgbx = np.empty(frame.allocation_size(_RGBX), np.uint8)
    # the copy is done once copy_to returns
    _ = frame.copy_to(memoryview(rgbx), _RGBX).result()
    rgb = _oriented_rgb(rgbx.reshape(height, width, 4)[:, :, :3], frame)

    shown_height, shown_width = rgb.shape[:2]
    return RgbImage(rgb.tobytes(), (shown_width, shown_height))


def _oriented_rgb(rgb: NDArray[np.uint8], frame: webrtc.VideoFrame) -> NDArray[np.uint8]:
    """A camera may send pixels unturned and say how to turn them."""
    if frame.flip:
        rgb = rgb[:, ::-1]
    # a negative turn is clockwise
    return np.rot90(rgb, k=-(frame.rotation // 90))


class VideoWriter:
    """Sends RGB or RGBA images on a generated video track, as written."""

    def __init__(self) -> None:
        self._generator = webrtc.VideoTrackGenerator()
        self._writer = self._generator.writable.get_writer()
        self._start: float | None = None
        # the frame copies the pixels, so the buffer is reused
        self._rgbx: NDArray[np.uint8] | None = None
        self._closed = False

    @property
    def track(self) -> webrtc.MediaStreamTrack:
        """The track carrying the images."""
        return self._generator.track

    async def write(self, image: OutputImageRawFrame) -> bool:
        """Sends an image now.

        Args:
            image: ``RGB``, ``RGBA``, or no format for RGB.

        Returns:
            Whether it was sent: not once closed, or for another format or a size that doesn't fit.
        """
        if self._closed:
            return False
        width, height = image.size
        image_format = _IMAGE_FORMATS.get(image.format)
        if image_format is None or len(image.image) != width * height * image_format.pixel_bytes:
            logger.error('Not sending a {}x{} image of format {}', width, height, image.format)
            return False
        pixel_format = image_format.sent_as

        loop = asyncio.get_running_loop()
        if self._start is None:
            self._start = loop.time()
        timestamp = round((loop.time() - self._start) * _MICROSECONDS)

        init = webrtc.VideoFrameBufferInit(
            format=pixel_format, coded_width=width, coded_height=height, timestamp=timestamp
        )
        padded = pixel_format == webrtc.VideoPixelFormat.RGBX
        pixels = self._padded(image.image, width, height) if padded else image.image
        await self._writer.write(webrtc.VideoFrame(pixels, init))
        return True

    def close(self) -> None:
        """Ends the track."""
        self._closed = True
        self._writer.release_lock()
        self.track.stop()

    def _padded(self, rgb: bytes, width: int, height: int) -> NDArray[np.uint8]:
        """RGB pixels with a fourth byte each."""
        if self._rgbx is None or self._rgbx.shape != (height, width, 4):
            self._rgbx = np.full((height, width, 4), 255, np.uint8)
        self._rgbx[:, :, :3] = np.frombuffer(rgb, np.uint8).reshape(height, width, 3)
        return self._rgbx


def _retrieved(future: asyncio.Future[None]) -> None:
    if not future.cancelled():
        _ = future.exception()
