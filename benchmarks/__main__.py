#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Runs the benchmarks and writes their results as Markdown.

python -m benchmarks                  # everything, about 15 minutes
python -m benchmarks --quick          # a few seconds of each, no soak
python -m benchmarks --only loopback  # one group: copy, loopback, audio, slow, soak
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import pathlib
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from benchmarks import media
from benchmarks.measure import machine

if TYPE_CHECKING:
    from collections.abc import Collection

RESOLUTIONS = [(320, 240), (640, 480), (1280, 720), (1920, 1080)]
GROUPS = ('copy', 'loopback', 'audio', 'slow', 'soak')


def _mb(value: int) -> str:
    return f'{value / 1e6:.0f}'


def _commit() -> str:
    git = shutil.which('git')
    if git is None:
        return 'unknown'
    try:
        commit = subprocess.check_output([git, 'rev-parse', '--short', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output([git, 'status', '--porcelain'], text=True).strip()
        return commit + (' with uncommitted changes' if dirty != '' else '')
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


async def _copy(budget: float) -> list[str]:
    _log('copy: VideoFrame.copy_to per format and size')
    results = await media.copy_costs(RESOLUTIONS, budget=budget)
    lines = ['## VideoFrame.copy_to', '', 'The cost of a copy of the planes (I420) or of a conversion to RGB.', '']
    lines += ['| Size | Format | ms per frame | Megapixels/s |', '| --- | --- | --- | --- |']
    lines += [
        f'| {r.width}x{r.height} | {r.format} | {r.milliseconds:.3f} | {r.megapixels_per_second:.0f} |' for r in results
    ]
    construct = media.construct_cost(1920, 1080, budget=budget)
    return [*lines, '', f'Creating a 1920x1080 I420 VideoFrame from bytes (a copy of them): {construct:.3f} ms.', '']


async def _loopback(seconds: int) -> list[str]:
    lines = [
        '## Video through a connection',
        '',
        (
            f'Frames written to a VideoTrackGenerator at 30 fps for {seconds} s (after a warmup), sent over VP8, '
            'read from a MediaStreamTrackProcessor of the remote track (buffer of 1 frame). Latency is from the '
            'write to the read, matched by a frame number drawn in the pixels. Lag is how late the event loop runs '
            'a 5 ms timer.'
        ),
        '',
        (
            '| Size | Delivered fps | Sent | Received | Received sizes | Dropped by the processor '
            '| Latency p50 / p95 (ms) | Loop lag p95 / max (ms) | CPU | RSS start / end (MB) |'
        ),
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for width, height in RESOLUTIONS:
        _log(f'loopback: {width}x{height}')
        r = await media.VideoLoopback(width, height, seconds=seconds).run()
        lines.append(
            f'| {width}x{height} | {r.delivered_fps:.1f} | {r.sent} | {r.received} | {r.received_sizes} '
            f'| {r.discarded} '
            f'| {r.latency_p50_ms:.0f} / {r.latency_p95_ms:.0f} | {r.lag_p95_ms:.1f} / {r.lag_max_ms:.1f} '
            f'| {r.usage.cpu_percent:.0f}% | {_mb(r.usage.rss_start)} / {_mb(r.usage.rss_end)} |'
        )
    return [*lines, '']


async def _audio(seconds: int) -> list[str]:
    _log(f'audio: 48 kHz stereo for {seconds} s')
    r = await media.audio_loopback(channels=2, seconds=seconds)
    return [
        '## Audio through a connection',
        '',
        (
            f'10 ms chunks of 48 kHz stereo written to a MediaStreamTrackGenerator in real time for {seconds} s, '
            'sent over Opus, read from a MediaStreamTrackProcessor of the remote track.'
        ),
        '',
        (
            '| Written | Received | Chunks/s | Frames received | Dropped | Loop lag p95 (ms) | CPU '
            '| RSS start / end (MB) |'
        ),
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
        (
            f'| {r.written} | {r.received} | {r.chunks_per_second:.1f} | {r.received_frames} | {r.discarded} '
            f'| {r.lag_p95_ms:.1f} | {r.usage.cpu_percent:.0f}% '
            f'| {_mb(r.usage.rss_start)} / {_mb(r.usage.rss_end)} |'
        ),
        '',
    ]


async def _slow(seconds: int) -> list[str]:
    _log('slow: a consumer taking 100 ms per frame, 720p')
    r = await media.VideoLoopback(1280, 720, seconds=seconds, consumer_delay=0.1, rss_every=1).run()
    return [
        '## Slow consumer',
        '',
        (
            f'720p at 30 fps read by a consumer that takes 100 ms per frame, for {seconds} s: the processor drops '
            "the frames it can't deliver, so memory stays flat."
        ),
        '',
        '| Delivered fps | Dropped by the processor | RSS start / end (MB) | RSS slope (MB/min) |',
        '| --- | --- | --- | --- |',
        (
            f'| {r.delivered_fps:.1f} | {r.discarded} | {_mb(r.usage.rss_start)} / {_mb(r.usage.rss_end)} '
            f'| {r.rss_slope:+.2f} |'
        ),
        '',
    ]


async def _soak() -> list[str]:
    _log('soak: 720p for 10 minutes')
    r = await media.VideoLoopback(1280, 720, seconds=600, rss_every=10).run()
    return [
        '## Soak',
        '',
        '720p at 30 fps through a connection for 10 minutes, the resident memory sampled every 10 s.',
        '',
        (
            '| Delivered fps | Latency p95 (ms) | CPU | RSS start / end (MB) | RSS slope (MB/min) '
            '| RSS slope, second half (MB/min) |'
        ),
        '| --- | --- | --- | --- | --- | --- |',
        (
            f'| {r.delivered_fps:.1f} | {r.latency_p95_ms:.0f} | {r.usage.cpu_percent:.0f}% '
            f'| {_mb(r.usage.rss_start)} / {_mb(r.usage.rss_end)} | {r.rss_slope:+.2f} '
            f'| {r.rss_slope_second_half:+.2f} |'
        ),
        '',
        'RSS samples (s, MB): ' + ', '.join(f'{t:.0f}: {b / 1e6:.0f}' for t, b in r.rss),
        '',
    ]


async def run(groups: Collection[str], *, quick: bool) -> str:
    """Runs the benchmark groups and returns their results as Markdown."""
    seconds = 5 if quick else 30
    lines = [
        '# Benchmarks',
        '',
        (
            f'{datetime.datetime.now().astimezone().date().isoformat()}, {machine()}, commit {_commit()}. '
            f'Written by `python -m benchmarks{" --quick" if quick else ""}`.'
        ),
        '',
        (
            'Both peers run in one process on the machine, so encoding, decoding and Python share its cores. '
            'CPU is of one core (100% is a core busy).'
        ),
        '',
    ]
    if 'copy' in groups:
        lines += await _copy(0.3 if quick else 1.0)
    if 'loopback' in groups:
        lines += await _loopback(seconds)
    if 'audio' in groups:
        lines += await _audio(5 if quick else 60)
    if 'slow' in groups:
        lines += await _slow(seconds)
    if 'soak' in groups and not quick:
        lines += await _soak()
    return '\n'.join(lines)


def main() -> None:
    """Runs the benchmarks of the command line and writes the results."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks', description=__doc__.split('\n')[0])
    parser.add_argument('--quick', action='store_true', help='a few seconds of each benchmark, without the soak')
    parser.add_argument('--only', choices=GROUPS, action='append', help='run a group only (repeatable)')
    parser.add_argument(
        '--output', type=pathlib.Path, default=pathlib.Path(__file__).with_name('RESULTS.md'), help='the results file'
    )
    args = parser.parse_args()
    report = asyncio.run(run(args.only or GROUPS, quick=args.quick))
    args.output.write_text(report + '\n')
    print(report)


if __name__ == '__main__':
    main()
