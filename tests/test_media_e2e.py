#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Media through a connection: generated on one end, read with a processor on the other."""

from __future__ import annotations

import array
import asyncio
import math

import pytest

import webrtc
from tests.helpers import connect_track, write_video, writing

TIMEOUT = 20
WIDTH, HEIGHT = 320, 240


def solid_i420(y: int, u: int, v: int) -> bytes:
    chroma = (WIDTH // 2) * (HEIGHT // 2)
    return bytes([y] * (WIDTH * HEIGHT) + [u] * chroma + [v] * chroma)


async def write_sine(generator: webrtc.MediaStreamTrackGenerator, frequency: float, *, stop: asyncio.Event) -> None:
    """Writes a sine of 48 kHz mono in 10 ms frames, at the pace of real time."""
    writer = generator.writable.get_writer()
    loop = asyncio.get_running_loop()
    start = loop.time()
    written = 0
    while not stop.is_set():
        samples = array.array(
            'h', (int(12000 * math.sin(2 * math.pi * frequency * (written + i) / 48000)) for i in range(480))
        )
        audio = webrtc.AudioData(
            webrtc.AudioDataInit(
                format='s16',
                sample_rate=48000,
                number_of_frames=480,
                number_of_channels=1,
                timestamp=written * 1_000_000 // 48000,
                data=samples.tobytes(),
            )
        )
        await writer.write(audio)
        written += 480
        await asyncio.sleep(max(0.0, start + written / 48000 - loop.time()))


def dominant_frequency(samples: list[float], rate: int) -> float:
    """The frequency of a sine, from its rising zero crossings."""
    crossings = [i for i in range(1, len(samples)) if samples[i - 1] < 0 <= samples[i]]
    return (len(crossings) - 1) * rate / (crossings[-1] - crossings[0])


async def read_frames(
    reader: webrtc.ReadableStreamDefaultReader[webrtc.VideoFrame | webrtc.AudioData], count: int
) -> tuple[list[int], bytearray]:
    """Reads frames of the size, returns their timestamps and the last one in RGBA."""
    timestamps: list[int] = []
    for _ in range(count):
        frame = (await asyncio.wait_for(reader.read(), TIMEOUT)).value
        assert isinstance(frame, webrtc.VideoFrame)
        assert (frame.coded_width, frame.coded_height) == (WIDTH, HEIGHT)
        rtp_timestamp = frame.metadata().rtp_timestamp
        assert rtp_timestamp is not None
        assert rtp_timestamp > 0
        timestamps.append(frame.timestamp)
        rgba = bytearray(frame.allocation_size(webrtc.VideoFrameCopyToOptions(format='RGBA')))
        await frame.copy_to(rgba, webrtc.VideoFrameCopyToOptions(format='RGBA'))
        frame.close()
    return timestamps, rgba


@pytest.mark.asyncio
async def test_video_through_a_connection(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Frames of one color arrive in that color, at their size, with increasing timestamps."""
    generator = webrtc.VideoTrackGenerator()
    # pure red in BT.601 limited range
    async with writing(write_video, generator, solid_i420(81, 90, 240), (WIDTH, HEIGHT)):
        remote = await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
        reader = webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(remote, max_buffer_size=5)
        ).readable.get_reader()
        timestamps, rgba = await read_frames(reader, 10)
        await reader.cancel()
    generator.track.stop()

    center = (HEIGHT // 2 * WIDTH + WIDTH // 2) * 4
    r, g, b, a = rgba[center : center + 4]
    # encoding adds some noise
    assert r > 230
    assert g < 25
    assert b < 25
    assert a == 255
    assert timestamps == sorted(set(timestamps))


@pytest.mark.asyncio
async def test_audio_through_a_connection(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """A sine arrives as a sine of the same frequency, decoded at 48 kHz."""
    generator = webrtc.MediaStreamTrackGenerator('audio')
    async with writing(write_sine, generator, 440):
        remote = await connect_track(caller, callee, generator, timeout=TIMEOUT)
        reader = webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(remote, max_buffer_size=100)
        ).readable.get_reader()
        samples: list[float] = []
        for chunk in range(150):
            audio = (await asyncio.wait_for(reader.read(), TIMEOUT)).value
            assert isinstance(audio, webrtc.AudioData)
            assert audio.sample_rate == 48000
            plane = array.array('f', [0.0] * audio.number_of_frames)
            audio.copy_to(
                memoryview(plane).cast('B'), webrtc.AudioDataCopyToOptions(plane_index=0, format='f32-planar')
            )
            audio.close()
            # the first half second is the jitter buffer filling up
            if chunk >= 50:
                samples.extend(plane)
        await reader.cancel()
    generator.stop()

    assert max(samples) > 0.1, 'the sine arrived, not silence'
    assert abs(dominant_frequency(samples, 48000) - 440) < 5


@pytest.mark.asyncio
async def test_remote_track_end_closes_the_processor(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The processor of a remote track closes when the remote peer stops sending it."""
    generator = webrtc.VideoTrackGenerator()
    async with writing(write_video, generator, solid_i420(128, 128, 128), (WIDTH, HEIGHT)):
        remote = await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
        reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(remote)).readable.get_reader()
        frame = (await asyncio.wait_for(reader.read(), TIMEOUT)).value
        assert isinstance(frame, webrtc.VideoFrame)
        frame.close()
        callee.close()
        await asyncio.wait_for(reader.closed, TIMEOUT)
    generator.track.stop()
