#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Media files for the media suite, generated once with ffmpeg from its ``testsrc2`` pattern and a tone."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

from benchmarks.runner import BENCHMARKS

FIXTURES = BENCHMARKS / 'fixtures'
SECONDS = 20
#: raw frames are looped, so a short clip keeps the senders' memory low at 4K
RAW_FRAMES = 15


@dataclass(frozen=True)
class Video:
    """A video case: its size, frame rate and bitrate."""

    width: int
    height: int
    fps: int
    bitrate: int

    @property
    def name(self) -> str:
        """Like ``720p30 2.5 Mbps``."""
        return f'{self.height}p{self.fps} {self.bitrate / 1e6:g} Mbps'

    @property
    def stem(self) -> str:
        """The file name without the codec, like ``1280x720-30-2500k``."""
        return f'{self.width}x{self.height}-{self.fps}-{self.bitrate // 1000}k'


def _ffmpeg() -> str:
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        msg = 'ffmpeg is needed to generate the media fixtures'
        raise RuntimeError(msg)
    return ffmpeg


def _testsrc(video: Video, seconds: float) -> list[str]:
    return ['-f', 'lavfi', '-i', f'testsrc2=size={video.width}x{video.height}:rate={video.fps}', '-t', str(seconds)]


def _encoder(video: Video, codec: str) -> list[str]:
    rate = ['-b:v', str(video.bitrate), '-maxrate', str(video.bitrate), '-g', str(video.fps * 2), '-pix_fmt', 'yuv420p']
    if codec == 'VP8':
        return ['-c:v', 'libvpx', '-deadline', 'realtime', '-cpu-used', '8', '-minrate', str(video.bitrate), *rate]
    profile = 'high' if codec == 'H264-High' else 'baseline'
    return [
        *('-c:v', 'libx264', '-profile:v', profile, '-preset', 'veryfast', '-tune', 'zerolatency'),
        # one slice a frame, no B-frames: what a WebRTC sender sends
        *('-x264-params', 'sliced-threads=0', '-bf', '0', '-bufsize', str(video.bitrate), *rate),
    ]


def _generate(path_name: str, arguments: list[str]) -> str:
    path = FIXTURES / path_name
    if not path.exists():
        FIXTURES.mkdir(exist_ok=True)
        partial = path.with_name(f'partial-{path.name}')
        subprocess.run([_ffmpeg(), '-v', 'error', '-y', *arguments, str(partial)], check=True)
        partial.rename(path)
    return str(path)


def encoded(video: Video, codec: str) -> str:
    """An IVF VP8 or Annex B H.264 file of the video, as Pion sends it unchanged."""
    extension = 'ivf' if codec == 'VP8' else 'h264'
    arguments = [*_testsrc(video, SECONDS), *_encoder(video, codec)]
    return _generate(f'{codec.lower()}-{video.stem}.{extension}', arguments)


def raw(video: Video) -> str:
    """Raw I420 frames of the video, for the libraries to encode."""
    seconds = RAW_FRAMES / video.fps
    arguments = [*_testsrc(video, seconds), '-pix_fmt', 'yuv420p', '-f', 'rawvideo']
    return _generate(f'raw-{video.width}x{video.height}.yuv', arguments)


def opus() -> str:
    """Ogg Opus of a tone, 48 kHz stereo in 20 ms packets, a packet a page, as Pion reads it."""
    tone = ['-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000:duration={SECONDS}', '-ac', '2']
    encoder = ['-c:a', 'libopus', '-b:a', '64k', '-frame_duration', '20', '-page_duration', '20000']
    return _generate('tone.ogg', [*tone, *encoder])


def ffmpeg_decode_ms(path: str, frames: int) -> float:
    """The CPU time a frame of ffmpeg decoding a file on one thread: the reference for a real-time decoder."""
    benchmark = [_ffmpeg(), '-benchmark', '-threads', '1', '-i', path, '-f', 'null', '-']
    output = subprocess.run(benchmark, capture_output=True, text=True, check=True).stderr
    utime = re.search(r'utime=([\d.]+)s', output)
    return float(utime.group(1)) * 1000 / frames if utime is not None else float('nan')
