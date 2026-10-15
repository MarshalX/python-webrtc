#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Data channel throughput and latency between two processes of a library.

Flood: the offerer sends messages one way for a warmup and the measured seconds, keeping ``bufferedAmount`` between
512 KB (``bufferedAmountLowThreshold``) and 1 MB; the runner reads the bytes and messages the answerer received
every second. Ping: 1 KB messages at 100 a second to an echoing answerer, timed on the offerer.
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
from benchmarks.signaling import Connection
from benchmarks.stats import median, percentile

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import IO

    from benchmarks.protocol import Count, Hello
    from benchmarks.runner import Driver, Options

LOW_WATERMARK = 512 * 1024
HIGH_WATERMARK = 1024 * 1024
INTERVAL = 1.0
PING_SIZE = 1024
PING_RATE = 100.0


@dataclass(frozen=True)
class Cell:
    """A flood: ordered or not, the size of the messages, and the connections flooding at once."""

    ordered: bool
    size: int
    connections: int

    @property
    def name(self) -> str:
        """Like ``ordered 64 KB x10``."""
        kind = 'ordered' if self.ordered else 'unordered'
        return f'{kind} {self.size // 1024} KB x{self.connections}'


CELLS = tuple(
    Cell(ordered, size, connections)
    for ordered in (True, False)
    for size in (1024, 64 * 1024)
    for connections in (1, 10)
)


@dataclass(frozen=True)
class Timing:
    """How long each part of a case runs, in seconds."""

    warmup: float
    measured: int
    ping: float


class FloodRun(TypedDict):
    """A flood of one pair of processes: the rates of each measured second, summed over the connections."""

    mbps: list[float]
    messages_per_second: list[float]
    megabytes: float
    cpu_seconds: float


class PingRun(TypedDict):
    """The round trips of one pair of processes, and how many were sent."""

    rtts_ms: list[float]
    sent: int


class Results(TypedDict):
    """The runs of a library: floods by cell name, and pings (None for a run that failed)."""

    flood: dict[str, list[FloodRun | None]]
    ping: list[PingRun | None]


async def _counts(answerer: Driver, connections: Sequence[Connection]) -> list[Count]:
    return list(await asyncio.gather(*(answerer.count(connection.callee) for connection in connections)))


def _rate(before: Sequence[Count], after: Sequence[Count], key: Literal['bytes', 'messages']) -> float:
    """The sum of the rates of the connections between two counts, a second."""
    return sum((b[key] - a[key]) / (b['t'] - a['t']) for a, b in zip(before, after))


async def _measure(drivers: tuple[Driver, Driver], connections: list[Connection], timing: Timing) -> FloodRun:
    offerer, answerer = drivers
    await asyncio.sleep(timing.warmup)

    # a count a second over the measured seconds, and the CPU of both processes over them
    samples = [await _counts(answerer, connections)]
    offerer.sampler.start()
    answerer.sampler.start()
    for _ in range(timing.measured):
        await asyncio.sleep(INTERVAL)
        samples.append(await _counts(answerer, connections))
    usage = offerer.sampler.stop(), answerer.sampler.stop()

    pairs = list(zip(samples, samples[1:]))
    return {
        'mbps': [_rate(before, after, 'bytes') * 8 / 1e6 for before, after in pairs],
        'messages_per_second': [_rate(before, after, 'messages') for before, after in pairs],
        'megabytes': sum(b['bytes'] - a['bytes'] for a, b in zip(samples[0], samples[-1])) / 1e6,
        'cpu_seconds': sum(u.cpu_seconds for u in usage),
    }


async def _flood(
    drivers: tuple[Driver, Driver], connections: list[Connection], *, cell: Cell, timing: Timing
) -> FloodRun:
    offerer = drivers[0]
    await asyncio.gather(*(c.open(ordered=cell.ordered) for c in connections))

    # the floods outlast the warmup and the measured seconds
    seconds = timing.warmup + (timing.measured + 1) * INTERVAL
    floods = asyncio.gather(
        *(
            offerer.flood(c.caller, size=cell.size, seconds=seconds, low=LOW_WATERMARK, high=HIGH_WATERMARK)
            for c in connections
        )
    )

    try:
        run = await _measure(drivers, connections, timing)
    except BaseException:
        floods.cancel()
        raise
    await floods
    return run


async def flood_run(library: str, cell: Cell, *, timing: Timing, log: IO[bytes]) -> FloodRun | None:
    """Floods the connections of a cell between a fresh pair of processes, or returns None if it failed."""
    async with pair(library, log) as (offerer, answerer):
        connections = [Connection(offerer, answerer, trickle=True) for _ in range(cell.connections)]
        try:
            return await _flood((offerer, answerer), connections, cell=cell, timing=timing)
        except DriverError as error:
            print(f'  flood failed: {error}', file=sys.stderr)
            return None
        finally:
            await asyncio.gather(*(connection.close() for connection in connections))


async def ping_run(library: str, timing: Timing, log: IO[bytes]) -> PingRun | None:
    """Measures round trips between a fresh pair of processes, or returns None if it failed."""
    async with pair(library, log) as (offerer, answerer):
        connection = Connection(offerer, answerer, trickle=True)
        try:
            await connection.open()
            await answerer.echo(connection.callee)
            pinged = await offerer.ping(connection.caller, size=PING_SIZE, rate=PING_RATE, seconds=timing.ping)
        except DriverError as error:
            print(f'  ping failed: {error}', file=sys.stderr)
            return None
        finally:
            await connection.close()
    return {'rtts_ms': pinged['rtts_ms'], 'sent': round(PING_RATE * timing.ping)}


def _name(cell: Cell | None) -> str:
    """Like ``ordered 64 KB x10`` or ``ping``: what ``--case`` matches."""
    return 'ping' if cell is None else cell.name


def _cases(options: Options) -> list[tuple[str, Cell | None]]:
    """The library and the cell (None for the ping) of each selected case, in a random order."""
    cells = [cell for cell in (*CELLS, None) if options.selects(_name(cell))]
    cases = [(library, cell) for library in options.libraries for cell in cells for _ in range(options.repeat)]
    random.shuffle(cases)
    return cases


def cases(options: Options) -> list[str]:
    """The name of every case of a run, selected or not."""
    del options
    return [_name(cell) for cell in (*CELLS, None)]


async def run(options: Options) -> dict[str, Results]:
    """Runs the floods and the pings of every library, the cases in a random order.

    Returns:
        The runs by library.
    """
    timing = Timing(warmup=1, measured=3, ping=3) if options.quick else Timing(warmup=2, measured=10, ping=10)
    results: dict[str, Results] = {
        library: {'flood': {cell.name: [] for cell in CELLS}, 'ping': []} for library in options.libraries
    }

    for library, cell in _cases(options):
        print(f'datachannel: {library} {_name(cell)}', file=sys.stderr, flush=True)
        if cell is None:
            results[library]['ping'].append(await ping_run(library, timing, options.log))
        else:
            results[library]['flood'][cell.name].append(await flood_run(library, cell, timing=timing, log=options.log))

    return results


def _runs(result: Results, cell: Cell) -> list[FloodRun]:
    return [run for run in result['flood'][cell.name] if run is not None]


def _mbps(runs: list[FloodRun]) -> float:
    return median([rate for run in runs for rate in run['mbps']])


def _messages_per_second(runs: list[FloodRun]) -> float:
    return median([rate for run in runs for rate in run['messages_per_second']])


def _cpu_ms_per_mb(runs: list[FloodRun]) -> float:
    return median([run['cpu_seconds'] * 1000 / run['megabytes'] for run in runs if run['megabytes'] > 0])


def _by_cell(data: dict[str, Results], metric: Callable[[list[FloodRun]], float]) -> dict[str, dict[str, float]]:
    """The metric of each cell and library."""
    return {cell.name: {name: metric(_runs(result, cell)) for name, result in data.items()} for cell in CELLS}


def _table(
    data: dict[str, Results], libraries: dict[str, Hello], metric: Callable[[list[FloodRun]], float]
) -> list[str]:
    others = [name for name in data if name != BASELINE]
    rows = [
        [
            cell,
            *(markdown.number(value, 0) for value in values.values()),
            *(markdown.percent_of(values[name], values.get(BASELINE, math.nan)) for name in others),
        ]
        for cell, values in _by_cell(data, metric).items()
    ]

    header = [
        'Flood',
        *(markdown.library(name, libraries) for name in data),
        *(f'{name}, % of {BASELINE}' for name in others),
    ]
    return markdown.table(header, rows)


def _rtts(result: Results) -> list[float]:
    return [rtt for run in result['ping'] if run is not None for rtt in run['rtts_ms']]


def _ping_row(name: str, result: Results, *, libraries: dict[str, Hello], baseline: float) -> list[str]:
    rtts = _rtts(result)
    lost = sum(run['sent'] - len(run['rtts_ms']) for run in result['ping'] if run is not None)
    return [
        markdown.library(name, libraries),
        markdown.spread(rtts),
        str(lost),
        markdown.percent_of(percentile(rtts, 0.5), baseline),
    ]


def render(data: dict[str, Results], libraries: dict[str, Hello]) -> list[str]:
    """The tables of the results: throughput, message rate, CPU per MB, then round trips."""
    lines = ['- Summed over the connections of a flood; % above 100 is faster.', '']

    lines += ['### Throughput (Mbps)', '', *_table(data, libraries, _mbps)]

    lines += ['### Message rate (messages/s)', '', *_table(data, libraries, _messages_per_second)]

    lines += [
        '### CPU per MB delivered, both processes (ms)',
        '',
        '- % below 100 is cheaper.',
        '',
        *_table(data, libraries, _cpu_ms_per_mb),
    ]

    baseline = percentile(_rtts(data[BASELINE]), 0.5) if BASELINE in data else math.nan
    pings = [_ping_row(name, result, libraries=libraries, baseline=baseline) for name, result in data.items()]
    lines += [
        f'### Round trip of {PING_SIZE // 1024} KB messages at {PING_RATE:.0f} a second',
        '',
        *markdown.table(['Library', 'RTT p50 / p95 (ms)', 'Lost', f'p50, % of {BASELINE}'], pings),
    ]

    return lines


def figures(data: dict[str, Results]) -> list[Figure]:
    """The charts of the throughput, the CPU per MB, and the round trip."""
    ping = {'1 KB at 100/s': {name: percentile(_rtts(result), 0.5) for name, result in data.items()}}

    return [
        Figure(
            'datachannel-throughput',
            'Data channel throughput',
            'Throughput',
            lower_is_better=False,
            values=_by_cell(data, _mbps),
        ),
        Figure(
            'datachannel-cpu',
            'Data channel CPU per MB delivered',
            'Efficiency',
            lower_is_better=True,
            values=_by_cell(data, _cpu_ms_per_mb),
        ),
        Figure('datachannel-rtt', 'Data channel round trip, p50', 'Speed', lower_is_better=True, values=ping),
    ]
