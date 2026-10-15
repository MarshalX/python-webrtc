#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Memory per connection, the most connections a pair of processes holds, and what stays after closing them.

The runner reads the RSS of both processes after asking each to collect its garbage (Python's ``gc.collect``, Go's
``runtime.GC`` and ``debug.FreeOSMemory``, the C++ and Rust drivers' allocator trim), so the numbers are of live memory
rather than of collector timing. Libraries without media skip the audio state.
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

import psutil

from benchmarks import markdown
from benchmarks.figures import Figure
from benchmarks.markdown import BASELINE
from benchmarks.runner import MEDIA_LIBRARIES, DriverError, pair
from benchmarks.signaling import Connection
from benchmarks.stats import median, percentile, slope

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import IO

    from benchmarks.protocol import Hello
    from benchmarks.runner import Driver, Options

#: connections opened at once
BATCH = 10
#: how long connections run before a reading, so audio flows and buffers fill
SETTLE = 2.0
#: the total RSS of both processes at which growing stops
RSS_CAP = 2 * 1024**3
#: the memory the system must keep available while growing
AVAILABLE_FLOOR = 1.5 * 1024**3
SLOW_SETUP_MS = 5000.0

State = Literal['created', 'datachannel', 'audio']
STATES: tuple[State, ...] = ('created', 'datachannel', 'audio')


@dataclass(frozen=True)
class Sizes:
    """The connection counts of a run."""

    levels: tuple[int, ...]
    growth_step: int
    growth_limit: int


class Reading(TypedDict):
    """The RSS of both processes with some connections, in MB."""

    connections: int
    offerer_mb: float
    answerer_mb: float


class StateRun(TypedDict):
    """The RSS of a pair of processes at each count of connections in a state, and once they're all closed."""

    baseline: Reading
    levels: list[Reading]
    closed: Reading


class Step(TypedDict):
    """A step of growth: the connections, the RSS of both processes, the system's available memory, and setup."""

    connections: int
    total_mb: float
    available_mb: float
    setup_p95_ms: float


class Growth(TypedDict):
    """Connections opened in steps until a limit: the last count that stayed within them, and why it stopped."""

    steps: list[Step]
    last_good: int
    stopped_by: str


class Results(TypedDict):
    """The runs of a library: the states (None for a run that failed), and the growth."""

    states: dict[State, list[StateRun | None]]
    growth: list[Growth]


async def _reading(drivers: tuple[Driver, Driver], connections: int) -> Reading:
    await asyncio.gather(*(driver.collect() for driver in drivers))
    offerer, answerer = drivers
    return {'connections': connections, 'offerer_mb': offerer.rss() / 1e6, 'answerer_mb': answerer.rss() / 1e6}


async def _add(drivers: tuple[Driver, Driver], state: State) -> tuple[Connection, float]:
    """A new connection in a state, and how long it took in ms."""
    connection = Connection(*drivers, trickle=True)
    start = time.perf_counter()
    if state == 'created':
        await connection.create()
    else:
        await connection.open(audio=state == 'audio')
    return connection, (time.perf_counter() - start) * 1000


async def _grow(drivers: tuple[Driver, Driver], state: State, count: int) -> tuple[list[Connection], list[float]]:
    """Adds connections in batches; the connections and their setup times."""
    connections: list[Connection] = []
    times: list[float] = []
    while len(connections) < count:
        batch = min(BATCH, count - len(connections))
        added = await asyncio.gather(*(_add(drivers, state) for _ in range(batch)))
        connections += [connection for connection, _ in added]
        times += [ms for _, ms in added]
    return connections, times


async def _close(connections: Sequence[Connection]) -> None:
    for start in range(0, len(connections), BATCH):
        await asyncio.gather(*(c.close() for c in connections[start : start + BATCH]))


async def _through_levels(
    drivers: tuple[Driver, Driver], connections: list[Connection], *, state: State, levels: Sequence[int]
) -> StateRun:
    baseline = await _reading(drivers, 0)

    readings: list[Reading] = []
    for level in levels:
        connections += (await _grow(drivers, state, level - len(connections)))[0]
        await asyncio.sleep(SETTLE)
        readings.append(await _reading(drivers, level))
        if _limit(sum(driver.rss() for driver in drivers)) is not None:
            print(f'  memory limit at {level} connections, no more levels', file=sys.stderr)
            break

    # what both processes keep once every connection is closed
    await _close(connections)
    connections.clear()
    await asyncio.sleep(SETTLE)
    return {'baseline': baseline, 'levels': readings, 'closed': await _reading(drivers, 0)}


async def state_run(library: str, state: State, *, levels: Sequence[int], log: IO[bytes]) -> StateRun | None:
    """Grows the connections of a fresh pair of processes through the levels, then closes them all."""
    async with pair(library, log) as drivers:
        connections: list[Connection] = []
        try:
            return await _through_levels(drivers, connections, state=state, levels=levels)
        except DriverError as error:
            print(f'  memory run failed: {error}', file=sys.stderr)
            return None
        finally:
            await _close(connections)


def _limit(total: int) -> str | None:
    """Why growing must stop at this total RSS of both processes, if it must."""
    if total > RSS_CAP:
        return f'RSS over {RSS_CAP / 1024**3:.0f} GB'
    if psutil.virtual_memory().available < AVAILABLE_FLOOR:
        return f'system memory available under {AVAILABLE_FLOOR / 1024**3:.1f} GB'
    return None


async def _step(drivers: tuple[Driver, Driver], connections: list[Connection], sizes: Sizes) -> tuple[Step, str | None]:
    """Opens a step of connections in batches, stopping early at a memory limit; the step and why to stop."""
    times: list[float] = []
    target = len(connections) + sizes.growth_step
    reason = None

    while len(connections) < target and reason is None:
        added, batch_times = await _grow(drivers, 'datachannel', min(BATCH, target - len(connections)))
        connections += added
        times += batch_times
        reason = _limit(sum(driver.rss() for driver in drivers))

    p95 = percentile(times, 0.95)
    if reason is None and p95 > SLOW_SETUP_MS:
        reason = f'setup p95 over {SLOW_SETUP_MS / 1000:.0f} s'

    step: Step = {
        'connections': len(connections),
        'total_mb': sum(driver.rss() for driver in drivers) / 1e6,
        'available_mb': psutil.virtual_memory().available / 1e6,
        'setup_p95_ms': p95,
    }
    return step, reason


async def _grow_to_limit(
    drivers: tuple[Driver, Driver], connections: list[Connection], *, sizes: Sizes, growth: Growth
) -> None:
    while len(connections) < sizes.growth_limit:
        step, reason = await _step(drivers, connections, sizes)
        growth['steps'].append(step)
        if reason is not None:
            growth['stopped_by'] = reason
            return
        growth['last_good'] = step['connections']


async def growth_run(library: str, sizes: Sizes, log: IO[bytes]) -> Growth:
    """Opens connections with data channels in steps until setup fails, slows down, or memory runs short."""
    growth: Growth = {'steps': [], 'last_good': 0, 'stopped_by': f'reached {sizes.growth_limit} connections'}
    async with pair(library, log) as drivers:
        connections: list[Connection] = []
        try:
            await _grow_to_limit(drivers, connections, sizes=sizes, growth=growth)
        except DriverError as error:
            growth['stopped_by'] = f'setup failed: {error}'
        finally:
            await _close(connections)
    return growth


def _states(library: str) -> tuple[State, ...]:
    """The states a library is measured in: audio only where its driver sends it."""
    return STATES if library in MEDIA_LIBRARIES else tuple(state for state in STATES if state != 'audio')


def _name(state: State | None) -> str:
    """Like ``datachannel`` or ``growth``: what ``--case`` matches."""
    return 'growth' if state is None else state


def _every(options: Options) -> list[tuple[str, State | None]]:
    cases: list[tuple[str, State | None]] = [
        (library, state) for library in options.libraries for state in _states(library) for _ in range(options.repeat)
    ]
    return cases + [(library, None) for library in options.libraries]


def _cases(options: Options) -> list[tuple[str, State | None]]:
    """The library and the state (None for growth) of each selected case, in a random order."""
    cases = [(library, state) for library, state in _every(options) if options.selects(_name(state))]
    random.shuffle(cases)
    return cases


def cases(options: Options) -> list[str]:
    """The name of every case of a run, selected or not."""
    return list(dict.fromkeys(_name(state) for _, state in _every(options)))


async def run(options: Options) -> dict[str, Results]:
    """Runs the states of every library and grows each once, the cases in a random order.

    Returns:
        The runs by library.
    """
    if options.quick:
        sizes = Sizes(levels=(1, 5, 10, 20), growth_step=10, growth_limit=50)
    else:
        sizes = Sizes(levels=(1, 10, 50, 100, 200), growth_step=50, growth_limit=2000)

    results: dict[str, Results] = {
        library: {'states': {state: [] for state in STATES}, 'growth': []} for library in options.libraries
    }
    for library, state in _cases(options):
        print(f'memory: {library} {_name(state)}', file=sys.stderr, flush=True)
        if state is None:
            results[library]['growth'].append(await growth_run(library, sizes, options.log))
        else:
            results[library]['states'][state].append(
                await state_run(library, state, levels=sizes.levels, log=options.log)
            )

    return results


def _total(reading: Reading) -> float:
    return reading['offerer_mb'] + reading['answerer_mb']


def _runs(result: Results, state: State) -> list[StateRun]:
    return [run for run in result['states'][state] if run is not None]


def _per_connection_kb(result: Results, state: State) -> float:
    """The median over the runs of the slope of the RSS of both processes over the connections."""
    return median([
        slope([(r['connections'], _total(r)) for r in run['levels']]) * 1000 for run in _runs(result, state)
    ])


def _retained_mb(result: Results, state: State) -> float:
    return median([_total(run['closed']) - _total(run['baseline']) for run in _runs(result, state)])


def _baseline_mb(result: Results) -> float:
    return median([_total(run['baseline']) for state in STATES for run in _runs(result, state)])


def _per_connection_row(name: str, data: dict[str, Results], libraries: dict[str, Hello]) -> list[str]:
    result = data[name]
    values = [_per_connection_kb(result, state) for state in STATES]
    baselines = [_per_connection_kb(data[BASELINE], state) if BASELINE in data else float('nan') for state in STATES]
    return [
        markdown.library(name, libraries),
        markdown.number(_baseline_mb(result), 0),
        *(markdown.number(value, 0) for value in values),
        *map(markdown.percent_of, values, baselines),
    ]


def _levels_rows(name: str, result: Results, libraries: dict[str, Hello]) -> list[list[str]]:
    rows: list[list[str]] = []
    for state in STATES:
        runs = _runs(result, state)
        if len(runs) == 0:
            continue
        totals = [median([_total(run['levels'][i]) for run in runs]) for i in range(len(runs[0]['levels']))]
        rows.append([markdown.library(name, libraries), state, *(markdown.number(total, 0) for total in totals)])
    return rows


def _growth_row(name: str, result: Results, libraries: dict[str, Hello]) -> list[str]:
    growth = result['growth'][-1] if len(result['growth']) != 0 else None
    if growth is None or len(growth['steps']) == 0:
        return [markdown.library(name, libraries), '-', '-', '-', '-']

    last = growth['steps'][-1]
    return [
        markdown.library(name, libraries),
        str(growth['last_good']),
        growth['stopped_by'],
        markdown.number(last['total_mb'], 0),
        markdown.number(last['setup_p95_ms']),
    ]


def _levels(data: dict[str, Results]) -> list[int]:
    runs = [run for result in data.values() for state in STATES for run in _runs(result, state)]
    return [] if len(runs) == 0 else [reading['connections'] for reading in runs[0]['levels']]


def render(data: dict[str, Results], libraries: dict[str, Hello]) -> list[str]:
    """The tables of the results: per connection, after closing, at each count, and the growth."""
    names = list(data)
    per_state = ['Created', 'Data channel', 'Audio']
    lines = [
        '- RSS of both processes after a garbage collection.',
        '- Created: not negotiated. Data channel: open. Audio: plus a 48 kHz tone.',
        '',
    ]

    header = [
        'Library',
        'Baseline (MB)',
        *(f'{s} (KB)' for s in per_state),
        *(f'{s}, % of {BASELINE}' for s in per_state),
    ]
    rows = [_per_connection_row(name, data, libraries) for name in names]
    lines += [
        '### Per connection',
        '',
        '- Baseline: the library started. KB: the slope over the connection counts.',
        '',
        *markdown.table(header, rows),
    ]

    rows = [
        [markdown.library(name, libraries), *(markdown.number(_retained_mb(data[name], s)) for s in STATES)]
        for name in names
    ]
    lines += [
        '### Kept after closing every connection (MB over the baseline)',
        '',
        *markdown.table(['Library', *per_state], rows),
    ]

    header = ['Library', 'State', *(str(level) for level in _levels(data))]
    rows = [row for name in names for row in _levels_rows(name, data[name], libraries)]
    lines += ['### RSS of both processes by connections (MB)', '', *markdown.table(header, rows)]

    limits = (
        f'- Steps of {BATCH} until setup fails, its p95 > {SLOW_SETUP_MS / 1000:.0f} s, '
        f'RSS > {RSS_CAP / 1024**3:.0f} GB or free memory < {AVAILABLE_FLOOR / 1024**3:.1f} GB.'
    )
    header = ['Library', 'Last good', 'Stopped by', 'RSS at the last step (MB)', 'Setup p95 at the last step (ms)']
    rows = [_growth_row(name, data[name], libraries) for name in names]
    lines += ['### Most connections', '', limits, '', *markdown.table(header, rows)]

    return lines


def figures(data: dict[str, Results]) -> list[Figure]:
    """The chart of the memory per connection in each state."""
    values: dict[str, dict[str, float]] = {
        state: {name: _per_connection_kb(result, state) for name, result in data.items()} for state in STATES
    }

    return [Figure('memory', 'Memory per connection', 'Less memory', lower_is_better=True, values=values)]
