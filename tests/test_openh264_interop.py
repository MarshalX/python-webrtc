#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""H.264 of other encoders, sent by ffmpeg over WHIP, decoded by OpenH264."""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
import sys

import pytest

from tests.helpers import run_isolated

WIDTH, HEIGHT, RATE = 320, 240, 30

# receives one WHIP stream, decodes it, and compares the luma of some frames with ffmpeg's rendering of the source
SCRIPT = """
import asyncio
import json
import math
import subprocess
import sys
import tempfile

import webrtc
from tests.helpers import stats_of_type, wait_for_ice_gathering_complete

ENCODER = json.loads(sys.argv[1])
WIDTH, HEIGHT, RATE = 320, 240, 30
SOURCE = f'testsrc2=size={WIDTH}x{HEIGHT}:rate={RATE}'
FRAMES = 90
SAMPLES = range(10, FRAMES, 10)
LUMA = WIDTH * HEIGHT


def patch_offer(sdp):
    # ffmpeg groups its rtx ssrc without an a=ssrc line for it, which libwebrtc rejects
    lines = sdp.split('\\r\\n')
    for line in list(lines):
        if line.startswith('a=ssrc-group:FID '):
            primary, rtx = line.split()[1:3]
            cname = next(l for l in lines if l.startswith(f'a=ssrc:{primary} cname:'))
            if not any(l.startswith(f'a=ssrc:{rtx} ') for l in lines):
                lines.insert(lines.index(cname) + 1, cname.replace(primary, rtx, 1))
    return '\\r\\n'.join(lines)


def loopback_only(sdp):
    # ffmpeg's WHIP client tries a single candidate
    return '\\r\\n'.join(
        l for l in sdp.split('\\r\\n') if not l.startswith('a=candidate') or (' udp ' in l and ' 127.0.0.1 ' in l)
    )


def psnr(a, b):
    mse = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
    return math.inf if mse == 0 else 10 * math.log10(255 * 255 / mse)


async def main():
    try:
        await webrtc.openh264.install()
    except RuntimeError as e:
        print(json.dumps({'skip': str(e)}))
        return

    pc = webrtc.RTCPeerConnection()
    received = asyncio.get_running_loop().create_future()

    @pc.on('track')
    def on_track(event):
        received.set_result(event.track)

    async def handle(reader, writer):
        head = (await reader.readuntil(b'\\r\\n\\r\\n')).decode()
        length = next((int(l.split(':')[1]) for l in head.split('\\r\\n') if l.lower().startswith('content-length')), 0)
        body = (await reader.readexactly(length)).decode()
        if head.startswith('POST'):
            await pc.set_remote_description(webrtc.RTCSessionDescriptionInit(type='offer', sdp=patch_offer(body)))
            await pc.set_local_description(await pc.create_answer())
            await wait_for_ice_gathering_complete(pc)
            answer = loopback_only(pc.local_description.sdp).encode()
            writer.write(
                b'HTTP/1.1 201 Created\\r\\nContent-Type: application/sdp\\r\\nLocation: /whip/1\\r\\n'
                + f'Content-Length: {len(answer)}\\r\\n\\r\\n'.encode() + answer
            )
        else:
            writer.write(b'HTTP/1.1 200 OK\\r\\nContent-Length: 0\\r\\n\\r\\n')
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    ffmpeg = await asyncio.create_subprocess_exec(
        'ffmpeg', '-v', 'error', '-re', '-f', 'lavfi', '-i', SOURCE, '-t', '10', *ENCODER, '-g', str(RATE),
        '-bf', '0', '-pix_fmt', 'yuv420p', '-f', 'whip', f'http://127.0.0.1:{port}/whip',
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )

    track = await asyncio.wait_for(received, 20)
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=FRAMES)
    ).readable.get_reader()
    sizes, timestamps, lumas = set(), [], {}
    for i in range(FRAMES):
        frame = (await asyncio.wait_for(reader.read(), 20)).value
        sizes.add(f'{frame.coded_width}x{frame.coded_height}')
        timestamps.append(frame.metadata().rtp_timestamp)
        if i in SAMPLES or i == 0:
            options = webrtc.VideoFrameCopyToOptions(format='I420')
            data = bytearray(frame.allocation_size(options))
            await frame.copy_to(data, options)
            lumas[i] = bytes(data[:LUMA])
        frame.close()
    await reader.cancel()

    stats = await pc.get_stats()
    inbound = next(s for s in stats_of_type(stats, 'inbound-rtp') if s.kind == 'video')
    codec = stats[inbound.codec_id]
    ffmpeg.kill()
    await ffmpeg.wait()
    pc.close()
    server.close()

    # the source frame of each decoded one, from its RTP timestamp; where the first one starts is searched
    with tempfile.NamedTemporaryFile(suffix='.yuv') as file:
        subprocess.run(
            ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', SOURCE, '-t', '12', '-pix_fmt', 'yuv420p', file.name],
            check=True,
        )
        reference = file.read()
    source = lambda n: reference[n * LUMA * 3 // 2 : n * LUMA * 3 // 2 + LUMA]
    start = max(range(2 * RATE), key=lambda n: psnr(lumas[0], source(n)))
    step = 90000 // RATE
    values = [psnr(lumas[i], source(start + (timestamps[i] - timestamps[0]) // step)) for i in SAMPLES]

    print(json.dumps({
        'codec': codec.mime_type,
        'fmtp': codec.sdp_fmtp_line,
        'decoder': inbound.decoder_implementation,
        'decoded': inbound.frames_decoded,
        'sizes': sorted(sizes),
        'psnr': [min(v, 99.0) for v in values],
    }))


asyncio.run(main())
"""


@functools.cache
def ffmpeg_encoders() -> str:
    """The encoders of the ffmpeg on PATH, empty without one that can publish over WHIP."""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        return ''

    def listing(kind: str) -> str:
        return subprocess.run([ffmpeg, '-hide_banner', kind], capture_output=True, text=True, check=False).stdout

    return listing('-encoders') if ' whip ' in listing('-muxers') else ''


CASES = [
    pytest.param(['-c:v', 'libx264', '-profile:v', 'baseline', '-tune', 'zerolatency'], '42', id='x264-baseline'),
    pytest.param(['-c:v', 'libx264', '-profile:v', 'main', '-tune', 'zerolatency'], '4d', id='x264-main'),
    pytest.param(['-c:v', 'libx264', '-profile:v', 'high', '-tune', 'zerolatency'], '64', id='x264-high'),
    pytest.param(
        ['-c:v', 'h264_videotoolbox', '-profile:v', 'high', '-realtime', '1', '-b:v', '2M'],
        '64',
        id='videotoolbox-high',
        marks=pytest.mark.skipif(sys.platform != 'darwin', reason='macOS only'),
    ),
]


@pytest.mark.parametrize(('encoder', 'profile'), CASES)
def test_decodes_h264_of_ffmpeg(encoder: list[str], profile: str) -> None:
    """A stream of another encoder in a profile arrives negotiated, decoded by OpenH264, close to its source."""
    if encoder[1] not in ffmpeg_encoders():
        pytest.skip(f'no ffmpeg with WHIP and {encoder[1]}')

    output = run_isolated(SCRIPT.replace('sys.argv[1]', repr(json.dumps(encoder))), timeout=120)
    result: dict[str, object] = json.loads(output.strip().splitlines()[-1])
    if 'skip' in result:
        pytest.skip(str(result['skip']))

    assert result['codec'] == 'video/H264'
    assert f'profile-level-id={profile}' in str(result['fmtp'])
    assert result['decoder'] == 'OpenH264'
    assert result['sizes'] == [f'{WIDTH}x{HEIGHT}']
    psnr = result['psnr']
    assert isinstance(psnr, list)
    # encoding loses some, a wrong decode or a misplaced frame loses far more
    assert min(psnr) > 35, psnr
