#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Statistics, event loop lag and the manifest of the machine: standard library only, as every driver imports it."""

from __future__ import annotations

import array
import asyncio
import os
import platform
import shutil
import statistics
import subprocess
import sys
from typing import TYPE_CHECKING

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


def median(values: Sequence[float]) -> float:
    """The median, or NaN without values."""
    return statistics.median(values) if len(values) != 0 else float('nan')


def slope(points: Sequence[tuple[float, float]]) -> float:
    """The least squares slope of (x, y) points: NaN for less than two distinct x."""
    if len(points) == 0:
        return float('nan')
    xs, ys = [x for x, _ in points], [y for _, y in points]
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return float('nan')
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator


class LoopLag:
    """How late the event loop runs a timer: a busy loop (like one blocked on the GIL) delays everything on it."""

    #: how often the timer fires, in seconds
    INTERVAL = 0.005

    def __init__(self) -> None:
        # compact: a 5 ms probe collects 12000 a minute
        self.lags = array.array('d')
        self._task: asyncio.Task[None] | None = None

    async def _probe(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            start = loop.time()
            await asyncio.sleep(self.INTERVAL)
            self.lags.append(max(0.0, loop.time() - start - self.INTERVAL))

    def __enter__(self) -> Self:
        self._task = asyncio.ensure_future(self._probe())
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._task is not None:
            self._task.cancel()

    def reset(self) -> None:
        """Forgets the lags collected so far."""
        self.lags = array.array('d')

    @property
    def p95_ms(self) -> float:
        """The 95th percentile lag."""
        return percentile(self.lags, 0.95) * 1000


def _output(*command: str) -> str | None:
    executable = shutil.which(command[0])
    if executable is None:
        return None
    try:
        return subprocess.check_output([executable, *command[1:]], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _cpu() -> str:
    brand = _output('sysctl', '-n', 'machdep.cpu.brand_string') if sys.platform == 'darwin' else None
    if brand is not None:
        return brand
    return platform.processor() if platform.processor() != '' else platform.machine()


def machine() -> str:
    """The CPU, the OS and Python of the machine."""
    return (
        f'{_cpu()}, {os.cpu_count()} cores, {platform.system()} {platform.release()} ({platform.machine()}), '
        f'Python {platform.python_version()}'
    )


def commit() -> str:
    """The commit of the repository, and whether the working tree has changes."""
    revision = _output('git', 'rev-parse', '--short', 'HEAD')
    if revision is None:
        return 'unknown'
    changes = _output('git', 'status', '--porcelain')
    return revision if changes in {None, ''} else f'{revision} with uncommitted changes'


def go_version() -> str | None:
    """The version of the Go toolchain, if installed."""
    return _output('go', 'env', 'GOVERSION')
