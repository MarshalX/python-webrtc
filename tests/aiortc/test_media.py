#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""aiortc-shaped tracks, senders and stats over loopback."""

from __future__ import annotations

import asyncio
import concurrent.futures
import datetime as dt
import fractions
import threading
from typing import TYPE_CHECKING, cast

import av
import pytest
from typing_extensions import ParamSpec, TypeVar, override

import webrtc
from tests.helpers import wait_until
from tests.timing import seconds
from webrtc.aiortc import (
    AudioStreamTrack,
    MediaStreamTrack,
    RTCConfiguration,
    RTCInboundRtpStreamStats,
    RTCOutboundRtpStreamStats,
    RTCPeerConnection,
    RTCRtpCodecCapability,
    RTCRtpReceiver,
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
    from collections.abc import Callable
    from pathlib import Path

    from av.frame import Frame

_P = ParamSpec('_P')
_T = TypeVar('_T')

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


def new_pair() -> tuple[RTCPeerConnection, RTCPeerConnection]:
    """A caller and a callee gathering local candidates only."""
    return RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)


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
    caller, callee = new_pair()
    tracks = received_tracks(callee)
    try:
        caller.addTrack(VideoStreamTrack())
        caller.addTrack(AudioStreamTrack())
        await negotiate(caller, callee)
        video = await next_track(tracks)
        audio = await next_track(tracks)

        frames = [await recv_video(video) for _ in range(3)]
        chunks = [await recv_audio(audio) for _ in range(3)]

        assert [(f.format.name, f.width, f.height) for f in frames] == [('yuv420p', 640, 480)] * 3
        timestamps = [f.pts for f in frames if f.pts is not None]
        assert len(timestamps) == 3
        assert timestamps[0] == 0
        assert timestamps == sorted(timestamps)
        assert frames[0].time_base == fractions.Fraction(1, 90000)

        chunk_shapes = [(c.format.name, c.layout.name, c.sample_rate, c.samples) for c in chunks]
        assert chunk_shapes == [('s16', 'stereo', 48000, 960)] * 3
        assert [c.pts for c in chunks] == [0, 960, 1920]
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_relay_of_a_remote_track_stays_native() -> None:
    """A relayed remote track is sent on natively: no reader and no pump."""
    source, relay_in = new_pair()
    relay_out, sink = new_pair()
    incoming = received_tracks(relay_in)
    outgoing = received_tracks(sink)
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
    caller, callee = new_pair()
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


async def received_alone(track: MediaStreamTrack) -> tuple[RTCPeerConnection, RTCPeerConnection, RemoteStreamTrack]:
    """A caller sending the track, a callee and the track it receives."""
    caller, callee = new_pair()
    tracks = received_tracks(callee)
    caller.addTrack(track)
    await negotiate(caller, callee)
    return caller, callee, await next_track(tracks)


def only_receiver(pc: RTCPeerConnection) -> RTCRtpReceiver:
    receivers = pc.getReceivers()
    assert len(receivers) == 1
    return receivers[0]


@pytest.mark.asyncio
async def test_disabled_receiver_keeps_no_video() -> None:
    caller, callee, track = await received_alone(VideoStreamTrack())
    try:
        receiver = only_receiver(callee)
        before = await recv_video(track)

        receiver._enabled = False
        await asyncio.sleep(1)
        receiver._enabled = True
        after = await recv_video(track)

        assert before.pts is not None
        assert after.pts is not None
        assert after.pts - before.pts > 0.5 * 90000
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_disabled_receiver_keeps_no_audio() -> None:
    caller, callee, track = await received_alone(AudioStreamTrack())
    try:
        receiver = only_receiver(callee)
        before = await recv_audio(track)

        receiver._enabled = False
        await asyncio.sleep(1)
        receiver._enabled = True
        after = await recv_audio(track)

        # a second of audio is 50 frames
        assert track._queue.qsize() < 10
        assert before.pts is not None
        assert after.pts is not None
        assert after.pts - before.pts > 0.5 * before.sample_rate
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_audio_pts_skip_the_chunks_dropped_unread() -> None:
    caller, callee, track = await received_alone(AudioStreamTrack())
    try:
        before = await recv_audio(track)
        processor = track._processor
        assert processor is not None

        await wait_until(
            lambda: processor.discarded_frames >= rtcrtpreceiver._AUDIO_BUFFER, 'a second of audio dropped', TIMEOUT
        )
        after = await recv_audio(track)

        assert before.pts is not None
        assert after.pts is not None
        assert after.pts - before.pts > 0.5 * before.sample_rate
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_disabling_the_receiver_keeps_a_waiting_read() -> None:
    """A pending read gets the next frame, not the end of the track."""
    caller, callee, track = await received_alone(VideoStreamTrack())
    try:
        receiver = only_receiver(callee)
        reading = asyncio.ensure_future(track.recv())
        await asyncio.sleep(0)

        receiver._enabled = False
        frame = await asyncio.wait_for(reading, TIMEOUT)

        assert isinstance(frame, av.VideoFrame)
        assert track.readyState == 'live'
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_queue_drains_the_frames_nobody_read() -> None:
    caller, callee, track = await received_alone(VideoStreamTrack())
    try:
        first = await recv_video(track)
        await asyncio.sleep(0.5)
        queue = track._queue
        queued = queue.qsize()

        while not queue.empty():
            _ = queue.get_nowait()
            queue.task_done()
        latest = await recv_video(track)

        assert isinstance(queue, asyncio.Queue)
        assert queued >= 5
        assert first.pts is not None
        assert latest.pts is not None
        assert latest.pts - first.pts > 0.3 * 90000
    finally:
        await close(caller, callee)


def numbered_frame(number: int) -> webrtc.VideoFrame:
    """A 4x2 frame with its number in the luma."""
    init = webrtc.VideoFrameBufferInit(format='I420', coded_width=4, coded_height=2, timestamp=number * 1000)
    return webrtc.VideoFrame(bytes([number] * 8 + [128] * 4), init)


def frame_number(frame: Frame) -> int:
    assert isinstance(frame, av.VideoFrame)
    return bytes(frame.planes[0])[0]


def has_waiting_read(track: RemoteStreamTrack) -> bool:
    processor = track._processor
    source = processor._source if processor is not None else None
    controller = source._controller if source is not None else None
    return controller is not None and controller._has_pending_reads()


async def waiting_recv(track: RemoteStreamTrack) -> asyncio.Future[Frame]:
    """Starts recv() and returns once it waits on the reader."""
    reading = asyncio.ensure_future(track.recv())
    await wait_until(lambda: has_waiting_read(track), 'recv() to wait')
    return reading


@pytest.mark.asyncio
async def test_queue_size_keeps_the_frame_of_a_waiting_recv() -> None:
    generator = webrtc.VideoTrackGenerator()
    writer = generator.writable.get_writer()
    track = RemoteStreamTrack._of(generator.track, None)
    try:
        reading = await waiting_recv(track)

        # qsize() runs before the wakeup
        written = writer.write(numbered_frame(1))
        _ = track._queue.qsize()
        await written
        first = await asyncio.wait_for(reading, TIMEOUT)

        reading = await waiting_recv(track)
        processor = track._processor
        assert processor is not None
        assert processor._source is not None
        written = [writer.write(numbered_frame(2)), writer.write(numbered_frame(3))]
        processor._source.deliver()
        _ = track._queue.qsize()
        await asyncio.gather(*written)
        second = await asyncio.wait_for(reading, TIMEOUT)
        third = await asyncio.wait_for(track.recv(), TIMEOUT)

        assert [frame_number(first), frame_number(second), frame_number(third)] == [1, 2, 3]
    finally:
        track.stop()


@pytest.mark.asyncio
async def test_recv_timed_out_leaves_the_next_frame_to_the_next_recv() -> None:
    generator = webrtc.VideoTrackGenerator()
    writer = generator.writable.get_writer()
    track = RemoteStreamTrack._of(generator.track, None)
    try:
        reading = await waiting_recv(track)
        # what wait_for() does on its timeout
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading

        await writer.write(numbered_frame(1))
        await writer.write(numbered_frame(2))
        frame = await asyncio.wait_for(track.recv(), TIMEOUT)

        assert frame_number(frame) == 1
    finally:
        track.stop()


@pytest.mark.asyncio
async def test_recv_canceled_after_its_read_settled_keeps_the_frame() -> None:
    generator = webrtc.VideoTrackGenerator()
    writer = generator.writable.get_writer()
    track = RemoteStreamTrack._of(generator.track, None)
    try:
        reading = await waiting_recv(track)
        assert track._reader is not None
        request = track._reader._read_requests.popleft()

        # the timeout lands in the same loop turn as the frame
        request.set_result(webrtc.ReadableStreamReadResult(numbered_frame(1), done=False))
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading

        await writer.write(numbered_frame(2))
        frame = await asyncio.wait_for(track.recv(), TIMEOUT)

        assert frame_number(frame) == 1
    finally:
        track.stop()


def filled_chunk(value: int) -> webrtc.AudioData:
    """10 ms of 48 kHz stereo audio, every sample the value."""
    init = webrtc.AudioDataInit(
        format='s16',
        sample_rate=48000,
        number_of_frames=480,
        number_of_channels=2,
        timestamp=0,
        data=value.to_bytes(2, 'little') * 960,
    )
    return webrtc.AudioData(init)


def chunk_values(frame: Frame) -> list[int]:
    """The value of each 10 ms chunk of a frame of filled chunks."""
    assert isinstance(frame, av.AudioFrame)
    samples = bytes(frame.planes[0])
    chunk_size = 480 * 2 * 2
    return [int.from_bytes(samples[start : start + 2], 'little') for start in range(0, len(samples), chunk_size)]


@pytest.mark.asyncio
async def test_audio_drop_after_a_taken_chunk_cuts_after_it() -> None:
    generator = webrtc.MediaStreamTrackGenerator('audio')
    writer = generator.writable.get_writer()
    track = RemoteStreamTrack._of(generator, None)._clone(buffered=False)
    try:
        reading = await waiting_recv(track)
        processor = track._processor
        assert processor is not None
        assert processor._source is not None

        written = [writer.write(filled_chunk(1))]
        processor._source.deliver()
        # before recv() resumes: 2 is dropped for 3, the queue holding one chunk
        written += [writer.write(filled_chunk(2)), writer.write(filled_chunk(3))]
        await asyncio.gather(*written)
        assert processor.discarded_frames == 1
        await wait_until(lambda: reading.done() or has_waiting_read(track), 'recv() to take 3')
        if not reading.done():
            await writer.write(filled_chunk(4))
        frame = await asyncio.wait_for(reading, TIMEOUT)

        assert chunk_values(frame) == [3, 4]
    finally:
        track.stop()
        generator.stop()


async def relayed_call(relay: MediaRelay, source: MediaStreamTrack, pcs: list[RTCPeerConnection]) -> RTCRtpSender:
    """Sends a proxy of the source on a new connection, adding the connections to pcs."""
    caller, callee = new_pair()
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
    relay = MediaRelay()
    source = AudioStreamTrack()
    try:
        first = await relayed_call(relay, source, pcs)
        second = await relayed_call(relay, source, pcs)

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
    source, relay_in = new_pair()
    relay_out, sink = new_pair()
    incoming = received_tracks(relay_in)
    outgoing = received_tracks(sink)
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
    caller, callee = new_pair()
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
    caller, callee = new_pair()
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
    caller, callee = new_pair()
    tracks = received_tracks(callee)
    try:
        track = VideoStreamTrack()
        sender = caller.addTrack(track)
        await negotiate(caller, callee)
        _ = await recv_video(await next_track(tracks))

        sent = await caller.getStats()
        received = await callee.getStats()

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
    caller, callee = new_pair()
    tracks = received_tracks(callee)
    try:
        first = CountingTrack()
        second = CountingTrack()
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
    caller, callee = new_pair()
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
        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert others == []
    finally:
        await close(caller, callee)


class GatedExecutor(concurrent.futures.ThreadPoolExecutor):
    """Holds the next job, once armed, until released."""

    def __init__(self) -> None:
        super().__init__(max_workers=4)
        self.armed = False
        self.entered: concurrent.futures.Future[None] = concurrent.futures.Future()
        self.release = threading.Event()
        self.held: concurrent.futures.Future[object] | None = None

    @override
    def submit(self, fn: Callable[_P, _T], /, *args: _P.args, **kwargs: _P.kwargs) -> concurrent.futures.Future[_T]:
        if not self.armed:
            return super().submit(fn, *args, **kwargs)

        self.armed = False

        def gated() -> object:
            self.entered.set_result(None)
            _ = self.release.wait()
            return fn(*args, **kwargs)

        self.held = super().submit(gated)
        return cast('concurrent.futures.Future[_T]', self.held)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', ['replaceTrack', 'close'])
async def test_stopped_pump_closes_the_frame_it_was_converting(cancel: str) -> None:
    gate = GatedExecutor()
    asyncio.get_running_loop().set_default_executor(gate)
    caller, callee = new_pair()
    tracks = received_tracks(callee)
    try:
        sender = caller.addTrack(CountingTrack())
        await negotiate(caller, callee)
        remote = await next_track(tracks)
        _ = await recv_video(remote)

        gate.armed = True
        await asyncio.wrap_future(gate.entered)
        assert gate.held is not None
        converted = asyncio.wrap_future(gate.held)

        if cancel == 'replaceTrack':
            pump = sender._pump
            assert pump is not None
            sender.replaceTrack(None)
            _ = await asyncio.gather(pump, return_exceptions=True)
        else:
            await caller.close()

        gate.release.set()
        frame = await converted

        assert isinstance(frame, webrtc.VideoFrame)
        assert frame.format is None
    finally:
        gate.release.set()
        await close(caller, callee)


def write_media(path: Path) -> None:
    """Writes a second of blank video and silent audio."""
    with av.open(str(path), 'w', format='webm') as container:
        video = container.add_stream('libvpx', rate=30)
        video.width = 320
        video.height = 240
        video.pix_fmt = 'yuv420p'
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
    caller, callee = new_pair()
    tracks = received_tracks(callee)
    try:
        assert player.video is not None
        assert player.audio is not None
        caller.addTrack(player.video)
        caller.addTrack(player.audio)
        await negotiate(caller, callee)
        first = await next_track(tracks)
        second = await next_track(tracks)
        received = {track.kind: track for track in (first, second)}

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


def test_audio_pts_follow_the_clock_only_across_a_cut() -> None:
    frames = rtcrtpreceiver._AudioFrames('stereo', 48000)

    def chunk(timestamp: int) -> webrtc.AudioData:
        init = webrtc.AudioDataInit(
            format='s16',
            sample_rate=48000,
            number_of_frames=480,
            number_of_channels=2,
            timestamp=timestamp,
            data=bytes(1920),
        )
        return webrtc.AudioData(init)

    contiguous = [frame.pts for timestamp in (0, 12_000, 19_000, 31_000) for frame in frames.convert(chunk(timestamp))]
    frames.drop_partial()
    after_cut = [frame.pts for timestamp in (3_000_000, 3_010_000) for frame in frames.convert(chunk(timestamp))]

    assert contiguous == [0, 960]
    assert after_cut == [3 * 48000]


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
