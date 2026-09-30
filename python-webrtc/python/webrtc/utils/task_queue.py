#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The queue of the callbacks libwebrtc threads post to an event loop."""

from __future__ import annotations

import asyncio
import collections
import threading
import weakref
from typing import Callable, NamedTuple


class _Item(NamedTuple):
    callback: Callable[..., object]
    args: tuple[object, ...]
    resumes: bool
    after_ready: bool


class TaskQueue:
    """Runs callbacks posted from any thread on an event loop in order, like browser tasks.

    Each one runs with what it schedules with ``call_soon`` before the next one, like microtasks.

    Args:
        loop (:obj:`asyncio.AbstractEventLoop`): The loop.
    """

    #: How many times a callback waits for other ready callbacks of the loop
    MAX_DEFERRALS = 100
    #: How many callbacks run in one iteration of the loop, when they schedule nothing
    MAX_BATCH = 100

    #: The queues of the loops without a ``__dict__`` (like uvloop's), the others keep their own
    _queues: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, TaskQueue] = weakref.WeakKeyDictionary()
    _ATTRIBUTE = '_webrtc_task_queue'

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        # weakly: a queue in _queues referencing its loop would keep it forever
        self._loop_ref = weakref.ref(loop)
        self._items: collections.deque[_Item] = collections.deque()
        self._lock = threading.Lock()
        self._scheduled = False
        # whether the last callback resumed code (like a coroutine awaiting a result) that runs before the next one
        self._resumed = False

    @property
    def _loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop_ref()

    @classmethod
    def of(cls, loop: asyncio.AbstractEventLoop) -> TaskQueue:
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
    def post_to_running(
        cls, callback: Callable[..., object], *args: object, resumes: bool = False, after_ready: bool = False
    ) -> bool:
        """Posts a callback to the queue of the running loop (see :meth:`post`).

        Args:
            callback (:obj:`callable`): The callback.
            *args: Its arguments.
            resumes (:obj:`bool`, optional): See :meth:`post`.
            after_ready (:obj:`bool`, optional): See :meth:`post`.

        Returns:
            :obj:`bool`: Whether it was posted: :obj:`False` outside of a running loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        cls.of(loop).post(callback, *args, resumes=resumes, after_ready=after_ready)
        return True

    def post(
        self, callback: Callable[..., object], *args: object, resumes: bool = False, after_ready: bool = False
    ) -> None:
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
        # a gone or closed loop won't run what's queued, nor release it
        if loop is None:
            self._items.clear()
            return
        try:
            loop.call_soon_threadsafe(self._run)
        except RuntimeError:
            self._items.clear()

    def _others_ready(self) -> bool:
        """Whether the loop has microtask-like callbacks ready: coroutine steps and ``call_soon`` callbacks."""
        # rather than timers, the loop's own callbacks or the ones of this queue
        # CPython internals (loop._ready, handle._callback): other loops (like uvloop) never report any
        ready = getattr(self._loop, '_ready', None) or ()
        for handle in ready:
            callback = getattr(handle, '_callback', None)
            if isinstance(handle, asyncio.TimerHandle) or getattr(callback, '__self__', None) in {self, self._loop}:
                continue
            return True
        return False

    def _defers(self, deferred: int, *, resumed: bool) -> bool:
        """Whether a callback waits for the code the previous one resumed, or for the ready microtasks."""
        # bounded, so a busy loop can't starve the queue
        return (resumed or self._others_ready()) and deferred < self.MAX_DEFERRALS

    def _settle(self, deferred: int = 0) -> None:
        # the code a callback resumed runs until the loop has nothing else ready (a coroutine continues over
        # several iterations): from then on, callbacks don't wait for it anymore
        if self._defers(deferred, resumed=False):
            self._loop.call_soon(self._settle, deferred + 1)
        else:
            self._resumed = False

    def _run(self, deferred: int = 0) -> None:
        if self._defers(deferred, resumed=self._resumed):
            self._loop.call_soon(self._run, deferred + 1)
            return

        more = True
        try:
            more = self._run_batch()
        except BaseException:
            with self._lock:
                more = bool(self._items)
                self._scheduled = more
            raise
        finally:
            if more:
                self._loop.call_soon(self._run)

    def _run_batch(self) -> bool:
        """Runs callbacks until one has to wait for the loop. Returns whether any are left."""
        for _ in range(self.MAX_BATCH):
            resumes = self._run_next()
            with self._lock:
                more = bool(self._items)
                self._scheduled = more
                if not more:
                    return False
                after_ready = self._items[0].after_ready
            if self._yields(resumes=resumes, after_ready=after_ready):
                return True
        return True

    def _run_next(self) -> bool:
        """Runs the next callback. Returns whether it resumes code."""
        with self._lock:
            item = self._items.popleft()
        if item.resumes:
            self._resumed = True
            self._loop.call_soon(self._settle)
        item.callback(*item.args)
        # the item is released on return, outside of the lock: the destructor of a native object may wait for
        # a libwebrtc thread, which may be posting here
        return item.resumes

    def _yields(self, *, resumes: bool, after_ready: bool) -> bool:
        """Whether the next callback waits for the loop rather than running right away."""
        # it waits for the code this one resumed, for the ready callbacks, or for the ones this one scheduled (they
        # run first); without the internals _others_ready() reads, one callback runs per iteration of the loop
        if resumes or after_ready:
            return True
        return not hasattr(self._loop, '_ready') or self._others_ready()
