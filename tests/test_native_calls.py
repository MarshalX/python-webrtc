#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""call_native, which awaits native methods reporting to callbacks from libwebrtc threads."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Callable

import pytest

import wrtc
from tests.helpers import mistyped
from webrtc.utils.native_calls import call_native

OnSuccess = Callable[[object], None]
OnFailure = Callable[[wrtc.RTCCallbackException], None]


def _error(error: Exception) -> wrtc.RTCCallbackException:
    """A stand-in of the native exception passed to on_failure."""
    return mistyped(SimpleNamespace(toPython=lambda: error))


def _later(callback: Callable[..., None], *args: object, delay: float = 0.0) -> None:
    threading.Timer(delay, callback, args).start()


@pytest.mark.asyncio
async def test_result() -> None:
    def method(on_success: Callable[[int], None], _on_failure: OnFailure, *numbers: int) -> None:
        _later(on_success, sum(numbers))

    assert await call_native(method, 1, 2) == 3


@pytest.mark.asyncio
async def test_no_result() -> None:
    def method(on_success: Callable[[], None], _on_failure: OnFailure) -> None:
        _later(on_success)

    assert await call_native(method) is None


@pytest.mark.asyncio
async def test_failure_is_raised_as_python_error() -> None:
    def method(_on_success: OnSuccess, on_failure: OnFailure) -> None:
        _later(on_failure, _error(ValueError('native')))

    with pytest.raises(ValueError, match='native'):
        await call_native(method)


@pytest.mark.asyncio
async def test_late_result_after_cancel_is_dropped() -> None:
    """A result arriving after the caller was canceled doesn't reach the loop's exception handler."""
    loop = asyncio.get_running_loop()
    errors: list[dict[str, object]] = []
    loop.set_exception_handler(lambda _, context: errors.append(context))
    settled = threading.Event()

    def method(on_success: OnSuccess, _on_failure: OnFailure) -> None:
        def succeed() -> None:
            on_success('late')
            settled.set()

        _later(succeed, delay=0.05)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(call_native(method), 0.01)
    await asyncio.get_running_loop().run_in_executor(None, settled.wait)
    await asyncio.sleep(0.01)
    assert errors == []
