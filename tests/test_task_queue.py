#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Order of the callbacks of TaskQueue, which delivers events and results of operations."""

from __future__ import annotations

import asyncio
import gc
import threading
import weakref

import pytest

from webrtc.utils.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_posted_callbacks_run_before_later_timers() -> None:
    """Callbacks posted from another thread run before a timer set after they were posted."""
    loop = asyncio.get_running_loop()
    queue = TaskQueue.of(loop)
    order = []

    def post_many() -> None:
        for i in range(10):
            queue.post(order.append, i)

    thread = threading.Thread(target=post_many)
    thread.start()
    thread.join()
    timer = loop.create_future()

    def on_timer() -> None:
        order.append('timer')
        timer.set_result(None)

    loop.call_later(0, on_timer)
    await timer
    assert order == [*range(10), 'timer']


@pytest.mark.asyncio
async def test_microtasks_of_a_callback_run_before_the_next_one() -> None:
    """What a callback schedules with call_soon runs before the next posted callback."""
    loop = asyncio.get_running_loop()
    queue = TaskQueue.of(loop)
    order = []
    done = loop.create_future()

    def first() -> None:
        order.append('first')
        loop.call_soon(order.append, 'microtask')

    def second() -> None:
        order.append('second')
        done.set_result(None)

    queue.post(first)
    queue.post(second)
    await done
    assert order == ['first', 'microtask', 'second']


@pytest.mark.asyncio
async def test_resumed_code_runs_before_the_next_callback_only() -> None:
    """Code a callback resumes runs before the next callback; after it, callbacks don't wait for timers."""
    loop = asyncio.get_running_loop()
    queue = TaskQueue.of(loop)
    order = []
    resumed = asyncio.Event()

    async def awaiting() -> None:
        await resumed.wait()
        order.append('resumed')
        await asyncio.sleep(0)
        order.append('resumed again')

    task = loop.create_task(awaiting())
    await asyncio.sleep(0)
    after_next = loop.create_future()
    queue.post(resumed.set, resumes=True)
    queue.post(order.append, 'next')
    queue.post(after_next.set_result, None)
    await task
    await after_next
    assert order == ['resumed', 'resumed again', 'next']

    # once the resumed code is done, callbacks don't wait for timers
    timer = loop.create_future()
    queue.post(order.append, 'later')
    loop.call_later(0, timer.set_result, None)
    await timer
    assert order[-1] == 'later'


def test_loops_are_collected_with_what_they_had_queued() -> None:
    """A closed loop is collected with what was still queued for it."""

    class Held:
        pass

    refs = []
    for _ in range(5):
        loop = asyncio.new_event_loop()
        held = Held()
        held.loop = loop
        # never run: the loop closes first
        TaskQueue.of(loop).post(lambda _held=held: None)
        loop.close()
        refs.append((weakref.ref(loop), weakref.ref(held)))
        del loop, held
    gc.collect()

    assert [ref for pair in refs for ref in pair if ref() is not None] == []
