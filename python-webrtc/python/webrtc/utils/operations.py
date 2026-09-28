#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
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

import asyncio
import contextlib
from typing import AsyncIterator, Callable, Optional


class OperationsChain:
    """Runs the operations of a connection one after another, as the specification requires. With none running,
    an operation starts right away, so its checks fail in the task that called it.

    Args:
        on_empty (:obj:`callable`): Called when the last operation ends.
    """

    def __init__(self, on_empty: Callable[[], None]):
        self._on_empty = on_empty
        #: The operation that ends last
        self._last: Optional[asyncio.Future] = None

    @property
    def busy(self) -> bool:
        """:obj:`bool`: Whether an operation is running."""
        return self._last is not None and not self._last.done()

    @contextlib.asynccontextmanager
    async def operation(self) -> AsyncIterator[None]:
        """Chains an operation after the ones that are running."""
        previous = self._last
        done = asyncio.get_running_loop().create_future()
        self._last = done
        try:
            if previous is not None and not previous.done():
                await previous
            yield
        finally:
            done.set_result(None)
            if self._last is done:
                self._on_empty()


async def later() -> None:
    """Operations of a connection take effect in a later task than the code that started them: a track added right
    after set_remote_description() is added before the description is applied."""
    await asyncio.sleep(0)
