#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import inspect
import os
import pathlib
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING, Callable, Protocol, TypeVar, cast

import pytest
from typing_extensions import Never

import webrtc
import wrtc

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable

#: The fixture creating connections with a configuration
CreatePC = Callable[..., webrtc.RTCPeerConnection]

_T = TypeVar('_T')


def stats_of_type(report: webrtc.RTCStatsReport, stats_type: str) -> list[webrtc.RTCStats]:
    """The stats of a type in a report."""
    return [stats for stats in report.values() if stats.type == stats_type]


def copy_frame(
    frame: webrtc.RTCEncodedVideoFrame | webrtc.RTCEncodedAudioFrame,
) -> webrtc.RTCEncodedVideoFrame | webrtc.RTCEncodedAudioFrame:
    """A copy of an encoded frame, by the constructor of its kind."""
    if isinstance(frame, webrtc.RTCEncodedVideoFrame):
        return webrtc.RTCEncodedVideoFrame(frame)
    return webrtc.RTCEncodedAudioFrame(frame)


def mistyped(value: object) -> _T:
    """A value of the wrong type, passed where a test checks that the library rejects it at runtime."""
    return cast('_T', value)


async def exchange_offer(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)


async def exchange_answer(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    await caller.set_remote_description(answer)


async def exchange_offer_answer(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    await exchange_offer(caller, callee)
    await exchange_answer(caller, callee)


async def generate_answer(offer: webrtc.RTCSessionDescriptionInit) -> webrtc.RTCSessionDescriptionInit:
    pc = webrtc.RTCPeerConnection()

    await pc.set_remote_description(offer)
    answer = await pc.create_answer()

    pc.close()

    return answer


#: How long a test waits to see that something doesn't happen
QUIET_PERIOD = 0.3


async def _called(function: Callable[[], object]) -> object:
    result = function()
    return await result if inspect.isawaitable(result) else result


async def wait_until(predicate: Callable[[], object], what: str, timeout: float = 10) -> None:
    """Polls until the predicate (a function or a coroutine function) is true.

    Raises:
        TimeoutError: The predicate isn't true in time, the message names what it waited for.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not bool(await _called(predicate)):
        if loop.time() > deadline:
            msg = f'Timed out waiting for {what}'
            raise TimeoutError(msg)
        await asyncio.sleep(0.05)


async def wait_for_ice_gathering_complete(pc: webrtc.RTCPeerConnection, timeout: float = 10) -> None:
    await wait_until(lambda: pc.ice_gathering_state == webrtc.RTCIceGatheringState.complete, 'ICE gathering', timeout)


class NamedEvents(Protocol):
    """An event target with untyped names."""

    def on(self, name: str, handler: Callable[[webrtc.Event], object], /) -> object: ...

    def off(self, name: str, handler: Callable[[webrtc.Event], object], /) -> None: ...


def wait_for_event(
    target: webrtc.EventTarget[Never],
    name: str,
    timeout: float = 10,
    *,
    predicate: Callable[[webrtc.Event], bool] | None = None,
) -> Awaitable[webrtc.Event]:
    """Registers for the next event of a type (the next one the predicate accepts, if given) right away.

    Returns:
        An awaitable of the event.
    """
    future = asyncio.get_running_loop().create_future()
    events = cast('NamedEvents', target)

    def on_event(event: webrtc.Event) -> None:
        if not future.done() and (predicate is None or predicate(event)):
            events.off(name, on_event)
            future.set_result(event)

    _ = events.on(name, on_event)
    return asyncio.wait_for(future, timeout)


async def next_task() -> None:
    """Lets the current task end, like awaiting a timer.

    What a task keeps until it ends (like the parameters of a sender) expires, and callbacks posted meanwhile run.
    asyncio.sleep(0) doesn't end it: the code it resumes is like a microtask of the same task.
    """
    loop = asyncio.get_running_loop()
    timer = loop.create_future()
    loop.call_later(0, timer.set_result, None)
    await timer


# tasks adding candidates, kept until done (the loop only keeps a weak reference to a task)
_adding_candidates: set[asyncio.Future[None]] = set()


async def _add_ice_candidate(pc: webrtc.RTCPeerConnection, candidate: webrtc.RTCIceCandidate) -> None:
    try:
        await pc.add_ice_candidate(candidate)
    except webrtc.InvalidStateError:
        # a test may close the connection before the candidates of the other one are added
        if pc.signaling_state != webrtc.RTCSignalingState.closed:
            raise


def exchange_ice_candidates(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Trickles the candidates of each connection to the other one."""
    for pc, other in ((caller, callee), (callee, caller)):

        def on_candidate(event: webrtc.RTCPeerConnectionIceEvent, other: webrtc.RTCPeerConnection = other) -> None:
            if event.candidate is not None:
                task = asyncio.ensure_future(_add_ice_candidate(other, event.candidate))
                _adding_candidates.add(task)
                task.add_done_callback(_adding_candidates.discard)

        pc.on('icecandidate', on_candidate)


async def connect(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, timeout: float = 10) -> None:
    """Negotiates and waits until both connections are connected."""
    exchange_ice_candidates(caller, callee)
    await exchange_offer_answer(caller, callee)

    def connected() -> bool:
        return all(pc.connection_state == webrtc.RTCPeerConnectionState.connected for pc in (caller, callee))

    await wait_until(connected, 'both connections to connect', timeout)


async def wait_until_unmuted(track: webrtc.MediaStreamTrack, timeout: float = 10) -> None:
    """Waits until media arrives on a remote track, which may take longer than connecting."""
    if track.muted:
        await wait_for_event(track, 'unmute', timeout)


def capture_mode(track: webrtc.MediaStreamTrack) -> tuple[int | None, int | None, float | None]:
    """The width, height and frame rate a camera track captures at."""
    settings = track.get_settings()
    return settings.width, settings.height, settings.frame_rate


async def connect_track(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    track: webrtc.MediaStreamTrack,
    *,
    timeout: float = 10,
) -> webrtc.MediaStreamTrack:
    """Sends a track from the caller, connects, and returns the remote track of the callee."""
    caller.add_track(track)
    track_event = wait_for_event(callee, 'track', timeout)
    await connect(caller, callee, timeout)
    event = await track_event
    assert isinstance(event, webrtc.RTCTrackEvent)
    return event.track


async def write_video(
    generator: webrtc.VideoTrackGenerator,
    data: bytes,
    size: tuple[int, int],
    *,
    stop: asyncio.Event,
    interval: float = 1 / 30,
) -> None:
    """Writes I420 frames of the data and the size to a generator, one an interval, until stopped."""
    width, height = size
    writer = generator.writable.get_writer()
    timestamp = 0
    while not stop.is_set():
        await writer.write(
            webrtc.VideoFrame(
                data,
                webrtc.VideoFrameBufferInit(format='I420', coded_width=width, coded_height=height, timestamp=timestamp),
            )
        )
        timestamp += round(interval * 1_000_000)
        await asyncio.sleep(interval)


@contextlib.asynccontextmanager
async def writing(write: Callable[..., Awaitable[None]], *args: object, **kwargs: object) -> AsyncGenerator[None]:
    """Runs write(*args, stop=stop, **kwargs) in a task for the block, then stops it."""
    stop = asyncio.Event()
    task = asyncio.ensure_future(write(*args, stop=stop, **kwargs))
    try:
        yield
    finally:
        stop.set()
        await asyncio.wait_for(task, 10)


# the memory of sanitizers (ASan quarantine, TSan shadow) hides leaks from resident memory
SANITIZED: bool = wrtc._sanitized
skip_if_sanitized = pytest.mark.skipif(SANITIZED, reason='resident memory says nothing under sanitizers')


def rss_bytes() -> int:
    """The resident memory of the process, in bytes."""
    if sys.platform.startswith('linux'):
        statm = pathlib.Path('/proc/self/statm').read_text(encoding='utf-8')
        return int(statm.split()[1]) * os.sysconf('SC_PAGE_SIZE')
    if sys.platform == 'win32':

        class Counters(ctypes.Structure):
            _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [
                (name, ctypes.c_size_t)
                for name in (
                    'PeakWorkingSetSize',
                    'WorkingSetSize',
                    'QuotaPeakPagedPoolUsage',
                    'QuotaPagedPoolUsage',
                    'QuotaPeakNonPagedPoolUsage',
                    'QuotaNonPagedPoolUsage',
                    'PagefileUsage',
                    'PeakPagefileUsage',
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
        return int(counters.WorkingSetSize)
    # macOS and other BSDs
    return int(subprocess.check_output(['/bin/ps', '-o', 'rss=', '-p', str(os.getpid())])) * 1024


#: The root of the project, which has the tests package (pytest may run from elsewhere, like cibuildwheel)
ROOT = pathlib.Path(pathlib.Path(pathlib.Path(__file__).resolve()).parent).parent


def run_isolated(script: str, timeout: float = 60) -> str:
    """Runs a script in its own process, so a crash or a deadlock fails the test only; returns its output."""
    # a crash tells where: the Python stacks of every thread, and glibc's fatal errors, written to a tty otherwise
    env = {**os.environ, 'PYTHONFAULTHANDLER': '1', 'LIBC_FATAL_STDERR_': '1'}
    result = subprocess.run(
        [sys.executable, '-c', textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=ROOT,
        env=env,
        check=False,
    )
    assert result.returncode == 0, f'exit code {result.returncode}:\n{result.stderr[-6000:]}'
    return result.stdout
