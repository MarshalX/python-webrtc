#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#


"""The tone, the video and the codecs of python-webrtc."""

from __future__ import annotations

import asyncio

import webrtc
from benchmarks.drivers import frames
from benchmarks.protocol import now

AUDIO_RATE = 48_000
AUDIO_FRAMES = 960
#: the length of a 20 ms chunk of the tone, in microseconds
CHUNK_US = 20_000
#: the MIME type and the parts of the fmtp line of each codec name of the protocol
CODECS: dict[str, tuple[str, tuple[str, ...]]] = {
    'VP8': ('video/VP8', ()),
    'VP9': ('video/VP9', ('profile-id=0',)),
    'AV1': ('video/AV1', ()),
    'H264': ('video/H264', ('profile-level-id=42e01f', 'packetization-mode=1')),
    'H264-High': ('video/H264', ('profile-level-id=64001f', 'packetization-mode=1')),
}


class ToneSource:
    """A tone, 20 ms chunks of 48 kHz mono written in real time to a generator: one track for every connection."""

    def __init__(self) -> None:
        self.track = webrtc.MediaStreamTrackGenerator('audio')
        self._task = asyncio.ensure_future(self._write())

    async def _write(self) -> None:
        writer = self.track.writable.get_writer()
        loop = asyncio.get_running_loop()
        chunk = frames.tone(AUDIO_RATE, AUDIO_FRAMES)
        start = loop.time()
        written = 0

        while True:
            init = webrtc.AudioDataInit(
                format='s16',
                sample_rate=AUDIO_RATE,
                number_of_frames=AUDIO_FRAMES,
                number_of_channels=1,
                timestamp=written * CHUNK_US,
                data=chunk,
            )
            await writer.write(webrtc.AudioData(init))
            written += 1

            due = start + written * CHUNK_US / 1_000_000
            await asyncio.sleep(max(0.0, due - loop.time()))


class VideoSource:
    """Raw frames written in real time to a generator, in a loop, numbered if asked."""

    def __init__(self, raw: list[bytes], *, size: tuple[int, int], fps: float, numbered: bool) -> None:
        self.generator = webrtc.VideoTrackGenerator()
        self.tally = frames.Tally()
        self._task = asyncio.ensure_future(self._write(raw, size, fps, numbered=numbered))

    async def _write(self, raw: list[bytes], size: tuple[int, int], fps: float, *, numbered: bool) -> None:
        width, height = size
        writer = self.generator.writable.get_writer()
        loop = asyncio.get_running_loop()
        start = loop.time()
        count = 0

        while True:
            data = raw[count % len(raw)]
            if numbered:
                number = count % 2**frames.BITS
                data = frames.numbered(data, width, number)
                self.tally.numbers[number] = now()

            init = webrtc.VideoFrameBufferInit(
                format='I420', coded_width=width, coded_height=height, timestamp=round(count * 1_000_000 / fps)
            )
            await writer.write(webrtc.VideoFrame(data, init))
            count += 1
            self.tally.frames = count

            await asyncio.sleep(max(0.0, start + count / fps - loop.time()))

    def stop(self) -> None:
        """Stops writing."""
        self._task.cancel()


def codecs(codec: str) -> list[webrtc.RTCRtpCodec]:
    """The capabilities of a codec name of the protocol."""
    capabilities = webrtc.RTCRtpSender.get_capabilities('video')
    mime, parts = CODECS[codec]
    if capabilities is None:
        return []
    return [c for c in capabilities.codecs if c.mime_type == mime and _has_parts(c, parts)]


def _has_parts(codec: webrtc.RTCRtpCodec, parts: tuple[str, ...]) -> bool:
    fmtp = codec.sdp_fmtp_line if codec.sdp_fmtp_line is not None else ''
    return all(part in fmtp for part in parts)


async def read_number(frame: webrtc.VideoFrame) -> int:
    """The number written into a frame."""
    i420 = webrtc.VideoFrameCopyToOptions(format='I420')
    data = bytearray(frame.allocation_size(i420))
    await frame.copy_to(data, i420)
    return frames.read_number(data, frame.coded_width)
