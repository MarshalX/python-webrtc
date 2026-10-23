#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""ffmpeg's testsrc2 sent as H.264, and the frames the encoder makes of it."""

from __future__ import annotations

import asyncio
import dataclasses
import math
import subprocess

import webrtc
from tests.timing import seconds

WIDTH = 320
HEIGHT = 240
RATE = 30
SOURCE_FRAMES = 300
SIZE = WIDTH * HEIGHT * 3 // 2
LUMA = WIDTH * HEIGHT


def psnr(a: bytes, b: bytes) -> float:
    mse = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
    if mse == 0:
        return math.inf
    return 10 * math.log10(255 * 255 / mse)


def nv12_of(i420: bytes) -> bytes:
    """The picture with its U and V planes interleaved."""
    chroma = LUMA // 4
    uv = bytearray(2 * chroma)
    uv[0::2] = i420[LUMA : LUMA + chroma]
    uv[1::2] = i420[LUMA + chroma :]
    return i420[:LUMA] + bytes(uv)


def h264_codecs() -> list[webrtc.RTCRtpCodec]:
    capabilities = webrtc.RTCRtpSender.get_capabilities('video')
    assert capabilities is not None
    return [c for c in capabilities.codecs if c.mime_type == 'video/H264']


@dataclasses.dataclass
class Encoded:
    data: bytes
    key: bool
    rtp_timestamp: int | None
    written: int
    time: float


class Recorder:
    def __init__(self, ffmpeg: str, format: webrtc.VideoPixelFormatValue = 'I420') -> None:
        self.source = subprocess.run(
            [
                ffmpeg,
                *('-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={WIDTH}x{HEIGHT}:rate={RATE}'),
                *('-frames:v', str(SOURCE_FRAMES), '-pix_fmt', 'yuv420p', '-f', 'rawvideo', '-'),
            ],
            capture_output=True,
            check=True,
        ).stdout
        self.format = format
        self.generator = webrtc.VideoTrackGenerator()
        self.written = 0
        self.encoded: list[Encoded] = []
        self._recorded = asyncio.Condition()

    def frame_of(self, n: int) -> bytes:
        start = (n % SOURCE_FRAMES) * SIZE
        return self.source[start : start + SIZE]

    def best_psnr(self, picture: bytes, written: int) -> float:
        """Of the luma, or of the whole I420 picture, against the source frame it's closest to."""
        # the source of a sent frame is one of the last ones written before it was encoded
        sources = range(max(0, written - 8), written + 1)
        return max(psnr(picture, self.frame_of(n)[: len(picture)]) for n in sources)

    async def tap(self, event: webrtc.RTCTransformEvent) -> None:
        loop = asyncio.get_running_loop()
        reader = event.transformer.readable.get_reader()
        writer = event.transformer.writable.get_writer()
        while not (result := await reader.read()).done:
            frame = result.value
            assert isinstance(frame, webrtc.RTCEncodedVideoFrame)
            encoded = Encoded(
                data=bytes(frame.data),
                key=frame.type == webrtc.EncodedVideoChunkType.key,
                rtp_timestamp=frame.get_metadata().rtp_timestamp,
                written=self.written,
                time=loop.time(),
            )
            async with self._recorded:
                self.encoded.append(encoded)
                self._recorded.notify_all()
            _ = writer.write(frame)

    async def write(self, *, stop: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        writer = self.generator.writable.get_writer()
        start = loop.time()
        while not stop.is_set():
            init = webrtc.VideoFrameBufferInit(
                format=self.format, coded_width=WIDTH, coded_height=HEIGHT, timestamp=self.written * 1_000_000 // RATE
            )
            source = self.frame_of(self.written)
            data = nv12_of(source) if self.format == 'NV12' else source
            await writer.write(webrtc.VideoFrame(data, init))
            self.written += 1
            await asyncio.sleep(max(0.0, start + self.written / RATE - loop.time()))

    async def frames(self, count: int) -> None:
        target = len(self.encoded) + count
        async with self._recorded:
            await self._recorded.wait_for(lambda: len(self.encoded) >= target)

    async def bitrate(self, duration: float) -> float:
        await asyncio.wait_for(self.frames(2 * RATE), seconds(20))
        first = len(self.encoded)
        await asyncio.wait_for(self.frames(round(duration * RATE)), seconds(20))

        sent = self.encoded[first:]
        bits = sum(len(e.data) for e in sent) * 8
        return bits / (sent[-1].time - sent[0].time)

    async def key_frame_on_request(self, sender: webrtc.RTCRtpSender) -> int | None:
        options = webrtc.RTCSetParameterOptions(encoding_options=[webrtc.RTCEncodingOptions(key_frame=True)])
        await sender.set_parameters(sender.get_parameters(), options)
        requested_at = len(self.encoded)
        await asyncio.wait_for(self.frames(15), seconds(20))

        for index, encoded in enumerate(self.encoded[requested_at:]):
            if encoded.key:
                return index
        return None
