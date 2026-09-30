#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio
from typing import Any, Callable

from webrtc.utils.task_queue import TaskQueue


async def call_native(method: Callable, *args) -> Any:
    """Calls a native method taking success and failure callbacks, called from a libwebrtc thread, and awaits them.

    The result goes through the task queue of the loop, so the code awaiting it runs after the handlers of the events
    libwebrtc emitted before completing the call.

    Args:
        method (:obj:`callable`): The native method, called as ``method(on_success, on_failure, *args)``.
        *args: Its arguments.

    Returns:
        The result passed to ``on_success``, if any.

    Raises:
        The error passed to ``on_failure``, as a Python exception.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def settle(result: Any, error: Any) -> None:
        # the caller may have been canceled meanwhile
        if future.done():
            return
        if error is not None:
            future.set_exception(error.toPython())
        else:
            future.set_result(result)

    # libwebrtc threads, with the GIL held: only schedule
    def on_success(result: Any = None) -> None:
        TaskQueue.of(loop).post(settle, result, None, resumes=True, after_ready=True)

    def on_failure(error: Any) -> None:
        TaskQueue.of(loop).post(settle, None, error, resumes=True, after_ready=True)

    method(on_success, on_failure, *args)
    return await future
