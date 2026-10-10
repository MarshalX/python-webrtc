#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""LoopState ordering and release."""

from __future__ import annotations

import asyncio
import gc
import threading
import weakref
from typing import Callable

import pytest
from typing_extensions import Never, override

import webrtc
import wrtc
from tests.helpers import called, mistyped
from tests.isolation import isolated
from webrtc.utils.events import EventTarget
from webrtc.utils.loops import LoopState


def _in_thread(target: Callable[[], None]) -> None:
    thread = threading.Thread(target=target)
    thread.start()
    thread.join()


@pytest.mark.asyncio
async def test_posted_callbacks_run_before_later_timers() -> None:
    """Callbacks posted before a timer run before it."""
    loop = asyncio.get_running_loop()
    state = LoopState.of(loop)
    order: list[int | str] = []
    for i in range(10):
        state.post(lambda i=i: order.append(i))
    wrtc._testing.dispatcher_idle()
    timer = loop.create_future()

    def on_timer() -> None:
        order.append('timer')
        timer.set_result(None)

    loop.call_later(0, on_timer)
    await timer
    assert order == [*range(10), 'timer']


@pytest.mark.asyncio
async def test_completions_from_native_threads_settle_in_order() -> None:
    """Cross-thread completions settle in order."""
    state = LoopState.of(asyncio.get_running_loop())
    started = [state.start(None) for _ in range(10)]
    order: list[int] = []
    for i, (_, future) in enumerate(started):
        future.add_done_callback(lambda _future, i=i: order.append(i))

    def complete_all() -> None:
        for i, (token, _) in enumerate(started):
            wrtc._testing.complete(state.mailbox, token, i * 10)

    _in_thread(complete_all)
    results = await asyncio.gather(*(future for _, future in started))
    assert results == [i * 10 for i in range(10)]
    assert order == list(range(10))
    assert state.pending == {}


@pytest.mark.asyncio
async def test_microtasks_of_a_callback_run_before_the_next_one() -> None:
    """call_soon runs before the next posted callback."""
    loop = asyncio.get_running_loop()
    state = LoopState.of(loop)
    order: list[str] = []
    done = loop.create_future()

    def first() -> None:
        order.append('first')
        loop.call_soon(order.append, 'microtask')

    def second() -> None:
        order.append('second')
        done.set_result(None)

    state.post(first)
    state.post(second)
    await done
    assert order == ['first', 'microtask', 'second']


@pytest.mark.asyncio
async def test_resumed_code_runs_before_the_next_callback_only() -> None:
    """Resumed code runs before the next callback."""
    loop = asyncio.get_running_loop()
    state = LoopState.of(loop)
    order: list[str] = []
    resumed = asyncio.Event()

    async def awaiting() -> None:
        await resumed.wait()
        order.append('resumed')
        await asyncio.sleep(0)
        order.append('resumed again')

    task = loop.create_task(awaiting())
    await asyncio.sleep(0)
    after_next = loop.create_future()
    state.post(resumed.set, resumes=True)
    state.post(lambda: order.append('next'))
    state.post(lambda: after_next.set_result(None))
    await task
    await after_next
    assert order == ['resumed', 'resumed again', 'next']

    timer = loop.create_future()
    state.post(lambda: order.append('later'))
    loop.call_later(0, timer.set_result, None)
    await timer
    assert order[-1] == 'later'


@pytest.mark.asyncio
async def test_code_awaiting_a_completion_runs_before_the_next_record() -> None:
    """Awaiter resumes before later records."""
    loop = asyncio.get_running_loop()
    state = LoopState.of(loop)
    order: list[str] = []
    token, future = state.start(None)

    async def awaiting() -> None:
        order.append(f'result {await future}')
        await asyncio.sleep(0)
        order.append('resumed again')

    task = loop.create_task(awaiting())
    await asyncio.sleep(0)
    _in_thread(lambda: wrtc._testing.complete(state.mailbox, token, 1))
    after_next = loop.create_future()
    state.post(lambda: order.append('next'))
    state.post(lambda: after_next.set_result(None))
    await task
    await after_next
    assert order == ['result 1', 'resumed again', 'next']


def test_states_are_kept_by_their_loop() -> None:
    loop = asyncio.new_event_loop()
    try:
        state = LoopState.of(loop)
        assert LoopState.of(loop) is state
    finally:
        loop.close()


def test_loops_are_collected_with_what_they_had_queued() -> None:
    """Closed loop is collected with its state."""

    class Held:
        loop: asyncio.AbstractEventLoop

    refs: list[weakref.ref[object]] = []
    for _ in range(5):
        loop = asyncio.new_event_loop()
        held = Held()
        held.loop = loop
        state = LoopState.of(loop)
        _, future = state.start(None)
        # never run: the loop closes first
        state.post(lambda _held=held: None)
        loop.close()
        refs.extend(weakref.ref(obj) for obj in (loop, held, state, future, state.mailbox))
        del loop, held, state, future
    gc.collect()

    assert [ref for ref in refs if ref() is not None] == []


def test_closed_loop_held_by_the_user_is_released_on_collection() -> None:
    """Held closed loop's state is released."""
    loop = asyncio.new_event_loop()
    state = LoopState.of(loop)
    _, future = state.start(None)
    state.post(lambda: None)
    # an in-progress Dispatcher collection (--gc-on-emit) would skip this one
    wrtc._testing.dispatcher_idle()
    loop.close()
    assert not state.mailbox.closed

    gc.collect()
    assert state.mailbox.closed
    assert state.mailbox.dropped == 1
    assert state.pending == {}
    assert not future.cancelled()  # a closed loop can't run its callbacks

    other = asyncio.new_event_loop()
    try:
        released = LoopState.of(other)
        other.close()
        _ = LoopState.of(asyncio.new_event_loop()).mailbox
        assert released.mailbox.closed
    finally:
        other.close()


@isolated(timeout=60)
def test_collections_under_the_locks_of_the_states_do_not_wait_for_them() -> None:
    """GC sweeps under the state locks without waiting."""
    thresholds = gc.get_threshold()
    # collect every other allocation, hitting every locked region
    gc.set_threshold(1)
    try:
        for _ in range(10):
            loop = asyncio.new_event_loop()
            state = LoopState.of(loop)
            state.post(lambda: None)
            loop.close()
            state.release()
        wrtc._testing.dispatcher_idle()
    finally:
        gc.set_threshold(*thresholds)


def test_wake_of_a_closed_loop_releases_its_state() -> None:
    loop = asyncio.new_event_loop()
    state = LoopState.of(loop)
    loop.close()
    wrtc._testing.post(state.mailbox, 'event', 1)
    wrtc._testing.dispatcher_idle()

    assert state.mailbox.closed
    assert state.mailbox.dropped == 1


def test_pending_call_at_loop_close_is_released() -> None:
    """Pending operation is released with the loop."""

    async def start_and_leave() -> tuple[weakref.ref[object], weakref.ref[object], wrtc.Mailbox]:
        state = LoopState.of(asyncio.get_running_loop())
        _, future = state.start(None)
        wrtc._testing.post(state.mailbox, 'event', 1)
        wrtc._testing.post(state.mailbox, 'event', 2)
        await asyncio.sleep(0)
        return weakref.ref(state), weakref.ref(future), state.mailbox

    # park the wake so nothing drains before the loop closes
    wrtc._testing.park('dispatcher.wake')
    try:
        state_ref, future_ref, mailbox = asyncio.run(start_and_leave())
        gc.collect()
        assert state_ref() is None
        assert future_ref() is None
        assert mailbox.closed
        assert mailbox.dropped == 2
        assert len(mailbox) == 0
    finally:
        wrtc._testing.release('dispatcher.wake')
    wrtc._testing.dispatcher_idle()


class _SlottedLoop:
    """A loop without a ``__dict__``, e.g. uvloop."""

    __slots__ = ('__weakref__', 'closed')

    def __init__(self) -> None:
        self.closed = False

    def is_closed(self) -> bool:
        return self.closed


def test_states_of_loops_without_a_dict_are_released_with_them() -> None:
    loop = _SlottedLoop()
    state = LoopState.of(mistyped(loop))
    assert LoopState.of(mistyped(loop)) is state
    mailbox = state.mailbox
    state_ref = weakref.ref(state)

    del state, loop
    gc.collect()
    assert state_ref() is None
    assert mailbox.closed


class _Unbound:
    """A native object without a binding."""

    @property
    def _bound(self) -> bool:
        return False

    @property
    def _mailbox(self) -> int | None:
        return None

    @staticmethod
    def _bind(mailbox: wrtc.Mailbox) -> bool:  # ruff: ignore[unused-static-method-argument]
        return False


class _Active(EventTarget[Never]):
    """A target with manual activity."""

    __slots__ = ('__weakref__', '_parent', 'reason')

    def __init__(self, parent: _Active | None = None) -> None:
        self.reason: str | None = 'has handlers'
        self._parent = parent

    @property
    @override
    def _native_obj(self) -> _Unbound:
        return _Unbound()

    @property
    @override
    def _connection(self) -> webrtc.RTCPeerConnection | None:
        return mistyped(self._parent)

    @override
    def _activity(self) -> str | None:
        return self.reason


@pytest.mark.asyncio
async def test_completion_re_evaluates_the_object_of_its_call() -> None:
    state = LoopState.of(asyncio.get_running_loop())
    target = _Active()
    state.update(target)
    assert target in state.active
    token, future = state.start(target)
    target.reason = None
    _in_thread(lambda: wrtc._testing.complete(state.mailbox, token, 1))
    assert await future == 1
    assert target not in state.active


def test_release_of_a_closed_loop_drops_what_it_kept() -> None:
    """Sweep drops a held closed loop's state."""
    loop = asyncio.new_event_loop()
    target = _Active()

    def keep() -> tuple[LoopState, webrtc.RTCPeerConnection]:
        state = LoopState.of(loop)
        state.update(target)
        state.tasks.add(loop.create_future())
        pc = webrtc.RTCPeerConnection()
        pc.on('negotiationneeded', lambda _event: None)
        return state, pc

    state, pc = loop.run_until_complete(called(keep))
    # never run: the loop closes first
    state.post(lambda: None)
    wrtc._testing.dispatcher_idle()
    loop.close()
    assert state.active == {target: 'has handlers', pc: 'handlers'}
    assert len(state._markers) == 1

    gc.collect()
    assert state.mailbox.closed
    assert (state.active, state.tasks, state._markers) == ({}, set(), {})
    assert pc.listeners('negotiationneeded') == []
    pc.close()


def test_release_of_a_running_loop_cancels_its_calls() -> None:
    """Release while running cancels calls on the loop."""

    def release() -> tuple[LoopState, asyncio.Future[object]]:
        state = LoopState.of(asyncio.get_running_loop())
        _, future = state.start(None)
        state.release()
        return state, future

    state, future = asyncio.run(called(release))
    assert future.cancelled()
    assert state.pending == {}


def test_update_roots_by_activity() -> None:
    loop = asyncio.new_event_loop()
    try:
        state = LoopState.of(loop)
        connection = _Active()
        child = _Active(connection)
        state.update(connection)
        state.update(child)
        assert state.active == {connection: 'has handlers', child: 'has handlers'}
        connection.reason = child.reason = None
        state.update(connection)
        assert state.active == {}
    finally:
        loop.close()
