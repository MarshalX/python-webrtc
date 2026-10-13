#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The protocol between the runner and a driver: JSON objects, one a line, over the driver's stdin and stdout.

The runner sends commands, ``{"id": 1, "cmd": "offer", "pc": 0}``, and the driver replies to each with
``{"id": 1, "result": {...}}`` or ``{"id": 1, "error": "..."}``, in any order. The driver also sends events,
``{"event": "connected", "pc": 0, "t": 12.5}``. Times are seconds of the driver's own monotonic clock, so only
differences of times of one driver mean something. Lines of stdout that aren't JSON objects are skipped.

Commands are the methods of :class:`benchmarks.runner.Driver`, their replies the typed dictionaries below.

Events: ``candidate`` (with ``candidate``, only with ``trickle``), ``gathered``, ``ice_connected`` (ICE
``connected`` or ``completed``), ``connected`` (the connection, so DTLS too), ``dc_open`` (the data channel),
``track`` (the answerer received the audio track), ``failed``. Each but ``candidate`` is sent once a connection.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from typing import TYPE_CHECKING, TypedDict, Union, cast

from benchmarks.stats import LoopLag

if TYPE_CHECKING:
    from collections.abc import Mapping

Message = dict[str, object]
Candidate = dict[str, Union[str, int, None]]
DATA_CHANNEL_LABEL = 'bench'


class _Event(TypedDict):
    event: str
    pc: int
    t: float


class Event(_Event, total=False):
    """An event of a connection."""

    candidate: Candidate


class _Command(TypedDict):
    id: int


class Reply(_Command, total=False):
    """The reply to a command: its result, or the error it failed with."""

    result: Message
    error: str


class Hello(TypedDict):
    """The reply to ``hello``."""

    library: str
    version: str
    trickle: bool


class Created(TypedDict):
    """The reply to ``create``."""

    t_start: float
    t_end: float


class Offer(TypedDict):
    """The reply to ``offer``."""

    sdp: str
    t_start: float
    t_offer: float


class Answer(TypedDict):
    """The reply to ``answer``."""

    sdp: str


class Count(TypedDict):
    """The reply to ``count``."""

    bytes: int
    messages: int
    t: float


class Pinged(TypedDict):
    """The reply to ``ping``."""

    rtts_ms: list[float]


class _MediaStats(TypedDict):
    t: float
    frames: int
    implementation: str


class MediaStats(_MediaStats, total=False):
    """The reply to ``media_stats``."""

    audio_ms: float
    bytes: int
    numbers: list[tuple[int, float]]


class Probe(TypedDict, total=False):
    """The reply to ``probe``."""

    lag_p95_ms: float


def encode(message: Mapping[str, object]) -> str:
    """A message as a line."""
    return json.dumps(message, separators=(',', ':'))


def decode(line: str | bytes) -> Message | None:
    """The message of a line, or None if the line isn't a JSON object."""
    try:
        message: object = json.loads(line)
    except ValueError:
        return None
    return cast('Message', message) if isinstance(message, dict) else None


def now() -> float:
    """The monotonic clock of the driver, in seconds."""
    return time.perf_counter()


class Server:
    """The driver side of the protocol for the drivers in Python: runs each command as the driver's method of its name.

    Create it in a running event loop.
    """

    def __init__(self) -> None:
        self._sent: set[tuple[int, str]] = set()
        self._lag = LoopLag()
        self._lines: asyncio.Queue[str | None] = asyncio.Queue()
        self._tasks: set[asyncio.Task[None]] = set()

    def emit(self, pc: int, event: str) -> None:
        """Sends an event of a connection, once."""
        if (pc, event) in self._sent:
            return
        self._sent.add((pc, event))
        self._send({'event': event, 'pc': pc, 't': now()})

    def emit_candidate(self, pc: int, candidate: Candidate) -> None:
        """Sends a local candidate of a connection."""
        self._send({'event': 'candidate', 'pc': pc, 't': now(), 'candidate': candidate})

    def emit_states(self, pc: int, ice: str, connection: str) -> None:
        """Sends the events the ICE and connection states of a connection reached."""
        if ice in {'connected', 'completed'}:
            self.emit(pc, 'ice_connected')
        if connection in {'connected', 'failed'}:
            self.emit(pc, connection)

    async def serve(self, driver: object) -> None:
        """Runs the commands on the driver until ``exit`` or the end of stdin."""
        loop = asyncio.get_running_loop()
        threading.Thread(target=_read_stdin, args=(loop, self._lines), daemon=True).start()
        with self._lag:
            while (line := await self._lines.get()) is not None:
                self._dispatch(driver, line)

    def _dispatch(self, driver: object, line: str) -> None:
        message = decode(line)
        if message is None:
            return
        task = asyncio.ensure_future(self._run(driver, message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, driver: object, message: Message) -> None:
        command_id, name = message.pop('id'), str(message.pop('cmd'))
        if name == 'exit':
            self._send({'id': command_id, 'result': {}})
            self._lines.put_nowait(None)
            return
        try:
            result = await (self._probe() if name == 'probe' else getattr(driver, name)(**message))
        except Exception as error:  # ruff: ignore[blind-except] - the runner reports what failed
            self._send({'id': command_id, 'error': f'{type(error).__name__}: {error}'})
        else:
            self._send({'id': command_id, 'result': result})

    async def _probe(self) -> Probe:
        result: Probe = {'lag_p95_ms': self._lag.p95_ms}
        self._lag.reset()
        return result

    @staticmethod
    def _send(message: Mapping[str, object]) -> None:
        sys.stdout.write(encode(message) + '\n')
        sys.stdout.flush()


def _read_stdin(loop: asyncio.AbstractEventLoop, lines: asyncio.Queue[str | None]) -> None:
    for line in sys.stdin:
        loop.call_soon_threadsafe(lines.put_nowait, line)
    loop.call_soon_threadsafe(lines.put_nowait, None)
