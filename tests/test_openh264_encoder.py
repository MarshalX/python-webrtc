#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The H.264 that OpenH264 sends, tapped by an encoded transform and checked with ffmpeg's own decoder."""

from __future__ import annotations

import functools
import json
import shutil

import pytest

from tests.helpers import run_isolated

WIDTH, HEIGHT = 320, 240

# sends ffmpeg's testsrc2 as H.264, records the encoded frames, then asks for a key frame and caps the bitrate
SCRIPT = """
import asyncio
import json
import math
import subprocess
import sys
import tempfile

import webrtc
from tests.helpers import connect

FFMPEG, FFPROBE = json.loads(sys.argv[1])
WIDTH, HEIGHT, RATE = 320, 240, 30
SOURCE_FRAMES = 300
SIZE = WIDTH * HEIGHT * 3 // 2
LUMA = WIDTH * HEIGHT
DECODED = 90
SAMPLES = range(10, DECODED, 10)


def psnr(a, b):
    mse = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
    return math.inf if mse == 0 else 10 * math.log10(255 * 255 / mse)


def h264():
    return [c for c in webrtc.RTCRtpSender.get_capabilities('video').codecs if c.mime_type == 'video/H264']


async def main():
    # the OS's H.264 (macOS), offered without OpenH264
    builtin = {c.sdp_fmtp_line for c in h264()}
    try:
        await webrtc.openh264.install()
    except RuntimeError as e:
        print(json.dumps({'skip': str(e)}))
        return

    source = subprocess.run(
        [FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={WIDTH}x{HEIGHT}:rate={RATE}',
         '-frames:v', str(SOURCE_FRAMES), '-pix_fmt', 'yuv420p', '-f', 'rawvideo', '-'],
        capture_output=True, check=True,
    ).stdout
    frame_of = lambda n: source[(n % SOURCE_FRAMES) * SIZE : (n % SOURCE_FRAMES + 1) * SIZE]

    loop = asyncio.get_running_loop()
    written = 0
    # (bytes, key frame, the source frames written by then, arrival time)
    encoded = []

    async def tap(event):
        reader = event.transformer.readable.get_reader()
        writer = event.transformer.writable.get_writer()
        while not (result := await reader.read()).done:
            frame = result.value
            encoded.append((bytes(frame.data), frame.type == webrtc.EncodedVideoChunkType.key, written, loop.time()))
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

    async def frames(count):
        target = len(encoded) + count
        while len(encoded) < target:
            await asyncio.sleep(0.01)

    async def bitrate(seconds):
        await asyncio.sleep(2)  # settle
        first = len(encoded)
        await asyncio.sleep(seconds)
        sent = encoded[first:]
        return sum(len(data) for data, *_ in sent) * 8 / (sent[-1][3] - sent[0][3])

    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    generator = webrtc.VideoTrackGenerator()
    sender = caller.add_track(generator.track)
    transceiver = next(t for t in caller.get_transceivers() if t.sender == sender)
    transceiver.set_codec_preferences([c for c in h264() if c.sdp_fmtp_line not in builtin])
    sender.transform = webrtc.RTCRtpScriptTransform(tap)

    stop = asyncio.Event()
    writing = asyncio.ensure_future(write(stop))
    await connect(caller, callee, 20)
    await asyncio.wait_for(frames(DECODED), 20)
    stream = encoded[:DECODED]

    keys_before = sum(key for _, key, *_ in encoded)
    options = webrtc.RTCSetParameterOptions(encoding_options=[webrtc.RTCEncodingOptions(key_frame=True)])
    await sender.set_parameters(sender.get_parameters(), options)
    requested_at = len(encoded)
    await asyncio.wait_for(frames(15), 20)
    keys_after = sum(key for _, key, *_ in encoded)
    first_key = next((i - requested_at for i, (_, key, *_) in enumerate(encoded) if i >= requested_at and key), None)

    parameters = sender.get_parameters()
    parameters.encodings[0].max_bitrate = 100_000
    await sender.set_parameters(parameters)
    capped = await bitrate(3)
    parameters = sender.get_parameters()
    parameters.encodings[0].max_bitrate = 2_000_000
    await sender.set_parameters(parameters)
    uncapped = await bitrate(3)

    stop.set()
    await writing
    caller.close()
    callee.close()

    with tempfile.TemporaryDirectory() as directory:
        path = f'{directory}/sent.h264'
        with open(path, 'wb') as file:
            file.write(b''.join(data for data, *_ in stream))
        probe = json.loads(subprocess.run(
            [FFPROBE, '-v', 'error', '-show_entries', 'stream=profile,width,height',
             '-of', 'json', path],
            capture_output=True, text=True, check=True,
        ).stdout)['streams'][0]
        decoded = subprocess.run(
            [FFMPEG, '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-'],
            capture_output=True, check=True,
        ).stdout

    count = len(decoded) // SIZE
    # the source of a sent frame is one of the last ones written before it was encoded
    values = []
    for i in SAMPLES:
        luma = decoded[i * SIZE : i * SIZE + LUMA]
        latest = stream[i][2]
        values.append(max(psnr(luma, frame_of(n)[:LUMA]) for n in range(max(0, latest - 8), latest + 1)))

    print(json.dumps({
        'profile': probe.get('profile'),
        'size': [probe.get('width'), probe.get('height')],
        'decoded': count,
        'sent': len(stream),
        'first_is_key': stream[0][1],
        'psnr': [min(v, 99.0) for v in values],
        'keys_before': keys_before,
        'keys_after': keys_after,
        'first_key_after_request': first_key,
        'capped': capped,
        'uncapped': uncapped,
    }))


asyncio.run(main())
"""


@functools.cache
def result() -> dict[str, object]:
    """Runs the script once for every test of the module."""
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if ffmpeg is None or ffprobe is None:
        return {'skip': 'no ffmpeg and ffprobe'}
    output = run_isolated(SCRIPT.replace('sys.argv[1]', repr(json.dumps([ffmpeg, ffprobe]))), timeout=180)
    parsed: dict[str, object] = json.loads(output.strip().splitlines()[-1])
    return parsed


@pytest.fixture
def sent() -> dict[str, object]:
    outcome = result()
    if 'skip' in outcome:
        pytest.skip(str(outcome['skip']))
    return outcome


def test_ffmpeg_decodes_what_openh264_sends(sent: dict[str, object]) -> None:
    """The stream is Constrained Baseline at its size, starts with a key frame, and every frame decodes."""
    assert sent['profile'] == 'Constrained Baseline'
    assert sent['size'] == [WIDTH, HEIGHT]
    assert sent['first_is_key'] is True
    assert sent['decoded'] == sent['sent']


def test_sent_frames_are_close_to_their_source(sent: dict[str, object]) -> None:
    psnr = sent['psnr']
    assert isinstance(psnr, list)
    # encoding loses some, a broken stream or a wrong frame loses far more
    assert min(psnr) > 30, psnr


def test_key_frame_on_request(sent: dict[str, object]) -> None:
    """set_parameters with key_frame makes the encoder send one within a few frames."""
    keys_before, keys_after = sent['keys_before'], sent['keys_after']
    assert isinstance(keys_before, int)
    assert isinstance(keys_after, int)
    assert keys_after > keys_before
    first = sent['first_key_after_request']
    assert isinstance(first, int)
    assert first < 10


def test_max_bitrate_caps_the_stream(sent: dict[str, object]) -> None:
    capped, uncapped = sent['capped'], sent['uncapped']
    assert isinstance(capped, float)
    assert isinstance(uncapped, float)
    assert capped < 100_000 * 1.3
    assert uncapped > capped * 2
