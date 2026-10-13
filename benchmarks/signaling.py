#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Connects two drivers: the runner relays the descriptions and, if both drivers trickle, the candidates."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from benchmarks.runner import DriverError

#: how long a connection may take to open
TIMEOUT = 15.0

if TYPE_CHECKING:
    from benchmarks.protocol import Candidate, Created, Offer
    from benchmarks.runner import Driver


class _Relay:
    """Passes candidates to a connection, holding them until it has the remote description."""

    def __init__(self, driver: Driver, pc: int) -> None:
        self._driver, self._pc = driver, pc
        self._held: list[Candidate] | None = []
        self._sending: set[asyncio.Task[None]] = set()

    def push(self, candidate: Candidate) -> None:
        """Sends a candidate, or holds it."""
        if self._held is None:
            task = asyncio.ensure_future(self._send(candidate))
            self._sending.add(task)
            task.add_done_callback(self._sending.discard)
        else:
            self._held.append(candidate)

    def open(self) -> None:
        """Sends the held candidates and the next ones, as the connection has its remote description."""
        held: list[Candidate] = self._held if self._held is not None else []
        self._held = None
        for candidate in held:
            self.push(candidate)

    def stop(self) -> None:
        """Drops the candidates on their way."""
        for task in self._sending:
            task.cancel()

    async def _send(self, candidate: Candidate) -> None:
        with contextlib.suppress(DriverError):
            await self._driver.add_candidate(self._pc, candidate)


class Connection:
    """A connection of an offering driver to an answering one, with a data channel."""

    def __init__(self, offerer: Driver, answerer: Driver, *, trickle: bool) -> None:
        self.offerer, self.answerer = offerer, answerer
        self.caller, self.callee = offerer.new_pc(), answerer.new_pc()
        #: Whether candidates trickle: only if asked and both drivers can
        self.trickle = trickle and offerer.info['trickle'] and answerer.info['trickle']
        self._relays: list[_Relay] = []

    async def create(self, *, ordered: bool = True, audio: bool = False, codec: str = '') -> Created:
        """Creates both ends; returns the creation of the caller."""
        options = {'trickle': self.trickle, 'ordered': ordered, 'codec': codec}
        created, _ = await asyncio.gather(
            self.offerer.create(self.caller, 'offerer', audio=audio, **options),
            self.answerer.create(self.callee, 'answerer', audio=False, **options),
        )
        return created

    async def negotiate(self, *, ordered: bool = True, audio: bool = False) -> tuple[Created, Offer]:
        """Creates both ends and exchanges the descriptions; returns the creation and the offer of the caller."""
        created = await self.create(ordered=ordered, audio=audio)
        return created, await self.exchange()

    async def exchange(self) -> Offer:
        """Exchanges the descriptions of the created ends; returns the offer of the caller."""
        caller, callee = (self.offerer, self.caller), (self.answerer, self.callee)
        to_callee, to_caller = self._relay(caller, callee), self._relay(callee, caller)
        offer = await self.offerer.offer(self.caller)
        answer = await self.answerer.answer(self.callee, offer['sdp'])
        to_callee.open()
        await self.offerer.accept(self.caller, answer['sdp'])
        to_caller.open()
        return offer

    async def open(self, timeout: float = TIMEOUT, *, ordered: bool = True, audio: bool = False) -> None:
        """Negotiates and waits until the data channel is open at both ends, and the audio track received."""
        await self.negotiate(ordered=ordered, audio=audio)
        await self.opened(timeout, track=audio)

    async def opened(self, timeout: float = TIMEOUT, *, track: bool = False) -> None:
        """Waits until the data channel is open at both ends, and the answerer received a track if asked."""
        events = [
            self.offerer.event(self.caller, 'dc_open', timeout),
            self.answerer.event(self.callee, 'dc_open', timeout),
        ]
        if track:
            events.append(self.answerer.event(self.callee, 'track', timeout))
        await asyncio.gather(*events)

    async def close(self) -> None:
        """Closes both ends, ignoring a driver that failed."""
        for relay in self._relays:
            relay.stop()
        await asyncio.gather(_close(self.offerer, self.caller), _close(self.answerer, self.callee))

    def _relay(self, source: tuple[Driver, int], target: tuple[Driver, int]) -> _Relay:
        relay = _Relay(*target)
        self._relays.append(relay)
        if self.trickle:
            source[0].on_candidate(source[1], relay.push)
        return relay


async def _close(driver: Driver, pc: int) -> None:
    with contextlib.suppress(DriverError):
        await driver.close(pc)
