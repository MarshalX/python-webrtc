#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Runs the benchmark suites, writes their results to benchmarks/results/ and renders RESULTS.md.

python -m benchmarks                                         # every suite, every library
python -m benchmarks --suite setup --libs wrtc,pion --quick  # a smoke test of a suite
python -m benchmarks --case 'ping' --libs wrtc --out DIR     # one case, into DIR, RESULTS.md untouched
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import fnmatch
import io
import json
import pathlib
import platform
import sys
import time
from typing import IO, TYPE_CHECKING

from benchmarks import report
from benchmarks.report import SUITES
from benchmarks.runner import BENCHMARKS, LIBRARIES, RESULTS, Driver, Options, duration
from benchmarks.stats import commit, go_version, machine

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from benchmarks.protocol import Hello
    from benchmarks.report import Manifest, Run


def _names(choices: Sequence[str]) -> Callable[[str], list[str]]:
    def parse(value: str) -> list[str]:
        names = [name.strip() for name in value.split(',') if name.strip() != '']
        unknown = sorted(set(names) - set(choices))
        if unknown != []:
            msg = f'unknown {", ".join(unknown)}; choose from {", ".join(choices)}'
            raise argparse.ArgumentTypeError(msg)
        return names

    return parse


@dataclasses.dataclass(frozen=True)
class Command:
    """The command line: what to run, and where its results go."""

    suites: list[str]
    libraries: list[str]
    quick: bool
    repeat: int
    cases: list[str]
    out: pathlib.Path | None

    def options(self, log: IO[bytes]) -> Options:
        """The options of the suites, their drivers' stderr written to the log."""
        return Options(libraries=self.libraries, quick=self.quick, repeat=self.repeat, log=log, cases=self.cases)


def _parser() -> argparse.ArgumentParser:
    description = __doc__.split('\n')[0] if __doc__ is not None else None
    parser = argparse.ArgumentParser(prog='python -m benchmarks', description=description)
    parser.add_argument(
        '--suite',
        type=_names(list(SUITES)),
        default=list(SUITES),
        help=f'comma-separated suites ({",".join(SUITES)})',
    )
    parser.add_argument('--libs', type=_names(LIBRARIES), default=list(LIBRARIES), help='comma-separated libraries')
    parser.add_argument('--quick', action='store_true', help='fewer trials and one run: a smoke test, not results')
    parser.add_argument('--repeat', type=int, help='runs of each case in fresh processes (3, or 1 with --quick)')
    parser.add_argument(
        '--case',
        action='append',
        default=[],
        metavar='PATTERN',
        help="cases whose name matches, like 'ping' or 'video_receive VP8*'; repeatable",
    )
    parser.add_argument(
        '--out', type=pathlib.Path, metavar='DIR', help='write the results into DIR and leave RESULTS.md as it is'
    )
    return parser


def _command(parser: argparse.ArgumentParser) -> Command:
    namespace = parser.parse_args()
    quick: bool = namespace.quick
    repeat: int | None = namespace.repeat
    if repeat is None:
        repeat = 1 if quick else 3

    command = Command(
        suites=namespace.suite,
        libraries=namespace.libs,
        quick=quick,
        repeat=repeat,
        cases=namespace.case,
        out=namespace.out,
    )
    return _select(parser, command)


def _select(parser: argparse.ArgumentParser, command: Command) -> Command:
    """The command with only the suites that have a selected case; an error for a pattern that matches no case."""
    if len(command.cases) == 0:
        return command

    # nothing runs yet, so nothing logs
    options = command.options(io.BytesIO())
    names = {suite: SUITES[suite].cases(options) for suite in command.suites}
    every_name = [name for cases in names.values() for name in cases]
    unmatched = [
        pattern for pattern in command.cases if not any(fnmatch.fnmatchcase(name, pattern) for name in every_name)
    ]
    if len(unmatched) != 0:
        parser.error(f'--case {", ".join(unmatched)} matches no case; the cases are:{_listing(names)}')

    suites = [suite for suite, cases in names.items() if any(options.selects(name) for name in cases)]
    return dataclasses.replace(command, suites=suites)


def _listing(names: dict[str, list[str]]) -> str:
    """The cases of each suite, a line each, under the suite's name."""
    lines: list[str] = []
    for suite, cases in names.items():
        lines.append(f'{suite}:')
        lines += [f'  {name}' for name in cases]
    return ''.join(f'\n{line}' for line in lines)


async def _versions(libraries: Sequence[str], log: IO[bytes]) -> dict[str, Hello]:
    versions: dict[str, Hello] = {}
    for library in libraries:
        driver = await Driver.start(library, log)
        versions[library] = driver.info
        await driver.stop()
    return versions


def _manifest(options: Options, versions: dict[str, Hello]) -> Manifest:
    return {
        'date': dt.datetime.now().astimezone().isoformat(timespec='seconds'),
        'machine': machine(),
        'os': f'{platform.system()} {platform.release()}',
        'arch': platform.machine(),
        'python': platform.python_version(),
        'go': go_version(),
        'commit': commit(),
        'command': ' '.join(['python -m benchmarks', *sys.argv[1:]]),
        'quick': options.quick,
        'repeat': options.repeat,
        'libraries': versions,
    }


async def _run(names: list[str], options: Options) -> Run:
    today = dt.datetime.now().astimezone()
    options.progress(f'started {today:%Y-%m-%d}: {", ".join(names)} of {", ".join(options.libraries)}')
    manifest = _manifest(options, await _versions(options.libraries, options.log))
    suites: dict[str, object] = {}
    for name in names:
        started = time.monotonic()
        suites[name] = await SUITES[name].run(options)
        options.progress(f'{name}: done in {duration(time.monotonic() - started)}')
    options.progress(f'done in {duration(time.monotonic() - options.started)}')
    return {'manifest': manifest, 'suites': suites}


def main() -> None:
    """Runs the suites of the command line, saves their results, and renders the report unless ``--out`` is given."""
    command = _command(_parser())
    directory = command.out if command.out is not None else RESULTS
    directory.mkdir(parents=True, exist_ok=True)

    stamp = dt.datetime.now().astimezone().strftime('%Y-%m-%dT%H%M%S')
    name = f'{stamp}-{platform.system().lower()}-{platform.machine().lower()}'
    with (directory / f'{name}.log').open('ab') as log:
        options = command.options(log)
        try:
            results = asyncio.run(_run(command.suites, options))
        except KeyboardInterrupt:
            options.progress(f'interrupted, no results saved; drivers logged to {log.name}')
            sys.exit(130)

    path = directory / f'{name}.json'
    path.write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')
    if command.out is not None:
        print(f'results: {path}', file=sys.stderr)
        return

    markdown = report.render(RESULTS.glob('*.json'))
    (BENCHMARKS / 'RESULTS.md').write_text(markdown + '\n', encoding='utf-8')
    print(markdown)
    print(f'\nresults: {path}', file=sys.stderr)


if __name__ == '__main__':
    main()
