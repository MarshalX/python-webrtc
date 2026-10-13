#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Raw media for the drivers in Python: I420 frames with their number drawn in, and PCM."""

from __future__ import annotations

import array
import math
import pathlib
from dataclasses import dataclass, field

# the frame number, as bits in blocks of luma at the top left of a frame
BITS = 16
BLOCK = 16
LUMA_ONE, LUMA_ZERO, LUMA_THRESHOLD = 235, 16, 125
TONE = 440.0


def load_raw(path: str, width: int, height: int) -> list[bytes]:
    """The I420 frames of a raw file."""
    data = pathlib.Path(path).read_bytes()
    size = width * height * 3 // 2
    return [data[start : start + size] for start in range(0, len(data) - size + 1, size)]


def numbered(frame: bytes, width: int, number: int) -> bytes:
    """A copy of an I420 frame with the number drawn in its luma."""
    copy = bytearray(frame)
    for bit in range(BITS):
        block = bytes([LUMA_ONE if number >> bit & 1 != 0 else LUMA_ZERO]) * BLOCK
        for y in range(BLOCK):
            start = y * width + bit * BLOCK
            copy[start : start + BLOCK] = block
    return bytes(copy)


def read_number(luma: bytes | bytearray, stride: int) -> int:
    """The number drawn in a luma plane, read at the centers of the blocks, away from compression blur."""
    number = 0
    for bit in range(BITS):
        samples = [luma[y * stride + bit * BLOCK + x] for y in range(5, 11) for x in range(5, 11)]
        if sum(samples) / len(samples) > LUMA_THRESHOLD:
            number |= 1 << bit
    return number


def tone(rate: int, frames: int) -> bytes:
    """A chunk of a 440 Hz tone, mono s16."""
    samples = (int(8000 * math.sin(2 * math.pi * TONE * i / rate)) for i in range(frames))
    return array.array('h', samples).tobytes()


@dataclass
class Tally:
    """What a sender wrote or a sink read: frames, audio, and when each numbered frame was."""

    frames: int = 0
    audio_ms: float = 0.0
    numbers: dict[int, float] = field(default_factory=dict)
