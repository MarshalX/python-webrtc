#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""call_native, which awaits native methods reporting to callbacks from libwebrtc threads."""

import asyncio
import threading

import pytest

from webrtc.utils.native_calls import call_native


class _Error:
    def __init__(self, error):
        self._error = error

    def toPython(self):
        return self._error


def _later(callback, *args, delay=0.0):
    threading.Timer(delay, callback, args).start()


@pytest.mark.asyncio
async def test_result():
    def method(on_success, on_failure, a, b):
        _later(on_success, a + b)

    assert await call_native(method, 1, 2) == 3


@pytest.mark.asyncio
async def test_no_result():
    assert await call_native(lambda on_success, on_failure: _later(on_success)) is None


@pytest.mark.asyncio
async def test_failure_is_raised_as_python_error():
    def method(on_success, on_failure):
        _later(on_failure, _Error(ValueError('native')))

    with pytest.raises(ValueError, match='native'):
        await call_native(method)


@pytest.mark.asyncio
async def test_late_result_after_cancel_is_dropped():
    """A result arriving after the caller was canceled doesn't reach the loop's exception handler"""
    loop = asyncio.get_running_loop()
    errors = []
    loop.set_exception_handler(lambda loop, context: errors.append(context))
    settled = threading.Event()

    def method(on_success, on_failure):
        def succeed():
            on_success('late')
            settled.set()

        _later(succeed, delay=0.05)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(call_native(method), 0.01)
    await asyncio.get_running_loop().run_in_executor(None, settled.wait)
    await asyncio.sleep(0.01)
    assert errors == []
