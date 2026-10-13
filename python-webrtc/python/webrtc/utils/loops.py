#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Per-loop mailbox, pending native calls and roots; native threads post records, the loop drains them in order."""

from __future__ import annotations

import asyncio
import atexit
import collections
import contextlib
import functools
import gc
import os
import sys
import threading
import weakref
from typing import TYPE_CHECKING, Callable, ClassVar, NamedTuple, cast

import wrtc
from webrtc.exceptions import InvalidStateError
from webrtc.utils import lifetime

if TYPE_CHECKING:
    from collections.abc import Generator

    from typing_extensions import Concatenate, Never, ParamSpec

    from webrtc.utils.events import EventTarget

    _P = ParamSpec('_P')

#: (event name or None, token, failed, args or None)
_Record = tuple['str | None', int, bool, 'tuple[object, ...] | None']


class _Item(NamedTuple):
    """A mailbox record or posted callback, ready to run."""

    run: Callable[[], object]
    #: the code it resumes runs before the next item
    resumes: bool
    #: waits for the loop's ready callbacks
    after_ready: bool


class _Call(NamedTuple):
    """A native call in flight."""

    future: asyncio.Future[object]
    #: weak: a pending call is no root
    target: weakref.ref[EventTarget[Never]] | None


#: by mailbox id, for Dispatcher wakes
_states: weakref.WeakValueDictionary[int, LoopState] = weakref.WeakValueDictionary()
# re-entrant: gc sweeps at any allocation, even under this lock
_states_lock = threading.RLock()
# a leaf lock: held over int arithmetic only, which never runs gc
_counts_lock = threading.Lock()


@contextlib.contextmanager
def _acquired(lock: threading.RLock) -> Generator[bool, None, None]:
    """Yields whether the lock was taken; never blocks at finalization, where a parked daemon may hold it."""
    if not lock.acquire(blocking=not sys.is_finalizing()):
        yield False
        return
    try:
        yield True
    finally:
        lock.release()


#: states of loops without a ``__dict__``, e.g. uvloop
_held_states: dict[int, LoopState] = {}
_ATTRIBUTE = '_webrtc'


@functools.cache
def checking_roots() -> bool:
    """Whether ``WRTC_CHECK_ROOTS=1`` makes every event check the roots."""
    return os.environ.get('WRTC_CHECK_ROOTS') == '1'


#: failed checks for tests: raised in a drain, they only reach the loop's handler
mismatches: list[str] = []


def record_mismatch(msg: str) -> None:
    """Records a failed check."""
    mismatches.append(msg)


def _unbound(target: EventTarget[Never]) -> str | None:
    """The mismatch of an active object bound to no loop, unless a released loop let go of it."""
    if target._state() is not None or (reason := target._activity()) is None or target._native_obj._orphaned:
        return None
    return f'{type(target).__name__} is active but unbound, with activity {reason!r}'


def check_bound(target: EventTarget[Never]) -> None:
    """Asserts an active object is bound, as only its loop roots it."""
    if not target._rootable:
        return
    loop = _current_loop()
    roots = LoopState.of(loop) if loop is not None and not loop.is_closed() else None
    generation = roots.settled_generation() if roots is not None else 0
    if generation is None:
        # another thread is mid-change, like rebinding it
        return
    msg = _unbound(target)
    if msg is None or (roots is not None and not roots.settled(generation)):
        return
    record_mismatch(msg)
    raise AssertionError(msg)


class LoopState:
    """Per-loop mailbox, pending calls, handler tasks and roots; released when the loop closes or is collected."""

    #: max waits of a drain for other ready callbacks
    MAX_DEFERRALS = 100
    #: max records per loop iteration
    MAX_BATCH = 100
    #: set at exit: completions stop, so new calls fail
    exiting: ClassVar[bool] = False

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        # weak: the loop holds the state
        self._loop_ref = weakref.ref(loop)
        self.mailbox = wrtc.Mailbox()
        self.pending: dict[int, _Call] = {}
        #: kept until done, or they'd be collected
        self.tasks: set[asyncio.Future[object]] = set()
        #: objects kept alive while they can fire a handled event, with the reason
        self.active: dict[EventTarget[Never], str] = {}
        #: objects with handlers here, or bound here with handlers elsewhere
        self.targets: weakref.WeakSet[EventTarget[Never]] = weakref.WeakSet()
        #: activity changes in progress on other threads
        self.changes = 0
        #: bumped on root changes, so a root check can detect a race
        self.generation = 0
        # last pass that stored each root, in a cell (see _store)
        self._read_at: weakref.WeakKeyDictionary[EventTarget[Never], list[int]] = weakref.WeakKeyDictionary()
        self._passes = 0
        self._markers: dict[int, _Item] = {}
        # drop handlers of call_soon callbacks not run yet, by key
        self._soon: dict[int, Callable[[], object]] = {}
        self._next_key = 0
        # re-entrant, like _states_lock
        self._lock = threading.RLock()
        self._scheduled = False
        self._released = False
        # the last item resumed code that runs before the next one
        self._resumed = False
        self._held: _Item | None = None
        with _states_lock:
            _states[self.mailbox.id] = self
        # closing the mailbox stops queued records pinning their sources
        _ = weakref.finalize(self, self.mailbox.close)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """:obj:`asyncio.AbstractEventLoop`: The loop."""
        return self._live_loop

    @property
    def _live_loop(self) -> asyncio.AbstractEventLoop:
        """The loop, alive when called from its callbacks."""
        loop = self._loop_ref()
        if loop is None:
            msg = 'the loop of the state is gone'
            raise RuntimeError(msg)
        return loop

    @classmethod
    def of(cls, loop: asyncio.AbstractEventLoop) -> LoopState:
        """Returns the loop's state, creating it on first use."""
        try:
            attributes = vars(loop)
        except TypeError:
            attributes = None
        if attributes is not None:
            state: LoopState | None = attributes.get(_ATTRIBUTE)
            if state is not None:
                return state
            _sweep()
            # atomic: racing threads keep the same state
            shared: LoopState = attributes.setdefault(_ATTRIBUTE, cls(loop))
            return shared
        key = id(loop)
        with _states_lock:
            state = _held_states.get(key)
        if state is None:
            _sweep()
            state = cls(loop)
            with _states_lock:
                state = _held_states.setdefault(key, state)
            _ = weakref.finalize(loop, _forget, key)
        return state

    @classmethod
    def find(cls, mailbox_id: int | None) -> LoopState | None:
        """Returns the state of a mailbox id if its loop is open, else None, releasing a closed loop's state."""
        if mailbox_id is None:
            return None
        with _states_lock:
            state = _states.get(mailbox_id)
        if state is None or state._released:
            return None
        loop = state._loop_ref()
        if loop is not None and not loop.is_closed():
            return state
        state.release()
        return None

    def start(self, target: EventTarget[Never] | None) -> tuple[int, asyncio.Future[object]]:
        """Returns a token and the future its completion settles; fails at exit."""
        if LoopState.exiting:
            msg = 'The interpreter is exiting'
            raise InvalidStateError(msg)
        future: asyncio.Future[object] = self._live_loop.create_future()
        with self._lock:
            token = self._key()
            self.pending[token] = _Call(future, weakref.ref(target) if target is not None else None)
        return token, future

    def post(self, callback: Callable[[], object], *, resumes: bool = False, after_ready: bool = False) -> None:
        """Schedules a callback in order with the native records (flags as in ``_Item``)."""
        item = _Item(callback, resumes, after_ready)
        with self._lock:
            key = self._key()
            # after allocating: gc may have released the state under the lock
            if self._released:
                return
            self._markers[key] = item
        self.mailbox.postMarker(key)
        self._schedule()

    def call_soon(self, callback: Callable[[], object], *, dropped: Callable[[], object]) -> None:
        """Runs a callback on the loop soon, from any thread, unordered with the native records.

        If the loop is released first, ``dropped`` runs instead: exactly one of them runs.
        """
        with self._lock:
            key = self._key()
            released = self._released
            if not released:
                self._soon[key] = dropped
        if released:
            _ = dropped()
            return

        def run() -> None:
            with self._lock:
                # gone once released: its drop handler ran
                if self._soon.pop(key, None) is None:
                    return
            _ = callback()

        # closed or gone: the release runs the drop handler
        loop = self._loop_ref()
        if loop is None:
            self.release()
            return
        try:
            _ = loop.call_soon_threadsafe(run)
        except RuntimeError:
            self.release()

    def _key(self) -> int:
        """Next marker, completion or ``call_soon`` key; call under the lock."""
        self._next_key += 1
        return self._next_key

    def _schedule(self) -> None:
        """Schedules one drain from any thread; releases the state if the loop is closed."""
        with self._lock:
            if self._scheduled or self._released:
                return
            self._scheduled = True
        loop = self._loop_ref()
        if loop is None:
            self.release()
            return
        try:
            _ = loop.call_soon_threadsafe(_Drain(self))
        except RuntimeError:
            self.release()

    def drain(self, deferred: int = 0) -> None:
        """Runs the mailbox records in order on the loop."""
        if self._defers(deferred, resumed=self._resumed):
            _ = self._live_loop.call_soon(_Drain(self, deferred + 1))
            return

        more = True
        try:
            more = self._run_batch()
        finally:
            self._finish(more=more)

    def _finish(self, *, more: bool) -> None:
        """Schedules another drain if anything is left."""
        with self._lock:
            if not more:
                # a post since the last take saw a drain scheduled and skipped its wake
                more = self._held is not None or len(self.mailbox) > 0
            self._scheduled = more
        if more:
            _ = self._live_loop.call_soon(_Drain(self))

    def _run_batch(self) -> bool:
        """Runs items until one must wait; returns whether any are left."""
        if self._take() is None:
            return False
        for _ in range(self.MAX_BATCH):
            resumes = self._run()
            item = self._take()
            if item is None:
                return False
            if self._yields(resumes=resumes, after_ready=item.after_ready):
                return True
        return True

    def _take(self) -> _Item | None:
        """Holds and returns the next live item."""
        while self._held is None:
            record: _Record | None = self.mailbox.take()
            if record is None:
                return None
            self._held = self._item(record)
        return self._held

    def _item(self, record: _Record) -> _Item | None:
        name, token, failed, args = record
        if name is not None:
            run = functools.partial(self._dispatch_event, name, args if args is not None else ())
            return _Item(run, resumes=False, after_ready=False)
        with self._lock:
            marker = self._markers.pop(token, None)
            if marker is not None:
                return marker
            call = self.pending.pop(token, None)
        if call is None:
            return None
        run = functools.partial(self._settle_call, call, args, failed=failed)
        return _Item(run, resumes=True, after_ready=True)

    def _dispatch_event(self, name: str, args: tuple[object, ...]) -> None:
        """Delivers an event record, its native object first, to that object's wrapper, recreating a dead one."""
        native, args = args[0], args[1:]
        wrapper = lifetime.find(cast('lifetime.Native', native))
        created = wrapper is None
        target = (wrapper if wrapper is not None else lifetime.wrapper_of(cast('lifetime.Native', native)))._target()
        if target is None:
            return
        target._deliver(self, name, args)
        # after handlers, so a terminal event's handlers run before unrooting; fresh wrappers aren't rooted
        if created or not target._rootable or not target._changes_activity(name):
            return
        self.update(target)
        if checking_roots():
            self._check_roots()

    @staticmethod
    def _settle_call(call: _Call, args: tuple[object, ...] | None, *, failed: bool) -> None:
        """Settles a call's future and re-evaluates its object."""
        # the caller may have been canceled meanwhile
        if not call.future.done():
            result = args[0] if args is not None and len(args) > 0 else None
            if failed and isinstance(result, BaseException):
                call.future.set_exception(result)
            else:
                call.future.set_result(result)
        target = call.target() if call.target is not None else None
        if target is not None:
            target._update()

    def _run(self) -> bool:
        """Runs the held item; returns whether it resumes code."""
        item, self._held = self._held, None
        if item is None:
            return False
        if item.resumes:
            self._resumed = True
            _ = self._live_loop.call_soon(self._settle)
        _ = item.run()
        return item.resumes

    def _settle(self, deferred: int = 0) -> None:
        # resumed code may span several iterations: wait until nothing else is ready
        if self._defers(deferred, resumed=False):
            _ = self._live_loop.call_soon(self._settle, deferred + 1)
        else:
            self._resumed = False

    def _defers(self, deferred: int, *, resumed: bool) -> bool:
        """Whether an item waits for resumed code or ready callbacks."""
        # bounded, so a busy loop can't starve the mailbox
        return (resumed or self._others_ready()) and deferred < self.MAX_DEFERRALS

    def _others_ready(self) -> bool:
        """Whether the loop has ready callbacks other than timers, its own or this state's."""
        # CPython internals: other loops (e.g. uvloop) never report any
        loop = self._loop_ref()
        ready: object = getattr(loop, '_ready', None)
        # copy() holds the deque's lock; iterating races call_soon_threadsafe on free-threaded builds
        handles = cast('collections.deque[object]', ready).copy() if isinstance(ready, collections.deque) else ()
        for handle in handles:
            callback = getattr(handle, '_callback', None)
            owner = callback.state if isinstance(callback, _Drain) else getattr(callback, '__self__', None)
            if isinstance(handle, asyncio.TimerHandle) or owner is self or owner is loop:
                continue
            return True
        return False

    def _yields(self, *, resumes: bool, after_ready: bool) -> bool:
        """Whether the next item waits for the loop instead of running now."""
        # without loop._ready, run one item per iteration
        if resumes or after_ready:
            return True
        return not hasattr(self._loop_ref(), '_ready') or self._others_ready()

    def update(self, target: EventTarget[Never]) -> None:
        """Roots or unroots an object and its rooted children from their ``_activity()``."""
        if self._released:
            return
        with self._lock:
            # an earlier pass never overwrites a later pass's store
            self._passes += 1
            started = self._passes
            # a connection's close ends its children's activity
            targets = [target, *(c for c in self.active if c._connection is target)]
        # outside the lock: _activity() may block on libwebrtc; only the bound loop roots
        reasons = [(t, t._activity() if t._state() is self else None) for t in targets]
        with self._lock:
            if self._released:
                return
            for each, reason in reasons:
                if not self._store(each, reason, started):
                    return
            with _counts_lock:
                self.generation += 1
        self._recheck(reasons)
        if reasons[0][1] is None:
            # children may be rooted on other loops
            for other in _states_elsewhere(self._loop_ref()):
                other._update_children(target)

    def _recheck(self, reasons: list[tuple[EventTarget[Never], str | None]]) -> None:
        """Updates again the objects just rooted here but unbound meanwhile."""
        # an unbind sweeps the roots after it; a root stored after that sweep is caught here
        for target, reason in reasons:
            if reason is not None and target._state() is not self:
                self.update(target)

    def _store(self, target: EventTarget[Never], reason: str | None, started: int) -> bool:
        """Stores a root for a pass unless a later pass did; returns False once released."""
        read_at = self._read_at.get(target)
        if read_at is None:
            read_at = self._read_at.setdefault(target, [0])
        # no allocation between compare and set, so gc can't interleave
        if read_at[0] > started:
            return True
        read_at[0] = started
        if self._released:
            return False
        if reason is None:
            _ = self.active.pop(target, None)
        else:
            self.active[target] = reason
        return True

    def _update_children(self, parent: EventTarget[Never]) -> None:
        """Re-evaluates a connection's rooted children."""
        with self._lock:
            children = [c for c in self.active if c._connection is parent]
        for child in children:
            self.update(child)

    def remember(self, target: EventTarget[Never]) -> None:
        """Adds an object to ``targets``."""
        with self._lock:
            self.targets.add(target)

    def _check_roots(self) -> None:
        """Asserts every object of the loop is rooted iff it's bound here and active, and is bound if it's active."""
        with self._lock:
            generation = self.settled_generation()
            if generation is None:
                # another thread is mid-change
                return
            rooted = set(self.active)
            targets = rooted | set(self.targets)
        # a racing change voids this check; the next one sees it
        msgs: list[str] = []
        for target in targets:
            binding = target._state()
            if binding is not self and target not in rooted:
                # its own loop checks it
                if binding is None and (msg := _unbound(target)) is not None:
                    msgs.append(msg)
                continue
            reason = target._activity() if binding is self else None
            if (target in rooted) != (reason is not None):
                rooting = 'rooted' if target in rooted else 'not rooted'
                where = '' if binding is self else ' and bound elsewhere' if binding is not None else ' and unbound'
                msgs.append(f'{type(target).__name__} is {rooting} with activity {reason!r}{where}')
        if not self.settled(generation):
            return
        if len(msgs) > 0:
            record_mismatch(msgs[0])
            raise AssertionError(msgs[0])

    def changing(self, delta: int) -> None:
        """Counts an activity change another thread starts (1) or ends (-1)."""
        with _counts_lock:
            self.changes += delta
            self.generation += 1

    def settled_generation(self) -> int | None:
        """The root generation, or None while another thread is mid-change."""
        with _counts_lock:
            return self.generation if self.changes == 0 else None

    def settled(self, generation: int) -> bool:
        """Whether no root or activity changed since ``generation``."""
        with _counts_lock:
            return self.changes == 0 and self.generation == generation

    def release(self) -> None:
        """Drops records, pending calls, roots and handlers once the loop is closed or gone."""
        # unlocked check: a gc sweep mustn't wait for a release in progress
        if self._released:
            return
        others: list[LoopState] = [] if sys.is_finalizing() else _states_elsewhere(self._loop_ref())
        # their roots checks wait while its objects are rebound
        for other in others:
            other.changing(1)
        try:
            self._release()
        finally:
            for other in others:
                other.changing(-1)

    def _release(self) -> None:
        with _acquired(self._lock) as acquired:
            if not acquired or self._released:
                return
            self._released = True
            self._scheduled = False
            pending = self.pending
            self.pending = {}
            dropped = list(self._soon.values())
            self._soon.clear()
            self._markers.clear()
            self._held = None
            self.tasks.clear()
            self.active.clear()
            targets = list(self.targets)
            self.targets.clear()
        # outside the lock: native calls may never return once exit starts
        self.mailbox.close()
        if not sys.is_finalizing():
            for drop in dropped:
                _ = drop()
        loop = self._loop_ref()
        if loop is not None and not sys.is_finalizing():
            _let_go(loop, list(pending.values()), targets)


class _Drain:
    """A scheduled drain that releases the state if its loop closes first."""

    __slots__ = ('_deferred', '_ran', 'state')

    def __init__(self, state: LoopState, deferred: int = 0) -> None:
        self.state = state
        self._deferred = deferred
        self._ran = False

    def __call__(self) -> None:
        self._ran = True
        self.state.drain(self._deferred)

    def __del__(self) -> None:
        if not self._ran:
            self.state.release()


def _let_go(loop: asyncio.AbstractEventLoop, calls: list[_Call], targets: list[EventTarget[Never]]) -> None:
    """Cancels a released loop's calls and removes its handlers, on the loop's thread."""

    def let_go() -> None:
        # a closed loop can't run their callbacks
        if not loop.is_closed():
            for call in calls:
                _ = call.future.cancel()
        for target in targets:
            target._released(loop)

    # futures are only touched on their loop's thread
    if loop.is_running() and loop is not _current_loop():
        with contextlib.suppress(RuntimeError):
            _ = loop.call_soon_threadsafe(let_go)
        return
    let_go()


def _current_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _states_elsewhere(loop: asyncio.AbstractEventLoop | None) -> list[LoopState]:
    """Unreleased states of loops other than ``loop``."""
    with _states_lock:
        states = list(_states.values())
    return [state for state in states if state._loop_ref() is not loop and not state._released]


def states_elsewhere() -> list[LoopState]:
    """Returns the states of loops other than the running one."""
    return _states_elsewhere(_current_loop())


def _forget(key: int) -> None:
    """Releases the state of a collected loop without a ``__dict__``."""
    with _acquired(_states_lock) as acquired:
        state = _held_states.pop(key, None) if acquired else None
    if state is not None:
        state.release()


def _sweep() -> None:
    """Releases states of closed or collected loops so they don't pin objects."""
    states: list[LoopState] = []
    with _acquired(_states_lock) as acquired:
        if acquired:
            states = list(_states.values())
    for state in states:
        loop = state._loop_ref()
        if loop is None or loop.is_closed():
            state.release()


def _on_collection(phase: str, _info: dict[str, int]) -> None:
    # not at finalization: a parked daemon thread may hold the lock
    if phase == 'start' and not sys.is_finalizing():
        _sweep()


def _wake(mailbox_id: int) -> None:
    """Schedules a drain for a mailbox; Dispatcher only, never runs user code."""
    with _states_lock:
        state = _states.get(mailbox_id)
    if state is not None:
        state._schedule()


def _exit() -> None:
    """Releases every state at exit; later calls fail fast."""
    LoopState.exiting = True
    with _states_lock:
        states = list(_states.values())
    for state in states:
        state.release()


async def call_native(
    method: Callable[Concatenate[wrtc.Mailbox, int, _P], None], *args: _P.args, **kwargs: _P.kwargs
) -> object:
    """Awaits ``method(mailbox, token, ...)``, resuming after the events emitted before its completion."""
    state = LoopState.of(asyncio.get_running_loop())
    native: lifetime.Native | None = getattr(method, '__self__', None)
    wrapper = lifetime.find(native) if native is not None else None
    token, future = state.start(wrapper._target() if wrapper is not None else None)
    method(state.mailbox, token, *args, **kwargs)
    return await future


gc.callbacks.append(_on_collection)
wrtc._set_wake(_wake)
# atexit is LIFO: runs before the Dispatcher's handler, registered at wrtc import
_ = atexit.register(_exit)
