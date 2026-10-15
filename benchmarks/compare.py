#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Compares two runs: the charted medians of each case before and after, as Markdown for a pull request.

python -m benchmarks.compare BEFORE.json AFTER.json
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from dataclasses import dataclass
from typing import cast

from benchmarks import markdown
from benchmarks.report import SUITES, Manifest, Run


@dataclass(frozen=True)
class Metric:
    """A charted value: the chart's title, the case, the library, and which way is better."""

    title: str
    case: str
    library: str
    lower_is_better: bool


def _load(path: pathlib.Path) -> Run:
    return cast('Run', json.loads(path.read_text(encoding='utf-8')))


def _values(suite: str, run: Run) -> dict[Metric, float]:
    """The charted medians of a suite in a run, none if it didn't run the suite."""
    if suite not in run['suites']:
        return {}
    return {
        Metric(figure.title, case, library, figure.lower_is_better): value
        for figure in SUITES[suite].figures(run['suites'][suite])
        for case, by_library in figure.values.items()
        for library, value in by_library.items()
        if math.isfinite(value)
    }


def _number(value: float | None) -> str:
    """At least three significant digits, without an exponent."""
    if value is None or value == 0:
        return markdown.number(value, 0)
    return markdown.number(value, max(0, min(3, 2 - math.floor(math.log10(abs(value))))))


def _change(metric: Metric, before: float | None, after: float | None) -> tuple[str, str]:
    """After over before, and whether that's better, worse or the same."""
    if before is None or after is None:
        return '-', 'only after' if before is None else 'only before'
    if before == 0:
        return '-', '-'
    change = (after - before) / before
    better = change < 0 if metric.lower_is_better else change > 0
    return f'{change:+.1%}', 'same' if change == 0 else 'better' if better else 'worse'


def _row(metric: Metric, before: float | None, after: float | None, *, with_library: bool) -> list[str]:
    library: list[str] = [metric.library] if with_library else []
    return [
        metric.title,
        metric.case,
        *library,
        _number(before),
        _number(after),
        *_change(metric, before, after),
        '↓' if metric.lower_is_better else '↑',
    ]


def _suite(suite: str, before: Run, after: Run) -> list[str]:
    """The table of a suite: a row a metric, case and library in either run, grouped by metric."""
    old, new = _values(suite, before), _values(suite, after)
    metrics = list(dict.fromkeys([*old, *new]))
    titles = list(dict.fromkeys(metric.title for metric in metrics))
    metrics.sort(key=lambda metric: titles.index(metric.title))

    with_library = len({metric.library for metric in metrics}) > 1
    rows = [_row(metric, old.get(metric), new.get(metric), with_library=with_library) for metric in metrics]
    library: list[str] = ['Library'] if with_library else []
    header = ['Metric', 'Case', *library, 'Before', 'After', 'Change', 'Result', 'Better']
    return [f'### {SUITES[suite].title}', '', *markdown.table(header, rows)]


def _source(name: str, manifest: Manifest) -> str:
    runs = f'{manifest["repeat"]} run{"s" if manifest["repeat"] != 1 else ""}'
    quick = ', quick' if manifest['quick'] else ''
    return f'- {name}: {manifest["date"][:10]}, commit {manifest["commit"]}, {runs}{quick}.'


def compare(before: Run, after: Run) -> str:
    """The Markdown of the charted medians of every suite in either run, before and after."""
    lines = [
        _source('Before', before['manifest']),
        _source('After', after['manifest']),
        '- Medians of the runs; Better: the direction of an improvement.',
        '',
    ]
    for suite in SUITES:
        if suite in before['suites'] or suite in after['suites']:
            lines += _suite(suite, before, after)
    return '\n'.join(lines)


def main() -> None:
    """Prints the comparison of the two runs of the command line."""
    description = __doc__.split('\n')[0] if __doc__ is not None else None
    parser = argparse.ArgumentParser(prog='python -m benchmarks.compare', description=description)
    parser.add_argument('before', type=pathlib.Path, help='the results of the run before the change')
    parser.add_argument('after', type=pathlib.Path, help='the results of the run after it')
    namespace = parser.parse_args()
    print(compare(_load(namespace.before), _load(namespace.after)))


if __name__ == '__main__':
    main()
