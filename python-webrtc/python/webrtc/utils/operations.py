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
import contextlib
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class OperationsChain:
    """Runs the operations of a connection one after another, as the specification requires.

    With none running, an operation starts right away, so its checks fail in the task that called it.

    Args:
        on_empty (:obj:`callable`): Called when the last operation ends.
    """

    def __init__(self, on_empty: Callable[[], None]) -> None:
        self._on_empty = on_empty
        #: The operation that ends last
        self._last: asyncio.Future[None] | None = None

    @property
    def busy(self) -> bool:
        """:obj:`bool`: Whether an operation is running."""
        return self._last is not None and not self._last.done()

    @contextlib.asynccontextmanager
    async def operation(self) -> AsyncGenerator[None, None]:
        """Chains an operation after the ones that are running."""
        previous = self._last
        done = asyncio.get_running_loop().create_future()
        self._last = done
        try:
            if previous is not None and not previous.done():
                # shielded: cancelling this operation must not cancel the end of the previous one
                await asyncio.shield(previous)
            yield
        finally:
            if previous is not None and not previous.done():
                # cancelled while waiting: the next operations still wait for the previous one
                previous.add_done_callback(lambda _: self._end(done))
            else:
                self._end(done)

    def _end(self, done: asyncio.Future[None]) -> None:
        done.set_result(None)
        if self._last is done:
            self._on_empty()


async def later() -> None:
    """Waits for a later task, where the operations of a connection take effect.

    A track added right after set_remote_description() is added before the description is applied.
    """
    await asyncio.sleep(0)
