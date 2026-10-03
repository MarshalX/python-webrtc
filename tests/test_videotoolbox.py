#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""H.264 of the OS's VideoToolbox, sent and received over a loopback call."""

from __future__ import annotations

import functools
import json
import shutil
import sys

import pytest

from tests.helpers import run_isolated

pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='macOS only')

WIDTH, HEIGHT = 320, 240

# sends ffmpeg's testsrc2 as H.264 of one profile, taps what is sent, and compares what arrives with its source
SCRIPT = """
import asyncio
import json
import math
import subprocess
import sys
import tempfile

import webrtc
from tests.helpers import connect, stats_of_type, wait_for_event

FFMPEG, FFPROBE, PROFILE = json.loads(sys.argv[1])
WIDTH, HEIGHT, RATE = 320, 240, 30
SOURCE_FRAMES = 300
SIZE = WIDTH * HEIGHT * 3 // 2
LUMA = WIDTH * HEIGHT
RECEIVED = 90
SAMPLES = range(10, RECEIVED, 10)


def psnr(a, b):
    mse = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
    return math.inf if mse == 0 else 10 * math.log10(255 * 255 / mse)


async def main():
    source = subprocess.run(
        [FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={WIDTH}x{HEIGHT}:rate={RATE}',
         '-frames:v', str(SOURCE_FRAMES), '-pix_fmt', 'yuv420p', '-f', 'rawvideo', '-'],
        capture_output=True, check=True,
    ).stdout
    frame_of = lambda n: source[(n % SOURCE_FRAMES) * SIZE : (n % SOURCE_FRAMES + 1) * SIZE]

    loop = asyncio.get_running_loop()
    written = 0
    # (bytes, key frame), and the source frames written by the time each RTP timestamp was encoded
    encoded, written_by = [], {}

    async def tap(event):
        reader = event.transformer.readable.get_reader()
        writer = event.transformer.writable.get_writer()
        while not (result := await reader.read()).done:
            frame = result.value
            encoded.append((bytes(frame.data), frame.type == webrtc.EncodedVideoChunkType.key))
            written_by[frame.get_metadata().rtp_timestamp] = written
            _ = writer.write(frame)

    async def write(stop):
        nonlocal written
        writer = generator.writable.get_writer()
        start = loop.time()
        while not stop.is_set():
            init = webrtc.VideoFrameBufferInit(
                format='I420', coded_width=WIDTH, coded_height=HEIGHT, timestamp=written * 1_000_000 // RATE
            )
            await writer.write(webrtc.VideoFrame(frame_of(written), init))
            written += 1
            await asyncio.sleep(max(0.0, start + written / RATE - loop.time()))

    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    generator = webrtc.VideoTrackGenerator()
    sender = caller.add_track(generator.track)
    transceiver = next(t for t in caller.get_transceivers() if t.sender == sender)
    transceiver.set_codec_preferences([
        c for c in webrtc.RTCRtpSender.get_capabilities('video').codecs
        if c.mime_type == 'video/H264' and f'profile-level-id={PROFILE}' in (c.sdp_fmtp_line or '')
    ])
    sender.transform = webrtc.RTCRtpScriptTransform(tap)
    track_event = wait_for_event(callee, 'track', 20)

    stop = asyncio.Event()
    writing = asyncio.ensure_future(write(stop))
    await connect(caller, callee, 20)
    track = (await track_event).track

    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=RECEIVED)
    ).readable.get_reader()
    sizes, lumas = set(), {}
    for i in range(RECEIVED):
        frame = (await asyncio.wait_for(reader.read(), 20)).value
        sizes.add(f'{frame.coded_width}x{frame.coded_height}')
        if i in SAMPLES:
            options = webrtc.VideoFrameCopyToOptions(format='I420')
            data = bytearray(frame.allocation_size(options))
            await frame.copy_to(data, options)
            lumas[i] = (frame.metadata().rtp_timestamp, bytes(data[:LUMA]))
        frame.close()
    await reader.cancel()

    options = webrtc.RTCSetParameterOptions(encoding_options=[webrtc.RTCEncodingOptions(key_frame=True)])
    await sender.set_parameters(sender.get_parameters(), options)
    requested_at = len(encoded)
    while len(encoded) < requested_at + 15:
        await asyncio.sleep(0.01)
    first_key = next((i - requested_at for i, (_, key) in enumerate(encoded) if i >= requested_at and key), None)

    outbound = next(s for s in stats_of_type(await caller.get_stats(), 'outbound-rtp') if s.kind == 'video')
    stats = await callee.get_stats()
    inbound = next(s for s in stats_of_type(stats, 'inbound-rtp') if s.kind == 'video')

    stop.set()
    await writing
    caller.close()
    callee.close()

    with tempfile.TemporaryDirectory() as directory:
        path = f'{directory}/sent.h264'
        with open(path, 'wb') as file:
            file.write(b''.join(data for data, _ in encoded))
        probe = json.loads(subprocess.run(
            [FFPROBE, '-v', 'error', '-show_entries', 'stream=profile,color_range', '-of', 'json', path],
            capture_output=True, text=True, check=True,
        ).stdout)['streams'][0]

    # the source of a received frame is one of the last ones written before it was encoded
    values = []
    for rtp_timestamp, luma in lumas.values():
        latest = written_by[rtp_timestamp]
        values.append(max(psnr(luma, frame_of(n)[:LUMA]) for n in range(max(0, latest - 8), latest + 1)))

    print(json.dumps({
        'codec': stats[inbound.codec_id].sdp_fmtp_line,
        'encoder': outbound.encoder_implementation,
        'decoder': inbound.decoder_implementation,
        'profile': probe.get('profile'),
        'range': probe.get('color_range'),
        'sizes': sorted(sizes),
        'first_is_key': encoded[0][1],
        'psnr': [min(v, 99.0) for v in values],
        'first_key_after_request': first_key,
    }))


asyncio.run(main())
"""


@functools.cache
def result(profile: str) -> dict[str, object]:
    """Runs the script once per profile."""
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if ffmpeg is None or ffprobe is None:
        return {'skip': 'no ffmpeg and ffprobe'}
    output = run_isolated(SCRIPT.replace('sys.argv[1]', repr(json.dumps([ffmpeg, ffprobe, profile]))), timeout=120)
    parsed: dict[str, object] = json.loads(output.strip().splitlines()[-1])
    return parsed


PROFILES = [
    # VideoToolbox encodes Constrained Baseline as Baseline, without the constraint flag in its SPS
    pytest.param('42e01f', 'Baseline', id='constrained-baseline'),
    pytest.param('640c1f', 'High', id='high'),
]


@pytest.mark.parametrize(('profile', 'name'), PROFILES)
def test_loopback(profile: str, name: str) -> None:
    """Both ends use VideoToolbox, the stream is in the negotiated profile and arrives close to its source."""
    sent = result(profile)
    if 'skip' in sent:
        pytest.skip(str(sent['skip']))

    assert f'profile-level-id={profile}' in str(sent['codec'])
    assert sent['encoder'] == 'VideoToolbox'
    assert sent['decoder'] == 'VideoToolbox'
    assert sent['profile'] == name
    # video range, as the frames are: a full-range flag makes players stretch them
    assert sent['range'] != 'pc'
    assert sent['sizes'] == [f'{WIDTH}x{HEIGHT}']
    assert sent['first_is_key'] is True
    psnr = sent['psnr']
    assert isinstance(psnr, list)
    # encoding loses some, a broken stream or a wrong frame loses far more
    assert min(psnr) > 30, psnr


@pytest.mark.parametrize('profile', ['42e01f', '640c1f'])
def test_key_frame_on_request(profile: str) -> None:
    sent = result(profile)
    if 'skip' in sent:
        pytest.skip(str(sent['skip']))

    first = sent['first_key_after_request']
    assert isinstance(first, int)
    assert first < 10
