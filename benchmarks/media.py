#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Media through a connection in the same process: generated on one end, read with a processor on the other."""

from __future__ import annotations

import array
import asyncio
import contextlib
import gc
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

import webrtc
from benchmarks.measure import LoopLag, Usage, percentile, slope_mb_per_minute
from tests.helpers import connect, rss_bytes, wait_for_event

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Iterable, Sequence

# the frame number, drawn as bits in blocks of luma at the top left of each frame
BITS = 16
BLOCK = 16
LUMA_ONE, LUMA_ZERO, LUMA_THRESHOLD = 235, 16, 125


@dataclass
class VideoResult:
    """The frames sent and received, their latency, and what it cost."""

    width: int
    height: int
    fps: float
    seconds: float
    sent: int = 0
    received: int = 0
    discarded: int = 0
    # compact, as a soak collects thousands
    latencies: array.array[float] = field(default_factory=lambda: array.array('d'))
    lag_p95_ms: float = 0
    lag_max_ms: float = 0
    usage: Usage = field(default_factory=Usage)
    # (seconds, bytes) of the resident memory during the run
    rss: list[tuple[float, int]] = field(default_factory=list)
    # the sizes of the frames received, as the encoder may scale them down
    sizes: dict[tuple[int, int], int] = field(default_factory=dict)

    @property
    def delivered_fps(self) -> float:
        """The frames received per second while measuring."""
        return self.received / self.seconds

    @property
    def latency_p50_ms(self) -> float:
        """The median latency of a frame."""
        return percentile(self.latencies, 0.5) * 1000

    @property
    def latency_p95_ms(self) -> float:
        """The 95th percentile latency of a frame."""
        return percentile(self.latencies, 0.95) * 1000

    @property
    def rss_slope(self) -> float:
        """The trend of the resident memory, in MB per minute."""
        return slope_mb_per_minute(self.rss)

    @property
    def rss_slope_second_half(self) -> float:
        """Once caches and pools of the process reached their size."""
        return slope_mb_per_minute(self.rss[len(self.rss) // 2 :])

    @property
    def received_sizes(self) -> str:
        """The sizes of the frames received, the most frequent first."""
        return ', '.join(f'{w}x{h}' for (w, h), _ in sorted(self.sizes.items(), key=lambda item: -item[1]))


def _frames(width: int, height: int, count: int = 10) -> list[bytearray]:
    """I420 frames of a gradient with a bar moving across, so the encoder has motion to encode."""
    frames = []
    chroma = (width // 2) * (height // 2)
    row = bytes((x * 255 // width) for x in range(width))
    base = bytearray(row * height + bytes([128]) * (2 * chroma))
    bar = max(8, width // 16)
    for i in range(count):
        frame = bytearray(base)
        left = (i * width // count) % (width - bar)
        for y in range(height // 3, height // 3 + height // 4):
            frame[y * width + left : y * width + left + bar] = b'\xff' * bar
        frames.append(frame)
    return frames


def _draw_number(frame: bytearray, width: int, number: int) -> None:
    for bit in range(BITS):
        value = LUMA_ONE if number >> bit & 1 else LUMA_ZERO
        block = bytes([value]) * BLOCK
        for y in range(BLOCK):
            start = y * width + bit * BLOCK
            frame[start : start + BLOCK] = block


def _read_number(luma: bytes, stride: int) -> int:
    number = 0
    for bit in range(BITS):
        # the center of the block, away from the blur of compression at its edges
        samples = [luma[y * stride + bit * BLOCK + x] for y in range(5, 11) for x in range(5, 11)]
        if sum(samples) / len(samples) > LUMA_THRESHOLD:
            number |= 1 << bit
    return number


@contextlib.asynccontextmanager
async def _connection() -> AsyncIterator[tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]]:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    try:
        yield caller, callee
    finally:
        caller.close()
        callee.close()


async def _remote_track(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    track: webrtc.MediaStreamTrack,
    *,
    max_bitrate: int | None = None,
) -> webrtc.MediaStreamTrack:
    sender = caller.add_track(track)
    track_event = wait_for_event(callee, 'track', 30)
    await connect(caller, callee, 30)
    if max_bitrate:
        parameters = sender.get_parameters()
        for encoding in parameters.encodings:
            encoding.max_bitrate = max_bitrate
        await sender.set_parameters(parameters)
    return (await track_event).track


@dataclass
class _Phases:
    """A writer and a reader warm up, then count while measuring, then stop once done."""

    warmup: float
    seconds: float
    measuring: asyncio.Event = field(default_factory=asyncio.Event)
    done: asyncio.Event = field(default_factory=asyncio.Event)

    async def measure(
        self,
        result: VideoResult | AudioResult,
        processor: webrtc.MediaStreamTrackProcessor,
        *,
        write: Callable[[], Awaitable[None]],
        read: Callable[[], Awaitable[None]],
    ) -> LoopLag:
        """Runs the writer and the reader: warms up, measures for the seconds, then stops both."""
        writing, reading = asyncio.ensure_future(write()), asyncio.ensure_future(read())
        await asyncio.sleep(self.warmup)
        discarded = processor.discarded_frames
        gc.collect()
        with LoopLag() as lag:
            result.usage.start()
            self.measuring.set()
            await asyncio.sleep(self.seconds)
            self.measuring.clear()
            result.usage.stop()
        self.done.set()
        result.discarded = processor.discarded_frames - discarded
        await asyncio.wait_for(writing, 10)
        reading.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reading
        return lag


@dataclass
class VideoLoopback:
    """Frames written to a generator at a steady rate, read from the processor of the remote track."""

    width: int
    height: int
    fps: float = 30
    seconds: float = 30
    warmup: float = 3
    consumer_delay: float = 0
    max_buffer_size: int = 1
    rss_every: float | None = None

    async def run(self) -> VideoResult:
        """Runs the benchmark."""
        run = _VideoRun(self, VideoResult(self.width, self.height, self.fps, self.seconds))
        async with _connection() as (caller, callee):
            generator = webrtc.VideoTrackGenerator()
            # enough for the size, so the encoder doesn't drop frames for bitrate
            bitrate = int(self.width * self.height * self.fps * 0.2)
            remote = await _remote_track(caller, callee, generator.track, max_bitrate=bitrate)
            processor = webrtc.MediaStreamTrackProcessor(remote, max_buffer_size=self.max_buffer_size)
            sampling = asyncio.ensure_future(run.sample_rss(self.rss_every)) if self.rss_every else None
            lag = await run.phases.measure(
                run.result, processor, write=lambda: run.write(generator), read=lambda: run.read(processor)
            )
            if sampling:
                await sampling
            run.result.lag_p95_ms, run.result.lag_max_ms = lag.p95_ms, lag.max_ms
            generator.track.stop()
        return run.result


@dataclass
class _VideoRun:
    options: VideoLoopback
    result: VideoResult
    phases: _Phases = field(init=False)
    # when each frame number was written
    sent_at: dict[int, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.phases = _Phases(self.options.warmup, self.options.seconds)

    async def write(self, generator: webrtc.VideoTrackGenerator) -> None:
        width, height, fps = self.options.width, self.options.height, self.options.fps
        frames = _frames(width, height)
        writer = generator.writable.get_writer()
        loop = asyncio.get_running_loop()
        start = loop.time()
        number = 0
        while not self.phases.done.is_set():
            frame = frames[number % len(frames)]
            _draw_number(frame, width, number)
            self.sent_at[number] = loop.time()
            # frames lost on the way are forgotten
            self.sent_at.pop(number - 300, None)
            if self.phases.measuring.is_set():
                self.result.sent += 1
            await writer.write(
                webrtc.VideoFrame(frame, format='I420', coded_width=width, coded_height=height, timestamp=number)
            )
            number += 1
            await asyncio.sleep(max(0.0, start + number / fps - loop.time()))

    async def read(self, processor: webrtc.MediaStreamTrackProcessor) -> None:
        header = {'rect': {'x': 0, 'y': 0, 'width': BITS * BLOCK, 'height': BLOCK}}
        loop = asyncio.get_running_loop()
        async for frame in processor.readable:
            now = loop.time()
            luma = bytearray(frame.allocation_size(header))
            await frame.copy_to(luma, header)
            size = (frame.coded_width, frame.coded_height)
            frame.close()
            if self.phases.measuring.is_set():
                self._count(size, _read_number(luma, BITS * BLOCK), now)
            if self.options.consumer_delay:
                await asyncio.sleep(self.options.consumer_delay)
            if self.phases.done.is_set():
                break

    def _count(self, size: tuple[int, int], number: int, received_at: float) -> None:
        self.result.sizes[size] = self.result.sizes.get(size, 0) + 1
        if number in self.sent_at:
            self.result.received += 1
            self.result.latencies.append(received_at - self.sent_at.pop(number))

    async def sample_rss(self, every: float) -> None:
        await self.phases.measuring.wait()
        loop = asyncio.get_running_loop()
        start = loop.time()
        while not self.phases.done.is_set():
            self.result.rss.append((loop.time() - start, rss_bytes()))
            await asyncio.sleep(every)


@dataclass
class AudioResult:
    """The chunks written and received, and what it cost."""

    channels: int
    seconds: float
    written: int = 0
    received: int = 0
    received_frames: int = 0
    discarded: int = 0
    lag_p95_ms: float = 0
    usage: Usage = field(default_factory=Usage)

    @property
    def chunks_per_second(self) -> float:
        """The chunks received per second while measuring."""
        return self.received / self.seconds


async def audio_loopback(channels: int = 2, seconds: float = 60, warmup: float = 2) -> AudioResult:
    """10 ms chunks of a 48 kHz sine written to a generator in real time, read from the remote processor."""
    result = AudioResult(channels, seconds)
    loop = asyncio.get_running_loop()
    phases = _Phases(warmup, seconds)
    chunk = array.array(
        'h', (int(8000 * math.sin(2 * math.pi * 440 * (i // channels) / 48000)) for i in range(480 * channels))
    ).tobytes()

    async with _connection() as (caller, callee):
        generator = webrtc.MediaStreamTrackGenerator('audio')
        remote = await _remote_track(caller, callee, generator)
        processor = webrtc.MediaStreamTrackProcessor(remote, max_buffer_size=50)

        async def write() -> None:
            writer = generator.writable.get_writer()
            start = loop.time()
            written = 0
            while not phases.done.is_set():
                await writer.write(
                    webrtc.AudioData(
                        format='s16',
                        sample_rate=48000,
                        number_of_frames=480,
                        number_of_channels=channels,
                        timestamp=written * 10_000,
                        data=chunk,
                    )
                )
                written += 1
                if phases.measuring.is_set():
                    result.written += 1
                await asyncio.sleep(max(0.0, start + written / 100 - loop.time()))

        async def read() -> None:
            async for audio in processor.readable:
                if phases.measuring.is_set():
                    result.received += 1
                    result.received_frames += audio.number_of_frames
                audio.close()
                if phases.done.is_set():
                    break

        lag = await phases.measure(result, processor, write=write, read=read)
        result.lag_p95_ms = lag.p95_ms
        generator.stop()
    return result


@dataclass
class CopyResult:
    """The cost of a copy of a frame to a format."""

    width: int
    height: int
    format: str
    milliseconds: float

    @property
    def megapixels_per_second(self) -> float:
        """The throughput of the copy."""
        return self.width * self.height / (self.milliseconds / 1000) / 1e6


async def copy_costs(
    sizes: Iterable[tuple[int, int]], formats: Sequence[str] = ('I420', 'RGBA', 'BGRA'), budget: float = 1.0
) -> list[CopyResult]:
    """How long VideoFrame.copy_to takes: a copy of the planes, or a conversion to RGB."""
    results = []
    for width, height in sizes:
        chroma = (width // 2) * (height // 2)
        frame = webrtc.VideoFrame(
            bytes(width * height + 2 * chroma), format='I420', coded_width=width, coded_height=height, timestamp=0
        )
        for format in formats:
            options = {'format': format}
            destination = bytearray(frame.allocation_size(options))
            runs = 0
            start = time.perf_counter()
            while time.perf_counter() - start < budget:
                await frame.copy_to(destination, options)
                runs += 1
            results.append(CopyResult(width, height, format, (time.perf_counter() - start) / runs * 1000))
        frame.close()
    return results


def construct_cost(width: int, height: int, budget: float = 1.0) -> float:
    """How long creating a VideoFrame from a buffer takes, in milliseconds (it copies the pixels)."""
    data = bytes(width * height * 3 // 2)
    runs = 0
    start = time.perf_counter()
    while time.perf_counter() - start < budget:
        webrtc.VideoFrame(data, format='I420', coded_width=width, coded_height=height, timestamp=0).close()
        runs += 1
    return (time.perf_counter() - start) / runs * 1000
