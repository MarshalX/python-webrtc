#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""call_native and mailbox completions."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from typing import Callable

import pytest

import webrtc
import wrtc
from tests.isolation import isolated
from webrtc.utils import loops
from webrtc.utils.loops import LoopState, call_native


def _in_thread(target: Callable[[], None]) -> None:
    thread = threading.Thread(target=target)
    thread.start()
    thread.join()


@pytest.mark.asyncio
async def test_result() -> None:
    def method(mailbox: wrtc.Mailbox, token: int, *numbers: int) -> None:
        _in_thread(lambda: wrtc._testing.complete(mailbox, token, sum(numbers)))

    assert await call_native(method, 1, 2) == 3


@pytest.mark.asyncio
async def test_failure_is_raised_as_python_error() -> None:
    def method(mailbox: wrtc.Mailbox, token: int) -> None:
        _in_thread(lambda: wrtc._testing.fail(mailbox, token))

    with pytest.raises(webrtc.RTCException, match='The operation failed'):
        await call_native(method)


@pytest.mark.asyncio
async def test_abandoned_completion_raises_invalid_state_error() -> None:
    """Dropped completion fails the call."""

    def method(mailbox: wrtc.Mailbox, token: int) -> None:
        wrtc._testing.abandon(mailbox, token)

    with pytest.raises(webrtc.InvalidStateError, match='abandoned'):
        await call_native(method)


@pytest.mark.asyncio
async def test_late_completion_after_cancel_is_dropped() -> None:
    """Late completion after cancel is silent."""
    loop = asyncio.get_running_loop()
    errors: list[dict[str, object]] = []
    loop.set_exception_handler(lambda _, context: errors.append(context))
    state = LoopState.of(loop)
    tokens: list[int] = []

    def method(_mailbox: wrtc.Mailbox, token: int) -> None:
        tokens.append(token)

    task = loop.create_task(call_native(method))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # the drain drops the completion, then runs the marker
    await loop.run_in_executor(None, wrtc._testing.complete, state.mailbox, tokens[0], 1)
    done = loop.create_future()
    state.post(lambda: done.set_result(None))
    await done
    assert errors == []
    assert state.pending == {}


@pytest.mark.asyncio
async def test_call_of_a_native_object_is_started_for_its_wrapper() -> None:
    """Completion re-evaluates the bound wrapper."""
    loop = asyncio.get_running_loop()
    state = LoopState.of(loop)
    pc = webrtc.RTCPeerConnection()
    task = loop.create_task(call_native(pc._native_obj.getStats))
    await asyncio.sleep(0)
    # weakly: a call in flight is no root
    assert [call.target() if call.target is not None else None for call in state.pending.values()] == [pc]
    assert isinstance(await task, str)
    assert state.pending == {}
    pc.close()


@isolated
def test_exit_cancels_the_calls_of_a_loop_of_another_thread_on_that_thread() -> None:
    """Exit cancels calls on the loop's own thread."""
    started = threading.Event()
    cancelled = threading.Event()

    async def awaiting() -> None:
        state = LoopState.of(asyncio.get_running_loop())
        _, future = state.start(None)
        started.set()
        with contextlib.suppress(asyncio.CancelledError):
            await future
        cancelled.set()

    # debug mode raises on a loop touched from another thread
    thread = threading.Thread(target=asyncio.run, args=(awaiting(),), kwargs={'debug': True}, daemon=True)
    thread.start()
    assert started.wait(5)
    loops._exit()
    assert cancelled.wait(5)
    thread.join(5)
    assert not thread.is_alive()


@isolated
def test_calls_at_exit_are_cancelled_and_later_ones_fail_right_away() -> None:
    """Exit cancels calls; later calls fail."""
    loop = asyncio.new_event_loop()
    try:
        state = LoopState.of(loop)
        _, future = state.start(None)
        loops._exit()
        assert future.cancelled()
        assert state.pending == {}
        assert state.mailbox.closed

        def method(_mailbox: wrtc.Mailbox, _token: int) -> None:
            pytest.fail('never called')

        with pytest.raises(webrtc.InvalidStateError, match='exiting'):
            loop.run_until_complete(call_native(method))
    finally:
        loop.close()
