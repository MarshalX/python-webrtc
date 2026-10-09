#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Bug hunt: runs the jobs of JOBS one at a time, and keeps the evidence of every new failure.

python -m scripts.debug.hunt --hours 8                 # or make hunt H=8
python -m scripts.debug.hunt --until 07:30 --jobs chaos,chaos-asan
python -m scripts.debug.hunt --self-test               # the runner itself, without the library

The results are in build/hunt/REPORT.md (make hunt-report). A restart continues the seeds where they stopped;
removing build/hunt starts over.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, BinaryIO, TypedDict

from scripts.debug import cover, stacks
from scripts.debug.triage import FAILURES, BundleInfo, Evidence, classify, crash_report_pid, signature, slug

if sys.platform != 'win32':
    import resource

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[2]
SANITIZERS = '.github/scripts/sanitizers-macos.sh'
ASAN = 'address,undefined'
TSAN = 'thread'

CHAOS = ('python', '-m', 'tests.chaos', '--steps', '1000', '--wait-when-stuck')
CHAOS_TRANSFORMS = (*CHAOS, '--transforms')
# pytest's own timeouts would end the process before the stacks are taken
PYTEST = (
    'python', '-m', 'pytest', 'tests', '--ignore=tests/wpt', '-p', 'no:cacheprovider', '-s', '-v', '-x',
    '-o', 'timeout=0', '-o', 'faulthandler_timeout=0',
)  # fmt: skip
PYTEST_GC = (*PYTEST, '--gc-on-emit')
PYTEST_STRESS = (*PYTEST, '--stress', '-m', 'stress')

JOB_ENV = {
    'CMAKE_BUILD_PARALLEL_LEVEL': '4',
    'PYTHONUNBUFFERED': '1',
    'PYTHONFAULTHANDLER': '1',
    'WRTC_ALLOW_LOOPBACK': '1',
    'WRTC_HUNT': '1',
}

POLL_INTERVAL = 1
MEMORY_PAUSE = 30
ABORT_WAIT = 10
GROUP_EXIT_WAIT = 5
CRASH_REPORT_WAIT = 20
BUNDLES_PER_SIGNATURE = 3
SAME_FAILURE_LIMIT = 5
CORES_MIN_FREE_GB = 20
OUTPUT_LINES = 500
KB_PER_GB = 1 << 20
GB = 1 << 30
#: macOS kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical
CRITICAL_PRESSURE = 4
#: Linux: critical below this share of the memory available
CRITICAL_AVAILABLE = 0.1
SELF_TEST_RUNS = 2
#: Python coverage costs up to a fifth of a run
PYTHON_COVERAGE_EVERY = 10

_STUCK = re.compile(rb' is stuck$', re.MULTILINE)
_BLOCKED_LOCK = re.compile(r'acquire|_PyParkingLot_Park|futex|sem_wait|semaphore_wait|psynch')


def _format(timestamp: float) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def _now() -> str:
    return _format(time.time())


@dataclass(frozen=True)
class Job:
    """A kind of run, and its share of the time."""

    name: str
    weight: int
    argv: tuple[str, ...]
    seeded: bool = False
    #: The SANITIZE build of sanitizers-macos.sh to run in
    sanitizer: str | None = None
    #: On the efficiency cores (taskpolicy -b), whose timings reproduced rare races
    ecores: bool = False
    silence_s: int = 60
    wall_s: int = 900
    rss_gb: float = 3

    @property
    def runs_here(self) -> bool:
        """Whether the platform has what the job needs: the sanitizer builds and taskpolicy are macOS only."""
        return sys.platform == 'darwin' or (self.sanitizer is None and not self.ecores)


JOBS = (
    Job('chaos', 3, CHAOS, seeded=True),
    Job('chaos-transforms', 3, CHAOS_TRANSFORMS, seeded=True),
    Job('chaos-transforms-ecores', 2, CHAOS_TRANSFORMS, seeded=True, ecores=True, silence_s=90, wall_s=1200),
    Job('chaos-asan', 3, CHAOS, seeded=True, sanitizer=ASAN, silence_s=120, wall_s=1800, rss_gb=5),
    Job('chaos-tsan', 2, CHAOS_TRANSFORMS, seeded=True, sanitizer=TSAN, silence_s=300, wall_s=3600, rss_gb=5),
    Job('suite-asan-gc-ecores', 2, PYTEST_GC, sanitizer=ASAN, ecores=True, silence_s=300, wall_s=3600, rss_gb=5),
    # under the timeout(900) of the stress tests, which still applies
    Job('stress', 1, PYTEST_STRESS, silence_s=840, wall_s=5400, rss_gb=4),
    Job('suite', 1, PYTEST, silence_s=300, wall_s=1800),
)

SELF_TEST_OUTCOMES = {'deadlock': 'hang', 'segfault': 'crash', 'failure': 'failure', 'leak': 'leak', 'memory': 'memory'}
SELF_TEST_JOBS = tuple(
    Job(name, 1, ('python', '-m', 'scripts.debug.synthetic', name), seeded=True, silence_s=3, wall_s=60, rss_gb=0.1)
    for name in SELF_TEST_OUTCOMES
)


@dataclass(frozen=True)
class Paths:
    root: pathlib.Path

    @property
    def state(self) -> pathlib.Path:
        return self.root / 'state.json'

    @property
    def log(self) -> pathlib.Path:
        return self.root / 'hunt.log'

    @property
    def report(self) -> pathlib.Path:
        return self.root / 'REPORT.md'

    @property
    def build_log(self) -> pathlib.Path:
        return self.root / 'build.log'

    @property
    def output(self) -> pathlib.Path:
        return self.root / 'current' / 'output.log'

    @property
    def stacks(self) -> pathlib.Path:
        return self.root / 'current' / 'stacks'


@dataclass
class Run:
    job: Job
    seed: int | None
    command: list[str]
    started: float
    pid: int = 0
    pids: list[int] = field(default_factory=list)
    aborted: bool = False
    returncode: int = 0
    killed: str | None = None
    duration: float = 0
    exited: float = 0
    peak_rss_kb: int = 0


class JobStats(TypedDict):
    next_seed: int
    runs: int
    failures: int
    seconds: float


class Found(TypedDict):
    """The runs that hit the same bug."""

    signature: str
    outcome: str
    job: str
    repro: str
    first_seen: str
    last_seen: str
    hits: int
    bundles: list[str]


class _Saved(TypedDict):
    version: int
    jobs: dict[str, JobStats]
    signatures: dict[str, Found]


@dataclass
class State:
    jobs: dict[str, JobStats] = field(default_factory=dict)
    signatures: dict[str, Found] = field(default_factory=dict)

    @classmethod
    def load(cls, path: pathlib.Path) -> State:
        if not path.exists():
            return cls()
        saved: _Saved = json.loads(path.read_text(encoding='utf-8'))
        return cls(saved['jobs'], saved['signatures'])

    def save(self, path: pathlib.Path) -> None:
        """Replaces the saved state at once: stopping at any moment leaves a whole file."""
        temporary = path.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(_Saved(version=1, jobs=self.jobs, signatures=self.signatures), indent=2), encoding='utf-8'
        )
        temporary.replace(path)

    def stats(self, job: Job) -> JobStats:
        return self.jobs.setdefault(job.name, JobStats(next_seed=1, runs=0, failures=0, seconds=0))


class Watchdog:
    """Tells when a running job hangs or holds too much memory."""

    def __init__(self, job: Job, output: pathlib.Path) -> None:
        self.job = job
        self.output = output
        self.started = self.quiet_since = time.monotonic()
        self.size = 0
        self.searched_to = 0
        self.peak_rss_kb = 0

    def check(self, pid: int) -> str | None:
        """Why the job must be stopped: memory, stuck (it says so), silent or wall (too long); None if it mustn't."""
        rss_kb = sum(process.rss_kb for process in stacks.tree(pid))
        self.peak_rss_kb = max(self.peak_rss_kb, rss_kb)
        if rss_kb > self.job.rss_gb * KB_PER_GB:
            return 'memory'
        if self._read_output():
            return 'stuck'
        return self._overdue()

    def _read_output(self) -> bool:
        size = self.output.stat().st_size
        if size == self.size:
            return False
        self.size, self.quiet_since = size, time.monotonic()
        with self.output.open('rb') as output:
            output.seek(self.searched_to)
            text = output.read(size - self.searched_to)
        complete = text.rfind(b'\n') + 1
        self.searched_to += complete
        return _STUCK.search(text[:complete]) is not None

    def _overdue(self) -> str | None:
        now = time.monotonic()
        if now - self.quiet_since > self.job.silence_s:
            return 'silent'
        return 'wall' if now - self.started > self.job.wall_s else None


def _argv(job: Job, seed: int | None) -> list[str]:
    return [*job.argv, *(['--seed', str(seed)] if seed is not None else [])]


def _wrapped(job: Job, argv: list[str], python: list[str]) -> list[str]:
    run = [SANITIZERS, '--exec', *argv] if job.sanitizer is not None else [*python, *argv[1:]]
    return ['taskpolicy', '-b', *run] if job.ecores else run


def command(job: Job, seed: int | None) -> list[str]:
    return _wrapped(job, _argv(job, seed), [sys.executable])


def repro(job: Job, seed: int | None) -> str:
    run = shlex.join(_wrapped(job, _argv(job, seed), ['uv', 'run', '--no-sync', 'python']))
    return f'SANITIZE={shlex.quote(job.sanitizer)} {run}' if job.sanitizer is not None else run


def _env(job: Job) -> dict[str, str]:
    env = dict(JOB_ENV)
    if job.sanitizer is not None:
        env['SANITIZE'] = job.sanitizer
    return env


def _wait_group_gone(pgid: int) -> None:
    if sys.platform == 'win32':
        return
    deadline = time.monotonic() + GROUP_EXIT_WAIT
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.1)


def _kill_tree(process: subprocess.Popen[bytes], *, abort: bool) -> list[int]:
    """Kills the job and what it started, after SIGABRT for cores and Python stacks; returns the pids, root first."""
    pids = [process.pid]
    if sys.platform == 'win32':
        return pids
    # until the root is reaped, its pid (and so the tree) can't belong to another process
    if process.returncode is None:
        pids += [member.pid for member in stacks.tree(process.pid) if member.pid != process.pid]
        if abort:
            for pid in pids:
                stacks.send(pid, signal.SIGABRT)
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(ABORT_WAIT)
        for pid in pids[1:]:
            stacks.send(pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()
    _wait_group_gone(process.pid)
    return pids


def _watch(process: subprocess.Popen[bytes], job: Job, paths: Paths) -> tuple[str | None, int]:
    watchdog = Watchdog(job, paths.output)
    while process.poll() is None:
        reason = watchdog.check(process.pid)
        if reason is not None:
            # the debuggers would take minutes and another GB, when memory is what is short
            if reason != 'memory':
                stacks.collect(process.pid, paths.stacks, signal_root=True)
            return reason, watchdog.peak_rss_kb
        time.sleep(POLL_INTERVAL)
    return None, watchdog.peak_rss_kb


def _room_for_cores() -> bool:
    if _cores_off() is not None:
        return True
    return shutil.disk_usage('/cores' if sys.platform == 'darwin' else ROOT).free >= CORES_MIN_FREE_GB * GB


def run_job(job: Job, seed: int | None, paths: Paths, *, extra_env: Mapping[str, str]) -> Run:
    """Runs a job until it exits, hangs or holds too much memory; takes the stacks of a hang, and kills what is left."""
    shutil.rmtree(paths.output.parent, ignore_errors=True)
    paths.output.parent.mkdir(parents=True)
    run = Run(job, seed, command(job, seed), time.time())
    with paths.output.open('wb') as output:
        # a session of its own: Ctrl-C reaches only the runner, which then stops the job
        process = subprocess.Popen(
            run.command,
            cwd=ROOT,
            env={**os.environ, **_env(job), **extra_env},
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    run.pid = process.pid
    try:
        run.killed, run.peak_rss_kb = _watch(process, job, paths)
        run.exited = time.time()
    finally:
        # also what an exited job left running
        run.aborted = run.killed not in {None, 'memory'} and _room_for_cores()
        run.pids = _kill_tree(process, abort=run.aborted)
    run.returncode = process.returncode
    run.duration = time.time() - run.started
    return run


def _git(*args: str) -> bytes | None:
    try:
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _core_pattern() -> str | None:
    """Where the kernel writes cores, %p for the pid; None if it hands them to a program."""
    if sys.platform == 'darwin':
        return '/cores/core.%p'
    pattern = pathlib.Path('/proc/sys/kernel/core_pattern').read_text(encoding='utf-8').strip()
    if pattern.startswith('|'):
        return None
    uses_pid = pathlib.Path('/proc/sys/kernel/core_uses_pid').read_text(encoding='utf-8').strip() == '1'
    if '%p' not in pattern and uses_pid:
        pattern += '.%p'
    # a relative pattern is relative to the job's directory
    return pattern if pattern.startswith('/') else str(ROOT / pattern)


def _modified_since(path: pathlib.Path, since: float) -> bool:
    try:
        return path.stat().st_mtime >= since
    except OSError:
        return False


def _cores(run: Run) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """The cores written during the run: of the job's processes (the root's first), and of others."""
    pattern = _core_pattern()
    if pattern is None:
        return [], []
    written = [
        path
        for path in pathlib.Path('/').glob(re.sub(r'%.', '*', pattern).lstrip('/'))
        if _modified_since(path, run.started)
    ]
    if '%p' not in pattern:
        return written, []
    globs = [re.sub(r'%.', '*', pattern.replace('%p', str(pid))) for pid in run.pids]
    ours = [path for glob in globs for path in written if fnmatch.fnmatch(str(path), glob)]
    return ours, [path for path in written if path not in ours]


def _crash_report_of(run: Run) -> pathlib.Path | None:
    modified: dict[pathlib.Path, float] = {}
    for path in (pathlib.Path.home() / 'Library' / 'Logs' / 'DiagnosticReports').glob('python*.ips'):
        with contextlib.suppress(OSError):
            modified[path] = path.stat().st_mtime
    for path, mtime in modified.items():
        if mtime >= run.started and crash_report_pid(path) == run.pid:
            return path
    # macOS doesn't write a repeated crash again, it touches the report of the first one
    touched = [path for path, mtime in modified.items() if mtime >= run.exited - POLL_INTERVAL]
    return max(touched, key=modified.__getitem__, default=None)


def _wait_for_crash_report(run: Run) -> pathlib.Path | None:
    deadline = time.monotonic() + CRASH_REPORT_WAIT
    while time.monotonic() < deadline:
        report = _crash_report_of(run)
        if report is not None:
            return report
        time.sleep(POLL_INTERVAL)
    return None


def _worktree_sha1() -> str | None:
    diff = _git('diff', 'HEAD', '--binary')
    untracked = _git('ls-files', '--others', '--exclude-standard', '-z')
    if diff is None or untracked is None:
        return None
    digest = hashlib.sha1(diff, usedforsecurity=False)
    for name in sorted(name for name in untracked.split(b'\0') if name != b''):
        digest.update(name)
        with contextlib.suppress(OSError):
            digest.update((ROOT / os.fsdecode(name)).read_bytes())
    return digest.hexdigest()


def _info(run: Run, found: Found, cores: list[pathlib.Path]) -> BundleInfo:
    head = _git('rev-parse', 'HEAD')
    return BundleInfo(
        job=run.job.name,
        seed=run.seed,
        outcome=found['outcome'],
        signature=found['signature'],
        reason=run.killed,
        argv=run.command,
        repro=found['repro'],
        env_added=_env(run.job),
        cwd=str(ROOT),
        git_head=head.decode().strip() if head is not None else None,
        worktree_sha1=_worktree_sha1(),
        started=_format(run.started),
        duration_s=round(run.duration, 1),
        pid=run.pid,
        returncode=run.returncode,
        peak_rss_mb=run.peak_rss_kb // 1024,
        cores=[core.name for core in cores],
        platform=sys.platform,
    )


def _bundle_name(run: Run) -> str:
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(run.started))
    return '-'.join([stamp, run.job.name, *([str(run.seed)] if run.seed is not None else [])])


def _write_bundle(bundle: pathlib.Path, evidence: Evidence, info: BundleInfo, *, cores: list[pathlib.Path]) -> None:
    bundle.mkdir(parents=True)
    tail = evidence.output.splitlines()[-OUTPUT_LINES:]
    (bundle / 'output.txt').write_text('\n'.join(tail) + '\n', encoding='utf-8')
    if evidence.stacks is not None and evidence.stacks.exists():
        shutil.move(str(evidence.stacks), str(bundle / 'stacks'))
    if evidence.crash_report is not None:
        shutil.copy(evidence.crash_report, bundle / 'crash.ips')
    for core in cores:
        shutil.move(str(core), str(bundle / core.name))
    (bundle / 'info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')


def _remove(paths: Sequence[pathlib.Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _notify(message: str) -> None:
    if sys.platform == 'darwin':
        # the message as an argument, never as script code
        script = ['-e', 'on run argv', '-e', 'display notification (item 1 of argv) with title "hunt"', '-e', 'end run']
        subprocess.run(['osascript', *script, message], capture_output=True, check=False)


def _cell(text: str) -> str:
    return text.replace('|', '\\|')


class Results:
    """The state of a hunt and the files it writes: the log, the bundles, the report."""

    def __init__(self, paths: Paths, state: State, *, self_test: bool) -> None:
        self.paths = paths
        self.state = state
        self.self_test = self_test
        self.started = time.time()
        self.runs = 0
        self.failures = 0
        #: Per job: its last signature (None for a pass), and how many runs in a row hit it
        self.streaks: dict[str, tuple[str | None, int]] = {}
        self.benched: set[str] = set()

    def log(self, message: str) -> None:
        line = f'{_now()}  {message}'
        print(line, flush=True)
        with self.paths.log.open('a', encoding='utf-8') as log:
            log.write(line + '\n')

    def record(self, run: Run) -> None:
        """Files a finished run: its outcome, and for a failure its signature, a bundle and its cores."""
        output = self.paths.output.read_text(encoding='utf-8', errors='replace')
        evidence = Evidence(run.job.name, run.pid, output, run.returncode, run.killed, self.paths.stacks)
        outcome = classify(evidence)
        cores, others = _cores(run)
        # of tests that crash on purpose, gigabytes each
        _remove(others)
        if outcome == 'crash' and run.returncode < 0:
            evidence = self._crash_evidence(run, evidence, cores)
        stats = self.state.stats(run.job)
        stats['runs'] += 1
        if run.job.seeded:
            stats['next_seed'] += 1
        self.runs += 1
        line = f'{run.job.name} seed {run.seed}: {outcome} in {run.duration:.0f} s'
        if run.killed not in {None, 'memory'} and not run.aborted:
            line += ', no core: low on disk'
        name = None
        if outcome == 'pass':
            _remove(cores)
        else:
            stats['failures'] += 1
            self.failures += 1
            name, new = self._file_failure(run, outcome, evidence, cores=cores)
            line += f', {name}' + (' NEW' if new else '')
        # the triage and the bundle too, or a job that fails in a second would run over and over
        stats['seconds'] += time.time() - run.started
        self.state.save(self.paths.state)
        self.log(line)
        self._track_streak(run.job, name)

    def _crash_evidence(self, run: Run, evidence: Evidence, cores: list[pathlib.Path]) -> Evidence:
        if sys.platform == 'darwin':
            return replace(evidence, crash_report=_wait_for_crash_report(run))
        if cores != []:
            self.paths.stacks.mkdir(parents=True, exist_ok=True)
            stacks.core_backtrace(sys.executable, cores[0], self.paths.stacks / f'{run.pid}-core.txt')
        return evidence

    def _file_failure(
        self, run: Run, outcome: str, evidence: Evidence, *, cores: list[pathlib.Path]
    ) -> tuple[str, bool]:
        text = signature(outcome, evidence)
        name = slug(text)
        found = self.state.signatures.get(name)
        new = found is None
        if found is None:
            found = Found(
                signature=text,
                outcome=outcome,
                job=run.job.name,
                repro=repro(run.job, run.seed),
                first_seen=_now(),
                last_seen='',
                hits=0,
                bundles=[],
            )
            self.state.signatures[name] = found
        found['hits'] += 1
        found['last_seen'] = _now()
        if len(found['bundles']) < BUNDLES_PER_SIGNATURE:
            found['bundles'].append(_bundle_name(run))
            _write_bundle(
                self.paths.root / name / found['bundles'][-1], evidence, _info(run, found, cores), cores=cores
            )
        else:
            _remove(cores)
        self.write_report()
        if new and not self.self_test:
            _notify(f'{run.job.name}: {text}')
        return name, new

    def _track_streak(self, job: Job, name: str | None) -> None:
        last, count = self.streaks.get(job.name, (None, 0))
        count = count + 1 if name is not None and name == last else 1
        self.streaks[job.name] = (name, count)
        if name is not None and count == SAME_FAILURE_LIMIT:
            self.benched.add(job.name)
            self.log(f'{job.name}: {name} {count} times in a row, not run again in this session')

    def write_report(self) -> None:
        """The signatures found, the most severe and most frequent first, and the time each job got."""
        found = sorted(
            self.state.signatures.items(), key=lambda item: (FAILURES.index(item[1]['outcome']), -item[1]['hits'])
        )
        started = _format(self.started)
        new = [name for name, entry in found if entry['first_seen'] >= started]
        hours = (time.time() - self.started) / 3600
        lines = [
            '# Hunt report',
            '',
            (
                f'Session {started} to {_now()}: {hours:.1f} h, {self.runs} runs, {self.failures} failures, '
                f'{len(found)} signatures ({len(new)} new)'
            ),
            '',
            '| Signature | Outcome | Hits | First seen | Repro |',
            '|---|---|---|---|---|',
        ]
        for name, entry in found:
            mark = '**new** ' if name in new else ''
            lines.append(
                f'| {mark}[{name}]({name}/) `{_cell(entry["signature"])}` | {entry["outcome"]} | {entry["hits"]} '
                f'| {entry["first_seen"][5:16]} | `{_cell(entry["repro"])}` |'
            )
        lines += ['', '| Job | Runs | Hours | Pass | Fail |', '|---|---|---|---|---|']
        for name, stats in self.state.jobs.items():
            passed = stats['runs'] - stats['failures']
            lines.append(
                f'| {name} | {stats["runs"]} | {stats["seconds"] / 3600:.1f} | {passed} | {stats["failures"]} |'
            )
        summary = None if self.self_test else cover.summary_line()
        if summary is not None:
            lines += ['', summary]
        self.paths.report.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _memory_critical() -> bool:
    if sys.platform == 'darwin':
        return _output(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level']).strip() == str(CRITICAL_PRESSURE)
    available, total = _linux_memory()
    return available < total * CRITICAL_AVAILABLE


def _linux_memory() -> tuple[int, int]:
    """Bytes available and in all: of the cgroup when it has a limit, as in a container run with --memory."""
    cgroup = pathlib.Path('/sys/fs/cgroup')
    with contextlib.suppress(OSError, ValueError):
        limit = int((cgroup / 'memory.max').read_text(encoding='utf-8'))
        used = int((cgroup / 'memory.current').read_text(encoding='utf-8'))
        stat = dict(line.split() for line in (cgroup / 'memory.stat').read_text(encoding='utf-8').splitlines())
        # the inactive page cache is reclaimed before anything is killed
        return limit - used + int(stat['inactive_file']), limit
    meminfo = pathlib.Path('/proc/meminfo').read_text(encoding='utf-8')
    kb = {line.split(':')[0]: int(line.split()[1]) for line in meminfo.splitlines() if line.endswith(' kB')}
    return kb['MemAvailable'] * 1024, kb['MemTotal'] * 1024


def _output(command: list[str]) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False).stdout
    except OSError:
        return ''


def _pause_for_memory(results: Results, deadline: float) -> None:
    results.log('paused: memory pressure')
    while _memory_critical() and time.time() < deadline:
        time.sleep(MEMORY_PAUSE)
    results.log('resumed')


def _next_job(jobs: Sequence[Job], state: State) -> Job:
    # the job furthest behind its share of the time; min() keeps the table order on ties
    return min(jobs, key=lambda job: state.stats(job)['seconds'] / job.weight)


def _coverage_env(job: Job) -> dict[str, str]:
    python = cover.count_run(job.name) % PYTHON_COVERAGE_EVERY == 1
    return cover.env(cover.CHAOS if job.seeded else cover.SUITE, python=python)


def hunt(jobs: Sequence[Job], deadline: float, results: Results) -> None:
    try:
        while time.time() < deadline:
            if _memory_critical():
                _pause_for_memory(results, deadline)
                continue
            runnable = [job for job in jobs if job.name not in results.benched]
            if runnable == []:
                results.log('every job keeps failing the same way, stopping')
                break
            job = _next_job(runnable, results.state)
            seed = results.state.stats(job)['next_seed'] if job.seeded else None
            results.record(run_job(job, seed, results.paths, extra_env=_coverage_env(job)))
            cover.collect()
    finally:
        results.write_report()


def _build_step(argv: list[str], env: dict[str, str], log: BinaryIO) -> int:
    # a session of its own, so that stopping the hunt stops the compilers too
    process = subprocess.Popen(
        argv,
        cwd=ROOT,
        env={**os.environ, **JOB_ENV, **env},
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        return process.wait()
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def build(jobs: Sequence[Job], results: Results) -> None:
    """Builds what the jobs run, once: the editable install, and the sanitizer builds they need."""
    steps: list[tuple[list[str], dict[str, str]]] = [([sys.executable, '-c', 'import webrtc'], {})]
    sanitizers = sorted({job.sanitizer for job in jobs if job.sanitizer is not None})
    steps += [([SANITIZERS, '--build-only'], {'SANITIZE': sanitizer}) for sanitizer in sanitizers]
    build_log = results.paths.build_log
    with build_log.open('ab') as log:
        for argv, env in steps:
            results.log(f'building: {shlex.join([*(f"{name}={value}" for name, value in env.items()), *argv])}')
            if _build_step(argv, env, log) != 0:
                sys.exit(f'hunt: the build failed, see {build_log}')
    cover.collect()


def _cores_off() -> str | None:
    """Why a crash writes no core, or None if it does."""
    if sys.platform == 'win32' or resource.getrlimit(resource.RLIMIT_CORE)[0] == 0:
        return 'the core size limit is 0 (ulimit -c)'
    if sys.platform == 'darwin' and not os.access('/cores', os.W_OK):
        return '/cores is not writable (sudo chmod 1777 /cores)'
    if _core_pattern() is None:
        return 'handed to the program in /proc/sys/kernel/core_pattern, not kept in the bundles'
    return None


def _enable_cores(results: Results) -> None:
    if sys.platform == 'win32':
        return
    _soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
    resource.setrlimit(resource.RLIMIT_CORE, (hard, hard))
    off = _cores_off()
    results.log(f'cores: off, {off}' if off is not None else f'cores: on, {_core_pattern()}')


def _attach_problem() -> str | None:
    if os.geteuid() == 0:
        return None
    return _macos_attach_problem() if sys.platform == 'darwin' else _linux_attach_problem()


def _macos_attach_problem() -> str | None:
    developer = '_developer' in _output(['id', '-Gn']).split()
    if developer or 'currently enabled' in _output(['DevToolsSecurity', '-status']):
        return None
    return 'sudo DevToolsSecurity -enable, or add the user to the _developer group'


def _linux_attach_problem() -> str | None:
    scope = pathlib.Path('/proc/sys/kernel/yama/ptrace_scope')
    # a debugger may then attach only to its own descendants, and the job isn't one
    if scope.exists() and scope.read_text(encoding='utf-8').strip() != '0':
        return 'sudo sysctl kernel.yama.ptrace_scope=0 (or run as root, with --cap-add SYS_PTRACE in a container)'
    return None


def _check_tools(results: Results) -> None:
    if shutil.which('ps') is None:
        sys.exit('hunt: needs ps (procps)')
    debuggers = ['lldb', 'sample'] if sys.platform == 'darwin' else ['gdb']
    missing = [tool for tool in debuggers if shutil.which(tool) is None]
    if missing != []:
        results.log(f'{", ".join(missing)} not found: hangs will have no native stacks')
    problem = _attach_problem()
    if problem is not None:
        results.log(f'debuggers may not attach, hangs would have no native stacks: {problem}')


def _deadline(hours: float, until: str | None) -> float:
    deadline = time.time() + hours * 3600
    if until is None:
        return deadline
    hour, minute = (int(part) for part in until.split(':'))
    now = time.localtime()
    at = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, minute, 0, 0, 0, -1))
    return min(deadline, at if at > time.time() else at + 24 * 3600)


def _select(names: str | None) -> list[Job]:
    jobs = [job for job in JOBS if job.runs_here]
    if names is None:
        return jobs
    chosen = [job for job in jobs if job.name in names.split(',')]
    unknown = set(names.split(',')) - {job.name for job in chosen}
    if unknown != set():
        sys.exit(f'hunt: no job {", ".join(sorted(unknown))} here; there are {", ".join(job.name for job in jobs)}')
    return chosen


def _deadlock_checks(bundle: pathlib.Path) -> list[tuple[bool, str]]:
    native = [path for path in (bundle / 'stacks').glob('*.txt') if path.stem.endswith(('-lldb', '-gdb'))]
    blocked = any(_BLOCKED_LOCK.search(path.read_text(encoding='utf-8', errors='replace')) for path in native)
    has_python = 'in deadlock' in (bundle / 'output.txt').read_text(encoding='utf-8')
    return [
        (blocked, 'deadlock: native stacks of the blocked lock'),
        (has_python, 'deadlock: Python stacks from SIGUSR1'),
    ]


def _check_self_test_job(job: Job, results: Results, report: str) -> list[tuple[bool, str]]:
    found = [(name, entry) for name, entry in results.state.signatures.items() if entry['job'] == job.name]
    if len(found) != 1:
        return [(False, f'{job.name}: one signature, not {len(found)}')]
    name, entry = found[0]
    bundles = [results.paths.root / name / bundle for bundle in entry['bundles']]
    complete = all((bundle / 'info.json').exists() and (bundle / 'output.txt').exists() for bundle in bundles)
    expected = SELF_TEST_OUTCOMES[job.name]
    hit_every_run = entry['hits'] == SELF_TEST_RUNS and len(bundles) == SELF_TEST_RUNS and complete
    in_report = re.search(rf'\[{re.escape(name)}\].*\| {SELF_TEST_RUNS} \|', report) is not None
    checks = [
        (entry['outcome'] == expected, f'{job.name}: {entry["outcome"]} (expected {expected}): {entry["signature"]}'),
        (hit_every_run, f'{job.name}: {SELF_TEST_RUNS} hits, bundles complete'),
        (results.state.stats(job)['next_seed'] == SELF_TEST_RUNS + 1, f'{job.name}: next seed {SELF_TEST_RUNS + 1}'),
        (in_report, f'{job.name}: in the report'),
    ]
    if job.name == 'segfault':
        checks.append(('SIGSEGV' in entry['signature'], 'segfault: SIGSEGV in the signature'))
        if sys.platform == 'darwin':
            reported = all((bundle / 'crash.ips').exists() for bundle in bundles)
            checks.append((reported, 'segfault: a crash report in every bundle'))
    if job.name == 'deadlock':
        checks += _deadlock_checks(bundles[0])
    return checks


def self_test(results: Results) -> bool:
    """Runs each synthetic failure twice and checks what the hunt made of them; True if all is right."""
    for job in SELF_TEST_JOBS:
        for _ in range(SELF_TEST_RUNS):
            results.record(run_job(job, results.state.stats(job)['next_seed'], results.paths, extra_env={}))
    results.write_report()
    report = results.paths.report.read_text(encoding='utf-8')
    checks = [check for job in SELF_TEST_JOBS for check in _check_self_test_job(job, results, report)]
    for passed, what in checks:
        print(f'{"ok  " if passed else "FAIL"} {what}')
    return all(passed for passed, _what in checks)


def _interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Bug hunt, results in build/hunt/REPORT.md.')
    parser.add_argument('--hours', type=float, default=8, help='stop starting jobs after this long')
    parser.add_argument('--until', help='or at this local time, HH:MM, whichever comes first')
    parser.add_argument('--jobs', help=f'comma-separated, of: {", ".join(job.name for job in JOBS)}')
    parser.add_argument('--no-build', action='store_true', help='skip the builds before the hunt')
    parser.add_argument('--self-test', action='store_true', help='check the runner on synthetic failures')
    return parser.parse_args()


def main() -> None:
    if sys.platform == 'win32':
        sys.exit('hunt: not supported on Windows')
    args = _parse_args()
    paths = Paths(ROOT / 'build' / ('hunt-self-test' if args.self_test else 'hunt'))
    if args.self_test:
        shutil.rmtree(paths.root, ignore_errors=True)
    paths.root.mkdir(parents=True, exist_ok=True)
    results = Results(paths, State.load(paths.state), self_test=args.self_test)
    signal.signal(signal.SIGTERM, _interrupt)
    # a closed terminal, else the job would outlive the runner
    signal.signal(signal.SIGHUP, _interrupt)
    if sys.platform == 'darwin':
        # exits with the runner, even a killed one
        subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])
    _check_tools(results)
    _enable_cores(results)
    jobs = _select(args.jobs)
    try:
        if args.self_test:
            sys.exit(0 if self_test(results) else 1)
        if not args.no_build:
            build(jobs, results)
        hunt(jobs, _deadline(args.hours, args.until), results)
    except KeyboardInterrupt:
        results.log('stopped; the interrupted run will run again')
        sys.exit(130)


if __name__ == '__main__':
    main()
