#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Starts the drivers of the libraries, sends them commands, and measures their processes from outside."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import fnmatch
import itertools
import os
import pathlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING, TypedDict, cast

import psutil

from benchmarks.protocol import decode, encode

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Sequence

    from typing_extensions import Self

    from benchmarks.protocol import (
        Answer,
        Candidate,
        Count,
        Created,
        Event,
        Hello,
        MediaStats,
        Message,
        Offer,
        Pinged,
        Probe,
        Reply,
    )

ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCHMARKS = ROOT / 'benchmarks'
RESULTS = BENCHMARKS / 'results'
LIBRARIES = ('wrtc', 'aiortc', 'pion', 'libdatachannel', 'webrtc-rs')
#: the libraries whose drivers send and receive audio and video; the others have data channels only
MEDIA_LIBRARIES = ('wrtc', 'aiortc', 'pion')
AIORTC_VENV = BENCHMARKS / '.venv-aiortc'
EXE = '.exe' if sys.platform == 'win32' else ''
PION_SOURCE = BENCHMARKS / 'drivers' / 'pion'
PION_BINARY = PION_SOURCE / 'bin' / f'pion-driver{EXE}'
LIBDATACHANNEL_SOURCE = BENCHMARKS / 'drivers' / 'libdatachannel'
LIBDATACHANNEL_BINARY = LIBDATACHANNEL_SOURCE / 'bin' / f'libdatachannel-driver{EXE}'
LIBDATACHANNEL_REPOSITORY = 'https://github.com/paullouisageneau/libdatachannel.git'
LIBDATACHANNEL_TAG = 'v0.24.6'
WEBRTC_RS_SOURCE = BENCHMARKS / 'drivers' / 'webrtc-rs'
WEBRTC_RS_BINARY = WEBRTC_RS_SOURCE / 'target' / 'release' / f'webrtc-rs-driver{EXE}'
LINE_LIMIT = 1 << 24
SAMPLE_INTERVAL = 0.05
EXIT_TIMEOUT = 5.0


class DriverError(Exception):
    """A driver failed a command, exited, or didn't send an event in time."""


def _aiortc_python() -> pathlib.Path:
    scripts = AIORTC_VENV / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not scripts.exists():
        msg = f'no aiortc environment at {AIORTC_VENV}: benchmarks/run.sh sets it up'
        raise DriverError(msg)
    return scripts


def _stale(binary: pathlib.Path, sources: Sequence[pathlib.Path]) -> bool:
    if not binary.exists():
        return True
    return max(path.stat().st_mtime for path in sources) > binary.stat().st_mtime


def _tool(name: str, library: str) -> str:
    path = shutil.which(name)
    if path is None:
        msg = f'{name} is needed to build the driver of {library}'
        raise DriverError(msg)
    return path


def build_pion() -> pathlib.Path:
    """Builds the driver of Pion if it's missing or older than its sources."""
    sources = [*PION_SOURCE.glob('*.go'), PION_SOURCE / 'go.mod', PION_SOURCE / 'go.sum']
    if _stale(PION_BINARY, sources):
        go = _tool('go', 'Pion')
        subprocess.run([go, 'build', '-o', str(PION_BINARY), '.'], cwd=PION_SOURCE, check=True)
    return PION_BINARY


def _fetch_libdatachannel(vendor: pathlib.Path) -> None:
    git = _tool('git', 'libdatachannel')
    clone = [git, 'clone', '--quiet', '--depth', '1', '--branch', LIBDATACHANNEL_TAG]
    shallow = ['--recurse-submodules', '--shallow-submodules', LIBDATACHANNEL_REPOSITORY, str(vendor)]
    subprocess.run([*clone, *shallow], check=True)


def _openssl_root() -> list[str]:
    """Where CMake finds OpenSSL on macOS, which ships none: Homebrew's, if installed."""
    if sys.platform != 'darwin':
        return []
    brew = shutil.which('brew')
    if brew is None:
        return []
    prefix = subprocess.run([brew, '--prefix', 'openssl@3'], capture_output=True, text=True, check=False)
    return [f'-DOPENSSL_ROOT_DIR={prefix.stdout.strip()}'] if prefix.returncode == 0 else []


def build_libdatachannel() -> pathlib.Path:
    """Builds the driver of libdatachannel, fetching the pinned release first, if it's missing or stale."""
    source = LIBDATACHANNEL_SOURCE
    sources = [*source.glob('*.cpp'), *source.glob('*.hpp'), source / 'CMakeLists.txt']
    if _stale(LIBDATACHANNEL_BINARY, sources):
        cmake = _tool('cmake', 'libdatachannel')
        if not (source / 'vendor' / 'CMakeLists.txt').exists():
            _fetch_libdatachannel(source / 'vendor')

        build = source / 'build'
        generator: list[str] = ['-G', 'Ninja'] if shutil.which('ninja') is not None else []
        configure = [cmake, '-S', str(source), '-B', str(build), *generator, '-DCMAKE_BUILD_TYPE=Release']
        subprocess.run([*configure, *_openssl_root()], check=True, stdout=subprocess.DEVNULL)

        compile_ = [cmake, '--build', str(build), '--config', 'Release', '--target', 'libdatachannel-driver']
        subprocess.run([*compile_, '--parallel', _build_jobs()], check=True)
    return LIBDATACHANNEL_BINARY


def _build_jobs() -> str:
    """Every core, as cargo uses, unless ``CMAKE_BUILD_PARALLEL_LEVEL`` says otherwise."""
    cores = os.cpu_count()
    return os.environ.get('CMAKE_BUILD_PARALLEL_LEVEL', str(cores if cores is not None else 1))


def build_webrtc_rs() -> pathlib.Path:
    """Builds the driver of webrtc-rs, with the locked crates, if it's missing or older than its sources."""
    source = WEBRTC_RS_SOURCE
    files = ('Cargo.toml', 'Cargo.lock', 'build.rs', 'rust-toolchain.toml')
    sources = [*source.glob('src/*.rs'), *(source / name for name in files)]
    if _stale(WEBRTC_RS_BINARY, sources):
        cargo = _tool('cargo', 'webrtc-rs')
        subprocess.run([cargo, 'build', '--release', '--locked'], cwd=source, check=True)
        # cargo leaves a binary that's up to date untouched
        WEBRTC_RS_BINARY.touch()
    return WEBRTC_RS_BINARY


BUILDS: dict[str, Callable[[], pathlib.Path]] = {
    'pion': build_pion,
    'libdatachannel': build_libdatachannel,
    'webrtc-rs': build_webrtc_rs,
}


def build_drivers(libraries: Sequence[str] = LIBRARIES) -> None:
    """Builds the native drivers of the libraries that are missing or stale."""
    for library in libraries:
        if library in BUILDS:
            BUILDS[library]()


def driver_command(library: str) -> list[str]:
    """The command line that starts the driver of a library."""
    if library == 'wrtc':
        return [sys.executable, '-m', 'benchmarks.drivers.wrtc']
    if library == 'aiortc':
        return [str(_aiortc_python()), '-m', 'benchmarks.drivers.aiortc']
    if library in BUILDS:
        return [str(BUILDS[library]())]
    msg = f'unknown library {library!r}'
    raise ValueError(msg)


@dataclass
class Options:
    """What to run, from the command line."""

    libraries: Sequence[str]
    quick: bool
    repeat: int
    log: IO[bytes]
    cases: Sequence[str] = ()
    started: float = field(default_factory=time.monotonic)

    def selects(self, case: str) -> bool:
        """Whether a case of that name runs."""
        return len(self.cases) == 0 or any(fnmatch.fnmatchcase(case, pattern) for pattern in self.cases)

    def progress(self, message: str) -> None:
        """Writes a line to stderr after the time of day and the time since the run started."""
        elapsed = duration(time.monotonic() - self.started)
        print(f'{dt.datetime.now().astimezone():%H:%M:%S} +{elapsed} {message}', file=sys.stderr, flush=True)


def duration(seconds: float) -> str:
    """A span of seconds as H:MM:SS."""
    return str(dt.timedelta(seconds=round(seconds)))


@dataclass
class Usage:
    """The CPU time and the peak resident memory of a process over a span."""

    cpu_seconds: float
    peak_rss: int


class Sampler:
    """Samples the CPU time (user and system, of every thread) and the resident memory of a process."""

    def __init__(self, pid: int) -> None:
        self._process = psutil.Process(pid)
        self._cpu_start = 0.0
        self._peak_rss = 0
        self._task: asyncio.Task[None] | None = None

    def _cpu(self) -> float:
        times = self._process.cpu_times()
        return times.user + times.system

    def rss(self) -> int:
        """The resident memory of the process now, in bytes."""
        return self._process.memory_info().rss

    def _sample_rss(self) -> None:
        with contextlib.suppress(psutil.Error):
            self._peak_rss = max(self._peak_rss, self._process.memory_info().rss)

    async def _sample(self) -> None:
        while True:
            self._sample_rss()
            await asyncio.sleep(SAMPLE_INTERVAL)

    def start(self) -> None:
        """Starts a span."""
        self._cpu_start = self._cpu()
        self._peak_rss = 0
        self._task = asyncio.ensure_future(self._sample())

    def stop(self) -> Usage:
        """Ends the span."""
        if self._task is not None:
            self._task.cancel()
        self._sample_rss()
        return Usage(cpu_seconds=self._cpu() - self._cpu_start, peak_rss=self._peak_rss)


class Driver:  # ruff: ignore[too-many-public-methods] - a method a command of the protocol
    """A driver process: commands to it, replies and events from it."""

    def __init__(self, library: str, process: asyncio.subprocess.Process) -> None:
        self.library = library
        self.sampler = Sampler(process.pid)
        self._process = process
        self._ids = itertools.count()
        self._pcs = itertools.count()
        self._replies: dict[int, asyncio.Future[Message]] = {}
        self._events: dict[tuple[int, str], asyncio.Future[float]] = {}
        self._candidates: dict[int, Callable[[Candidate], None]] = {}
        self._reader = asyncio.ensure_future(self._read())
        self.info: Hello = {'library': library, 'version': '?', 'trickle': False}

    @classmethod
    async def start(cls, library: str, log: IO[bytes]) -> Self:
        """Starts the driver of a library, its stderr written to the log, and waits until it replies."""
        process = await asyncio.create_subprocess_exec(
            *driver_command(library),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=log,
            cwd=ROOT,
            env={**os.environ, 'WRTC_ALLOW_LOOPBACK': '1'},
            limit=LINE_LIMIT,
            start_new_session=True,
        )

        driver = cls(library, process)
        try:
            driver.info = await driver.hello()
        except BaseException:
            await driver.stop()
            raise
        return driver

    def new_pc(self) -> int:
        """The id of a new connection of the driver."""
        return next(self._pcs)

    async def hello(self) -> Hello:
        """The library of the driver, its version, and whether it trickles."""
        return cast('Hello', await self._request('hello'))

    async def create(self, pc: int, role: str, **options: bool | str) -> Created:
        """A connection; the offerer opens the data channel, and sends the audio source with ``audio``."""
        return cast('Created', await self._request('create', pc=pc, role=role, **options))

    async def video_send(self, pc: int, video: VideoSource) -> None:
        """Sends a video track before the offer, looped at its fps.

        Pion sends the file (IVF or Annex B) unchanged; the others encode its raw I420 frames, capped at the bitrate,
        with their number drawn in if ``numbered``.
        """
        await self._request('video_send', pc=pc, **video)

    async def audio_send(self, pc: int, path: str) -> None:
        """Sends the process's one audio source: Pion the Ogg Opus file, the others a tone they encode."""
        await self._request('audio_send', pc=pc, path=path)

    async def media_sink(self, pc: int, *, numbered: bool = False, remb: int = 0) -> None:
        """Makes the app read every frame the connection receives; Pion counts RTP and sends REMB of ``remb`` bps."""
        await self._request('media_sink', pc=pc, numbered=numbered, remb=remb)

    async def media_stats(self, pc: int) -> MediaStats:
        """What the connection's sender wrote or its sink read; ``bytes``: the RTP sent, or a Pion sink received."""
        return cast('MediaStats', await self._request('media_stats', pc=pc))

    async def offer(self, pc: int) -> Offer:
        """Creates and sets an offer; without trickle the reply waits for gathering, so the SDP has the candidates."""
        return cast('Offer', await self._request('offer', pc=pc))

    async def answer(self, pc: int, sdp: str) -> Answer:
        """Sets an offer, then creates and sets an answer."""
        return cast('Answer', await self._request('answer', pc=pc, sdp=sdp))

    async def accept(self, pc: int, sdp: str) -> None:
        """Sets an answer."""
        await self._request('accept', pc=pc, sdp=sdp)

    async def add_candidate(self, pc: int, candidate: Candidate) -> None:
        """Adds a remote candidate."""
        await self._request('add_candidate', pc=pc, candidate=candidate)

    def on_candidate(self, pc: int, handler: Callable[[Candidate], None]) -> None:
        """Passes the local candidates the connection trickles to the handler."""
        self._candidates[pc] = handler

    async def count(self, pc: int) -> Count:
        """What the data channel of a connection received."""
        return cast('Count', await self._request('count', pc=pc))

    async def echo(self, pc: int) -> None:
        """Makes the data channel of a connection send back what it receives."""
        await self._request('echo', pc=pc)

    async def flood(self, pc: int, *, size: int, seconds: float, low: int, high: int) -> None:
        """Sends messages for a while, from ``bufferedAmount`` at ``high`` waiting for it to fall to ``low``."""
        await self._request('flood', pc=pc, size=size, seconds=seconds, low=low, high=high)

    async def ping(self, pc: int, *, size: int, rate: float, seconds: float) -> Pinged:
        """Round trips to an echoing peer of messages that start with their number (4 bytes, big endian)."""
        return cast('Pinged', await self._request('ping', pc=pc, size=size, rate=rate, seconds=seconds))

    async def close(self, pc: int) -> None:
        """Closes a connection and forgets its events."""
        self._candidates.pop(pc, None)
        try:
            await self._request('close', pc=pc)
        finally:
            closed = [(event_pc, name) for event_pc, name in self._events if event_pc == pc]
            for key in closed:
                del self._events[key]

    async def collect(self) -> None:
        """Runs the garbage collector of the driver, returning freed memory to the OS where the runtime can."""
        await self._request('collect')

    def rss(self) -> int:
        """The resident memory of the driver process, in bytes."""
        return self.sampler.rss()

    async def probe(self) -> Probe:
        """The event loop lag since the last probe, if the driver has a loop."""
        return cast('Probe', await self._request('probe'))

    async def event(self, pc: int, name: str, timeout: float) -> float:
        """The time of an event of a connection, waiting for it or for the connection to fail."""
        wanted = self._event(pc, name)
        failed = self._event(pc, 'failed')
        done, _ = await asyncio.wait({wanted, failed}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if wanted in done:
            return wanted.result()

        reason = 'the connection failed' if failed in done else f'no {name} in {timeout} s'
        msg = f'{self.library}: {reason}'
        raise DriverError(msg)

    async def stop(self) -> None:
        """Asks the driver to exit, and kills it if it doesn't."""
        with contextlib.suppress(DriverError, ConnectionError, asyncio.TimeoutError):
            await asyncio.wait_for(self._request('exit'), EXIT_TIMEOUT)
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), EXIT_TIMEOUT)
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
        self._reader.cancel()

    async def _request(self, command: str, **arguments: object) -> Message:
        stdin = self._process.stdin
        if stdin is None or self._reader.done():
            msg = f'{self.library}: the driver has exited'
            raise DriverError(msg)

        command_id = next(self._ids)
        reply = asyncio.get_running_loop().create_future()
        self._replies[command_id] = reply
        try:
            line = encode({'id': command_id, 'cmd': command, **arguments}) + '\n'
            stdin.write(line.encode())
            await stdin.drain()
            return cast('Message', await reply)
        finally:
            del self._replies[command_id]

    def _event(self, pc: int, name: str) -> asyncio.Future[float]:
        key = (pc, name)
        if key not in self._events:
            self._events[key] = asyncio.get_running_loop().create_future()
        return self._events[key]

    async def _read(self) -> None:
        stdout = self._process.stdout
        if stdout is None:
            return
        while (line := await stdout.readline()) != b'':
            message = decode(line)
            if message is not None:
                self._receive(message)
        self._fail_replies()

    def _receive(self, message: Message) -> None:
        if 'event' in message:
            self._receive_event(cast('Event', message))
            return
        reply = cast('Reply', message)
        future = self._replies.get(reply['id'])
        if future is None or future.done():
            return
        if 'result' in reply:
            future.set_result(reply['result'])
        else:
            future.set_exception(DriverError(f'{self.library}: {reply.get("error")}'))

    def _receive_event(self, event: Event) -> None:
        if 'candidate' in event:
            handler = self._candidates.get(event['pc'])
            if handler is not None:
                handler(event['candidate'])
            return
        future = self._event(event['pc'], event['event'])
        if not future.done():
            future.set_result(event['t'])

    def _fail_replies(self) -> None:
        for reply in self._replies.values():
            if not reply.done():
                reply.set_exception(DriverError(f'{self.library}: the driver has exited'))


class VideoSource(TypedDict):
    """The arguments of ``video_send``."""

    path: str
    width: int
    height: int
    fps: float
    bitrate: int
    numbered: bool


@contextlib.asynccontextmanager
async def pair(
    library: str, log: IO[bytes], answering: str | None = None
) -> AsyncGenerator[tuple[Driver, Driver], None]:
    """Two drivers in their own processes, an offerer of a library and an answerer of it or of another."""
    offerer = await Driver.start(library, log)
    try:
        answerer = await Driver.start(answering if answering is not None else library, log)
        try:
            yield offerer, answerer
        finally:
            await answerer.stop()
    finally:
        await offerer.stop()
