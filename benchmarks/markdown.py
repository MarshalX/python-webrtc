#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Numbers and tables of the report."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from benchmarks.stats import percentile

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from benchmarks.protocol import Hello

#: The library the others are compared with
BASELINE = 'aiortc'


def number(value: float | None, digits: int = 1) -> str:
    """A number, or a dash for none."""
    return '-' if value is None or math.isnan(value) else f'{value:.{digits}f}'


def spread(values: Sequence[float]) -> str:
    """The p50 and the p95 of values."""
    return f'{number(percentile(values, 0.5))} / {number(percentile(values, 0.95))}'


def percent_of(value: float, baseline: float) -> str:
    """A value as a percentage of the baseline's."""
    if math.isnan(value) or math.isnan(baseline) or baseline == 0:
        return '-'
    return f'{value / baseline:.0%}'


def library(name: str, libraries: dict[str, Hello]) -> str:
    """The name and the version of a library."""
    return f'{name} {libraries[name]["version"]}'


def table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    """The lines of a table, and an empty one after it."""
    lines = ['| ' + ' | '.join(header) + ' |', '|' + ' --- |' * len(header)]
    return [*lines, *('| ' + ' | '.join(row) + ' |' for row in rows), '']
