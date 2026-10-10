#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The operations chain of a connection."""

from __future__ import annotations

import asyncio
import gc
import threading
from typing import TYPE_CHECKING, Callable

import pytest

import webrtc
from tests.helpers import QUIET_PERIOD
from tests.isolation import isolated
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


def test_operations_stranded_by_a_closed_loop_end_quietly() -> None:
    """Operations waiting in the chain when their loop closes end without errors once collected."""
    chain = OperationsChain(lambda: None, lambda: False)
    loop = asyncio.new_event_loop()

    async def operation() -> None:
        async with chain.operation():
            await loop.create_future()

    operations = [operation() for _ in range(3)]
    tasks = [loop.create_task(coroutine) for coroutine in operations]
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    for coroutine in operations:
        # as collecting it does
        coroutine.close()
    assert not any(task.done() for task in tasks)


def test_operation_waiting_for_one_of_another_loop_resumes() -> None:
    """Operations chain across loops on other threads."""
    chain = OperationsChain(lambda: None, lambda: False)
    started = threading.Event()
    release = threading.Event()

    async def first() -> None:
        async with chain.operation():
            started.set()
            await asyncio.get_running_loop().run_in_executor(None, release.wait)

    other = threading.Thread(target=asyncio.run, args=(first(),))
    other.start()
    assert started.wait(5)

    async def second() -> None:
        async def operation() -> None:
            async with chain.operation():
                pass

        waiting = asyncio.ensure_future(operation())
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(waiting, 5)

    asyncio.run(second())
    other.join(5)
    assert not chain.busy


def test_operation_waiting_in_a_closed_loop_lets_the_chain_go_on(caplog: pytest.LogCaptureFixture) -> None:
    """An operation whose loop closes while it waits neither wakes that loop nor holds up the chain.

    Its task stays alive: its code never runs again, as on 3.9, where a collected task doesn't run it either.
    """
    chain = OperationsChain(lambda: None, lambda: False)
    started = threading.Event()
    release = threading.Event()

    async def first() -> None:
        async with chain.operation():
            started.set()
            await asyncio.get_running_loop().run_in_executor(None, release.wait)

    other = threading.Thread(target=asyncio.run, args=(first(),))
    other.start()
    assert started.wait(5)

    async def operation() -> None:
        async with chain.operation():
            pass

    loop = asyncio.new_event_loop()
    waiting = loop.create_task(operation())
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    release.set()
    other.join(5)
    assert not chain.busy
    # collected later, its code may end the operation again (3.10+)
    del waiting
    _ = gc.collect()
    assert not chain.busy
    assert [record.message for record in caplog.records if record.name == 'concurrent.futures'] == []


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
