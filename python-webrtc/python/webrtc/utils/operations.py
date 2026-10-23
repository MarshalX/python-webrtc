#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The operations chain of :obj:`webrtc.RTCPeerConnection`.

An operation (like setting a description) is used as::

    async with connection._operation():
        connection._check_state('do something')
        await later()
        ...  # the native call
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import threading
from typing import TYPE_CHECKING, Callable

from webrtc.utils.loops import LoopState

if TYPE_CHECKING:
    from types import TracebackType


class OperationsChain:
    """Runs the operations of a connection one after another, as the specification requires.

    With none running, an operation starts right away, so its checks fail in the task that called it. After close, a
    pending operation is cancelled, and a new one doesn't wait for it.

    Args:
        on_empty (:obj:`callable`): Called when the last operation ends.
        closed (:obj:`callable`): Whether the connection is closed.
        changing (:obj:`callable`, optional): A context manager around a change of :attr:`busy`.
    """

    def __init__(
        self,
        on_empty: Callable[[], None],
        closed: Callable[[], bool],
        changing: Callable[[], contextlib.AbstractContextManager[None]] = contextlib.nullcontext,
    ) -> None:
        self._on_empty = on_empty
        self._closed = closed
        self._changing = changing
        #: loop-agnostic: loops on several threads may chain operations
        self._last: concurrent.futures.Future[None] | None = None
        # operations start from any thread; chaining is a read-modify-write
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        """:obj:`bool`: Whether an operation is running."""
        return self._last is not None and not self._last.done()

    def operation(self) -> Operation:
        """Chains an operation after the ones that are running."""
        return Operation(self)

    def _cancel_if_closed(self) -> None:
        if self._closed():
            # the specification aborts its steps, it neither resolves nor rejects
            raise asyncio.CancelledError

    def _after(
        self, previous: concurrent.futures.Future[None], done: concurrent.futures.Future[None]
    ) -> asyncio.Future[None]:
        """A future of the running loop that the end of the previous operation resolves."""
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        state = LoopState.of(waiter.get_loop())

        def resolve() -> None:
            # cancelling it leaves the previous operation be
            if not waiter.done():
                waiter.set_result(None)

        def on_previous_done(_: concurrent.futures.Future[None]) -> None:
            # in order with the native records, once the code the previous one resumed ran (see LoopState.drain); if
            # the loop is released first, this operation can't run, so it ends then
            state.post(resolve, after_ready=True, dropped=lambda: self._end(done))

        previous.add_done_callback(on_previous_done)
        return waiter

    def _end(self, done: concurrent.futures.Future[None]) -> None:
        # waiters may be on other loops
        with self._changing():
            try:
                done.set_result(None)
            except concurrent.futures.InvalidStateError:
                # ended already: its loop closed while it waited
                return

            if self._last is done:
                self._on_empty()


class Operation:
    """An operation of the chain, used with ``async with``.

    Not an async generator: a loop's ``shutdown_asyncgens()`` would close one under a suspended operation, whose end
    then fails as an unraisable error that keeps its frames and their connections.
    """

    __slots__ = ('_chain', '_done', '_previous')

    def __init__(self, chain: OperationsChain) -> None:
        self._chain = chain
        # None while closed: the operation fails its checks right away
        self._done: concurrent.futures.Future[None] | None = None
        self._previous: concurrent.futures.Future[None] | None = None

    async def __aenter__(self) -> None:
        chain = self._chain
        if chain._closed():
            return

        done: concurrent.futures.Future[None] = concurrent.futures.Future()
        with chain._changing(), chain._lock:
            previous = chain._last
            chain._last = done
        self._done = done
        self._previous = previous

        if previous is not None and not previous.done():
            try:
                await chain._after(previous, done)
            except BaseException:
                self._end()
                raise

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._done is None:
            return
        try:
            # a cancellation or an exit isn't replaced
            if exc_type is None or issubclass(exc_type, Exception):
                self._chain._cancel_if_closed()
        finally:
            self._end()

    def _end(self) -> None:
        chain = self._chain
        done = self._done
        previous = self._previous
        if done is None:
            return

        if previous is not None and not previous.done():
            # cancelled while waiting: the next operations still wait for the previous one
            previous.add_done_callback(lambda _: chain._end(done))
        else:
            chain._end(done)


async def later() -> None:
    """Waits for a later task, where the operations of a connection take effect.

    A track added right after set_remote_description() is added before the description is applied.
    """
    await asyncio.sleep(0)
