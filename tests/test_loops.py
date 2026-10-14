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
import sys
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import pytest
from typing_extensions import Never, override

import webrtc
import wrtc
from tests.helpers import called, mistyped
from tests.isolation import isolated
from webrtc.utils import loops
from webrtc.utils.events import EventTarget
from webrtc.utils.loops import LoopState, checking_roots

TIMEOUT = 5


def _handled_on(loop: asyncio.AbstractEventLoop) -> tuple[LoopState, webrtc.RTCPeerConnection]:
    """A connection with a handler on the loop, bound there."""

    def bind() -> tuple[LoopState, webrtc.RTCPeerConnection]:
        pc = webrtc.RTCPeerConnection()
        pc.on('negotiationneeded', lambda _event: None)
        return LoopState.of(asyncio.get_running_loop()), pc

    return loop.run_until_complete(called(bind))


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
    # an in-progress Dispatcher collection would skip this one
    wrtc._testing.dispatcher_idle()
    gc.collect()

    assert [ref for ref in refs if ref() is not None] == []


def test_closed_loop_held_by_the_user_is_released_on_collection() -> None:
    """Held closed loop's state is released."""
    loop = asyncio.new_event_loop()
    state = LoopState.of(loop)
    _, future = state.start(None)
    # an in-progress Dispatcher collection (--gc-on-emit) would skip this one
    wrtc._testing.dispatcher_idle()
    # no drain scheduled: closing alone releases nothing
    wrtc._testing.park('dispatcher.wake')
    try:
        wrtc._testing.post(state.mailbox, 'event', 1)
        assert wrtc._testing.parked('dispatcher.wake', 5)
        loop.close()
        assert not state.mailbox.closed

        gc.collect()
    finally:
        wrtc._testing.release('dispatcher.wake')
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
    def _orphaned(self) -> bool:
        return False

    @property
    def _mailbox(self) -> int | None:
        return None

    @staticmethod
    def _bind(mailbox: wrtc.Mailbox) -> bool:  # ruff: ignore[unused-static-method-argument]
        return False


class _Active(EventTarget[Never]):
    """A target bound to a state, with activity set by hand."""

    __slots__ = ('__weakref__', '_bound_to', '_parent', 'reason')

    def __init__(self, state: LoopState | None, parent: _Active | None = None) -> None:
        self.reason: str | None = 'has handlers'
        self._bound_to = state
        self._parent = parent

    @override
    def _state(self) -> LoopState | None:
        return self._bound_to

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
    target = _Active(state)
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
    target = _Active(LoopState.of(loop))

    def keep() -> tuple[LoopState, webrtc.RTCPeerConnection]:
        state = LoopState.of(loop)
        state.update(target)
        state.tasks.add(loop.create_future())
        pc = webrtc.RTCPeerConnection()
        pc.on('negotiationneeded', lambda _event: None)
        return state, pc

    state, pc = loop.run_until_complete(called(keep))
    wrtc._testing.dispatcher_idle()
    # no drain scheduled: closing alone releases nothing
    wrtc._testing.park('dispatcher.wake')
    try:
        wrtc._testing.post(state.mailbox, 'event', 1)
        assert wrtc._testing.parked('dispatcher.wake', 5)
        loop.close()
        assert state.active == {target: 'has handlers', pc: 'handlers'}
        assert len(state.mailbox) == 1

        gc.collect()
    finally:
        wrtc._testing.release('dispatcher.wake')
    assert state.mailbox.closed
    assert (state.active, state.tasks, len(state.mailbox)) == ({}, set(), 0)
    assert pc.listeners('negotiationneeded') == []
    pc.close()


@pytest.mark.skipif(sys.platform == 'win32', reason='no wake pipe on Windows')
@pytest.mark.skipif(not LoopState.watches_pipe, reason='every loop is woken through the Dispatcher')
def test_a_watching_loop_is_woken_through_its_mailbox_pipe_until_released(monkeypatch: pytest.MonkeyPatch) -> None:
    """After its first drain, a loop is woken without the Dispatcher; a release stops watching the pipe."""

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        state = LoopState.of(loop)
        token, first = state.start(None)
        _in_thread(lambda: wrtc._testing.complete(state.mailbox, token, 1))
        assert await asyncio.wait_for(first, TIMEOUT) == 1
        fd = state._wake_fd
        assert fd is not None

        # a Dispatcher wake would do nothing now
        monkeypatch.setattr(state, '_schedule', lambda: None)
        token, second = state.start(None)
        _in_thread(lambda: wrtc._testing.complete(state.mailbox, token, 2))
        assert await asyncio.wait_for(second, TIMEOUT) == 2
        monkeypatch.undo()

        state.release()
        assert state._wake_fd is None
        assert not loop.remove_reader(fd)

    asyncio.run(scenario())


@pytest.mark.skipif(sys.platform == 'win32', reason='no wake pipe on Windows')
@pytest.mark.skipif(not LoopState.watches_pipe, reason='every loop is woken through the Dispatcher')
def test_a_record_posted_as_a_drain_finishes_wakes_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pipe is emptied before a drain takes records, so a post after its last take isn't swallowed."""

    async def scenario() -> None:
        state = LoopState.of(asyncio.get_running_loop())
        token, first = state.start(None)
        _in_thread(lambda: wrtc._testing.complete(state.mailbox, token, 1))
        assert await asyncio.wait_for(first, TIMEOUT) == 1
        finish = state._finish
        last, posted = state.start(None)

        def finish_then_post(*, more: bool) -> None:
            finish(more=more)
            if not more and not posted.done():
                # into the empty mailbox, once the drain no longer looks at it
                _in_thread(lambda: wrtc._testing.complete(state.mailbox, last, 3))

        # a Dispatcher wake would do nothing now
        monkeypatch.setattr(state, '_schedule', lambda: None)
        monkeypatch.setattr(state, '_finish', finish_then_post)
        token, second = state.start(None)
        _in_thread(lambda: wrtc._testing.complete(state.mailbox, token, 2))
        assert await asyncio.wait_for(second, TIMEOUT) == 2
        assert await asyncio.wait_for(posted, TIMEOUT) == 3
        monkeypatch.undo()

    asyncio.run(scenario())


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


def test_only_the_loop_of_an_object_roots_it() -> None:
    """Only the bound loop roots an active object."""
    first, second = asyncio.new_event_loop(), asyncio.new_event_loop()
    try:
        bound, unbound = _Active(LoopState.of(first)), _Active(None)
        for state in (LoopState.of(first), LoopState.of(second)):
            state.update(bound)
            state.update(unbound)
        assert LoopState.of(first).active == {bound: 'has handlers'}
        assert LoopState.of(second).active == {}
    finally:
        first.close()
        second.close()


def test_release_binds_an_object_to_a_loop_with_handlers_of_it() -> None:
    """A released loop's object is bound to a loop with handlers of it."""
    first = asyncio.new_event_loop()
    released, pc = _handled_on(first)

    def handle_elsewhere() -> None:
        pc.on('icecandidate', lambda _event: None)
        assert pc._state() is released
        first.close()
        released.release()
        state = LoopState.of(asyncio.get_running_loop())
        assert pc._state() is state
        assert state.active == {pc: 'handlers'}
        pc.close()
        assert state.active == {}

    asyncio.run(called(handle_elsewhere))


def test_release_of_another_loop_keeps_the_binding() -> None:
    """It drops only that loop's handlers."""
    first = asyncio.new_event_loop()
    bound, pc = _handled_on(first)

    def handle_elsewhere() -> LoopState:
        pc.on('icecandidate', lambda _event: None)
        assert pc._state() is bound
        return LoopState.of(asyncio.get_running_loop())

    elsewhere = asyncio.run(called(handle_elsewhere))
    elsewhere.release()
    assert pc._state() is bound
    assert pc.event_names() == {'negotiationneeded'}
    assert bound.active == {pc: 'handlers'}
    first.run_until_complete(called(pc.close))
    assert bound.active == {}
    first.close()


@pytest.mark.asyncio
async def test_events_without_root_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without WRTC_CHECK_ROOTS, events still reach their handlers."""
    monkeypatch.setenv('WRTC_CHECK_ROOTS', '0')
    # the setting is read once per process
    checking_roots.cache_clear()
    pc = webrtc.RTCPeerConnection()
    try:
        fired: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        pc.on('negotiationneeded', lambda event: fired.set_result(event.type))
        pc.add_transceiver(webrtc.MediaType.audio)
        assert await asyncio.wait_for(fired, TIMEOUT) == 'negotiationneeded'
        state = LoopState.of(asyncio.get_running_loop())
        assert pc in state.active
        pc.off()
        pc.close()
        assert pc not in state.active
    finally:
        pc.close()
        monkeypatch.undo()
        checking_roots.cache_clear()


@pytest.mark.roots('an _Active bound to no loop')
def test_an_active_object_bound_to_no_loop_is_a_mismatch() -> None:
    """An active object bound to no loop fails its update and the roots check."""
    loop = asyncio.new_event_loop()
    try:
        state = LoopState.of(loop)
        target = _Active(None)
        with pytest.raises(AssertionError, match='_Active is active but unbound'):
            target._update()
        # with handlers registered from the loop
        state.remember(target)
        with pytest.raises(AssertionError, match='_Active is active but unbound'):
            state._check_roots()
        target.reason = None
        target._update()
        state._check_roots()
    finally:
        loop.close()


def test_a_pending_operation_binds_a_connection_bound_to_no_loop() -> None:
    """A connection made outside a loop is bound by its first operation."""
    pc = webrtc.RTCPeerConnection()
    assert pc._state() is None

    async def operate() -> None:
        state = LoopState.of(asyncio.get_running_loop())
        first = asyncio.Event()
        release = asyncio.Event()

        async def hold() -> None:
            async with pc._operation():
                first.set()
                await release.wait()

        async def wait() -> None:
            async with pc._operation():
                pass

        held = asyncio.ensure_future(hold())
        await asyncio.wait_for(first.wait(), TIMEOUT)
        assert pc._state() is state
        assert state.active == {pc: 'pending operation'}
        # waits in the chain: still pending, still bound here
        waiting = asyncio.ensure_future(wait())
        await asyncio.sleep(0)
        assert state.active == {pc: 'pending operation'}
        release.set()
        await asyncio.wait_for(asyncio.gather(held, waiting), TIMEOUT)
        assert state.active == {}

    try:
        asyncio.run(operate())
    finally:
        pc.close()


def test_a_loop_made_while_another_is_released_never_sees_its_objects_active_and_unbound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loop whose state is made after a release began sees that loop's objects orphaned, not unbound."""
    first = asyncio.new_event_loop()
    released, pc = _handled_on(first)
    swept, detached = threading.Event(), threading.Event()
    sweep, unwatch = loops._sweep, LoopState._unwatch

    def sweep_then_wait() -> None:
        sweep()
        if threading.current_thread().name.startswith('checker') and not swept.is_set():
            swept.set()
            _ = detached.wait(TIMEOUT)

    def unwatch_after_the_check(self: LoopState) -> None:
        if self is released:
            # between marking the state released and closing its mailbox
            detached.set()
            _ = checked.exception(TIMEOUT)

        unwatch(self)

    monkeypatch.setattr(loops, '_sweep', sweep_then_wait)
    monkeypatch.setattr(LoopState, '_unwatch', unwatch_after_the_check)
    with ThreadPoolExecutor(1, thread_name_prefix='checker') as pool:
        # its state is made after its sweep, so the release doesn't hold its checks
        checked = pool.submit(asyncio.run, called(lambda: loops.check_bound(pc)))
        assert swept.wait(TIMEOUT)

        first.close()
        released.release()
        monkeypatch.undo()

        checked.result(TIMEOUT)

    assert detached.is_set()
    assert pc.event_names() == set()

    pc.close()


def test_handlers_bind_an_object_bound_to_a_closed_loop_not_swept_yet() -> None:
    """A handler on another loop binds an object whose loop closed but isn't swept yet."""
    pc = webrtc.RTCPeerConnection()

    def register() -> None:
        pc.on('negotiationneeded', lambda _event: None)

    def register_elsewhere() -> None:
        pc.on('icecandidate', lambda _event: None)
        state = LoopState.of(asyncio.get_running_loop())
        assert pc._state() is state
        assert state.active == {pc: 'handlers'}

    elsewhere = asyncio.new_event_loop()
    # its state exists, so binding there sweeps nothing on the way
    _ = LoopState.of(elsewhere)
    try:
        asyncio.run(called(register))
        # the closed loop's state stays until a sweep
        gc.disable()
        try:
            elsewhere.run_until_complete(called(register_elsewhere))
        finally:
            gc.enable()
    finally:
        elsewhere.close()
        pc.close()


def test_call_soon_runs_on_the_loop_from_another_thread() -> None:
    """A callback scheduled from another thread runs on the loop's thread; its drop handler doesn't."""
    ran: list[str] = []

    async def schedule() -> None:
        state = LoopState.of(asyncio.get_running_loop())
        done = asyncio.Event()

        def callback() -> None:
            ran.append(threading.current_thread().name)
            done.set()

        loop_thread = threading.current_thread().name
        _in_thread(lambda: state.call_soon(callback, dropped=lambda: ran.append('dropped')))
        await asyncio.wait_for(done.wait(), TIMEOUT)
        assert ran == [loop_thread]

    asyncio.run(schedule())


def test_call_soon_of_a_released_loop_runs_the_drop_handler_instead() -> None:
    """A callback queued when its loop is released never runs; its drop handler runs once, a later one drops at once."""
    loop = asyncio.new_event_loop()
    state = LoopState.of(loop)
    ran: list[str] = []
    # queued in the loop, which never runs again
    state.call_soon(lambda: ran.append('queued'), dropped=lambda: ran.append('queued dropped'))
    loop.close()
    state.release()
    state.release()
    state.call_soon(lambda: ran.append('late'), dropped=lambda: ran.append('late dropped'))
    assert ran == ['queued dropped', 'late dropped']


def test_update_roots_by_activity() -> None:
    loop = asyncio.new_event_loop()
    try:
        state = LoopState.of(loop)
        connection = _Active(state)
        child = _Active(state, connection)
        state.update(connection)
        state.update(child)
        assert state.active == {connection: 'has handlers', child: 'has handlers'}
        connection.reason = child.reason = None
        state.update(connection)
        assert state.active == {}
    finally:
        loop.close()


class _DictLoop:
    """A loop collected without a cycle, so no gc sweep sees it go."""

    def __init__(self) -> None:
        self.closed = False

    def is_closed(self) -> bool:
        return self.closed


def test_a_state_outliving_its_loop_is_released_by_its_next_use() -> None:
    """Posts and calls are dropped, and new calls fail."""
    for use in ('post', 'call_soon'):
        loop = _DictLoop()
        state = LoopState.of(mistyped(loop))
        del loop
        ran: list[str] = []
        if use == 'post':
            state.post(lambda ran=ran: ran.append('posted'))
        else:
            state.call_soon(lambda ran=ran: ran.append('soon'), dropped=lambda ran=ran: ran.append('dropped'))
        assert state.mailbox.closed
        assert state._markers == {}
        assert ran == ([] if use == 'post' else ['dropped'])
        with pytest.raises(RuntimeError, match='the loop of the state is gone'):
            state.start(None)


def test_a_post_to_a_closed_loop_releases_its_state() -> None:
    """Only the drop handler runs."""
    for use in ('post', 'call_soon'):
        loop = asyncio.new_event_loop()
        state = LoopState.of(loop)
        loop.close()
        ran: list[str] = []
        if use == 'post':
            state.post(lambda ran=ran: ran.append('posted'))
        else:
            state.call_soon(lambda ran=ran: ran.append('soon'), dropped=lambda ran=ran: ran.append('dropped'))
        assert state.mailbox.closed
        assert ran == ([] if use == 'post' else ['dropped'])
        assert LoopState.find(state.mailbox.id) is None
        # released: later posts are dropped right away
        state.post(lambda ran=ran: ran.append('late'))
        assert state._markers == {}
        assert ran == ([] if use == 'post' else ['dropped'])


def test_call_soon_released_before_it_runs_runs_the_drop_handler_only() -> None:
    ran: list[str] = []

    async def release() -> None:
        state = LoopState.of(asyncio.get_running_loop())
        state.call_soon(lambda: ran.append('soon'), dropped=lambda: ran.append('dropped'))
        state.release()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(release())
    assert ran == ['dropped']


@pytest.mark.asyncio
async def test_completion_of_an_unknown_call_is_skipped() -> None:
    """The records after it still run."""
    state = LoopState.of(asyncio.get_running_loop())
    token, future = state.start(None)
    _in_thread(lambda: wrtc._testing.complete(state.mailbox, token + 1000, 1))
    _in_thread(lambda: wrtc._testing.complete(state.mailbox, token, 2))
    assert await asyncio.wait_for(future, TIMEOUT) == 2
    assert state.pending == {}


def test_released_state_roots_nothing() -> None:
    loop = asyncio.new_event_loop()
    state = LoopState.of(loop)
    target = _Active(state)
    loop.close()
    state.release()
    state.update(target)
    assert state.active == {}


def test_unrooted_connection_re_evaluates_its_children_on_other_loops() -> None:
    first, second = asyncio.new_event_loop(), asyncio.new_event_loop()
    try:
        connection = _Active(LoopState.of(first))
        child = _Active(LoopState.of(second), connection)
        LoopState.of(second).update(child)
        assert LoopState.of(second).active == {child: 'has handlers'}
        connection.reason = child.reason = None
        LoopState.of(first).update(connection)
        assert LoopState.of(second).active == {}
    finally:
        first.close()
        second.close()


@pytest.mark.roots('an _Active rooted without activity')
def test_a_rooted_object_without_activity_is_a_mismatch() -> None:
    loop = asyncio.new_event_loop()
    try:
        state = LoopState.of(loop)
        target = _Active(state)
        state.update(target)
        target.reason = None
        with pytest.raises(AssertionError, match='_Active is rooted with activity None'):
            state._check_roots()
        state.update(target)
        state._check_roots()
    finally:
        loop.close()


def test_an_operation_binds_a_connection_whose_loop_closed_unswept() -> None:
    first, second = asyncio.new_event_loop(), asyncio.new_event_loop()
    pc = webrtc.RTCPeerConnection()
    first.run_until_complete(called(lambda: pc.on('negotiationneeded', lambda _event: None)))
    # its state exists, so binding there sweeps nothing on the way
    _ = LoopState.of(second)
    gc.disable()
    try:
        first.close()
        second.run_until_complete(pc.create_offer())
        assert pc._state() is LoopState.of(second)
    finally:
        gc.enable()
        pc.close()
        second.close()


def test_lookup_of_a_closed_binding_rebinds_to_a_loop_with_handlers() -> None:
    first, second = asyncio.new_event_loop(), asyncio.new_event_loop()
    pc = webrtc.RTCPeerConnection()

    def on_icecandidate(_event: webrtc.Event) -> None: ...

    first.run_until_complete(called(lambda: pc.on('negotiationneeded', lambda _event: None)))
    second.run_until_complete(called(lambda: pc.on('icecandidate', on_icecandidate)))
    state = LoopState.of(second)
    assert pc._state() is LoopState.of(first)
    # no sweep: the lookup itself finds the closed loop
    gc.disable()
    try:
        first.close()
        assert pc._state() is state
    finally:
        gc.enable()
    assert pc.listeners('negotiationneeded') == []
    assert pc.listeners('icecandidate') == [on_icecandidate]
    assert state.active == {pc: 'handlers'}
    pc.close()
    second.close()


class _Handled(_Active):
    """An _Active with handlers."""

    __slots__ = ('_handlers',)

    _events = ('ping',)

    def __init__(self, state: LoopState | None) -> None:
        super().__init__(state)
        self._handlers = None


@pytest.mark.roots('a _Handled neither rooted nor active')
@pytest.mark.asyncio
async def test_an_event_handled_while_neither_rooted_nor_active_is_a_mismatch() -> None:
    """The roots check of a delivery names the handlers that would run."""
    state = LoopState.of(asyncio.get_running_loop())
    target = _Handled(state)
    target.reason = None
    calls: list[str] = []

    def on_ping(event: webrtc.Event) -> None:
        calls.append(event.type)

    target._add('ping', on_ping, once=False)
    with pytest.raises(AssertionError, match=r"neither rooted nor active while 'ping' is handled by .*on_ping"):
        target._deliver(state, 'ping', ())
    assert calls == []

    target.reason = 'has handlers'
    target._update()
    target._deliver(state, 'ping', ())
    await asyncio.sleep(0)
    assert calls == ['ping']
