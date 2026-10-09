#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""H.264 of the OS's VideoToolbox, sent and received over a loopback call."""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

import webrtc
from tests.h264 import HEIGHT, LUMA, WIDTH, Recorder, h264_codecs
from tests.helpers import connect, stats_of_type, wait_for_event, writing
from tests.isolation import isolated

pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='macOS only')

RECEIVED = 90
SAMPLES = range(10, RECEIVED, 10)


@dataclasses.dataclass
class _Arrived:
    sizes: set[str]
    lumas: list[tuple[int | None, bytes]]


async def _arrived(track: webrtc.MediaStreamTrack) -> _Arrived:
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=RECEIVED)
    ).readable.get_reader()
    arrived = _Arrived(set(), [])
    options = webrtc.VideoFrameCopyToOptions(format='I420')
    for i in range(RECEIVED):
        frame = (await asyncio.wait_for(reader.read(), 20)).value
        assert isinstance(frame, webrtc.VideoFrame)
        arrived.sizes.add(f'{frame.coded_width}x{frame.coded_height}')
        if i in SAMPLES:
            data = bytearray(frame.allocation_size(options))
            await frame.copy_to(data, options)
            arrived.lumas.append((frame.metadata().rtp_timestamp, bytes(data[:LUMA])))
        frame.close()
    await reader.cancel()
    return arrived


@dataclasses.dataclass
class _Implementations:
    codec: str | None
    encoder: str | None
    decoder: str | None


@dataclasses.dataclass
class _Sent:
    implementations: _Implementations
    profile: object
    range: object
    sizes: list[str]
    first_is_key: bool
    psnr: list[float]
    first_key_after_request: int | None


async def _implementations(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> _Implementations:
    outbound = next(
        s
        for s in stats_of_type(await caller.get_stats(), 'outbound-rtp')
        if isinstance(s, webrtc.RTCOutboundRtpStreamStats) and s.kind == 'video'
    )
    stats = await callee.get_stats()
    inbound = next(
        s
        for s in stats_of_type(stats, 'inbound-rtp')
        if isinstance(s, webrtc.RTCInboundRtpStreamStats) and s.kind == 'video'
    )
    assert inbound.codec_id is not None
    codec = stats[inbound.codec_id]
    assert isinstance(codec, webrtc.RTCCodecStats)
    return _Implementations(codec.sdp_fmtp_line, outbound.encoder_implementation, inbound.decoder_implementation)


def _track(event: webrtc.Event) -> webrtc.MediaStreamTrack:
    assert isinstance(event, webrtc.RTCTrackEvent)
    return event.track


def _videotoolbox_sender(caller: webrtc.RTCPeerConnection, recorder: Recorder, profile: str) -> webrtc.RTCRtpSender:
    sender = caller.add_track(recorder.generator.track)
    transceiver = next(t for t in caller.get_transceivers() if t.sender == sender)
    fmtp = f'profile-level-id={profile}'
    transceiver.set_codec_preferences([
        c for c in h264_codecs() if c.sdp_fmtp_line is not None and fmtp in c.sdp_fmtp_line
    ])
    sender.transform = webrtc.RTCRtpScriptTransform(recorder.tap)
    return sender


def _psnrs(recorder: Recorder, arrived: _Arrived) -> list[float]:
    # the source of a received frame is one of the last ones written before it was encoded
    written_by = {e.rtp_timestamp: e.written for e in recorder.encoded}
    return [min(recorder.best_psnr(luma, written_by[timestamp]), 99.0) for timestamp, luma in arrived.lumas]


def _probe(ffprobe: str, stream: bytes) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / 'sent.h264'
        path.write_bytes(stream)
        shown = ['-show_entries', 'stream=profile,color_range', '-of', 'json']
        probed = subprocess.run([ffprobe, '-v', 'error', *shown, path], capture_output=True, text=True, check=True)
    probe: dict[str, object] = json.loads(probed.stdout)['streams'][0]
    return probe


async def _send(ffmpeg: str, ffprobe: str, profile: str) -> _Sent:
    recorder = Recorder(ffmpeg)
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    sender = _videotoolbox_sender(caller, recorder, profile)
    track_event = wait_for_event(callee, 'track', 20)
    async with writing(recorder.write):
        await connect(caller, callee, 20)
        arrived = await _arrived(_track(await track_event))
        first_key = await recorder.key_frame_on_request(sender)
        implementations = await _implementations(caller, callee)
    caller.close()
    callee.close()

    probe = _probe(ffprobe, b''.join(e.data for e in recorder.encoded))
    return _Sent(
        implementations=implementations,
        profile=probe.get('profile'),
        range=probe.get('color_range'),
        sizes=sorted(arrived.sizes),
        first_is_key=recorder.encoded[0].key,
        psnr=_psnrs(recorder, arrived),
        first_key_after_request=first_key,
    )


@isolated(timeout=120)
def _sent(ffmpeg: str, ffprobe: str, profile: str) -> _Sent:
    return asyncio.run(_send(ffmpeg, ffprobe, profile))


@functools.cache
def result(profile: str) -> _Sent:
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if ffmpeg is None or ffprobe is None:
        pytest.skip('no ffmpeg and ffprobe')
    return _sent(ffmpeg, ffprobe, profile)


PROFILES = [
    # VideoToolbox encodes Constrained Baseline as Baseline, without the constraint flag in its SPS
    pytest.param('42e01f', 'Baseline', id='constrained-baseline'),
    pytest.param('640c1f', 'High', id='high'),
]


@pytest.mark.parametrize(('profile', 'name'), PROFILES)
def test_loopback(profile: str, name: str) -> None:
    """Both ends use VideoToolbox, the stream is in the negotiated profile and arrives close to its source."""
    sent = result(profile)

    assert f'profile-level-id={profile}' in str(sent.implementations.codec)
    assert sent.implementations.encoder == 'VideoToolbox'
    assert sent.implementations.decoder == 'VideoToolbox'
    assert sent.profile == name
    # video range, as the frames are: a full-range flag makes players stretch them
    assert sent.range != 'pc'
    assert sent.sizes == [f'{WIDTH}x{HEIGHT}']
    assert sent.first_is_key
    # encoding loses some, a broken stream or a wrong frame loses far more
    assert min(sent.psnr) > 30, sent.psnr


@pytest.mark.parametrize('profile', ['42e01f', '640c1f'])
def test_key_frame_on_request(profile: str) -> None:
    first = result(profile).first_key_after_request

    assert first is not None
    assert first < 10
