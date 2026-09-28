#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Order of the callbacks of TaskQueue, which delivers events and results of operations."""

import asyncio
import threading

import pytest

from webrtc.utils.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_posted_callbacks_run_before_later_timers():
    loop = asyncio.get_running_loop()
    queue = TaskQueue.of(loop)
    order = []

    def post_many():
        for i in range(10):
            queue.post(order.append, i)

    thread = threading.Thread(target=post_many)
    thread.start()
    thread.join()
    # a timer set after the callbacks were posted runs after all of them, as in a browser
    timer = loop.create_future()
    loop.call_later(0, lambda: (order.append('timer'), timer.set_result(None)))
    await timer
    assert order == [*range(10), 'timer']


@pytest.mark.asyncio
async def test_microtasks_of_a_callback_run_before_the_next_one():
    loop = asyncio.get_running_loop()
    queue = TaskQueue.of(loop)
    order = []
    done = loop.create_future()

    def first():
        order.append('first')
        loop.call_soon(order.append, 'microtask')

    queue.post(first)
    queue.post(lambda: (order.append('second'), done.set_result(None)))
    await done
    assert order == ['first', 'microtask', 'second']


@pytest.mark.asyncio
async def test_resumed_code_runs_before_the_next_callback_only():
    loop = asyncio.get_running_loop()
    queue = TaskQueue.of(loop)
    order = []
    resumed = asyncio.Event()

    async def awaiting():
        await resumed.wait()
        order.append('resumed')
        await asyncio.sleep(0)
        order.append('resumed again')

    task = loop.create_task(awaiting())
    await asyncio.sleep(0)
    queue.post(resumed.set, resumes=True)
    queue.post(order.append, 'next')
    await task
    await asyncio.sleep(0.01)
    assert order == ['resumed', 'resumed again', 'next']

    # once the resumed code is done, callbacks don't wait for timers
    timer = loop.create_future()
    queue.post(order.append, 'later')
    loop.call_later(0, timer.set_result, None)
    await timer
    assert order[-1] == 'later'
