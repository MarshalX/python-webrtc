#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The outcome of a hunt job and the signature of its failure, which groups the runs that hit the same bug.

python -m scripts.debug.triage build/hunt/<signature>/<bundle>   # the signature again, after changing the rules
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import re
import signal
from dataclasses import dataclass
from typing import TypedDict

#: Outcomes of a failed run, the most severe first
FAILURES = ('crash', 'hang', 'leak', 'memory', 'failure')

#: They keep everything else alive, and what else is left varies from run to run
LEAK_OWNERS = ('factories', 'RTCPeerConnection')

TOP_FRAMES = 5
HANG_FRAMES = 6
TSAN_FRAMES = 3
TOP_PYTHON_FRAMES = 3
UBSAN_WORDS = 6
FAILED_TESTS = 3

_ASAN = re.compile(r'ERROR: AddressSanitizer: (\S+)')
_TSAN = re.compile(r'WARNING: ThreadSanitizer: (.+?) \(pid')
_UBSAN = re.compile(r'^\S+:\d+:\d+: runtime error: (.+)$', re.MULTILINE)
_LSAN = re.compile(r'ERROR: LeakSanitizer')
_SANITIZER_FRAME = re.compile(r'^\s*#(\d+) (?:0x[0-9a-f]+ in )?(.+)$')
_SANITIZER_LOCATION = re.compile(r'(?: \([^ ()]+\)|\s*\+0x[0-9a-f]+| \S+:\d+(?::\d+)?)+$')
_SANITIZER_MODULE = re.compile(r'\(([^ ()]+?)(?::\w+)?\+0x[0-9a-f]+\)$')
_SANITIZER_RUNTIME = (
    '__asan', '__tsan', '__ubsan', '__sanitizer', '__interceptor', 'wrap_', 'malloc', 'free', 'operator new',
    'operator delete',
)  # fmt: skip

_CHAOS_START = re.compile(r'^seed \d+, \d+ steps$', re.MULTILINE)
_CHAOS_DONE = re.compile(r'^done, (\d+) factories alive, native objects alive: (\{.*\})$', re.MULTILINE)
_CHAOS_STUCK = re.compile(r'^(?:step \d+ )?(.+) is stuck$', re.MULTILINE)
_CHECK_FAILED = re.compile(r'^# (Check failed: .+)$', re.MULTILINE)

_THREAD = re.compile(r'^\s*\*?\s*thread #\d+|^Thread \d+ ')
_LLDB_FRAME = re.compile(r'^\s*\*?\s*frame #\d+: 0x[0-9a-f]+ [^`]+`(.+?)(?: \+ \d+)?(?: at \S+)?(?: \[\w+\])*$')
_GDB_FRAME = re.compile(r'^#\d+\s+(?:0x[0-9a-f]+ in )?(.+?)(?: (?:at|from) \S+)?$')
_GDB_SIGNAL_FRAME = '<signal handler called>'

_PYTHON_THREAD = re.compile(r'^(?:Current thread|Thread) 0x[0-9a-f]+ .*\(most recent call first\):$')
_PYTHON_FRAME = re.compile(r'^\s+File "(.+)", line \d+ in (\S+)')
_PYTEST_FAILED = re.compile(r'^(?:FAILED|ERROR) ([^\s\[]+)', re.MULTILINE)
_EXCEPTION = re.compile(r'^(?:\w+\.)*(\w+(?:Error|Exception|Interrupt))\b', re.MULTILINE)
_TRACEBACK_FRAME = re.compile(r'^\s+File ".+", line \d+, in (\S+)$', re.MULTILINE)


class _Frame(TypedDict):
    symbol: str
    imageIndex: int


class _Image(TypedDict):
    name: str


class _Thread(TypedDict):
    frames: list[_Frame]


class _CrashReport(TypedDict):
    """The parts of a macOS crash report (.ips) used here."""

    pid: int
    faultingThread: int
    threads: list[_Thread]
    usedImages: list[_Image]


class BundleInfo(TypedDict):
    """The info.json of a bundle."""

    job: str
    seed: int | None
    outcome: str
    signature: str
    reason: str | None
    argv: list[str]
    repro: str
    env_added: dict[str, str]
    cwd: str
    git_head: str | None
    worktree_sha1: str | None
    started: str
    duration_s: float
    pid: int
    returncode: int
    peak_rss_mb: int
    cores: list[str]
    platform: str


@dataclass(frozen=True)
class Evidence:
    """What a finished run left behind."""

    job: str
    pid: int
    output: str
    returncode: int
    #: Why the runner stopped the run: stuck, silent, wall or memory
    killed: str | None = None
    #: The ``<pid>-<tool>.txt`` files of the stacks tool
    stacks: pathlib.Path | None = None
    crash_report: pathlib.Path | None = None


def classify(evidence: Evidence) -> str:
    """The outcome of a run: pass, or one of FAILURES."""
    ended = _abnormal_end(evidence)
    if ended is not None:
        return ended
    leaked = _leaked(evidence.output)
    if leaked is not None and leaked != []:
        return 'leak'
    unfinished_chaos = _CHAOS_START.search(evidence.output) is not None and leaked is None
    return 'failure' if evidence.returncode != 0 or unfinished_chaos else 'pass'


def _abnormal_end(evidence: Evidence) -> str | None:
    if _sanitizer(evidence.output) is not None:
        return 'crash'
    if evidence.killed is not None:
        # the runner's own SIGABRT after the stacks isn't a crash
        return 'memory' if evidence.killed == 'memory' else 'hang'
    if evidence.returncode >= 0:
        return None
    # killed by jetsam or the OOM killer
    return 'memory' if evidence.returncode == -signal.SIGKILL else 'crash'


def signature(outcome: str, evidence: Evidence) -> str:
    """The same text for runs that hit the same bug, starting with the outcome."""
    describe = {'crash': _crash, 'hang': _hang, 'leak': _leak, 'failure': _failure}.get(outcome)
    return f'{outcome} {describe(evidence) if describe is not None else evidence.job}'


def slug(text: str) -> str:
    """A directory name for a signature: its outcome, some readable text, a hash."""
    outcome, _, rest = text.partition(' ')
    readable = re.sub(r'[^A-Za-z0-9_.-]+', '_', rest).strip('_')[:40]
    return f'{outcome}-{readable}-{hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:8]}'


def crash_report_pid(path: pathlib.Path) -> int | None:
    """The process of a macOS crash report (.ips: a JSON header line, then a JSON body)."""
    report = _crash_report(path)
    return report.get('pid') if report is not None else None


def normalize(frame: str) -> str:
    """A symbol without what changes between builds and runs: addresses, offsets, parameters, clones."""
    frame = re.sub(r'\[clone [^\]]*\]|\[abi:[^\]]*\]|\(anonymous namespace\)::|\.llvm\.\d+', '', frame)
    frame = re.sub(r'\$_\d+', '$_', frame)
    frame = frame.replace('operator()', 'operator<call>')
    while True:
        stripped = re.sub(r'\([^()]*\)', '', frame)
        if stripped == frame:
            break
        frame = stripped
    # gdb wraps long argument lists to the next line
    frame = re.sub(r'\s*\(.*$|\s+const$|\s+0x[0-9a-f]+\b', '', frame)
    return frame.replace('operator<call>', 'operator()').strip()


def _sanitizer(output: str) -> str | None:
    for name, pattern in (('asan', _ASAN), ('tsan', _TSAN)):
        if (match := pattern.search(output)) is not None:
            return f'{name} {match[1]}'
    if (match := _UBSAN.search(output)) is not None:
        words = re.sub(r'0x[0-9a-f]+|\d+', 'N', match[1]).split()[:UBSAN_WORDS]
        return f'ubsan {" ".join(words)}'
    return 'lsan leak' if _LSAN.search(output) is not None else None


def _leaked(output: str) -> list[str] | None:
    match = _CHAOS_DONE.search(output)
    if match is None:
        return None
    alive: dict[str, int] = ast.literal_eval(match[2])
    return sorted(alive) + (['factories'] if int(match[1]) > 0 else [])


def _leak(evidence: Evidence) -> str:
    leaked = _leaked(evidence.output)
    names: list[str] = leaked if leaked is not None else []
    owners = [name for name in names if name in LEAK_OWNERS]
    return f'{evidence.job}: {", ".join(owners if owners != [] else names)}'


def _sanitizer_stacks(output: str) -> list[list[str]]:
    stacks: list[list[str]] = []
    for line in output.splitlines():
        match = _SANITIZER_FRAME.match(line)
        if match is None:
            continue
        if match[1] == '0':
            stacks.append([])
        symbol = _sanitizer_symbol(match[2])
        if stacks != [] and not symbol.startswith(_SANITIZER_RUNTIME):
            stacks[-1].append(normalize(symbol))
    return stacks


def _sanitizer_symbol(frame: str) -> str:
    symbol = _SANITIZER_LOCATION.sub('', frame).strip()
    # unsymbolized: the address changes with every run, the module doesn't
    if re.fullmatch(r'0x[0-9a-f]+', symbol) is not None and (module := _SANITIZER_MODULE.search(frame)) is not None:
        return pathlib.PurePath(module[1]).name
    return symbol


def _crash(evidence: Evidence) -> str:
    kind = _sanitizer(evidence.output)
    if kind is not None:
        stacks = _sanitizer_stacks(evidence.output)
        if kind.startswith('tsan'):
            # which of the two racing accesses is reported first varies
            frames = sorted(' | '.join(stack[:TSAN_FRAMES]) for stack in stacks[:2])
            return f'{kind}: {" || ".join(frames)}'
        return f'{kind}: {" | ".join(stacks[0][:TOP_FRAMES] if stacks != [] else [])}'
    name = signal.Signals(-evidence.returncode).name
    frames = _crash_report_frames(evidence.crash_report)
    if frames == []:
        frames = _core_frames(evidence)
    if frames == []:
        frames = _python_crash_frames(evidence.output)
    check = _CHECK_FAILED.search(evidence.output)
    return f'{name}: {" | ".join([*([check[1]] if check is not None else []), *frames])}'


def _crash_report(path: pathlib.Path) -> _CrashReport | None:
    try:
        _header, body = path.read_text(encoding='utf-8').split('\n', 1)
        report: _CrashReport = json.loads(body)
    except (OSError, ValueError):
        return None
    return report


def _crash_report_frames(path: pathlib.Path | None) -> list[str]:
    report = _crash_report(path) if path is not None else None
    if report is None:
        return []
    images = report['usedImages']
    frames = [
        (frame.get('symbol', '???'), images[frame['imageIndex']].get('name', '???'))
        for frame in report['threads'][report['faultingThread']]['frames']
    ]
    # the frames above it are faulthandler raising the signal again
    symbols = [symbol for symbol, _image in frames]
    if '_sigtramp' in symbols:
        frames = frames[symbols.index('_sigtramp') + 1 :]
    kept = [
        f'{normalize(symbol)} ({image})'
        for symbol, image in frames
        if not image.startswith('libsystem_') and symbol not in {'abort', 'raise'}
    ]
    return kept[:TOP_FRAMES]


def _core_frames(evidence: Evidence) -> list[str]:
    path = evidence.stacks / f'{evidence.pid}-core.txt' if evidence.stacks is not None else None
    if path is None or not path.exists():
        return []
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    frames = [match[1] for line in lines if (match := _GDB_FRAME.match(line)) is not None]
    # the frames above it are faulthandler raising the signal again
    if _GDB_SIGNAL_FRAME in frames:
        frames = frames[len(frames) - frames[::-1].index(_GDB_SIGNAL_FRAME) :]
    return [symbol for symbol in map(normalize, frames) if symbol != '??'][:TOP_FRAMES]


def _python_threads(output: str) -> list[list[tuple[str, str]]]:
    threads: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] | None = None
    for line in output.splitlines():
        if _PYTHON_THREAD.match(line) is not None:
            current = []
            threads.append(current)
        elif current is not None and (match := _PYTHON_FRAME.match(line)) is not None:
            current.append((match[1], match[2]))
        else:
            current = None
    return threads


def _python_crash_frames(output: str) -> list[str]:
    start = output.find('Current thread 0x')
    if start == -1:
        return []
    threads = _python_threads(output[start:])
    if threads == []:
        return []
    return [f'{function} ({pathlib.Path(file).name})' for file, function in threads[0][:TOP_PYTHON_FRAMES]]


def _native_threads(text: str) -> list[list[str]]:
    threads: list[list[str]] = []
    for line in text.splitlines():
        if _THREAD.match(line) is not None:
            threads.append([])
            continue
        match = _LLDB_FRAME.match(line)
        if match is None:
            match = _GDB_FRAME.match(line)
        if match is not None and threads != []:
            threads[-1].append(match[1])
    return threads


def _blocked_in_library(text: str) -> list[str]:
    blocked = set()
    for frames in _native_threads(text):
        ours = next((frame for frame in frames if 'python_webrtc::' in frame), None)
        if ours is not None:
            blocked.add(normalize(ours))
    return sorted(blocked)[:HANG_FRAMES]


def _debugger_outputs(evidence: Evidence) -> list[pathlib.Path]:
    if evidence.stacks is None:
        return []
    paths = [path for path in evidence.stacks.glob('*.txt') if path.stem.endswith(('-lldb', '-gdb'))]
    return sorted(paths, key=lambda path: (not path.name.startswith(f'{evidence.pid}-'), path.name))


def _in_stdlib(file: str) -> bool:
    return '/lib/python3' in file or file.startswith('<frozen')


def _hang(evidence: Evidence) -> str:
    for path in _debugger_outputs(evidence):
        blocked = _blocked_in_library(path.read_text(encoding='utf-8', errors='replace'))
        if blocked != []:
            return f'native: {" | ".join(blocked)}'
    # without the library's symbols, chaos names the step better than its Python frames
    stuck = _CHAOS_STUCK.findall(evidence.output)
    if stuck != []:
        return f'stuck: {stuck[-1]}'
    python: set[str] = set()
    for frames in _python_threads(evidence.output):
        ours = next(((file, function) for file, function in frames if not _in_stdlib(file)), None)
        if ours is not None:
            python.add(f'{ours[1]} ({pathlib.Path(ours[0]).name})')
    if python != set():
        return f'python: {" | ".join(sorted(python)[:HANG_FRAMES])}'
    return evidence.job


def _failure(evidence: Evidence) -> str:
    tests: list[str] = sorted(set(_PYTEST_FAILED.findall(evidence.output)))
    if tests != []:
        return ' | '.join(tests[:FAILED_TESTS])
    exceptions: list[str] = _EXCEPTION.findall(evidence.output)
    functions: list[str] = _TRACEBACK_FRAME.findall(evidence.output)
    if exceptions != []:
        where = f' in {functions[-1]}' if functions != [] else ''
        return f'{evidence.job}: {exceptions[-1]}{where}'
    return f'{evidence.job} exit {evidence.returncode}'


def main() -> None:
    parser = argparse.ArgumentParser(description='The signature of a hunt bundle.')
    parser.add_argument('bundle', type=pathlib.Path, help='build/hunt/<signature>/<bundle>')
    bundle: pathlib.Path = parser.parse_args().bundle
    info: BundleInfo = json.loads((bundle / 'info.json').read_text(encoding='utf-8'))
    report = bundle / 'crash.ips'
    evidence = Evidence(
        job=info['job'],
        pid=info['pid'],
        output=(bundle / 'output.txt').read_text(encoding='utf-8', errors='replace'),
        returncode=info['returncode'],
        killed=info['reason'],
        stacks=bundle / 'stacks',
        crash_report=report if report.exists() else None,
    )
    print(signature(info['outcome'], evidence))


if __name__ == '__main__':
    main()
