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
import contextlib
import dataclasses
import gc
import itertools
import math
import weakref
from typing import TYPE_CHECKING, cast

import pytest

import webrtc
from tests.helpers import (
    CreatePC,
    available_outgoing_bitrate,
    connect,
    connect_track,
    exchange_ice_candidates,
    exchange_offer,
    stats_of_type,
    wait_for_event,
    wait_until,
    wait_until_unmuted,
    write_video,
    writing,
)
from tests.timing import seconds

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

TIMEOUT = seconds(20)
#: no frame for this long means frames stopped; exact, as it defines the assertion
QUIET = 0.5
#: a send pause, seconds
PAUSE = 1.5
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
            cast('webrtc.VideoFrame', (await asyncio.wait_for(reader.read(), seconds(1))).value).close()
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
#: a size too large for the bitrate the frames are sent at, and the frames of it
LARGE = (640, 480)
LARGE_I420 = bytes(640 * 480 * 3 // 2)


async def send_at_low_bitrate(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    track: webrtc.MediaStreamTrack,
    *,
    preference: webrtc.RTCDegradationPreference,
) -> Awaitable[webrtc.Event]:
    """Sends the track at 100 kbps, too low a bitrate for 640x480, and returns the callee's coming track event."""
    init = webrtc.RTCRtpTransceiverInit(
        direction='sendonly', send_encodings=[webrtc.RTCRtpEncodingParameters(max_bitrate=100_000)]
    )
    sender = caller.add_transceiver(track, init).sender
    parameters = sender.get_parameters()
    parameters.degradation_preference = preference
    await sender.set_parameters(parameters)
    received = wait_for_event(callee, 'track', TIMEOUT)
    await connect(caller, callee, TIMEOUT)
    # libwebrtc drops frames too large for the bitrate only if it knows the bitrate before the first frame
    await wait_until(lambda: available_outgoing_bitrate(caller), 'a bandwidth estimate', TIMEOUT)
    return received


async def read_widths(track: webrtc.MediaStreamTrack, count: int) -> list[int]:
    """The widths of the next frames of the track."""
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=1)
    ).readable.get_reader()
    widths: list[int] = []
    while len(widths) < count:
        frame = (await asyncio.wait_for(reader.read(), TIMEOUT)).value
        assert isinstance(frame, webrtc.VideoFrame)
        widths.append(frame.coded_width)
        frame.close()
    await reader.cancel()
    return widths


async def received_track(received: Awaitable[webrtc.Event]) -> webrtc.MediaStreamTrack:
    event = await received
    assert isinstance(event, webrtc.RTCTrackEvent)
    return event.track


async def received_widths(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    preference: webrtc.RTCDegradationPreference,
) -> list[int]:
    """The widths of frames received of 640x480 video sent at a low bitrate."""
    generator = webrtc.VideoTrackGenerator()
    received = await send_at_low_bitrate(caller, callee, generator.track, preference=preference)
    async with writing(write_video, generator, LARGE_I420, LARGE):
        widths = await read_widths(await received_track(received), FRAMES)
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
async def test_a_sent_track_keeps_its_size_for_its_own_sinks(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A processor of a track and its settings see the frames of its source, not the smaller ones the encoder takes."""
    generator = webrtc.VideoTrackGenerator()
    received = await send_at_low_bitrate(
        caller, callee, generator.track, preference=webrtc.RTCDegradationPreference.maintain_framerate
    )
    async with writing(write_video, generator, LARGE_I420, LARGE):
        assert all(width < 640 for width in await read_widths(await received_track(received), FRAMES))
        local = await read_widths(generator.track, FRAMES)
        settings = generator.track.get_settings()
    generator.track.stop()

    assert local == [640] * FRAMES
    assert (settings.width, settings.height) == LARGE


@pytest.mark.asyncio
async def test_relayed_video_scales_down_for_the_encoder(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, create_pc: CreatePC
) -> None:
    """A remote track sent on at a low bitrate is sent in the smaller frames its encoder asks for."""
    relay, sink = create_pc(), create_pc()
    generator = webrtc.VideoTrackGenerator()
    async with writing(write_video, generator, LARGE_I420, LARGE):
        remote = await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
        await wait_until_unmuted(remote, TIMEOUT)
    # no frame reaches the relay's encoder before it knows its bitrate
    received = await send_at_low_bitrate(
        relay, sink, remote, preference=webrtc.RTCDegradationPreference.maintain_framerate
    )
    async with writing(write_video, generator, LARGE_I420, LARGE):
        widths = await read_widths(await received_track(received), FRAMES)
    generator.track.stop()

    assert all(width < 640 for width in widths)


#: a frame interval of the producer, in microseconds, the unit of frame timestamps
FRAME_US = 33_333
#: frames a producer writes at its pace first, a second of them, for the generator to learn its clock
PACED = 30
#: frames a producer that fell behind writes at once
BURST = 4


async def source_frames(pc: webrtc.RTCPeerConnection) -> int:
    """The frames the encoders of the connection took from their sources."""
    report = await pc.get_stats()
    sources = stats_of_type(report, 'media-source')
    return sum(s.frames for s in sources if isinstance(s, webrtc.RTCVideoSourceStats) and s.frames is not None)


def frame_writer(generator: webrtc.VideoTrackGenerator) -> Callable[[], Awaitable[None]]:
    """Writes the next frame of a producer to the generator, its timestamp a frame interval after the previous one."""
    writer = generator.writable.get_writer()
    data = solid_i420(128, 128, 128)
    timestamps = itertools.count(0, FRAME_US)

    async def write() -> None:
        init = webrtc.VideoFrameBufferInit(
            format='I420', coded_width=WIDTH, coded_height=HEIGHT, timestamp=next(timestamps)
        )
        await writer.write(webrtc.VideoFrame(data, init))

    return write


async def frames_taken(caller: webrtc.RTCPeerConnection, before: int, count: int) -> int:
    """The frames the encoder took since it had taken ``before``, once it took ``count`` or a while passed."""

    async def all_taken() -> bool:
        return await source_frames(caller) >= before + count

    with contextlib.suppress(TimeoutError):
        await wait_until(all_taken, 'the frames at the encoder', seconds(5))
    return await source_frames(caller) - before


@pytest.mark.asyncio
async def test_generator_frames_written_at_once_reach_the_encoder(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Two frames written back to back, a frame interval apart in their timestamps, are both encoded."""
    generator = webrtc.VideoTrackGenerator()
    write = frame_writer(generator)
    await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
    await write()
    await write()
    taken = await frames_taken(caller, 0, 2)
    generator.track.stop()

    assert taken == 2


@pytest.mark.asyncio
async def test_late_generator_frames_written_at_once_reach_the_encoder(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A producer that stalls, then writes the frames it owes at once, has none of them dropped as duplicates."""
    generator = webrtc.VideoTrackGenerator()
    write = frame_writer(generator)
    loop = asyncio.get_running_loop()
    await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
    start = loop.time()
    written = 0
    deadline = start + TIMEOUT
    while written < PACED or await source_frames(caller) == 0:
        assert loop.time() < deadline, 'no frame reached the encoder'
        await write()
        written += 1
        await asyncio.sleep(max(0.0, start + written * FRAME_US / 1e6 - loop.time()))
    # it falls behind by the burst, then catches up
    await asyncio.sleep(max(0.0, start + (written + BURST) * FRAME_US / 1e6 - loop.time()))
    before = await source_frames(caller)
    for _ in range(BURST):
        await write()
    taken = await frames_taken(caller, before, BURST)
    generator.track.stop()

    assert taken == BURST


#: the rids of three layers of 720p, lowest first, and their sizes
LAYERS = {'q': (320, 180), 'h': (640, 360), 'f': (1280, 720)}


@dataclasses.dataclass
class _Layer:
    codec: str | None
    size: tuple[int | None, int | None]


async def sent_layers(caller: webrtc.RTCPeerConnection) -> dict[str, _Layer]:
    """The codec and frame size of each outbound layer that encoded a frame."""
    report = await caller.get_stats()
    layers: dict[str, _Layer] = {}
    for stats in stats_of_type(report, 'outbound-rtp'):
        assert isinstance(stats, webrtc.RTCOutboundRtpStreamStats)
        if stats.rid is None or stats.frames_encoded in {None, 0} or stats.codec_id is None:
            continue
        codec = report[stats.codec_id]
        assert isinstance(codec, webrtc.RTCCodecStats)
        layers[stats.rid] = _Layer(codec.mime_type, (stats.frame_width, stats.frame_height))
    return layers


async def send_simulcast(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    track: webrtc.MediaStreamTrack,
    *,
    mime_type: str,
) -> None:
    """Negotiates sending the track in the layers, in the codec only."""
    capabilities = webrtc.RTCRtpSender.get_capabilities('video')
    assert capabilities is not None
    codecs = [c for c in capabilities.codecs if c.mime_type == mime_type]
    if len(codecs) == 0:
        pytest.skip(f'no {mime_type} encoder')
    # without a scalability mode, libwebrtc sends VP9 and AV1 layers as one stream
    mode = 'L1T1' if mime_type in {'video/VP9', 'video/AV1'} else None
    encodings = [
        webrtc.RTCRtpEncodingParameters(rid=rid, scale_resolution_down_by=1280 / width, scalability_mode=mode)
        for rid, (width, _) in LAYERS.items()
    ]
    init = webrtc.RTCRtpTransceiverInit(direction='sendonly', send_encodings=encodings)
    transceiver = caller.add_transceiver(track, init)
    transceiver.set_codec_preferences(codecs)
    exchange_ice_candidates(caller, callee)
    await exchange_offer(caller, callee)
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    # libwebrtc doesn't announce receiving the layers by itself
    simulcast = ''.join(f'a=rid:{rid} recv\r\n' for rid in LAYERS) + f'a=simulcast:recv {";".join(LAYERS)}\r\n'
    await caller.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', answer.sdp + simulcast))
    parameters = transceiver.sender.get_parameters()
    # the start bitrate would make libwebrtc scale the frames down
    parameters.degradation_preference = 'maintain-resolution'
    await transceiver.sender.set_parameters(parameters)


@pytest.mark.asyncio
@pytest.mark.parametrize('mime_type', ['video/VP8', 'video/VP9', 'video/AV1', 'video/H264'])
async def test_simulcast_sends_every_layer(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, mime_type: str
) -> None:
    """Each rid is a stream of the negotiated codec, at its scaled size, whether or not its encoder does simulcast."""
    generator = webrtc.VideoTrackGenerator()
    await send_simulcast(caller, callee, generator.track, mime_type=mime_type)

    async def all_sent() -> bool:
        return len(await sent_layers(caller)) == len(LAYERS)

    async with writing(write_video, generator, bytes(1280 * 720 * 3 // 2), (1280, 720)):
        with contextlib.suppress(TimeoutError):
            await wait_until(all_sent, 'every layer encoded', TIMEOUT)
        layers = await sent_layers(caller)
    generator.track.stop()

    assert layers == {rid: _Layer(mime_type, size) for rid, size in LAYERS.items()}


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


async def inbound_rtp(receiver: webrtc.RTCRtpReceiver) -> webrtc.RTCInboundRtpStreamStats | None:
    stats = stats_of_type(await receiver.get_stats(), 'inbound-rtp')
    if len(stats) == 0:
        return None
    assert isinstance(stats[0], webrtc.RTCInboundRtpStreamStats)
    return stats[0]


async def packets_received(receiver: webrtc.RTCRtpReceiver) -> int:
    stats = await inbound_rtp(receiver)
    return 0 if stats is None or stats.packets_received is None else stats.packets_received


async def set_active(sender: webrtc.RTCRtpSender, *, active: bool) -> None:
    parameters = sender.get_parameters()
    parameters.encodings[0].active = active
    await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_audio_resumes_after_a_send_pause(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """After a pause the RTP timestamps skip ahead with the capture time, so the jitter doesn't jump."""
    generator = webrtc.MediaStreamTrackGenerator('audio')
    async with writing(write_sine, generator, 440):
        await connect_track(caller, callee, generator, timeout=TIMEOUT)
        (sender,) = caller.get_senders()
        (receiver,) = callee.get_receivers()

        async def arriving() -> bool:
            return await packets_received(receiver) > 0

        await wait_until(arriving, 'packets to arrive', TIMEOUT)
        # stops and restarts the send stream, unlike replacing the track
        await set_active(sender, active=False)
        await asyncio.sleep(PAUSE)
        paused = await packets_received(receiver)
        await set_active(sender, active=True)

        # RFC 3550 jitter takes 1/16 of a transit jump: PAUSE / 16 without the skip, before it decays
        jitters: list[float] = []

        async def resumed() -> bool:
            stats = await inbound_rtp(receiver)
            assert stats is not None
            assert stats.jitter is not None
            assert stats.packets_received is not None
            jitters.append(stats.jitter)
            # half a second of 20 ms packets
            return stats.packets_received > paused + 25

        await wait_until(resumed, 'packets after the pause', TIMEOUT)
        assert max(jitters) < PAUSE / 16 / 2, jitters
    generator.stop()


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
            cast('webrtc.VideoFrame', (await asyncio.wait_for(reader.read(), QUIET)).value).close()
        except asyncio.TimeoutError:
            break
        drained += 1
    assert drained < 100
