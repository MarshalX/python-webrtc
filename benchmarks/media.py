#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Media through a connection in the same process: generated on one end, read with a processor on the other."""

import array
import asyncio
import contextlib
import gc
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import webrtc
from benchmarks.measure import LoopLag, Usage, percentile, slope_mb_per_minute
from tests.helpers import connect, rss_bytes, wait_for_event

# the frame number, drawn as bits in blocks of luma at the top left of each frame
BITS = 16
BLOCK = 16


@dataclass
class VideoResult:
    width: int
    height: int
    fps: float
    seconds: float
    sent: int = 0
    received: int = 0
    discarded: int = 0
    # compact, as a soak collects thousands
    latencies: array.array = field(default_factory=lambda: array.array('d'))
    lag_p95_ms: float = 0
    lag_max_ms: float = 0
    usage: Usage = field(default_factory=Usage)
    # (seconds, bytes) of the resident memory during the run
    rss: List[tuple] = field(default_factory=list)
    # the sizes of the frames received, as the encoder may scale them down
    sizes: Dict[tuple, int] = field(default_factory=dict)

    @property
    def delivered_fps(self) -> float:
        return self.received / self.seconds

    @property
    def latency_p50_ms(self) -> float:
        return percentile(self.latencies, 0.5) * 1000

    @property
    def latency_p95_ms(self) -> float:
        return percentile(self.latencies, 0.95) * 1000

    @property
    def rss_slope(self) -> float:
        return slope_mb_per_minute(self.rss)

    @property
    def rss_slope_second_half(self) -> float:
        """Once caches and pools of the process reached their size"""
        return slope_mb_per_minute(self.rss[len(self.rss) // 2 :])

    @property
    def received_sizes(self) -> str:
        return ', '.join(f'{w}x{h}' for (w, h), _ in sorted(self.sizes.items(), key=lambda item: -item[1]))


def _frames(width: int, height: int, count: int = 10) -> List[bytearray]:
    """I420 frames of a gradient with a bar moving across, so the encoder has motion to encode"""
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
        value = 235 if number >> bit & 1 else 16
        block = bytes([value]) * BLOCK
        for y in range(BLOCK):
            start = y * width + bit * BLOCK
            frame[start : start + BLOCK] = block


def _read_number(luma: bytes, stride: int) -> int:
    number = 0
    for bit in range(BITS):
        # the center of the block, away from the blur of compression at its edges
        samples = [luma[y * stride + bit * BLOCK + x] for y in range(5, 11) for x in range(5, 11)]
        if sum(samples) / len(samples) > 125:
            number |= 1 << bit
    return number


@contextlib.asynccontextmanager
async def _connection():
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    try:
        yield caller, callee
    finally:
        caller.close()
        callee.close()


async def _remote_track(caller, callee, track, max_bitrate: Optional[int] = None):
    sender = caller.add_track(track)
    track_event = wait_for_event(callee, 'track', 30)
    await connect(caller, callee, 30)
    if max_bitrate:
        parameters = sender.get_parameters()
        for encoding in parameters.encodings:
            encoding.max_bitrate = max_bitrate
        await sender.set_parameters(parameters)
    return (await track_event).track


async def _measure(result, processor, write, read, measuring, done, warmup, seconds, sample=None) -> LoopLag:
    """Runs the writer and the reader: warms up, measures for the seconds, then stops both"""
    writing, reading = asyncio.ensure_future(write()), asyncio.ensure_future(read())
    await asyncio.sleep(warmup)
    discarded = processor.discarded_frames
    gc.collect()
    sampling = asyncio.ensure_future(sample()) if sample else None
    with LoopLag() as lag:
        result.usage.start()
        measuring.set()
        await asyncio.sleep(seconds)
        measuring.clear()
        result.usage.stop()
    done.set()
    result.discarded = processor.discarded_frames - discarded
    await asyncio.wait_for(writing, 10)
    reading.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reading
    if sampling:
        await sampling
    return lag


async def video_loopback(
    width: int,
    height: int,
    fps: float = 30,
    seconds: float = 30,
    warmup: float = 3,
    consumer_delay: float = 0,
    max_buffer_size: int = 1,
    rss_every: Optional[float] = None,
) -> VideoResult:
    """Frames written to a generator at a steady rate, read from the processor of the remote track"""
    result = VideoResult(width, height, fps, seconds)
    frames = _frames(width, height)
    loop = asyncio.get_running_loop()
    sent_at: Dict[int, float] = {}
    measuring = asyncio.Event()
    done = asyncio.Event()

    async with _connection() as (caller, callee):
        generator = webrtc.VideoTrackGenerator()
        # enough for the size, so the encoder doesn't drop frames for bitrate
        remote = await _remote_track(caller, callee, generator.track, max_bitrate=int(width * height * fps * 0.2))
        processor = webrtc.MediaStreamTrackProcessor(remote, max_buffer_size=max_buffer_size)

        async def write():
            writer = generator.writable.get_writer()
            start = loop.time()
            number = 0
            while not done.is_set():
                frame = frames[number % len(frames)]
                _draw_number(frame, width, number)
                sent_at[number] = loop.time()
                # frames lost on the way are forgotten
                sent_at.pop(number - 300, None)
                if measuring.is_set():
                    result.sent += 1
                await writer.write(
                    webrtc.VideoFrame(frame, format='I420', coded_width=width, coded_height=height, timestamp=number)
                )
                number += 1
                await asyncio.sleep(max(0.0, start + number / fps - loop.time()))

        async def read():
            header = {'rect': {'x': 0, 'y': 0, 'width': BITS * BLOCK, 'height': BLOCK}}
            async for frame in processor.readable:
                now = loop.time()
                if measuring.is_set():
                    size = (frame.coded_width, frame.coded_height)
                    result.sizes[size] = result.sizes.get(size, 0) + 1
                luma = bytearray(frame.allocation_size(header))
                # synchronous, without the future of copy_to
                frame._copy_to(luma, header)
                frame.close()
                number = _read_number(luma, BITS * BLOCK)
                if measuring.is_set() and number in sent_at:
                    result.received += 1
                    result.latencies.append(now - sent_at.pop(number))
                if consumer_delay:
                    await asyncio.sleep(consumer_delay)
                if done.is_set():
                    break

        async def sample_rss():
            start = loop.time()
            while not done.is_set():
                result.rss.append((loop.time() - start, rss_bytes()))
                await asyncio.sleep(rss_every)

        sample = sample_rss if rss_every else None
        lag = await _measure(result, processor, write, read, measuring, done, warmup, seconds, sample)
        result.lag_p95_ms, result.lag_max_ms = lag.p95_ms, lag.max_ms
        generator.track.stop()
    return result


@dataclass
class AudioResult:
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
        return self.received / self.seconds


async def audio_loopback(channels: int = 2, seconds: float = 60, warmup: float = 2) -> AudioResult:
    """10 ms chunks of a 48 kHz sine written to a generator in real time, read from the remote processor"""
    result = AudioResult(channels, seconds)
    loop = asyncio.get_running_loop()
    measuring = asyncio.Event()
    done = asyncio.Event()
    chunk = array.array(
        'h', (int(8000 * math.sin(2 * math.pi * 440 * (i // channels) / 48000)) for i in range(480 * channels))
    ).tobytes()

    async with _connection() as (caller, callee):
        generator = webrtc.MediaStreamTrackGenerator('audio')
        remote = await _remote_track(caller, callee, generator)
        processor = webrtc.MediaStreamTrackProcessor(remote, max_buffer_size=50)

        async def write():
            writer = generator.writable.get_writer()
            start = loop.time()
            written = 0
            while not done.is_set():
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
                if measuring.is_set():
                    result.written += 1
                await asyncio.sleep(max(0.0, start + written / 100 - loop.time()))

        async def read():
            async for audio in processor.readable:
                if measuring.is_set():
                    result.received += 1
                    result.received_frames += audio.number_of_frames
                audio.close()
                if done.is_set():
                    break

        lag = await _measure(result, processor, write, read, measuring, done, warmup, seconds)
        result.lag_p95_ms = lag.p95_ms
        generator.stop()
    return result


@dataclass
class CopyResult:
    width: int
    height: int
    format: str
    milliseconds: float

    @property
    def megapixels_per_second(self) -> float:
        return self.width * self.height / (self.milliseconds / 1000) / 1e6


def copy_costs(sizes, formats=('I420', 'RGBA', 'BGRA'), budget: float = 1.0) -> List[CopyResult]:
    """How long VideoFrame.copy_to takes: a copy of the planes, or a conversion to RGB"""
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
                # the copy alone, without the future of copy_to
                frame._copy_to(destination, options)
                runs += 1
            results.append(CopyResult(width, height, format, (time.perf_counter() - start) / runs * 1000))
        frame.close()
    return results


def construct_cost(width: int, height: int, budget: float = 1.0) -> float:
    """How long creating a VideoFrame from a buffer takes, in milliseconds (it copies the pixels)"""
    data = bytes(width * height * 3 // 2)
    runs = 0
    start = time.perf_counter()
    while time.perf_counter() - start < budget:
        webrtc.VideoFrame(data, format='I420', coded_width=width, coded_height=height, timestamp=0).close()
        runs += 1
    return (time.perf_counter() - start) / runs * 1000
