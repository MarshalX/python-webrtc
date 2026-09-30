#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Awaiting the native methods that report their result with callbacks."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable, TypeVar

from webrtc.utils.task_queue import TaskQueue

if TYPE_CHECKING:
    from typing_extensions import Concatenate, ParamSpec

    import wrtc

    _P = ParamSpec('_P')

_T = TypeVar('_T')


async def call_native(
    method: Callable[Concatenate[Callable[[_T], None], Callable[[wrtc.RTCCallbackException], None], _P], None],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    """Calls a native method taking success and failure callbacks, called from a libwebrtc thread, and awaits them.

    The result goes through the task queue of the loop, so the code awaiting it runs after the handlers of the events
    libwebrtc emitted before completing the call.

    Args:
        method (:obj:`callable`): The native method, called as ``method(on_success, on_failure, *args)``.
        *args: Its arguments.
        **kwargs: Its keyword arguments.

    Returns:
        The result passed to ``on_success``, if any.

    Raises:
        The error passed to ``on_failure``, as a Python exception.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def settle(result: _T | None, error: wrtc.RTCCallbackException | None) -> None:
        # the caller may have been canceled meanwhile
        if future.done():
            return
        if error is not None:
            future.set_exception(error.toPython())
        else:
            future.set_result(result)

    # libwebrtc threads, with the GIL held: only schedule
    def on_success(result: _T | None = None) -> None:
        TaskQueue.of(loop).post(settle, result, None, resumes=True, after_ready=True)

    def on_failure(error: wrtc.RTCCallbackException) -> None:
        TaskQueue.of(loop).post(settle, None, error, resumes=True, after_ready=True)

    method(on_success, on_failure, *args, **kwargs)
    return await future
