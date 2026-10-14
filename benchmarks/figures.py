#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The data of a chart, as the suites give it: values by category and library, drawn by ``benchmarks.charts``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Detail:
    """A panel under a chart: each library's own value in each category, not relative to the baseline."""

    #: the y axis, like ``kbps``
    label: str
    #: by category, then library
    values: dict[str, dict[str, float]]
    #: the values are fractions of a target, drawn as ``1x`` with a line at it
    of_target: bool = False


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
    #: panels of absolute values under the bars, like the frame rate each library sent
    details: tuple[Detail, ...] = ()
