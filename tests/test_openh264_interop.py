#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""H.264 of other encoders, sent by ffmpeg over WHIP, decoded by OpenH264 (VideoToolbox on macOS)."""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import shutil
import subprocess
import sys

import pytest

import webrtc
from tests.h264 import HEIGHT, LUMA, RATE, WIDTH, psnr
from tests.helpers import stats_of_type, wait_for_ice_gathering_complete
from tests.isolation import isolated
from tests.timing import seconds

SOURCE = f'testsrc2=size={WIDTH}x{HEIGHT}:rate={RATE}'
FRAMES = 90
SAMPLES = range(10, FRAMES, 10)
#: The RTP clock rate of video
VIDEO_CLOCK = 90000


def _patch_offer(sdp: str) -> str:
    # ffmpeg groups its rtx ssrc without an a=ssrc line for it, which libwebrtc rejects
    lines = sdp.split('\r\n')
    for line in lines.copy():
        if not line.startswith('a=ssrc-group:FID '):
            continue

        primary, rtx = line.split()[1:3]
        cname = next(other for other in lines if other.startswith(f'a=ssrc:{primary} cname:'))
        if not any(other.startswith(f'a=ssrc:{rtx} ') for other in lines):
            lines.insert(lines.index(cname) + 1, cname.replace(primary, rtx, 1))

    return '\r\n'.join(lines)


def _is_loopback_udp(candidate: str) -> bool:
    return ' udp ' in candidate and ' 127.0.0.1 ' in candidate


def _loopback_only(sdp: str) -> str:
    # ffmpeg's WHIP client tries a single candidate
    lines = sdp.split('\r\n')
    return '\r\n'.join(line for line in lines if not line.startswith('a=candidate') or _is_loopback_udp(line))


def _content_length(head: str) -> int:
    fields = [line.split(':', 1) for line in head.split('\r\n')[1:] if ':' in line]
    return next((int(value) for name, value in fields if name.lower() == 'content-length'), 0)


def _created(answer: bytes) -> bytes:
    head = (
        'HTTP/1.1 201 Created\r\nContent-Type: application/sdp\r\nLocation: /whip/1\r\n'
        f'Content-Length: {len(answer)}\r\n\r\n'
    )
    return head.encode() + answer


class _WhipEndpoint:
    def __init__(self, pc: webrtc.RTCPeerConnection) -> None:
        self.pc = pc

    async def _answer(self, offer: str) -> bytes:
        patched = webrtc.RTCSessionDescriptionInit(type='offer', sdp=_patch_offer(offer))
        await self.pc.set_remote_description(patched)
        await self.pc.set_local_description(await self.pc.create_answer())
        await wait_for_ice_gathering_complete(self.pc)
        assert self.pc.local_description is not None
        return _loopback_only(self.pc.local_description.sdp).encode()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b'\r\n\r\n')).decode()
        body = (await reader.readexactly(_content_length(head))).decode()

        if head.startswith('POST'):
            writer.write(_created(await self._answer(body)))
        else:
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')
        await writer.drain()
        writer.close()


@dataclasses.dataclass
class _Arrived:
    sizes: set[str]
    rtp_timestamps: list[int | None]
    lumas: dict[int, bytes]


async def _luma(frame: webrtc.VideoFrame) -> bytes:
    options = webrtc.VideoFrameCopyToOptions(format='I420')
    data = bytearray(frame.allocation_size(options))
    await frame.copy_to(data, options)
    return bytes(data[:LUMA])


async def _arrived(track: webrtc.MediaStreamTrack) -> _Arrived:
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=FRAMES))
    reader = processor.readable.get_reader()
    arrived = _Arrived(set(), [], {})

    for i in range(FRAMES):
        frame = (await asyncio.wait_for(reader.read(), seconds(20))).value
        assert isinstance(frame, webrtc.VideoFrame)
        arrived.sizes.add(f'{frame.coded_width}x{frame.coded_height}')
        arrived.rtp_timestamps.append(frame.metadata().rtp_timestamp)
        if i in SAMPLES or i == 0:
            arrived.lumas[i] = await _luma(frame)
        frame.close()

    await reader.cancel()
    return arrived


def _psnrs(ffmpeg: str, arrived: _Arrived) -> list[float]:
    """The PSNR of each sampled frame against its source frame, found from its RTP timestamp."""
    generating = [ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', SOURCE, '-t', '12']
    generating += ['-pix_fmt', 'yuv420p', '-f', 'rawvideo', '-']
    reference = subprocess.run(generating, capture_output=True, check=True).stdout
    frame_size = LUMA * 3 // 2

    def source_luma(n: int) -> bytes:
        return reference[n * frame_size : n * frame_size + LUMA]

    # where the first frame starts in the source is searched for
    start = max(range(2 * RATE), key=lambda n: psnr(arrived.lumas[0], source_luma(n)))
    ticks_per_frame = VIDEO_CLOCK // RATE
    first = arrived.rtp_timestamps[0]
    assert first is not None

    values: list[float] = []
    for i in SAMPLES:
        timestamp = arrived.rtp_timestamps[i]
        assert timestamp is not None
        source = source_luma(start + (timestamp - first) // ticks_per_frame)
        values.append(min(psnr(arrived.lumas[i], source), 99.0))
    return values


@dataclasses.dataclass
class _Received:
    codec: str
    fmtp: str | None
    decoder: str | None
    sizes: list[str]
    psnr: list[float]


async def _decoder(pc: webrtc.RTCPeerConnection) -> tuple[webrtc.RTCCodecStats, str | None]:
    stats = await pc.get_stats()
    inbound = next(
        s
        for s in stats_of_type(stats, 'inbound-rtp')
        if isinstance(s, webrtc.RTCInboundRtpStreamStats) and s.kind == 'video'
    )
    assert inbound.codec_id is not None
    codec = stats[inbound.codec_id]
    assert isinstance(codec, webrtc.RTCCodecStats)
    return codec, inbound.decoder_implementation


async def _receive(ffmpeg: str, encoder: list[str]) -> _Received:
    try:
        await webrtc.openh264.install()
    except RuntimeError as e:
        pytest.skip(str(e))

    pc = webrtc.RTCPeerConnection()
    received: asyncio.Future[webrtc.MediaStreamTrack] = asyncio.get_running_loop().create_future()
    pc.on('track', lambda event: received.set_result(event.track))
    server = await asyncio.start_server(_WhipEndpoint(pc).handle, '127.0.0.1', 0)
    port: int = server.sockets[0].getsockname()[1]

    publishing = [ffmpeg, '-v', 'error', '-re', '-f', 'lavfi', '-i', SOURCE, '-t', '10', *encoder, '-g', str(RATE)]
    publishing += ['-bf', '0', '-pix_fmt', 'yuv420p', '-f', 'whip', f'http://127.0.0.1:{port}/whip']
    sending = await asyncio.create_subprocess_exec(
        *publishing, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )

    arrived = await _arrived(await asyncio.wait_for(received, seconds(20)))
    codec, decoder = await _decoder(pc)

    sending.kill()
    await sending.wait()
    pc.close()
    server.close()

    psnrs = _psnrs(ffmpeg, arrived)
    return _Received(codec.mime_type, codec.sdp_fmtp_line, decoder, sorted(arrived.sizes), psnrs)


@isolated(timeout=seconds(120))
def _received(ffmpeg: str, encoder: list[str]) -> _Received:
    return asyncio.run(_receive(ffmpeg, encoder))


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
    """A stream of another encoder in a profile arrives negotiated, decoded, close to its source."""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None or encoder[1] not in ffmpeg_encoders():
        pytest.skip(f'no ffmpeg with WHIP and {encoder[1]}')

    result = _received(ffmpeg, encoder)

    assert result.codec == 'video/H264'
    assert f'profile-level-id={profile}' in str(result.fmtp)
    assert result.decoder == ('VideoToolbox' if sys.platform == 'darwin' else 'OpenH264')
    assert result.sizes == [f'{WIDTH}x{HEIGHT}']
    # encoding loses some, a wrong decode or a misplaced frame loses far more
    assert min(result.psnr) > 35, result.psnr
