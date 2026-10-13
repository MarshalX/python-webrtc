#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The data of a chart, as the suites give it: values by category and library, drawn by ``benchmarks.charts``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Figure:
    """A chart: each library's value in each category, drawn relative to the baseline's so that higher is better."""

    #: the file name, without the extension
    name: str
    title: str
    #: what a bar above 1x means, like ``Throughput`` or ``Speed``
    measure: str
    #: the values are costs or times, so the baseline's value over a library's is drawn
    lower_is_better: bool
    #: by category, then library
    values: dict[str, dict[str, float]]
    #: a label drawn on a bar, by category, then library, like the bitrate a library chose
    notes: dict[str, dict[str, str]] = field(default_factory=dict)
