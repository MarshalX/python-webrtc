#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""What the drivers in Python share: the data channel commands, and serving the commands of the runner."""

from __future__ import annotations

import abc
import asyncio
import contextlib
import gc
import sys
from typing import TYPE_CHECKING

if sys.platform != 'win32':
    import resource

from benchmarks.drivers.frames import Tally
from benchmarks.protocol import Count, MediaStats, Message, Pinged, Server, now

if TYPE_CHECKING:
    from collections.abc import Callable

PING_DRAIN = 1.0
#: how long a flood may hold the event loop, as long as the lag probe's interval
FLOOD_SLICE = 0.005
#: the open files to allow when the hard limit is unlimited, as Go does on macOS
OPEN_FILES = 10240


class Channel(abc.ABC):
    """A data channel of a library: counts what it receives, and echoes, floods or pings."""

    def __init__(self) -> None:
        self.bytes = 0
        self.messages = 0
        self.echo = False
        self._low = asyncio.Event()
        self._pings: dict[int, float] = {}
        self._answered_all = asyncio.Event()
        self._rtts: list[float] = []

    @abc.abstractmethod
    def send(self, data: bytes) -> None:
        """Sends a binary message."""

    @property
    @abc.abstractmethod
    def buffered_amount(self) -> int:
        """The bytes queued to send."""

    @abc.abstractmethod
    def set_low_threshold(self, value: int) -> None:
        """Sets the buffered amount at or below which the library calls :meth:`on_low`."""

    def on_low(self) -> None:
        """Called by the library when the buffered amount drops to the low threshold."""
        self._low.set()

    def on_message(self, data: bytes) -> None:
        """Called by the library with each message received."""
        self.bytes += len(data)
        self.messages += 1
        if self.echo:
            self.send(data)
        if len(self._pings) != 0:
            self._answered(int.from_bytes(data[:4], 'big'))

    def _answered(self, number: int) -> None:
        sent = self._pings.pop(number, None)
        if sent is not None:
            self._rtts.append((now() - sent) * 1000)
        if len(self._pings) == 0:
            self._answered_all.set()

    async def flood(self, *, size: int, seconds: float, low: int, high: int) -> None:
        """Sends messages for a while, keeping the buffered amount between the watermarks."""
        self.set_low_threshold(low)
        payload, end = bytes(size), now() + seconds
        slice_end = now() + FLOOD_SLICE

        while (remaining := end - now()) > 0:
            if self.buffered_amount >= high:
                self._low.clear()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._low.wait(), remaining)
                continue

            self.send(payload)
            if now() > slice_end:
                # a library that never fills the buffer would block the loop for the whole flood
                await asyncio.sleep(0)
                slice_end = now() + FLOOD_SLICE

    async def ping(self, *, size: int, rate: float, seconds: float) -> list[float]:
        """Sends numbered messages at a rate to an echoing peer, and returns their round trip times in ms."""
        self._rtts = []
        start = now()
        for number in range(round(rate * seconds)):
            await asyncio.sleep(max(0.0, start + number / rate - now()))
            self._answered_all.clear()
            self._pings[number] = now()
            self.send(number.to_bytes(4, 'big') + bytes(size - 4))

        # the replies still in flight
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._answered_all.wait(), PING_DRAIN)
        self._pings.clear()
        return self._rtts


class Driver(abc.ABC):
    """Connections of a library, driven by the commands of the runner."""

    def __init__(self, server: Server) -> None:
        self.server = server
        self.channels: dict[int, Channel] = {}
        #: what each sending or sinking connection wrote or read
        self.tallies: dict[int, Tally] = {}
        #: the sinks that read frame numbers, by connection
        self.numbered: dict[int, bool] = {}

    @abc.abstractmethod
    async def sent_bytes(self, pc: int) -> int:
        """The RTP bytes the connection sent, from the library's stats."""

    @abc.abstractmethod
    async def implementation(self, pc: int) -> str:
        """The encoder of what the connection sends, or the decoder of what it receives."""

    def opened(self, pc: int, channel: Channel) -> None:
        """Keeps the open data channel of a connection."""
        self.channels[pc] = channel
        self.server.emit(pc, 'dc_open')

    async def count(self, pc: int) -> Count:
        """What the data channel of a connection received."""
        channel = self.channels[pc]
        return {'bytes': channel.bytes, 'messages': channel.messages, 't': now()}

    async def echo(self, pc: int) -> Message:
        """Makes the data channel of a connection send back what it receives."""
        self.channels[pc].echo = True
        return {}

    async def flood(self, pc: int, *, size: int, seconds: float, low: int, high: int) -> Message:
        """Sends messages on the data channel of a connection for a while."""
        await self.channels[pc].flood(size=size, seconds=seconds, low=low, high=high)
        return {}

    async def ping(self, pc: int, *, size: int, rate: float, seconds: float) -> Pinged:
        """Measures round trips on the data channel of a connection."""
        return {'rtts_ms': await self.channels[pc].ping(size=size, rate=rate, seconds=seconds)}

    async def media_sink(self, pc: int, *, numbered: bool, remb: int) -> Message:
        """Makes the app read every frame the connection receives; ``remb`` is for drivers that don't decode."""
        del remb
        self.tallies[pc] = Tally()
        self.numbered[pc] = numbered
        return {}

    async def media_stats(self, pc: int) -> MediaStats:
        """What the connection's sender wrote or its sink read."""
        tally = self.tallies[pc]
        return {
            't': now(),
            'frames': tally.frames,
            'audio_ms': tally.audio_ms,
            'bytes': await self.sent_bytes(pc),
            'implementation': await self.implementation(pc),
            'numbers': list(tally.numbers.items()),
        }

    @staticmethod
    async def collect() -> Message:
        """Runs the garbage collector."""
        gc.collect()
        return {}


def _raise_file_limit() -> None:
    """Allows as many sockets as the system does, as Go does by itself, for hundreds of connections."""
    if sys.platform == 'win32':
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    wanted = max(soft, OPEN_FILES) if hard == resource.RLIM_INFINITY else hard
    if wanted > soft:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_NOFILE, (wanted, hard))


async def _serve(factory: Callable[[Server], Driver]) -> None:
    server = Server()
    await server.serve(factory(server))


def serve(factory: Callable[[Server], Driver]) -> None:
    """Serves the commands of the runner with a driver."""
    _raise_file_limit()
    asyncio.run(_serve(factory))
