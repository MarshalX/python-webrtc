#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""aiortc-shaped tracks, senders and stats over loopback."""

from __future__ import annotations

import asyncio
import datetime as dt
import fractions
from typing import TYPE_CHECKING

import av
import pytest
from typing_extensions import override

import webrtc
from tests.timing import seconds
from webrtc.aiortc import (
    AudioStreamTrack,
    MediaStreamTrack,
    RTCConfiguration,
    RTCInboundRtpStreamStats,
    RTCOutboundRtpStreamStats,
    RTCPeerConnection,
    RTCRtpCodecCapability,
    RTCRtpSender,
    RTCSessionDescription,
    RTCStatsReport,
    RTCTransportStats,
    VideoStreamTrack,
    rtcrtpreceiver,
    rtcrtpsender,
)
from webrtc.aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRelay
from webrtc.aiortc.rtcrtpreceiver import RemoteStreamTrack

if TYPE_CHECKING:
    from pathlib import Path

TIMEOUT = seconds(10)
#: no STUN server, so gathering is local
CONFIGURATION = RTCConfiguration(iceServers=[])


class CountingTrack(VideoStreamTrack):
    def __init__(self) -> None:
        super().__init__()
        self.frames = 0
        self.read = asyncio.Event()

    @override
    async def recv(self) -> av.VideoFrame:
        self.frames += 1
        self.read.set()
        frame = await super().recv()
        assert isinstance(frame, av.VideoFrame)
        return frame.reformat(format='bgr24')


def local_description(pc: RTCPeerConnection) -> RTCSessionDescription:
    description = pc.localDescription
    assert description is not None
    return description


async def negotiate(caller: RTCPeerConnection, callee: RTCPeerConnection) -> None:
    await caller.setLocalDescription(await caller.createOffer())
    await callee.setRemoteDescription(local_description(caller))
    await callee.setLocalDescription(await callee.createAnswer())
    await caller.setRemoteDescription(local_description(callee))


def received_tracks(pc: RTCPeerConnection) -> asyncio.Queue[MediaStreamTrack]:
    tracks: asyncio.Queue[MediaStreamTrack] = asyncio.Queue()
    pc.on('track', tracks.put_nowait)
    return tracks


async def next_track(tracks: asyncio.Queue[MediaStreamTrack]) -> RemoteStreamTrack:
    track = await asyncio.wait_for(tracks.get(), TIMEOUT)
    assert isinstance(track, RemoteStreamTrack)
    return track


async def recv_video(track: MediaStreamTrack) -> av.VideoFrame:
    frame = await asyncio.wait_for(track.recv(), TIMEOUT)
    assert isinstance(frame, av.VideoFrame)
    return frame


async def recv_audio(track: MediaStreamTrack) -> av.AudioFrame:
    frame = await asyncio.wait_for(track.recv(), TIMEOUT)
    assert isinstance(frame, av.AudioFrame)
    return frame


async def close(*pcs: RTCPeerConnection) -> None:
    for pc in pcs:
        await pc.close()


@pytest.mark.asyncio
async def test_python_tracks_reach_the_remote() -> None:
    """Frames of recv() tracks arrive as aiortc's decoders give them."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        caller.addTrack(VideoStreamTrack())
        caller.addTrack(AudioStreamTrack())
        await negotiate(caller, callee)
        video, audio = await next_track(tracks), await next_track(tracks)

        frames = [await recv_video(video) for _ in range(3)]
        assert [(f.format.name, f.width, f.height) for f in frames] == [('yuv420p', 640, 480)] * 3
        timestamps = [f.pts for f in frames if f.pts is not None]
        assert len(timestamps) == 3
        assert timestamps[0] == 0
        assert timestamps == sorted(timestamps)
        assert frames[0].time_base == fractions.Fraction(1, 90000)

        chunks = [await recv_audio(audio) for _ in range(3)]
        assert [(c.format.name, c.layout.name, c.sample_rate, c.samples) for c in chunks] == [
            ('s16', 'stereo', 48000, 960)
        ] * 3
        assert [c.pts for c in chunks] == [0, 960, 1920]
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_relay_of_a_remote_track_stays_native() -> None:
    """A relayed remote track is sent on natively: no reader and no pump."""
    source, relay_in = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    relay_out, sink = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    incoming, outgoing = received_tracks(relay_in), received_tracks(sink)
    try:
        source.addTrack(VideoStreamTrack())
        await negotiate(source, relay_in)
        remote = await next_track(incoming)

        relayed = MediaRelay().subscribe(remote)
        sender = relay_out.addTrack(relayed)
        await negotiate(relay_out, sink)
        _ = await next_track(outgoing)

        assert isinstance(relayed, RemoteStreamTrack)
        assert relayed is not remote
        assert sender.track is relayed
        assert sender._native.track == relayed._native
        assert remote._reader is None
        assert relayed._reader is None
        assert sender._pump is None
    finally:
        await close(source, relay_in, relay_out, sink)


@pytest.mark.asyncio
async def test_unbuffered_relay_reads_the_latest_frame() -> None:
    """An unbuffered relay of a remote track skips the frames nobody read."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        caller.addTrack(VideoStreamTrack())
        await negotiate(caller, callee)
        latest = MediaRelay().subscribe(await next_track(tracks), buffered=False)
        first = await recv_video(latest)
        await asyncio.sleep(0.5)
        second = await recv_video(latest)

        assert first.pts is not None
        assert second.pts is not None
        assert second.pts - first.pts > 0.3 * 90000
    finally:
        await close(caller, callee)


async def relayed_call(relay: MediaRelay, source: MediaStreamTrack, pcs: list[RTCPeerConnection]) -> RTCRtpSender:
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    pcs += [caller, callee]
    tracks = received_tracks(callee)
    sender = caller.addTrack(relay.subscribe(source))
    await negotiate(caller, callee)
    _ = await recv_audio(await next_track(tracks))
    return sender


@pytest.mark.asyncio
async def test_relay_of_a_python_track_pumps_once() -> None:
    """The proxies of a relayed Python track share one pump, and each can stop alone."""
    pcs: list[RTCPeerConnection] = []
    relay, source = MediaRelay(), AudioStreamTrack()
    try:
        first, second = [await relayed_call(relay, source, pcs) for _ in range(2)]
        shared = first._relayed
        assert shared is not None
        assert second._relayed is shared
        assert first._pump is None
        pump = shared._pump
        assert pump is not None

        stopped = first.track
        assert stopped is not None
        stopped.stop()
        assert first.track is None
        assert second._relayed is shared
        assert not pump.done()

        await close(*pcs)
        assert pump.done()
        assert source.readyState == 'live'
    finally:
        await close(*pcs)


@pytest.mark.asyncio
async def test_native_relay_carries_video() -> None:
    """A remote video track sent on another connection carries its frames."""
    source, relay_in = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    relay_out, sink = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    incoming, outgoing = received_tracks(relay_in), received_tracks(sink)
    try:
        source.addTrack(VideoStreamTrack())
        await negotiate(source, relay_in)
        relay_out.addTrack(await next_track(incoming))
        await negotiate(relay_out, sink)
        relayed = await next_track(outgoing)

        frames = [await asyncio.wait_for(relayed.recv(), seconds(1)) for _ in range(90)]

        assert len(frames) == 90
    finally:
        await close(source, relay_in, relay_out, sink)


@pytest.mark.asyncio
async def test_blackhole_of_a_remote_track_reads_nothing() -> None:
    """A blackhole leaves a remote track unread, and reads Python tracks."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        local = CountingTrack()
        caller.addTrack(VideoStreamTrack())
        await negotiate(caller, callee)
        remote = await next_track(tracks)
        blackhole = MediaBlackhole()
        blackhole.addTrack(remote)
        blackhole.addTrack(local)
        await blackhole.start()
        await asyncio.wait_for(local.read.wait(), TIMEOUT)
        await blackhole.stop()

        assert remote._reader is None
        assert remote.readyState == 'live'
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_codec_preferences() -> None:
    """A preferred codec is negotiated, and others raise aiortc's error."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        sender = caller.addTrack(AudioStreamTrack())
        transceiver = next(t for t in caller.getTransceivers() if t.sender == sender)
        pcmu = next(c for c in RTCRtpSender.getCapabilities('audio').codecs if c.mimeType == 'audio/PCMU')
        with pytest.raises(ValueError, match='Codec is not in capabilities'):
            transceiver.setCodecPreferences([RTCRtpCodecCapability('audio/bogus', 8000, 1)])
        with pytest.raises(ValueError, match='unknown media'):
            RTCRtpSender.getCapabilities('bogus')
        transceiver.setCodecPreferences([pcmu, pcmu])
        await negotiate(caller, callee)
        chunk = await recv_audio(await next_track(tracks))

        assert (chunk.layout.name, chunk.sample_rate, chunk.samples) == ('mono', 8000, 160)
        assert 'PCMU/8000' in local_description(callee).sdp
        assert 'opus' not in local_description(callee).sdp
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_stats() -> None:
    """getStats() gives aiortc's stats types only, with datetimes."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        track = VideoStreamTrack()
        sender = caller.addTrack(track)
        await negotiate(caller, callee)
        _ = await recv_video(await next_track(tracks))

        sent, received = await caller.getStats(), await callee.getStats()
        assert isinstance(sent, RTCStatsReport)
        assert {s.type for s in sent.values()} <= {'outbound-rtp', 'remote-inbound-rtp', 'transport'}
        assert all(isinstance(s.timestamp, dt.datetime) for s in [*sent.values(), *received.values()])
        outbound = next(s for s in sent.values() if isinstance(s, RTCOutboundRtpStreamStats))
        assert outbound.trackId == str(id(track))
        assert outbound.packetsSent > 0
        inbound = next(s for s in received.values() if isinstance(s, RTCInboundRtpStreamStats))
        assert inbound.packetsReceived > 0
        assert isinstance(inbound.jitter, int)
        assert any(isinstance(s, RTCTransportStats) for s in (await sender.getStats()).values())
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_replace_track() -> None:
    """replaceTrack() is sync, feeds the same sender and leaves the old track live."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        first, second = CountingTrack(), CountingTrack()
        sender = caller.addTrack(first)
        await negotiate(caller, callee)
        remote = await next_track(tracks)
        _ = await recv_video(remote)

        sender.replaceTrack(second)
        frames = second.frames
        _ = [await recv_video(remote) for _ in range(5)]

        assert sender.track is second
        assert second.frames > frames
        assert first.readyState == 'live'
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_close_stops_tracks_and_pumps() -> None:
    """close() stops the local tracks and their pumps, and ends the remote ones."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        local = VideoStreamTrack()
        sender = caller.addTrack(local)
        await negotiate(caller, callee)
        remote = await next_track(tracks)
        _ = await recv_video(remote)
        ended = asyncio.Event()
        remote.on('ended', ended.set)
        pump = sender._pump
        assert pump is not None

        await caller.close()
        await callee.close()

        assert pump.done()
        assert local.readyState == 'ended'
        assert remote.readyState == 'ended'
        assert ended.is_set()
        assert sender.track is None
        assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []
    finally:
        await close(caller, callee)


def write_media(path: Path) -> None:
    with av.open(str(path), 'w', format='webm') as container:
        video = container.add_stream('libvpx', rate=30)
        video.width, video.height, video.pix_fmt = 320, 240, 'yuv420p'
        audio = container.add_stream('libopus', rate=48000)
        audio.layout = 'stereo'
        for index in range(30):
            picture = av.VideoFrame(320, 240, 'yuv420p')
            for plane in picture.planes:
                plane.update(bytes(plane.buffer_size))
            picture.pts = index
            container.mux(video.encode(picture))
        for index in range(50):
            sound = av.AudioFrame(format='s16', layout='stereo', samples=960)
            sound.planes[0].update(bytes(sound.planes[0].buffer_size))
            sound.sample_rate = 48000
            sound.pts = index * 960
            container.mux(audio.encode(sound))
        container.mux(video.encode())
        container.mux(audio.encode())


@pytest.mark.asyncio
async def test_player_without_decoding(tmp_path: Path) -> None:
    """Packets of a player that doesn't decode are sent, each sender decoding them on its own."""
    path = tmp_path / 'media.webm'
    write_media(path)
    player = MediaPlayer(str(path), decode=False)
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        assert player.video is not None
        assert player.audio is not None
        caller.addTrack(player.video)
        caller.addTrack(player.audio)
        await negotiate(caller, callee)
        received = {track.kind: track for track in [await next_track(tracks), await next_track(tracks)]}

        assert (await recv_video(received['video'])).width == 320
        assert (await recv_audio(received['audio'])).sample_rate == 48000
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_full_range_frames_are_sent_in_limited_range() -> None:
    """A full-range frame is converted, not sent as limited-range I420."""
    frame = av.VideoFrame(16, 16, 'yuvj420p')
    for plane in frame.planes:
        plane.update(bytes(plane.buffer_size))
    luma = webrtc.VideoFrameCopyToOptions(format='I420')

    with rtcrtpsender._native_video_frame(frame) as native:
        pixels = bytearray(native.allocation_size(luma))
        _ = await native.copy_to(pixels, luma)

    assert pixels[0] == 16


def test_audio_of_many_channels_is_stereo() -> None:
    """Six-channel audio comes out as stereo frames."""
    frames = rtcrtpreceiver._AudioFrames('stereo', 48000)
    init = webrtc.AudioDataInit(
        format='s16', sample_rate=48000, number_of_frames=480, number_of_channels=6, timestamp=0, data=bytes(5760)
    )

    converted = [frame for _ in range(4) for frame in frames.convert(webrtc.AudioData(init))]

    assert converted != []
    assert all(isinstance(f, av.AudioFrame) and (f.layout.name, f.samples) == ('stereo', 960) for f in converted)


def test_mono_audio_is_copied_to_both_channels() -> None:
    """Mono chunks, as mono Opus decodes, come out as stereo frames with the same samples in each channel."""
    frames = rtcrtpreceiver._AudioFrames('stereo', 48000)
    samples = bytes(range(256)) * 3 + bytes(192)
    init = webrtc.AudioDataInit(
        format='s16', sample_rate=48000, number_of_frames=480, number_of_channels=1, timestamp=0, data=samples
    )

    [frame] = [frame for _ in range(2) for frame in frames.convert(webrtc.AudioData(init))]

    assert isinstance(frame, av.AudioFrame)
    assert (frame.layout.name, frame.samples) == ('stereo', 960)
    interleaved = memoryview(frame.planes[0]).cast('h')
    mono = memoryview(samples).cast('h')
    assert list(interleaved[0::2]) == list(interleaved[1::2]) == list(mono) * 2


def test_pts_keep_increasing_when_rtp_timestamps_start() -> None:
    """A frame without an RTP timestamp doesn't make the later ones negative."""
    timestamps = rtcrtpreceiver._VideoFrames()

    pts = [timestamps.map(90_000_000, rtp=False), timestamps.map(5000), timestamps.map(8000)]

    assert pts == [0, 1, 3001]


def test_track_added_before_a_loop_runs() -> None:
    """A track can be added before the loop runs, and it's sent once connected."""
    caller = RTCPeerConnection(CONFIGURATION)
    sender = caller.addTrack(VideoStreamTrack())

    async def run() -> None:
        callee = RTCPeerConnection(CONFIGURATION)
        tracks = received_tracks(callee)
        try:
            await negotiate(caller, callee)
            _ = await recv_video(await next_track(tracks))
            assert sender._pump is not None
        finally:
            await close(caller, callee)

    asyncio.run(run())
