#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#


"""The tone, the video and the codecs of aiortc."""

from __future__ import annotations

import asyncio
import contextlib
import fractions
import time

import aiortc
import av
from aiortc.mediastreams import MediaStreamError

from benchmarks.drivers import frames
from benchmarks.protocol import now

AUDIO_RATE = 48_000
AUDIO_FRAMES = 960
VIDEO_CLOCK = 90_000
#: the MIME type and the parameters of each codec name of the protocol that aiortc has
CODECS: dict[str, tuple[str, dict[str, str]]] = {
    'VP8': ('video/VP8', {}),
    'H264': ('video/H264', {'profile-level-id': '42e01f', 'packetization-mode': '1'}),
}
#: the encoders and the decoders aiortc uses, through PyAV
IMPLEMENTATIONS = {'VP8': ('libvpx', 'libvpx'), 'H264': ('libx264', 'FFmpeg h264')}


class ToneTrack(aiortc.MediaStreamTrack):
    """A tone in 20 ms frames of 48 kHz mono, in real time."""

    kind = 'audio'

    def __init__(self) -> None:
        super().__init__()
        self._chunk = frames.tone(AUDIO_RATE, AUDIO_FRAMES)
        self._start: float | None = None
        self._count = 0

    async def recv(self) -> av.AudioFrame:
        """The next frame, once it's due."""
        if self._start is None:
            self._start = time.monotonic()
        due = self._start + self._count * AUDIO_FRAMES / AUDIO_RATE
        await asyncio.sleep(max(0.0, due - time.monotonic()))

        frame = av.AudioFrame(format='s16', layout='mono', samples=AUDIO_FRAMES)
        frame.planes[0].update(self._chunk)
        frame.sample_rate = AUDIO_RATE
        frame.pts = self._count * AUDIO_FRAMES
        frame.time_base = fractions.Fraction(1, AUDIO_RATE)

        self._count += 1
        return frame


class VideoTrack(aiortc.MediaStreamTrack):
    """Raw I420 frames in a loop at a frame rate, numbered if asked."""

    kind = 'video'

    def __init__(self, raw: list[bytes], *, size: tuple[int, int], fps: float, numbered: bool) -> None:
        super().__init__()
        self.tally = frames.Tally()
        self._raw = raw
        self._size = size
        self._fps = fps
        self._numbered = numbered
        self._start: float | None = None

    async def recv(self) -> av.VideoFrame:
        """The next frame, once it's due."""
        count = self.tally.frames
        if self._start is None:
            self._start = time.monotonic()
        due = self._start + count / self._fps
        await asyncio.sleep(max(0.0, due - time.monotonic()))

        width, height = self._size
        data = self._raw[count % len(self._raw)]
        if self._numbered:
            number = count % 2**frames.BITS
            data = frames.numbered(data, width, number)
            self.tally.numbers[number] = now()

        frame = _i420(data, width, height)
        frame.pts = round(count * VIDEO_CLOCK / self._fps)
        frame.time_base = fractions.Fraction(1, VIDEO_CLOCK)

        self.tally.frames = count + 1
        return frame


def _i420(data: bytes, width: int, height: int) -> av.VideoFrame:
    frame = av.VideoFrame(width, height, 'yuv420p')
    luma = width * height
    chroma = luma // 4
    offsets = (0, luma, luma + chroma)
    sizes = (luma, chroma, chroma)
    for plane, start, size in zip(frame.planes, offsets, sizes):
        plane.update(data[start : start + size])
    return frame


def codecs(codec: str) -> list[aiortc.RTCRtpCodecCapability]:
    """The capabilities of a codec name of the protocol."""
    mime, parameters = CODECS[codec]
    capabilities = aiortc.RTCRtpSender.getCapabilities('video').codecs
    return [c for c in capabilities if c.mimeType == mime and parameters.items() <= c.parameters.items()]


async def read(track: aiortc.MediaStreamTrack, tally: frames.Tally, *, numbered: bool) -> None:
    """Reads a remote track until it ends: aiortc queues what nothing reads."""
    with contextlib.suppress(MediaStreamError):
        while True:
            frame = await track.recv()
            tally.frames += 1
            if isinstance(frame, av.AudioFrame):
                tally.audio_ms += frame.samples / frame.sample_rate * 1000
            elif numbered:
                read = now()
                luma = frame.planes[0]
                tally.numbers[frames.read_number(bytes(luma), luma.line_size)] = read
