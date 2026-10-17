#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The operations chain of a connection."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import threading
from typing import TYPE_CHECKING, Callable

import pytest

import webrtc
from tests.helpers import QUIET_PERIOD, generate_answer, wait_for_event
from tests.isolation import isolated
from tests.timing import seconds
from webrtc.utils.loops import LoopState
from webrtc.utils.operations import OperationsChain

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterator

#: More unapplied descriptions than a connection keeps (32)
NEGOTIATIONS = 10
TIMEOUT = seconds(10)


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
    await asyncio.wait_for(asyncio.gather(first, third), seconds(5))
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert order == ['first', 'third']
    assert not chain.busy


@pytest.mark.asyncio
async def test_next_operation_waits_for_the_code_the_previous_one_resumed() -> None:
    """Code awaiting an operation resumes before the next one chained behind it, even over a few iterations.

    Like a browser's microtasks run before a task: a callback chain the completion started, as a JS bridge's promise
    jobs are, starts its work first.
    """
    chain = OperationsChain(lambda: None, lambda: False)
    release = asyncio.Event()
    order: list[str] = []

    async def operation(name: str, *, hold: bool = False) -> None:
        async with chain.operation():
            if hold:
                await release.wait()
            order.append(name)

    async def awaiting() -> None:
        await operation('first', hold=True)
        for _ in range(3):
            # a step of the resumed code
            await asyncio.sleep(0)
        order.append('resumed')

    resumed = asyncio.ensure_future(awaiting())
    await asyncio.sleep(0)
    second = asyncio.ensure_future(operation('second'))
    await asyncio.sleep(0)
    release.set()
    await asyncio.wait_for(asyncio.gather(resumed, second), seconds(5))
    assert order == ['first', 'resumed', 'second']


@pytest.mark.asyncio
async def test_operations_of_a_closed_chain_run_at_once() -> None:
    """Once closed, an operation doesn't wait for the running one."""
    closed = False
    chain = OperationsChain(lambda: None, lambda: closed)
    release = asyncio.Event()

    async def hold() -> None:
        async with chain.operation():
            await release.wait()

    held = asyncio.ensure_future(hold())
    await asyncio.sleep(0)
    closed = True
    ran = False
    async with chain.operation():
        ran = True
    assert ran
    assert chain.busy
    release.set()
    # the running one is aborted once it ends
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(held, seconds(5))


@pytest.mark.asyncio
async def test_add_ice_candidate_without_a_remote_description_rejects_at_once() -> None:
    """With the chain empty, it rejects in its first step, before the loop runs anything else."""
    pc = webrtc.RTCPeerConnection()
    try:
        added = asyncio.ensure_future(pc.add_ice_candidate())
        await asyncio.sleep(0)
        assert added.done()
        with pytest.raises(webrtc.InvalidStateError, match='remote description'):
            added.result()
        assert pc.remote_description is None
    finally:
        pc.close()


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
    # as asyncio.run and pytest-asyncio close a loop: its async generators first
    loop.run_until_complete(loop.shutdown_asyncgens())
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
    assert started.wait(seconds(5))

    async def second() -> None:
        async def operation() -> None:
            async with chain.operation():
                pass

        waiting = asyncio.ensure_future(operation())
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(waiting, seconds(5))

    asyncio.run(second())
    other.join(seconds(5))
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
    assert started.wait(seconds(5))

    async def operation() -> None:
        async with chain.operation():
            pass

    loop = asyncio.new_event_loop()
    waiting = loop.create_task(operation())
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    release.set()
    other.join(seconds(5))
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


async def created_connection() -> webrtc.RTCPeerConnection:  # ruff: ignore[unused-async]
    # its events go to the loop it's created on
    return webrtc.RTCPeerConnection()


@pytest.fixture
def idle_events() -> Iterator[tuple[webrtc.RTCPeerConnection, asyncio.AbstractEventLoop, asyncio.AbstractEventLoop]]:
    """A connection whose events wait on a loop only the test runs."""
    events, other = asyncio.new_event_loop(), asyncio.new_event_loop()
    pc = events.run_until_complete(created_connection())
    yield pc, events, other
    pc.close()
    events.close()
    other.close()


async def signaling_change(pc: webrtc.RTCPeerConnection, state: webrtc.RTCSignalingState) -> Awaitable[webrtc.Event]:  # ruff: ignore[unused-async]
    return wait_for_event(pc, 'signalingstatechange', predicate=lambda _event: pc.signaling_state == state)


def test_descriptions_of_an_operation_of_another_loop(
    idle_events: tuple[webrtc.RTCPeerConnection, asyncio.AbstractEventLoop, asyncio.AbstractEventLoop],
) -> None:
    """The descriptions show with the operation's event."""
    pc, events, other = idle_events
    pc.add_transceiver(webrtc.MediaType.audio)
    changed = events.run_until_complete(signaling_change(pc, webrtc.RTCSignalingState.have_local_offer))

    other.run_until_complete(pc.set_local_description())

    _ = events.run_until_complete(changed)
    assert pc.signaling_state == webrtc.RTCSignalingState.have_local_offer
    assert pc.local_description is not None
    assert pc.local_description.type == webrtc.RTCSdpType.offer


@pytest.mark.xfail(
    strict=True, reason='lifetime model: an operation of another loop applies its descriptions before its state'
)
def test_descriptions_and_state_of_an_operation_of_another_loop_change_together(
    idle_events: tuple[webrtc.RTCPeerConnection, asyncio.AbstractEventLoop, asyncio.AbstractEventLoop],
) -> None:
    """webrtc-pc: a description and its signaling state change in one step."""
    pc, _events, other = idle_events
    pc.add_transceiver(webrtc.MediaType.audio)

    other.run_until_complete(pc.set_local_description())

    assert pc.local_description is not None
    assert pc.local_description.type == webrtc.RTCSdpType.offer
    assert pc.signaling_state == webrtc.RTCSignalingState.have_local_offer


async def cancelled_once_called(operation: Awaitable[None]) -> None:
    """Cancels an operation once it called the engine."""
    state = LoopState.of(asyncio.get_running_loop())
    earlier = set(state.pending)
    task = asyncio.ensure_future(operation)
    # two yields run the task into the native call
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(set(state.pending) - earlier) > 0, 'the operation has not called the engine yet'
    _ = task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def signaling_changes(pc: webrtc.RTCPeerConnection, count: int) -> Awaitable[list[webrtc.RTCSignalingState]]:  # ruff: ignore[unused-async]
    states: list[webrtc.RTCSignalingState] = []
    done: asyncio.Future[list[webrtc.RTCSignalingState]] = asyncio.get_running_loop().create_future()

    def on_change(_event: webrtc.Event) -> None:
        states.append(pc.signaling_state)
        if len(states) == count:
            done.set_result(states)

    pc.on('signalingstatechange', on_change)
    return asyncio.wait_for(done, TIMEOUT)


def test_negotiations_while_the_events_wait(
    idle_events: tuple[webrtc.RTCPeerConnection, asyncio.AbstractEventLoop, asyncio.AbstractEventLoop],
) -> None:
    """Unapplied negotiations show the last descriptions once fired."""
    pc, events, other = idle_events
    changes = events.run_until_complete(signaling_changes(pc, 2 * NEGOTIATIONS))

    async def negotiate() -> None:
        offer = await remote_offer()
        for _ in range(NEGOTIATIONS):
            # the shown state stays stable: the checks pass
            await cancelled_once_called(pc.set_remote_description(offer))
            await cancelled_once_called(pc.set_local_description())

    other.run_until_complete(negotiate())

    states = events.run_until_complete(changes)
    assert states == [webrtc.RTCSignalingState.have_remote_offer, webrtc.RTCSignalingState.stable] * NEGOTIATIONS
    assert pc.local_description is not None
    assert pc.local_description.type == webrtc.RTCSdpType.answer
    assert pc.remote_description is not None
    assert pc.remote_description.type == webrtc.RTCSdpType.offer


def test_operations_of_another_loop_meet_the_actual_state(
    idle_events: tuple[webrtc.RTCPeerConnection, asyncio.AbstractEventLoop, asyncio.AbstractEventLoop],
) -> None:
    """The shown state lets them through; the engine's state refuses them."""
    pc, events, other = idle_events

    async def behind_stable() -> None:
        own = await pc.create_offer()
        await pc.set_remote_description(await remote_offer())
        with pytest.raises(webrtc.InvalidStateError):
            _ = await pc.create_offer()
        with pytest.raises(webrtc.InvalidStateError):
            await pc.set_local_description(own)

    shown = events.run_until_complete(signaling_change(pc, webrtc.RTCSignalingState.have_remote_offer))
    other.run_until_complete(behind_stable())
    _ = events.run_until_complete(shown)

    async def behind_remote_offer() -> None:
        await pc.set_local_description()
        with pytest.raises(webrtc.InvalidStateError):
            _ = await pc.create_answer()

    shown = events.run_until_complete(signaling_change(pc, webrtc.RTCSignalingState.stable))
    other.run_until_complete(behind_remote_offer())
    _ = events.run_until_complete(shown)
    shown = events.run_until_complete(signaling_change(pc, webrtc.RTCSignalingState.have_local_offer))
    other.run_until_complete(pc.set_local_description())
    _ = events.run_until_complete(shown)

    async def behind_local_offer() -> None:
        assert pc.local_description is not None
        answer = await generate_answer(webrtc.RTCSessionDescriptionInit('offer', pc.local_description.sdp))
        await pc.set_local_description(webrtc.RTCSessionDescriptionInit('rollback'))
        with pytest.raises(webrtc.InvalidStateError):
            await pc.set_remote_description(answer)

    other.run_until_complete(behind_local_offer())
