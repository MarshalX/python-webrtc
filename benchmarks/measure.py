#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""What the benchmarks measure besides media: event loop lag, CPU, memory, and the machine."""

import array
import asyncio
import os
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

from tests.helpers import rss_bytes


def percentile(values: List[float], fraction: float) -> float:
    if not values:
        return float('nan')
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


class LoopLag:
    """How late the event loop runs a timer: a busy loop (like one blocked on the GIL) delays everything on it"""

    def __init__(self, interval: float = 0.005):
        self.interval = interval
        # compact: a 5 ms probe collects 12000 a minute
        self.lags = array.array('d')
        self._task: Optional[asyncio.Task] = None

    async def _probe(self):
        loop = asyncio.get_running_loop()
        while True:
            start = loop.time()
            await asyncio.sleep(self.interval)
            self.lags.append(max(0.0, loop.time() - start - self.interval))

    def __enter__(self):
        self._task = asyncio.ensure_future(self._probe())
        return self

    def __exit__(self, *exc_info):
        self._task.cancel()

    @property
    def p95_ms(self) -> float:
        return percentile(self.lags, 0.95) * 1000

    @property
    def max_ms(self) -> float:
        return max(self.lags, default=float('nan')) * 1000


@dataclass
class Usage:
    """CPU and memory over a span of time"""

    wall: float = 0
    cpu: float = 0
    rss_start: int = 0
    rss_end: int = 0
    _started: tuple = field(default=(0.0, 0.0), repr=False)

    def start(self) -> 'Usage':
        self.rss_start = rss_bytes()
        self._started = (time.perf_counter(), time.process_time())
        return self

    def stop(self) -> 'Usage':
        wall, cpu = self._started
        self.wall = time.perf_counter() - wall
        self.cpu = time.process_time() - cpu
        self.rss_end = rss_bytes()
        return self

    @property
    def cpu_percent(self) -> float:
        """Of one core: the process uses several threads (encoders, decoders, network)"""
        return self.cpu / self.wall * 100 if self.wall else float('nan')


def slope_mb_per_minute(samples: List[tuple]) -> float:
    """The trend of (seconds, bytes) samples, by least squares"""
    if len(samples) < 2:
        return float('nan')
    xs = [t for t, _ in samples]
    ys = [b / 1e6 for _, b in samples]
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if not denominator:
        return float('nan')
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator * 60


def machine() -> str:
    cpu = platform.processor() or platform.machine()
    if sys.platform == 'darwin':
        try:
            cpu = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return (
        f'{cpu}, {os.cpu_count()} cores, {platform.system()} {platform.release()} ({platform.machine()}), '
        f'Python {platform.python_version()}'
    )
