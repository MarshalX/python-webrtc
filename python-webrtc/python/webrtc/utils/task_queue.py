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
from typing import Callable


class TaskQueue:
    """Runs callbacks posted from any thread on an event loop, in the order they were posted, before callbacks
    the loop gets later (like timers), as a browser runs its queued tasks.

    Events and results of asynchronous operations of libwebrtc go through the queue of their loop, so they arrive
    in the order libwebrtc reported them, and whatever a callback schedules (like the continuation of a coroutine
    awaiting a result) runs before the next callback, as a browser runs microtasks between tasks.
    """

    #: How many times a callback waits for other ready callbacks of the loop
    MAX_DEFERRALS = 100
    #: How many callbacks run in one iteration of the loop, when they schedule nothing
    MAX_BATCH = 100

    _queues: 'weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, TaskQueue]' = weakref.WeakKeyDictionary()
    _queues_lock = threading.Lock()

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._items = collections.deque()
        self._lock = threading.Lock()
        self._scheduled = False
        # whether the last callback resumed code (like a coroutine awaiting a result) that runs before the next one
        self._resumed = False

    @classmethod
    def of(cls, loop: asyncio.AbstractEventLoop) -> 'TaskQueue':
        with cls._queues_lock:
            queue = cls._queues.get(loop)
            if queue is None:
                queue = cls._queues[loop] = cls(loop)
            return queue

    def post(self, callback: Callable, *args, resumes: bool = False, after_ready: bool = False) -> None:
        """Schedules a callback, from any thread. Callbacks posted to a closed loop are dropped.

        Args:
            callback: The callback.
            *args: Its arguments.
            resumes: Whether the callback resumes code awaiting it, like the result of an operation. The next
                callback waits for what's resumed to run first, as microtasks run before the next task in a browser.
            after_ready: Whether the callback waits for the callbacks the loop has ready, like the end of the
                current task (with its microtasks) in a browser.
        """
        # Nothing is allocated under the lock: an allocation may run the garbage collector, and so the destructor
        # of a native object, which may wait for a libwebrtc thread that is posting here. Appending is atomic.
        self._items.append((callback, args, resumes, after_ready))
        with self._lock:
            if self._scheduled:
                return
            self._scheduled = True
        try:
            self._loop.call_soon_threadsafe(self._run)
        except RuntimeError:  # the loop is closed
            pass

    def _others_ready(self) -> bool:
        """Whether the loop has callbacks ready that are like microtasks: the steps of coroutines and callbacks
        scheduled with ``call_soon``, rather than timers, the loop's own ones or the ones of this queue"""
        ready = getattr(self._loop, '_ready', None) or ()
        for handle in ready:
            callback = getattr(handle, '_callback', None)
            if isinstance(handle, asyncio.TimerHandle) or getattr(callback, '__self__', None) in (self, self._loop):
                continue
            return True
        return False

    def _settle(self, deferred: int = 0):
        # the code a callback resumed runs until the loop has nothing else ready (a coroutine continues over
        # several iterations): from then on, callbacks don't wait for it anymore, as the next browser task
        # doesn't wait for the microtasks of an earlier one
        if self._others_ready() and deferred < self.MAX_DEFERRALS:
            self._loop.call_soon(self._settle, deferred + 1)
        else:
            self._resumed = False

    def _run(self, deferred: int = 0):
        # after a callback that resumed code, the callbacks that code scheduled run first. Deferring is bounded,
        # so a busy loop can't starve the queue.
        # like a browser task, a callback waits for the microtasks the loop has ready (a coroutine or a promise
        # continuing over several iterations)
        if (self._resumed or self._others_ready()) and deferred < self.MAX_DEFERRALS:
            self._loop.call_soon(self._run, deferred + 1)
            return

        ready = getattr(self._loop, '_ready', None)
        more = True
        try:
            for _ in range(self.MAX_BATCH):
                with self._lock:
                    item = self._items.popleft()
                callback, args, resumes, _ = item
                if resumes:
                    self._resumed = True
                    self._loop.call_soon(self._settle)
                callback(*args)
                # released outside of the lock: the destructor of a native object may wait for a libwebrtc thread,
                # which may be posting here
                item = callback = args = None
                with self._lock:
                    more = bool(self._items)
                    self._scheduled = more
                    if not more:
                        return
                    after_ready = self._items[0][3]
                # the next callback runs right away, like the next browser task, unless something like a microtask
                # is ready (what this one scheduled runs before the next one)
                if resumes or after_ready or ready is None or self._others_ready():
                    break
        except BaseException:
            with self._lock:
                more = bool(self._items)
                self._scheduled = more
            raise
        finally:
            if more:
                self._loop.call_soon(self._run)
