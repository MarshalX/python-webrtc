#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""What the benchmarks measure besides media: event loop lag, CPU, memory, and the machine."""

from __future__ import annotations

import array
import asyncio
import contextlib
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tests.helpers import rss_bytes

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from typing_extensions import Self


def percentile(values: Sequence[float], fraction: float) -> float:
    """The value below which the fraction of the values are, or NaN without values."""
    if len(values) == 0:
        return float('nan')
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


class LoopLag:
    """How late the event loop runs a timer: a busy loop (like one blocked on the GIL) delays everything on it."""

    def __init__(self, interval: float = 0.005) -> None:
        self.interval = interval
        # compact: a 5 ms probe collects 12000 a minute
        self.lags = array.array('d')
        self._task: asyncio.Task[None] | None = None

    async def _probe(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            start = loop.time()
            await asyncio.sleep(self.interval)
            self.lags.append(max(0.0, loop.time() - start - self.interval))

    def __enter__(self) -> Self:
        self._task = asyncio.ensure_future(self._probe())
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._task is not None:
            self._task.cancel()

    @property
    def p95_ms(self) -> float:
        """The 95th percentile lag."""
        return percentile(self.lags, 0.95) * 1000

    @property
    def max_ms(self) -> float:
        """The largest lag."""
        return max(self.lags, default=float('nan')) * 1000


@dataclass
class Usage:
    """CPU and memory over a span of time."""

    wall: float = 0
    cpu: float = 0
    rss_start: int = 0
    rss_end: int = 0
    _started: tuple[float, float] = field(default=(0.0, 0.0), repr=False)

    def start(self) -> Usage:
        """Starts the span."""
        self.rss_start = rss_bytes()
        self._started = (time.perf_counter(), time.process_time())
        return self

    def stop(self) -> Usage:
        """Ends the span."""
        wall, cpu = self._started
        self.wall = time.perf_counter() - wall
        self.cpu = time.process_time() - cpu
        self.rss_end = rss_bytes()
        return self

    @property
    def cpu_percent(self) -> float:
        """Of one core: the process uses several threads (encoders, decoders, network)."""
        return self.cpu / self.wall * 100 if self.wall != 0 else float('nan')


def slope_mb_per_minute(samples: Sequence[tuple[float, int]]) -> float:
    """The trend of (seconds, bytes) samples, by least squares: NaN for less than two."""
    if len(samples) == 0:
        return float('nan')
    xs = [t for t, _ in samples]
    ys = [b / 1e6 for _, b in samples]
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return float('nan')
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator * 60


def machine() -> str:
    """The CPU, the OS and Python of the machine."""
    cpu = platform.processor()
    if cpu == '':
        cpu = platform.machine()
    sysctl = shutil.which('sysctl') if sys.platform == 'darwin' else None
    if sysctl is not None:
        with contextlib.suppress(OSError, subprocess.CalledProcessError):
            cpu = subprocess.check_output([sysctl, '-n', 'machdep.cpu.brand_string'], text=True).strip()
    return (
        f'{cpu}, {os.cpu_count()} cores, {platform.system()} {platform.release()} ({platform.machine()}), '
        f'Python {platform.python_version()}'
    )
