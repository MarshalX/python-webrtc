#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Video and audio: what receiving, sending and a call between two processes of a library cost.

Pion is the neutral peer: it sends pre-encoded files unchanged (IVF VP8, Annex B H.264, Ogg Opus) to a measured
receiver, and only counts the RTP of a measured sender (asking for the bitrate cap with REMB). The CPU is of the
measured processes alone, over a window after a warmup.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, TypedDict, TypeVar

from benchmarks import fixtures, markdown
from benchmarks.figures import Detail, Figure
from benchmarks.fixtures import Video
from benchmarks.markdown import BASELINE
from benchmarks.runner import MEDIA_LIBRARIES, DriverError, pair
from benchmarks.signaling import Connection
from benchmarks.stats import median

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable, Sequence
    from typing import IO

    from benchmarks.protocol import Hello, MediaStats
    from benchmarks.runner import Driver, Options, Usage, VideoSource

NO_VIDEO = Video(0, 0, 0, 0)
BATCH = 10
NEUTRAL = 'pion'
#: Opus packets a second a stream: 20 ms each
PACKETS_PER_SECOND = 50
#: the codecs each measured library can receive, send, and call with
CODECS: dict[str, dict[str, tuple[str, ...]]] = {
    'video_receive': {'wrtc': ('VP8', 'H264', 'H264-High'), 'aiortc': ('VP8', 'H264')},
    'video_send': {'wrtc': ('VP8', 'H264'), 'aiortc': ('VP8', 'H264')},
    'video_call': {'wrtc': ('VP8', 'VP9', 'AV1', 'H264'), 'aiortc': ('VP8', 'H264')},
}
#: the codecs of the files Pion sends
PION_CODECS = sorted({codec for codecs in CODECS['video_receive'].values() for codec in codecs})
#: the most aiortc's encoders target (it has no API for a cap), so the send cases cap both libraries there
SEND_CAPS = {'VP8': 1_500_000, 'H264': 3_000_000}


@dataclass(frozen=True)
class Plan:
    """The sizes and durations of a run."""

    videos: tuple[Video, ...]
    call_videos: tuple[Video, ...]
    streams: tuple[int, ...]
    warmup: float
    #: senders start at a low estimate of the bandwidth and ramp up
    send_warmup: float
    measured: float


QUICK = Plan(
    videos=(Video(1280, 720, 30, 2_500_000),),
    call_videos=(Video(1280, 720, 30, 2_500_000),),
    streams=(1, 10),
    warmup=2,
    send_warmup=3,
    measured=3,
)
FULL = Plan(
    videos=(
        Video(1280, 720, 30, 2_500_000),
        Video(1920, 1080, 30, 5_000_000),
        Video(1920, 1080, 60, 8_000_000),
        Video(3840, 2160, 30, 20_000_000),
    ),
    call_videos=(Video(1280, 720, 30, 2_500_000), Video(1920, 1080, 30, 5_000_000)),
    streams=(1, 10, 50),
    warmup=2,
    send_warmup=10,
    measured=10,
)


class VideoRun(TypedDict):
    """A video case of one pair of processes."""

    fps: float
    kbps: float | None
    cpu_ms_per_frame: float
    implementation: str
    #: a call: from writing a frame on one side to reading it on the other
    latencies_ms: list[float]
    #: a call: the sender's CPU
    sender_cpu_ms_per_frame: float | None


class AudioRun(TypedDict):
    """An audio case of one pair of processes."""

    cpu_percent_per_stream: float
    delivered: float
    lag_p95_ms: float | None


Run = TypeVar('Run', VideoRun, AudioRun)


class Results(TypedDict):
    """The runs of a measured library by kind, then case (None for a run that failed)."""

    video: dict[str, dict[str, list[VideoRun | None]]]
    audio: dict[str, dict[str, list[AudioRun | None]]]


class MediaResults(TypedDict):
    """The runs by measured library, ffmpeg's one-thread decode time a frame of each file Pion sends, the cases."""

    libraries: dict[str, Results]
    reference_ms: dict[str, float]
    #: the names of the cases in the order of the tables
    order: list[str]


@dataclass(frozen=True)
class Case:
    """A run to make: a kind, a measured library, and a codec and a video, or a count of audio streams."""

    kind: str
    library: str
    codec: str = ''
    video: Video = NO_VIDEO
    streams: int = 0

    @property
    def name(self) -> str:
        """Like ``VP8 720p30 2.5 Mbps`` or ``10 streams``."""
        if self.streams == 0:
            return f'{self.codec} {self.video.name}'
        return f'{self.streams} stream' if self.streams == 1 else f'{self.streams} streams'

    def source(self, path: str, *, numbered: bool = False) -> VideoSource:
        """The arguments of ``video_send`` for the case's video."""
        video = self.video
        return {
            'path': path,
            'width': video.width,
            'height': video.height,
            'fps': video.fps,
            'bitrate': video.bitrate,
            'numbered': numbered,
        }


def _counter(stats: MediaStats, key: Literal['frames', 'bytes', 'audio_ms']) -> float:
    if key == 'frames':
        return stats['frames']
    return stats.get('bytes', 0) if key == 'bytes' else stats.get('audio_ms', 0.0)


@dataclass(frozen=True)
class Window:
    """Stats at the start and the end of the measured window, and what the measured processes used meanwhile."""

    before: list[MediaStats]
    after: list[MediaStats]
    usage: list[Usage]
    lag_p95_ms: float | None
    #: the stats of the connection whose bytes give the bitrate, before and after
    rate: tuple[MediaStats, MediaStats]

    @property
    def seconds(self) -> float:
        """The length of the window, by the clock of the stats' driver."""
        return self.after[0]['t'] - self.before[0]['t']

    def delta(self, key: Literal['frames', 'bytes', 'audio_ms']) -> float:
        """How much of a counter all the connections added in the window."""
        return sum(_counter(a, key) - _counter(b, key) for a, b in zip(self.after, self.before))

    @property
    def kbps(self) -> float:
        """The bitrate of the window."""
        before, after = self.rate
        return (after.get('bytes', 0) - before.get('bytes', 0)) * 8 / (after['t'] - before['t']) / 1000

    def per_frame_ms(self, process: int) -> float:
        """The CPU of a measured process a frame of the window."""
        frames = self.delta('frames')
        return self.usage[process].cpu_seconds * 1000 / frames if frames > 0 else float('nan')


async def _measure(
    stats: tuple[Driver, list[int]], measured: list[Driver], *, rate: tuple[Driver, int], warmup: float, seconds: float
) -> Window:
    """Reads the stats around a window after a warmup, and what the measured processes used in it."""
    driver, pcs = stats
    await asyncio.sleep(warmup)
    await measured[0].probe()

    rate_before, before = await rate[0].media_stats(rate[1]), [await driver.media_stats(pc) for pc in pcs]
    for process in measured:
        process.sampler.start()
    await asyncio.sleep(seconds)
    usage = [process.sampler.stop() for process in measured]

    after, rate_after = [await driver.media_stats(pc) for pc in pcs], await rate[0].media_stats(rate[1])
    lag = (await measured[0].probe()).get('lag_p95_ms')
    return Window(before, after, usage, lag, (rate_before, rate_after))


def _video_run(window: Window, implementation: str) -> VideoRun:
    return {
        'fps': window.delta('frames') / window.seconds,
        'kbps': window.kbps,
        'cpu_ms_per_frame': window.per_frame_ms(0),
        'implementation': implementation,
        'latencies_ms': [],
        'sender_cpu_ms_per_frame': None,
    }


@contextlib.asynccontextmanager
async def _connection(library: str, log: IO[bytes], answering: str | None = None) -> AsyncGenerator[Connection, None]:
    """A connection between a fresh pair of processes, closed at the end."""
    async with pair(library, log, answering=answering) as (offerer, answerer):
        connection = Connection(offerer, answerer, trickle=True)
        try:
            yield connection
        finally:
            await connection.close()


async def _start_video(connection: Connection, case: Case, path: str, *, numbered: bool = False, remb: int = 0) -> None:
    """Connects with the offerer sending the case's video from a file and the answerer reading it."""
    await connection.create(codec=case.codec)
    await connection.offerer.video_send(connection.caller, case.source(path, numbered=numbered))
    await connection.answerer.media_sink(connection.callee, numbered=numbered, remb=remb)
    await connection.exchange()
    await connection.opened(track=True)


async def _receive(case: Case, plan: Plan, log: IO[bytes]) -> VideoRun:
    async with _connection(NEUTRAL, log, answering=case.library) as connection:
        await _start_video(connection, case, fixtures.encoded(case.video, case.codec))
        pion, measured = connection.offerer, connection.answerer
        stats, rate = (measured, [connection.callee]), (pion, connection.caller)
        window = await _measure(stats, [measured], rate=rate, warmup=plan.warmup, seconds=plan.measured)
        return _video_run(window, window.after[0]['implementation'])


async def _send(case: Case, plan: Plan, log: IO[bytes]) -> VideoRun:
    async with _connection(case.library, log, answering=NEUTRAL) as connection:
        await _start_video(connection, case, fixtures.raw(case.video), remb=case.video.bitrate)
        measured, pion = connection.offerer, connection.answerer
        stats = (pion, [connection.callee])
        window = await _measure(
            stats, [measured], rate=(pion, connection.callee), warmup=plan.send_warmup, seconds=plan.measured
        )
        return _video_run(window, (await measured.media_stats(connection.caller))['implementation'])


def _latencies(sent: MediaStats, window: Window) -> list[float]:
    """From writing to reading each numbered frame read in the window, by the system-wide monotonic clock."""
    written = dict(sent.get('numbers', []))
    start, end = window.before[0]['t'], window.after[0]['t']
    read = [(number, time) for number, time in window.after[0].get('numbers', []) if start <= time <= end]
    return [(time - written[number]) * 1000 for number, time in read if number in written]


async def _call(case: Case, plan: Plan, log: IO[bytes]) -> VideoRun:
    async with _connection(case.library, log) as connection:
        await _start_video(connection, case, fixtures.raw(case.video), numbered=True)

        sender, receiver = connection.offerer, connection.answerer
        stats, rate = (receiver, [connection.callee]), (sender, connection.caller)
        window = await _measure(stats, [receiver, sender], rate=rate, warmup=plan.send_warmup, seconds=plan.measured)

        run = _video_run(window, window.after[0]['implementation'])
        run['latencies_ms'] = _latencies(await sender.media_stats(connection.caller), window)
        run['sender_cpu_ms_per_frame'] = window.per_frame_ms(1)
        return run


async def _connect_audio(drivers: tuple[Driver, Driver], streams: int) -> list[Connection]:
    """Connections in batches, each sending the offerer's audio to a sink on the answerer."""
    offerer, answerer = drivers
    path = fixtures.opus()

    async def add() -> Connection:
        connection = Connection(offerer, answerer, trickle=True)
        await connection.create()
        await offerer.audio_send(connection.caller, path)
        await answerer.media_sink(connection.callee)
        await connection.exchange()
        await connection.opened(track=True)
        return connection

    connections: list[Connection] = []
    while len(connections) < streams:
        connections += await asyncio.gather(*(add() for _ in range(min(BATCH, streams - len(connections)))))
    return connections


async def _audio(case: Case, plan: Plan, log: IO[bytes]) -> AudioRun:
    """Audio streams from Pion to the library (receive) or the other way (send), read on the answering side."""
    sending = case.kind == 'audio_send'
    offering, answering = (case.library, NEUTRAL) if sending else (NEUTRAL, case.library)
    async with pair(offering, log, answering=answering) as (offerer, answerer):
        connections = await _connect_audio((offerer, answerer), case.streams)
        try:
            pcs = [connection.callee for connection in connections]
            measured = offerer if sending else answerer
            window = await _measure(
                (answerer, pcs), [measured], rate=(answerer, pcs[0]), warmup=plan.warmup, seconds=plan.measured
            )
        finally:
            await asyncio.gather(*(connection.close() for connection in connections))

    expected_seconds = case.streams * window.seconds
    # Pion counts the packets it gets, 50 a second, the libraries the audio they read
    delivered = (
        window.delta('frames') / (expected_seconds * PACKETS_PER_SECOND)
        if sending
        else window.delta('audio_ms') / (expected_seconds * 1000)
    )

    return {
        'cpu_percent_per_stream': window.usage[0].cpu_seconds / expected_seconds * 100,
        'delivered': delivered,
        'lag_p95_ms': window.lag_p95_ms,
    }


VIDEO_RUNS = {'video_receive': _receive, 'video_send': _send, 'video_call': _call}
AUDIO_KINDS = ('audio_receive', 'audio_send')


def _case(kind: str, library: str, *, codec: str, video: Video) -> Case:
    if kind == 'video_send':
        bitrate = min(video.bitrate, SEND_CAPS[codec])
        video = Video(video.width, video.height, video.fps, bitrate)
    return Case(kind, library, codec, video)


def _measured(options: Options) -> list[str]:
    """The libraries measured: those with media, but the neutral peer."""
    return [library for library in options.libraries if library in MEDIA_LIBRARIES and library != NEUTRAL]


def _cases(options: Options, plan: Plan) -> list[Case]:
    """Every case of the measured libraries, in the order of the tables."""
    cases: list[Case] = []
    for library in _measured(options):
        for kind, codecs in CODECS.items():
            videos = plan.call_videos if kind == 'video_call' else plan.videos
            cases += [
                _case(kind, library, codec=codec, video=video) for codec in codecs.get(library, ()) for video in videos
            ]
        cases += [Case(kind, library, streams=n) for kind in AUDIO_KINDS for n in plan.streams]
    return cases


async def _attempt(run: Awaitable[Run]) -> Run | None:
    """The result of a run, or None if a driver failed it."""
    try:
        return await run
    except DriverError as error:
        print(f'  failed: {error}', file=sys.stderr)
        return None


async def _record(case: Case, plan: Plan, log: IO[bytes], *, results: Results) -> None:
    """Runs a case into the results, None if it failed."""
    print(f'media: {case.library} {case.kind} {case.name}', file=sys.stderr, flush=True)
    if case.kind in AUDIO_KINDS:
        audio = await _attempt(_audio(case, plan, log))
        results['audio'].setdefault(case.kind, {}).setdefault(case.name, []).append(audio)
    else:
        video = await _attempt(VIDEO_RUNS[case.kind](case, plan, log))
        results['video'].setdefault(case.kind, {}).setdefault(case.name, []).append(video)


def prepare(plan: Plan) -> None:
    """Generates every fixture of the plan up front, so that generating none competes with a case for the CPU."""
    fixtures.opus()
    for video in {*plan.videos, *plan.call_videos}:
        fixtures.raw(video)
    for video in plan.videos:
        for codec in PION_CODECS:
            fixtures.encoded(video, codec)


def _references(plan: Plan) -> dict[str, float]:
    """Ffmpeg's decode time a frame of every file Pion sends."""
    references: dict[str, float] = {}
    for codec in PION_CODECS:
        for video in plan.videos:
            path = fixtures.encoded(video, codec)
            references[Case('video_receive', NEUTRAL, codec, video).name] = fixtures.ffmpeg_decode_ms(
                path, fixtures.SECONDS * video.fps
            )
    return references


async def run(options: Options) -> MediaResults:
    """Runs every case of the measured libraries; Pion is the neutral peer, whatever the libraries.

    Returns:
        The runs by library, and ffmpeg's reference decode times.
    """
    plan = QUICK if options.quick else FULL
    prepare(plan)
    references = _references(plan)

    results: dict[str, Results] = {library: {'video': {}, 'audio': {}} for library in _measured(options)}
    cases = _cases(options, plan)
    shuffled = cases * options.repeat
    random.shuffle(shuffled)
    for case in shuffled:
        await _record(case, plan, options.log, results=results[case.library])

    order = list(dict.fromkeys(case.name for case in cases))
    return {'libraries': results, 'reference_ms': references, 'order': order}


@dataclass(frozen=True)
class Column(Generic[Run]):
    """A column of each library in a table: its title and its cell from the runs of a case."""

    title: str
    cell: Callable[[list[Run]], str]


def _median_of(values: Iterable[float | None]) -> float:
    return median([value for value in values if value is not None])


def _kbps(runs: list[VideoRun]) -> float:
    return _median_of(run['kbps'] for run in runs)


def _fps(runs: list[VideoRun]) -> float:
    return _median_of(run['fps'] for run in runs)


def _cpu(runs: list[VideoRun]) -> float:
    return _median_of(run['cpu_ms_per_frame'] for run in runs)


def _audio_cpu(runs: list[AudioRun]) -> float:
    return _median_of(run['cpu_percent_per_stream'] for run in runs)


def _implementation(runs: list[VideoRun]) -> str:
    return runs[0]['implementation'] if len(runs) != 0 else '-'


def _fps_cell(runs: list[VideoRun]) -> str:
    return markdown.number(_fps(runs))


def _kbps_cell(runs: list[VideoRun]) -> str:
    return markdown.number(_kbps(runs), 0)


def _latency(runs: list[VideoRun]) -> str:
    return markdown.spread([latency for run in runs for latency in run['latencies_ms']])


def _cpus(runs: list[VideoRun]) -> str:
    sender = markdown.number(_median_of(run['sender_cpu_ms_per_frame'] for run in runs))
    return f'{markdown.number(_cpu(runs))} / {sender}'


def _columns(codec: str) -> list[Column[VideoRun]]:
    """The columns of a video kind: its codec's implementation, the frame rate and the bitrate."""
    return [Column(codec, _implementation), Column('fps', _fps_cell), Column('kbps', _kbps_cell)]


VIDEO_COLUMNS: dict[str, list[Column[VideoRun]]] = {
    'video_receive': [*_columns('decoder'), Column('CPU/frame (ms)', lambda runs: markdown.number(_cpu(runs)))],
    'video_send': [*_columns('encoder'), Column('CPU/frame (ms)', lambda runs: markdown.number(_cpu(runs)))],
    'video_call': [
        *_columns('decoder'),
        Column('latency p50 / p95 (ms)', _latency),
        Column('receiver / sender CPU/frame (ms)', _cpus),
    ],
}
AUDIO_COLUMNS: list[Column[AudioRun]] = [
    Column('CPU per stream (% of a core)', lambda runs: markdown.number(_audio_cpu(runs), 2)),
    Column('delivered', lambda runs: f'{_median_of(run["delivered"] for run in runs):.0%}'),
    Column('loop lag p95 (ms)', lambda runs: markdown.number(_median_of(run['lag_p95_ms'] for run in runs))),
]


def _table(
    by_library: dict[str, dict[str, list[Run | None]]],
    order: list[str],
    *,
    columns: Sequence[Column[Run]],
    compare: Callable[[list[Run]], float],
    reference: dict[str, float] | None = None,
) -> list[str]:
    """A row a case, its reference if any, the columns of each library, then each compared to the baseline's."""
    names = list(by_library)
    others = [name for name in names if name != BASELINE]
    cases = [case for case in order if any(case in runs for runs in by_library.values())]

    rows: list[list[str]] = []
    for case in cases:
        runs = {name: [run for run in by_library[name].get(case, []) if run is not None] for name in names}
        cells = [column.cell(runs[name]) if len(runs[name]) != 0 else '-' for name in names for column in columns]

        baseline = compare(runs[BASELINE]) if len(runs.get(BASELINE, [])) != 0 else float('nan')
        compared = [
            markdown.percent_of(compare(runs[name]), baseline) if len(runs[name]) != 0 else '-' for name in others
        ]
        rows.append([case, *_reference(reference, case), *cells, *compared])

    header = [f'{name} {column.title}' for name in names for column in columns]
    compared_header = [f'{name}, % of {BASELINE}' for name in others]
    return markdown.table(['Case', *_reference(reference), *header, *compared_header], rows)


def _reference(reference: dict[str, float] | None, case: str | None = None) -> list[str]:
    """The reference column's cell of a case, or its title without a case; nothing without a reference."""
    if reference is None:
        return []
    return ['ffmpeg CPU/frame (ms)' if case is None else markdown.number(reference.get(case))]


def _video_runs(data: MediaResults, kind: str) -> dict[str, dict[str, list[VideoRun | None]]]:
    return {name: result['video'].get(kind, {}) for name, result in data['libraries'].items()}


def _audio_runs(data: MediaResults, kind: str) -> dict[str, dict[str, list[AudioRun | None]]]:
    return {name: result['audio'].get(kind, {}) for name, result in data['libraries'].items()}


def _video(data: MediaResults, kind: str, reference: dict[str, float] | None = None) -> list[str]:
    return _table(
        _video_runs(data, kind), data['order'], columns=VIDEO_COLUMNS[kind], compare=_cpu, reference=reference
    )


def _audio_table(data: MediaResults, kind: str) -> list[str]:
    return _table(_audio_runs(data, kind), data['order'], columns=AUDIO_COLUMNS, compare=_audio_cpu)


def libraries(data: MediaResults) -> list[str]:
    """The measured libraries in the results of a run."""
    return list(data['libraries'])


def merge(older: MediaResults, newer: MediaResults) -> MediaResults:
    """The results of two runs, a library's from the newer one if it has them."""
    return {
        'libraries': {**older['libraries'], **newer['libraries']},
        'reference_ms': {**older['reference_ms'], **newer['reference_ms']},
        'order': list(dict.fromkeys(older['order'] + newer['order'])),
    }


def render(data: MediaResults, libraries: dict[str, Hello]) -> list[str]:
    """The tables of the results: video received, sent, in a call, then audio received and sent."""
    del libraries
    lines = ['- Pion is the peer. CPU of the measured process; % below 100 is cheaper.', '']

    lines += [
        '### Video receive',
        '',
        '- ffmpeg: decoding the same file on one thread, for reference.',
        '',
        *_video(data, 'video_receive', data['reference_ms']),
    ]

    lines += [
        '### Video send',
        '',
        "- Caps lowered to aiortc's maximum (1.5 Mbps VP8, 3 Mbps H.264); read CPU with fps and kbps.",
        '',
        *_video(data, 'video_send'),
    ]

    lines += [
        '### Video call',
        '',
        '- Latency: a frame written to read. Each library sets its own bitrate: read CPU with kbps.',
        '',
        *_video(data, 'video_call'),
    ]

    lines += [
        '### Audio receive',
        '',
        '- One Opus stream a connection; delivered: audio read over real time.',
        '',
        *_audio_table(data, 'audio_receive'),
    ]

    lines += [
        '### Audio send',
        '',
        '- One tone a connection; delivered: packets Pion got over 50 a second.',
        '',
        *_audio_table(data, 'audio_send'),
    ]

    return lines


def _values(
    by_library: dict[str, dict[str, list[Run | None]]], order: list[str], metric: Callable[[list[Run]], float]
) -> dict[str, dict[str, float]]:
    """The metric of the runs of each case and library that has any."""
    values: dict[str, dict[str, float]] = {}
    for case in order:
        for name, cases in by_library.items():
            runs = [run for run in cases.get(case, []) if run is not None]
            if len(runs) != 0:
                values.setdefault(case, {})[name] = metric(runs)
    return values


def _video_values(
    data: MediaResults, kind: str, metric: Callable[[list[VideoRun]], float]
) -> dict[str, dict[str, float]]:
    return _values(_video_runs(data, kind), data['order'], metric)


def _audio_values(data: MediaResults) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    for kind, verb in (('audio_receive', 'receive'), ('audio_send', 'send')):
        for case, value in _values(_audio_runs(data, kind), data['order'], _audio_cpu).items():
            values[f'{verb}, {case}'] = value
    return values


def _videos(kind: str) -> dict[str, Video]:
    """The video of each case of a kind in either plan, by case name: a send's bitrate is its cap."""
    videos: dict[str, Video] = {}
    for plan in (QUICK, FULL):
        for video in plan.call_videos if kind == 'video_call' else plan.videos:
            for codec in {codec for codecs in CODECS[kind].values() for codec in codecs}:
                case = _case(kind, '', codec=codec, video=video)
                videos[case.name] = case.video
    return videos


def _of_target(
    data: MediaResults, kind: str, *, metric: Callable[[list[VideoRun]], float], target: Callable[[Video], float]
) -> dict[str, dict[str, float]]:
    """A metric of each case over its target, like the fps sent over the source's."""
    videos = _videos(kind)
    return {
        case: {name: value / target(videos[case]) for name, value in by.items()}
        for case, by in _video_values(data, kind, metric).items()
        if case in videos
    }


def _latency_p50(runs: list[VideoRun]) -> float:
    return median([latency for run in runs for latency in run['latencies_ms']])


def figures(data: MediaResults) -> list[Figure]:
    """The charts of the CPU of each video kind, the latency of a call, and the CPU of audio."""
    cpu = 'Efficiency'
    return [
        Figure(
            'media-video-receive',
            'Video receive: CPU per frame',
            cpu,
            lower_is_better=True,
            values=_video_values(data, 'video_receive', _cpu),
        ),
        Figure(
            'media-video-send',
            'Video send: CPU per frame, under a bitrate cap',
            cpu,
            lower_is_better=True,
            values=_video_values(data, 'video_send', _cpu),
            details=(
                Detail(
                    'fps / source',
                    _of_target(data, 'video_send', metric=_fps, target=lambda video: video.fps),
                    of_target=True,
                ),
                Detail(
                    'kbps / cap',
                    _of_target(data, 'video_send', metric=_kbps, target=lambda video: video.bitrate / 1000),
                    of_target=True,
                ),
            ),
        ),
        Figure(
            'media-video-call',
            'Video call: receiver CPU per frame, at the bitrate each library chose',
            cpu,
            lower_is_better=True,
            values=_video_values(data, 'video_call', _cpu),
            details=(Detail('kbps', _video_values(data, 'video_call', _kbps)),),
        ),
        Figure(
            'media-video-latency',
            'Video call: latency p50',
            'Speed',
            lower_is_better=True,
            values=_video_values(data, 'video_call', _latency_p50),
        ),
        Figure('media-audio', 'Audio: CPU per stream', cpu, lower_is_better=True, values=_audio_values(data)),
    ]
