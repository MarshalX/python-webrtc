#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Runs the benchmark suites, writes their results to benchmarks/results/ and renders RESULTS.md.

python -m benchmarks                                         # every suite, every library
python -m benchmarks --suite setup --libs wrtc,pion --quick  # a smoke test of a suite
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import platform
import sys
from typing import IO, TYPE_CHECKING

from benchmarks import report
from benchmarks.report import SUITES
from benchmarks.runner import BENCHMARKS, LIBRARIES, RESULTS, Driver, Options
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


def _arguments(log: IO[bytes]) -> tuple[list[str], Options]:
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

    namespace = parser.parse_args()
    suites: list[str] = namespace.suite
    quick: bool = namespace.quick
    repeat: int | None = namespace.repeat
    options = Options(
        libraries=namespace.libs,
        quick=quick,
        repeat=repeat if repeat is not None else (1 if quick else 3),
        log=log,
    )
    return suites, options


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
    manifest = _manifest(options, await _versions(options.libraries, options.log))
    suites = {name: await SUITES[name].run(options) for name in names}
    return {'manifest': manifest, 'suites': suites}


def main() -> None:
    """Runs the suites of the command line, saves their results, and renders the report."""
    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().astimezone().strftime('%Y-%m-%dT%H%M%S')
    name = f'{stamp}-{platform.system().lower()}-{platform.machine().lower()}'
    with (RESULTS / f'{name}.log').open('ab') as log:
        results = asyncio.run(_run(*_arguments(log)))

    path = RESULTS / f'{name}.json'
    path.write_text(json.dumps(results, indent=1) + '\n', encoding='utf-8')

    markdown = report.render(RESULTS.glob('*.json'))
    (BENCHMARKS / 'RESULTS.md').write_text(markdown + '\n', encoding='utf-8')
    print(markdown)
    print(f'\nresults: {path}', file=sys.stderr)


if __name__ == '__main__':
    main()
