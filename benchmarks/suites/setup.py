#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Connection establishment: a fresh pair of connections a trial, timed on the offerer from ``createOffer``.

Two modes: ``trickle`` sends the descriptions right away and relays the candidates as they're gathered, as browsers
do; aiortc can't, so it connects as in ``complete``, where each side sends its description once gathering completes.
Cold trials are the first connection of fresh processes, so they include starting the library (its factory, threads);
warm trials follow a discarded one in the same processes.
"""

from __future__ import annotations

import asyncio
import math
import random
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

from benchmarks import markdown
from benchmarks.figures import Figure
from benchmarks.markdown import BASELINE
from benchmarks.runner import DriverError, pair
from benchmarks.signaling import TIMEOUT, Connection
from benchmarks.stats import median

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import IO

    from benchmarks.protocol import Hello
    from benchmarks.runner import Driver, Options

#: trickle where both drivers can, or every candidate in the descriptions (once gathering completes)
Mode = Literal['trickle', 'complete']
#: the modes and their titles
MODES: dict[Mode, str] = {'trickle': 'Trickle', 'complete': 'Without trickle'}
Step = Literal['create', 'offer', 'gathered', 'ice_connected', 'connected', 'dc_open']
EVENTS: tuple[Step, ...] = ('gathered', 'ice_connected', 'connected', 'dc_open')


class Trial(TypedDict):
    """The milliseconds from ``createOffer`` to each step of a connection, and ``create``, the constructor's."""

    create: float
    offer: float
    gathered: float
    ice_connected: float
    connected: float
    dc_open: float


class WarmRun(TypedDict):
    """The warm trials of one pair of processes, and what they cost."""

    trials: list[Trial]
    failures: int
    cpu_ms_per_connection: float
    peak_rss_mb: float
    loop_lag_p95_ms: float | None


class Results(TypedDict):
    """The trials of a library: a cold one (None if it failed) and a warm run a pair of processes."""

    cold: list[Trial | None]
    warm: list[WarmRun]


async def _connect(connection: Connection) -> Trial:
    created, offer = await connection.negotiate()
    offerer, caller = connection.offerer, connection.caller
    gathered, ice_connected, connected, dc_open, _ = await asyncio.gather(
        *(offerer.event(caller, step, TIMEOUT) for step in EVENTS),
        connection.answerer.event(connection.callee, 'dc_open', TIMEOUT),
    )
    start = offer['t_start']

    def since_start(time: float) -> float:
        return (time - start) * 1000

    return {
        'create': (created['t_end'] - created['t_start']) * 1000,
        'offer': since_start(offer['t_offer']),
        'gathered': since_start(gathered),
        'ice_connected': since_start(ice_connected),
        'connected': since_start(connected),
        'dc_open': since_start(dc_open),
    }


async def trial(offerer: Driver, answerer: Driver, *, trickle: bool) -> Trial | None:
    """Connects a fresh pair and closes it, or returns None if it didn't connect in time."""
    connection = Connection(offerer, answerer, trickle=trickle)
    try:
        return await _connect(connection)
    except DriverError as error:
        print(f'  trial failed: {error}', file=sys.stderr)
        return None
    finally:
        await connection.close()


async def cold_trial(library: str, log: IO[bytes], *, trickle: bool) -> Trial | None:
    """The first connection of fresh processes."""
    async with pair(library, log) as (offerer, answerer):
        return await trial(offerer, answerer, trickle=trickle)


async def warm_run(library: str, count: int, log: IO[bytes], *, trickle: bool) -> WarmRun:
    """Connections of one pair of processes after a discarded first one, and what they cost."""
    async with pair(library, log) as (offerer, answerer):
        # the first connection, and the loop lag until now, are discarded
        await trial(offerer, answerer, trickle=trickle)
        await offerer.probe()

        offerer.sampler.start()
        answerer.sampler.start()
        results = [await trial(offerer, answerer, trickle=trickle) for _ in range(count)]
        usage = offerer.sampler.stop(), answerer.sampler.stop()
        lag = await offerer.probe()

    trials = [result for result in results if result is not None]
    return {
        'trials': trials,
        'failures': count - len(trials),
        'cpu_ms_per_connection': sum(u.cpu_seconds for u in usage) * 1000 / count,
        'peak_rss_mb': usage[0].peak_rss / 1e6,
        'loop_lag_p95_ms': lag.get('lag_p95_ms'),
    }


@dataclass
class _Case:
    library: str
    mode: Mode
    cold: bool


def _cases(options: Options) -> list[_Case]:
    """Every case, in a random order."""
    kinds = [True] * (3 if options.quick else 10) + [False] * options.repeat
    cases = [_Case(library, mode, cold) for library in options.libraries for mode in MODES for cold in kinds]
    random.shuffle(cases)
    return cases


async def run(options: Options) -> dict[Mode, dict[str, Results]]:
    """Runs the trials of every library in both modes, the cases in a random order.

    Returns:
        The trials by mode, then by library.
    """
    per_run = math.ceil((10 if options.quick else 100) / options.repeat)
    results: dict[Mode, dict[str, Results]] = {
        mode: {library: {'cold': [], 'warm': []} for library in options.libraries} for mode in MODES
    }

    for case in _cases(options):
        print(f'setup: {case.library} {case.mode} {"cold" if case.cold else "warm"}', file=sys.stderr, flush=True)
        result, trickle = results[case.mode][case.library], case.mode == 'trickle'
        if case.cold:
            result['cold'].append(await cold_trial(case.library, options.log, trickle=trickle))
        else:
            result['warm'].append(await warm_run(case.library, per_run, options.log, trickle=trickle))

    return results


STEP_TITLES: tuple[tuple[Step, str], ...] = (
    ('create', 'Create'),
    ('offer', 'Offer created'),
    ('gathered', 'Gathered'),
    ('ice_connected', 'ICE connected'),
    ('connected', 'Connected'),
    ('dc_open', 'Data channel open'),
)


def _warm(result: Results) -> list[Trial]:
    return [trial for run in result['warm'] for trial in run['trials']]


def _cold(result: Results) -> list[Trial]:
    return [trial for trial in result['cold'] if trial is not None]


def _step(trials: Iterable[Trial], step: Step) -> list[float]:
    return [trial[step] for trial in trials]


def _timings(
    data: dict[str, Results], libraries: dict[str, Hello], kind: Callable[[Results], list[Trial]]
) -> list[str]:
    baseline = median(_step(kind(data[BASELINE]), 'dc_open')) if BASELINE in data else math.nan
    rows: list[list[str]] = []
    for name, result in data.items():
        trials = kind(result)
        cells = [markdown.library(name, libraries), *(markdown.spread(_step(trials, step)) for step, _ in STEP_TITLES)]
        rows.append([*cells, markdown.percent_of(median(_step(trials, 'dc_open')), baseline)])
    header = ['Library', *(title for _, title in STEP_TITLES), f'Open, % of {BASELINE}']
    return markdown.table(header, rows)


def _cost(name: str, result: Results, libraries: dict[str, Hello]) -> list[str]:
    runs = result['warm']
    lags = [run['loop_lag_p95_ms'] for run in runs]
    return [
        markdown.library(name, libraries),
        markdown.number(median([run['cpu_ms_per_connection'] for run in runs])),
        markdown.number(median([run['peak_rss_mb'] for run in runs]), 0),
        markdown.number(median([lag for lag in lags if lag is not None])),
        str(sum(run['failures'] for run in runs) + result['cold'].count(None)),
    ]


def _mode(title: str, data: dict[str, Results], libraries: dict[str, Hello]) -> list[str]:
    warm = max(len(_warm(result)) for result in data.values())
    cold = max(len(_cold(result)) for result in data.values())
    return [
        f'### {title}, warm ({warm} trials)',
        '',
        *_timings(data, libraries, _warm),
        f'### {title}, cold: fresh processes ({cold} trials)',
        '',
        *_timings(data, libraries, _cold),
    ]


def libraries(data: dict[Mode, dict[str, Results]]) -> list[str]:
    """The libraries in the results of a run."""
    return list(dict.fromkeys(name for results in data.values() for name in results))


def merge(
    older: dict[Mode, dict[str, Results]], newer: dict[Mode, dict[str, Results]]
) -> dict[Mode, dict[str, Results]]:
    """The results of two runs, a library's from the newer one if it has them."""
    return {mode: {**older.get(mode, {}), **newer.get(mode, {})} for mode in MODES}


def render(data: dict[Mode, dict[str, Results]], libraries: dict[str, Hello]) -> list[str]:
    """The tables of the results: trickle first, then complete descriptions, then the cost of trickle."""
    no_trickle = [name for name in data['trickle'] if not libraries[name]['trickle']]
    notes = ['- ms, p50 / p95, from `createOffer`; Create: the constructors.']
    if len(no_trickle) != 0:
        notes.append(f"- {', '.join(no_trickle)} can't trickle: it connects without trickle in both.")
    lines = [*notes, '']

    for mode, title in MODES.items():
        lines += _mode(title, data[mode], libraries)

    costs = [_cost(name, result, libraries) for name, result in data['trickle'].items()]
    lines += [
        '### Cost of a warm trial, trickle',
        '',
        *markdown.table(
            ['Library', 'CPU, both (ms)', 'Peak RSS, offerer (MB)', 'Loop lag p95 (ms)', 'Failed trials'], costs
        ),
    ]

    return lines


def figures(data: dict[Mode, dict[str, Results]]) -> list[Figure]:
    """The chart of the median time to an open channel, by mode, warm and cold."""
    values: dict[str, dict[str, float]] = {}
    for mode, title in MODES.items():
        for kind, trials in (('warm', _warm), ('cold', _cold)):
            values[f'{title.lower()}, {kind}'] = {
                name: median(_step(trials(result), 'dc_open')) for name, result in data[mode].items()
            }

    title = 'Connection setup: time to an open data channel'
    return [Figure('setup', title, 'Speed', lower_is_better=True, values=values)]
