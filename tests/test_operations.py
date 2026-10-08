#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The operations chain of a connection."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

import pytest

import webrtc
from tests.helpers import QUIET_PERIOD, isolated
from webrtc.utils.operations import OperationsChain

if TYPE_CHECKING:
    from collections.abc import Awaitable


@pytest.mark.asyncio
async def test_cancelled_waiting_operation_leaves_the_running_one() -> None:
    """Cancelling an operation waiting in the chain doesn't break the one it waits for, or the next ones."""
    chain = OperationsChain(lambda: None, lambda: False)
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


async def remote_offer() -> webrtc.RTCSessionDescriptionInit:
    other = webrtc.RTCPeerConnection()
    other.add_transceiver(webrtc.MediaType.audio)
    offer = await other.create_offer()
    other.close()
    return offer


Start = Callable[[webrtc.RTCPeerConnection, webrtc.RTCSessionDescriptionInit], 'Awaitable[object]']

OPERATIONS: dict[str, tuple[webrtc.RTCSignalingState, Start]] = {
    'set_remote_description': (webrtc.RTCSignalingState.stable, lambda pc, offer: pc.set_remote_description(offer)),
    # rolls the local offer back first
    'set_remote_description_in_glare': (
        webrtc.RTCSignalingState.have_local_offer,
        lambda pc, offer: pc.set_remote_description(offer),
    ),
    'set_local_description': (webrtc.RTCSignalingState.stable, lambda pc, _: pc.set_local_description()),
    'create_offer': (webrtc.RTCSignalingState.stable, lambda pc, _: pc.create_offer()),
    'create_answer': (webrtc.RTCSignalingState.have_remote_offer, lambda pc, _: pc.create_answer()),
    'add_ice_candidate': (webrtc.RTCSignalingState.have_remote_offer, lambda pc, _: pc.add_ice_candidate()),
}


async def pending_at_close(name: str) -> asyncio.Future[object]:
    """Starts an operation, then closes its connection while the operation is pending."""
    state, start = OPERATIONS[name]
    pc = webrtc.RTCPeerConnection()
    offer = await remote_offer()
    if state == webrtc.RTCSignalingState.have_local_offer:
        await pc.set_local_description()
    elif state == webrtc.RTCSignalingState.have_remote_offer:
        await pc.set_remote_description(offer)
    task = asyncio.ensure_future(start(pc, offer))
    # the operation passes its checks and waits for its task
    await asyncio.sleep(0)
    pc.close()
    return task


@pytest.mark.asyncio
@pytest.mark.parametrize('name', OPERATIONS)
async def test_operation_pending_at_close_is_cancelled(name: str) -> None:
    """An operation pending at close neither returns nor raises an error: it's cancelled."""
    task = await pending_at_close(name)

    await asyncio.wait({task}, timeout=QUIET_PERIOD)

    assert task.cancelled()


@pytest.mark.asyncio
async def test_operations_after_close_do_not_wait_for_pending_ones() -> None:
    """Operations chained before close are cancelled; ones after it fail right away."""
    pc = webrtc.RTCPeerConnection()
    pending = asyncio.ensure_future(pc.set_local_description())
    queued = asyncio.ensure_future(pc.create_offer())
    await asyncio.sleep(0)
    pc.close()

    with pytest.raises(webrtc.InvalidStateError):
        await asyncio.wait_for(pc.create_offer(), QUIET_PERIOD)
    await asyncio.wait({pending, queued}, timeout=QUIET_PERIOD)

    assert pending.cancelled()
    assert queued.cancelled()


@isolated
def test_pending_operation_does_not_block_exit() -> None:
    """An operation pending at close doesn't keep asyncio.run() from returning."""
    task = asyncio.run(pending_at_close('set_remote_description'))

    assert task.cancelled()
