#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The results of a run, and the Markdown of each library's newest results in each suite, against the baseline."""

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


def _libraries(data: dict[str, object]) -> list[str]:
    return list(data)


def _merge(older: dict[str, object], newer: dict[str, object]) -> dict[str, object]:
    return {**older, **newer}


class Suite(NamedTuple):
    """A suite: its section's title, ``run(options)``, ``render(results, libraries)`` and ``figures(results)``."""

    title: str
    run: Callable[..., Awaitable[object]]
    render: Callable[..., list[str]]
    figures: Callable[..., list[Figure]]
    #: the libraries in the results of a run
    libraries: Callable[..., list[str]] = _libraries
    #: the results of two runs, a library's from the newer one if it has them
    merge: Callable[..., object] = _merge


SUITES = {
    'setup': Suite('Connection setup', setup.run, setup.render, setup.figures, setup.libraries, setup.merge),
    'datachannel': Suite('Data channels', datachannel.run, datachannel.render, datachannel.figures),
    'memory': Suite('Memory', memory.run, memory.render, memory.figures),
    'media': Suite('Media', media.run, media.render, media.figures, media.libraries, media.merge),
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


class Newest(NamedTuple):
    """Each library's newest results in a suite, and the runs they came from."""

    data: object
    #: every library's version, from the newest run that has it
    libraries: dict[str, Hello]
    #: the runs, oldest first, with the libraries each gave
    sources: list[tuple[Manifest, list[str]]]


def newest(paths: Iterable[pathlib.Path]) -> dict[str, Newest]:
    """Each library's newest results in each suite, from files that sort by date; full runs win over quick ones."""
    runs = [cast('Run', json.loads(path.read_text(encoding='utf-8'))) for path in sorted(paths)]
    found: dict[str, Newest] = {}
    for name, suite in SUITES.items():
        with_suite = [run for run in runs if name in run['suites']]
        full = [run for run in with_suite if not run['manifest']['quick']]
        chosen = full if len(full) != 0 else with_suite
        if len(chosen) == 0:
            continue

        data: object = None
        versions: dict[str, Hello] = {}
        given: dict[str, int] = {}
        for index, run in enumerate(chosen):
            part = run['suites'][name]
            data = part if data is None else suite.merge(data, part)
            versions.update(run['manifest']['libraries'])
            given.update(dict.fromkeys(suite.libraries(part), index))

        sources = [
            (run['manifest'], [lib for lib, at in given.items() if at == index]) for index, run in enumerate(chosen)
        ]
        found[name] = Newest(data, versions, [(manifest, libs) for manifest, libs in sources if len(libs) != 0])
    return found


def _run_rows(name: str, found: Newest) -> list[list[str]]:
    rows: list[list[str]] = []
    for manifest, libraries in found.sources:
        go = f', {manifest["go"]}' if manifest['go'] is not None else ''
        runs = 'quick' if manifest['quick'] else str(manifest['repeat'])
        machine = f'{manifest["machine"]}{go}'
        rows.append([name, ', '.join(libraries), manifest['date'][:10], runs, machine, manifest['commit']])
    return rows


def render(paths: Iterable[pathlib.Path]) -> str:
    """The Markdown of each library's newest results in each suite, in the files of runs."""
    found = newest(paths)
    runs = [row for name, suite in found.items() for row in _run_rows(name, suite)]

    lines = [
        '# Benchmarks',
        '',
        f"Medians; % columns are of {markdown.BASELINE}'s. How: [README](README.md#method).",
        '',
    ]
    if len({tuple(row[2:]) for row in runs}) == 1:
        # one run for every suite and library: a line
        date, repeats, machine, commit = runs[0][2:]
        lines += [f'{date}, {repeats} runs a case, {machine}, commit {commit}.', '']
    else:
        lines += markdown.table(['Suite', 'Libraries', 'Date', 'Runs', 'Machine', 'Commit'], runs)

    for name, suite in SUITES.items():
        results = found.get(name)
        if results is not None:
            lines += [f'## {suite.title}', '', *suite.render(results.data, results.libraries)]

    return '\n'.join(lines)
