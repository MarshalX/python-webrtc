#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Tones to send, and the tone of what comes back."""

from __future__ import annotations

import array
import math

#: the amplitude of a tone, and the least that isn't silence
AMPLITUDE = 12000
SILENCE = 1000


def sine(frequency: float, rate: int, *, first: int = 0, count: int) -> bytes:
    """16-bit samples of a sine at a rate, from the sample at the index ``first``."""
    samples = (int(AMPLITUDE * math.sin(2 * math.pi * frequency * (first + i) / rate)) for i in range(count))
    return array.array('h', samples).tobytes()


def dominant_frequency(samples: list[int], rate: int) -> float | None:
    """The frequency of a sine, from its rising zero crossings; :obj:`None` for silence."""
    if len(samples) == 0 or max(samples) < SILENCE:
        return None
    crossings = [i for i in range(1, len(samples)) if samples[i - 1] < 0 <= samples[i]]
    if len(crossings) < 2:
        return None
    return (len(crossings) - 1) * rate / (crossings[-1] - crossings[0])
