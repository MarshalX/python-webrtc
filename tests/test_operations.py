#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The operations chain of a connection."""

from __future__ import annotations

import asyncio

import pytest

from webrtc.utils.operations import OperationsChain


@pytest.mark.asyncio
async def test_cancelled_waiting_operation_leaves_the_running_one() -> None:
    """Cancelling an operation waiting in the chain doesn't break the one it waits for, or the next ones."""
    chain = OperationsChain(lambda: None)
    release = asyncio.Event()
    order: list[str] = []

    async def operation(name: str, *, hold: bool = False) -> None:
        async with chain.operation():
            if hold:
                await release.wait()
            order.append(name)

    first = asyncio.ensure_future(operation('first', hold=True))
    await asyncio.sleep(0)
    waiting = asyncio.ensure_future(operation('cancelled'))
    await asyncio.sleep(0)
    waiting.cancel()
    third = asyncio.ensure_future(operation('third'))
    await asyncio.sleep(0)

    release.set()
    await asyncio.wait_for(asyncio.gather(first, third), 5)
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert order == ['first', 'third']
    assert not chain.busy
