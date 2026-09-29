#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio
import collections
import threading
import weakref
from typing import Callable, NamedTuple, Tuple


class _Item(NamedTuple):
    callback: Callable
    args: Tuple
    resumes: bool
    after_ready: bool


class TaskQueue:
    """Runs callbacks posted from any thread on an event loop in order, each with what it schedules with
    ``call_soon`` before the next one (like browser tasks and microtasks)."""

    #: How many times a callback waits for other ready callbacks of the loop
    MAX_DEFERRALS = 100
    #: How many callbacks run in one iteration of the loop, when they schedule nothing
    MAX_BATCH = 100

    #: The queues of the loops without a ``__dict__`` (like uvloop's), the others keep their own
    _queues: 'weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, TaskQueue]' = weakref.WeakKeyDictionary()
    _ATTRIBUTE = '_webrtc_task_queue'

    def __init__(self, loop: asyncio.AbstractEventLoop):
        # weakly: a queue in _queues referencing its loop would keep it forever
        self._loop_ref = weakref.ref(loop)
        self._items = collections.deque()
        self._lock = threading.Lock()
        self._scheduled = False
        # whether the last callback resumed code (like a coroutine awaiting a result) that runs before the next one
        self._resumed = False

    @property
    def _loop(self) -> asyncio.AbstractEventLoop:
        return self._loop_ref()

    @classmethod
    def of(cls, loop: asyncio.AbstractEventLoop) -> 'TaskQueue':
        """Returns the queue of a loop.

        Args:
            loop (:obj:`asyncio.AbstractEventLoop`): The loop.

        Returns:
            :obj:`TaskQueue`: Its queue, created on first use.
        """
        # kept by the loop, so a closed loop is collected with what's still queued; setdefault is atomic
        try:
            attributes = vars(loop)
        except TypeError:
            attributes = None
        if attributes is not None:
            queue = attributes.get(cls._ATTRIBUTE)
            return queue if queue is not None else attributes.setdefault(cls._ATTRIBUTE, cls(loop))
        queue = cls._queues.get(loop)
        if queue is None:
            # the loops closed meanwhile won't run what's queued
            for other in list(cls._queues):
                if other.is_closed():
                    cls._queues.pop(other)._items.clear()
            queue = cls._queues.setdefault(loop, cls(loop))
        return queue

    @classmethod
    def post_to_running(cls, callback: Callable, *args, **kwargs) -> bool:
        """Posts a callback to the queue of the running loop (see :meth:`post`).

        Returns:
            :obj:`bool`: Whether it was posted: :obj:`False` outside of a running loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        cls.of(loop).post(callback, *args, **kwargs)
        return True

    def post(self, callback: Callable, *args, resumes: bool = False, after_ready: bool = False) -> None:
        """Schedules a callback, from any thread. Callbacks posted to a closed loop are dropped.

        Args:
            callback (:obj:`callable`): The callback.
            *args: Its arguments.
            resumes (:obj:`bool`, optional): Whether the callback resumes code awaiting it, like the result of
                an operation. The next callback waits for what's resumed to run first.
            after_ready (:obj:`bool`, optional): Whether the callback waits for the callbacks the loop has ready,
                like the end of the current task, with its microtasks.
        """
        item = _Item(callback, args, resumes, after_ready)
        # Nothing is allocated under the lock: an allocation may run the garbage collector, and so the destructor
        # of a native object, which may wait for a libwebrtc thread that is posting here. Appending is atomic.
        self._items.append(item)
        with self._lock:
            if self._scheduled:
                return
            self._scheduled = True
        loop = self._loop
        try:
            if loop is None:
                raise RuntimeError('the loop is gone')
            loop.call_soon_threadsafe(self._run)
        except RuntimeError:  # the loop is closed: nothing will run what's queued, nor release it
            self._items.clear()

    def _others_ready(self) -> bool:
        """Whether the loop has callbacks ready that are like microtasks: the steps of coroutines and callbacks
        scheduled with ``call_soon``, rather than timers, the loop's own ones or the ones of this queue"""
        # CPython internals (loop._ready, handle._callback): other loops (like uvloop) never report any
        ready = getattr(self._loop, '_ready', None) or ()
        for handle in ready:
            callback = getattr(handle, '_callback', None)
            if isinstance(handle, asyncio.TimerHandle) or getattr(callback, '__self__', None) in (self, self._loop):
                continue
            return True
        return False

    def _defers(self, deferred: int, resumed: bool) -> bool:
        """Whether a callback waits for the code the previous one resumed, or for the microtasks the loop has
        ready. Deferring is bounded, so a busy loop can't starve the queue."""
        return (resumed or self._others_ready()) and deferred < self.MAX_DEFERRALS

    def _settle(self, deferred: int = 0):
        # the code a callback resumed runs until the loop has nothing else ready (a coroutine continues over
        # several iterations): from then on, callbacks don't wait for it anymore
        if self._defers(deferred, resumed=False):
            self._loop.call_soon(self._settle, deferred + 1)
        else:
            self._resumed = False

    def _run(self, deferred: int = 0):
        if self._defers(deferred, self._resumed):
            self._loop.call_soon(self._run, deferred + 1)
            return

        # without the internals _others_ready() reads, one callback runs per iteration of the loop
        can_inspect_ready = hasattr(self._loop, '_ready')
        more = True
        try:
            for _ in range(self.MAX_BATCH):
                with self._lock:
                    item = self._items.popleft()
                resumes = item.resumes
                if resumes:
                    self._resumed = True
                    self._loop.call_soon(self._settle)
                item.callback(*item.args)
                # released outside of the lock: the destructor of a native object may wait for a libwebrtc thread,
                # which may be posting here
                item = None
                with self._lock:
                    more = bool(self._items)
                    self._scheduled = more
                    if not more:
                        return
                    after_ready = self._items[0].after_ready
                # the next callback runs right away, unless this one resumed code, the next one waits for the ready
                # callbacks, or this one scheduled some (they run first)
                if resumes or after_ready or not can_inspect_ready or self._others_ready():
                    break
        except BaseException:
            with self._lock:
                more = bool(self._items)
                self._scheduled = more
            raise
        finally:
            if more:
                self._loop.call_soon(self._run)
