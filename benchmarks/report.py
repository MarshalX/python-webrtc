#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The results of a run, and the Markdown of the newest run of each suite, compared with the baseline."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable, NamedTuple, TypedDict, cast

from benchmarks import markdown
from benchmarks.suites import datachannel, media, memory, setup

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Iterable

    from benchmarks.figures import Figure
    from benchmarks.protocol import Hello


class Suite(NamedTuple):
    """A suite: its section's title, ``run(options)``, ``render(results, libraries)`` and ``figures(results)``."""

    title: str
    run: Callable[..., Awaitable[object]]
    render: Callable[..., list[str]]
    figures: Callable[..., list[Figure]]


SUITES = {
    'setup': Suite('Connection setup', setup.run, setup.render, setup.figures),
    'datachannel': Suite('Data channels', datachannel.run, datachannel.render, datachannel.figures),
    'memory': Suite('Memory', memory.run, memory.render, memory.figures),
    'media': Suite('Media', media.run, media.render, media.figures),
}


class Manifest(TypedDict):
    """Where and how a run ran."""

    date: str
    machine: str
    os: str
    arch: str
    python: str
    go: str | None
    commit: str
    command: str
    quick: bool
    repeat: int
    libraries: dict[str, Hello]


class Run(TypedDict):
    """A results file."""

    manifest: Manifest
    #: the results of each suite that ran, by name
    suites: dict[str, object]


def _run_row(name: str, manifest: Manifest) -> list[str]:
    go = f', {manifest["go"]}' if manifest['go'] is not None else ''
    runs = 'quick' if manifest['quick'] else str(manifest['repeat'])
    return [name, manifest['date'][:10], runs, f'{manifest["machine"]}{go}', manifest['commit']]


def newest_runs(paths: Iterable[pathlib.Path]) -> dict[str, Run]:
    """The newest run of each suite, of files named so that they sort by date; a full run wins over a quick one."""
    newest: dict[str, Run] = {}
    for path in sorted(paths):
        run = cast('Run', json.loads(path.read_text(encoding='utf-8')))
        for suite in run['suites']:
            if suite not in newest or not run['manifest']['quick'] or newest[suite]['manifest']['quick']:
                newest[suite] = run
    return newest


def render(paths: Iterable[pathlib.Path]) -> str:
    """The Markdown of the newest run of each suite in the files of runs."""
    newest = newest_runs(paths)
    runs = [_run_row(name, run['manifest']) for name, run in newest.items()]

    lines = [
        '# Benchmarks',
        '',
        f"Medians; % columns are of {markdown.BASELINE}'s. How: [README](README.md#method).",
        '',
    ]
    if len({tuple(row[1:]) for row in runs}) == 1:
        # one machine and commit for every suite: a line
        date, repeats, machine, commit = runs[0][1:]
        lines += [f'{date}, {repeats} runs a case, {machine}, commit {commit}.', '']
    else:
        lines += markdown.table(['Suite', 'Date', 'Runs', 'Machine', 'Commit'], runs)

    for name, suite in SUITES.items():
        run = newest.get(name)
        if run is not None:
            lines += [f'## {suite.title}', '', *suite.render(run['suites'][name], run['manifest']['libraries'])]

    return '\n'.join(lines)
