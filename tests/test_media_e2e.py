#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Media through a connection: generated on one end, read with a processor on the other."""

from __future__ import annotations

import array
import asyncio
import gc
import math
import weakref
from typing import cast

import pytest

import webrtc
from tests.helpers import (
    CreatePC,
    available_outgoing_bitrate,
    connect,
    connect_track,
    wait_for_event,
    wait_until,
    write_video,
    writing,
)

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


async def sender_reports(pc: webrtc.RTCPeerConnection) -> int:
    report = await pc.get_stats()
    return sum(
        stats.reports_sent
        for stats in report.values()
        if isinstance(stats, webrtc.RTCRemoteOutboundRtpStreamStats) and stats.reports_sent is not None
    )


@pytest.mark.asyncio
async def test_relayed_video_outlasts_the_sender_reports(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, create_pc: CreatePC
) -> None:
    """A remote video track sent on another connection keeps sending once its RTCP sender reports arrive."""
    relay, sink = create_pc(), create_pc()
    generator = webrtc.VideoTrackGenerator()
    async with writing(write_video, generator, solid_i420(128, 128, 128), (WIDTH, HEIGHT)):
        remote = await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
        relayed = await connect_track(relay, sink, remote, timeout=TIMEOUT)
        reader = webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(relayed, max_buffer_size=5)
        ).readable.get_reader()
        deadline = asyncio.get_running_loop().time() + TIMEOUT
        # the second report gives the receiver an NTP estimate of the frames
        while await sender_reports(callee) < 2:
            assert asyncio.get_running_loop().time() < deadline, 'no RTCP sender reports arrived'
            for _ in range(10):
                cast('webrtc.VideoFrame', (await asyncio.wait_for(reader.read(), TIMEOUT)).value).close()
        # a second of frames past it
        for _ in range(30):
            cast('webrtc.VideoFrame', (await asyncio.wait_for(reader.read(), 1)).value).close()
        await reader.cancel()
    generator.track.stop()


@pytest.mark.asyncio
async def test_a_remote_video_track_has_one_sender_a_connection(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, create_pc: CreatePC
) -> None:
    """Adding a remote video track again is refused, also through a new wrapper of it."""
    generator = webrtc.VideoTrackGenerator()
    remote = await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
    relay = create_pc()
    clone = remote.clone()
    sender = relay.add_track(clone)
    with pytest.raises(webrtc.InvalidAccessError):
        relay.add_track(clone)

    wrapper = weakref.ref(clone)
    del clone
    _ = gc.collect()
    assert wrapper() is None
    again = sender.track
    assert again is not None
    with pytest.raises(webrtc.InvalidAccessError):
        relay.add_track(again)
    generator.track.stop()


#: frames read to check their size
FRAMES = 10


async def received_widths(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    preference: webrtc.RTCDegradationPreference,
) -> list[int]:
    """The widths of frames received of 640x480 video sent at 100 kbps, too low a bitrate for its size."""
    generator = webrtc.VideoTrackGenerator()
    init = webrtc.RTCRtpTransceiverInit(
        direction='sendonly', send_encodings=[webrtc.RTCRtpEncodingParameters(max_bitrate=100_000)]
    )
    sender = caller.add_transceiver(generator.track, init).sender
    parameters = sender.get_parameters()
    parameters.degradation_preference = preference
    await sender.set_parameters(parameters)
    received = wait_for_event(callee, 'track', TIMEOUT)
    await connect(caller, callee, TIMEOUT)
    # libwebrtc drops frames too large for the bitrate only if it knows the bitrate before the first frame
    await wait_until(lambda: available_outgoing_bitrate(caller), 'a bandwidth estimate', TIMEOUT)
    async with writing(write_video, generator, bytes(640 * 480 * 3 // 2), (640, 480)):
        event = await received
        assert isinstance(event, webrtc.RTCTrackEvent)
        reader = webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(event.track, max_buffer_size=5)
        ).readable.get_reader()
        widths: list[int] = []
        while len(widths) < FRAMES:
            frame = (await asyncio.wait_for(reader.read(), TIMEOUT)).value
            assert isinstance(frame, webrtc.VideoFrame)
            widths.append(frame.coded_width)
            frame.close()
        await reader.cancel()
    generator.track.stop()
    return widths


@pytest.mark.asyncio
async def test_a_generator_scales_down_for_the_encoder(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Under maintain-framerate, the source sends the smaller frames the encoder asks for at a low bitrate."""
    widths = await received_widths(caller, callee, preference=webrtc.RTCDegradationPreference.maintain_framerate)
    assert all(width < 640 for width in widths)


@pytest.mark.asyncio
async def test_a_generator_keeps_its_size_under_maintain_resolution(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    widths = await received_widths(caller, callee, preference=webrtc.RTCDegradationPreference.maintain_resolution)
    assert widths == [640] * FRAMES


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


@pytest.mark.asyncio
async def test_stopped_camera_track_stops_sending(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A stopped camera track stops sending camera frames."""
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=True))
    track = stream.get_video_tracks()[0]
    remote = await connect_track(caller, callee, track, timeout=TIMEOUT)
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(remote)).readable.get_reader()
    for _ in range(5):
        cast('webrtc.VideoFrame', (await asyncio.wait_for(reader.read(), TIMEOUT)).value).close()
    track.stop()
    await asyncio.sleep(1)
    drained = 0
    while drained < 100:
        try:
            cast('webrtc.VideoFrame', (await asyncio.wait_for(reader.read(), 0.5)).value).close()
        except asyncio.TimeoutError:
            break
        drained += 1
    assert drained < 100
