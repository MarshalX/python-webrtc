#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""An exit handler registered before the library is imported, so it runs after the library's own ones."""

from __future__ import annotations

import asyncio
import atexit
import importlib
import os
import sys
import threading
from typing import TYPE_CHECKING, Callable

import pytest

from tests.isolation import isolated

if TYPE_CHECKING:
    from collections.abc import Awaitable


async def _settles(operation: Callable[[], Awaitable[object]]) -> bool:
    import webrtc

    try:
        await asyncio.wait_for(operation(), 20)
    except asyncio.TimeoutError:
        return False
    except webrtc.InvalidStateError:
        pass
    return True


async def _operations_settle() -> bool:
    import webrtc

    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver('audio')
    return await _settles(pc.get_stats) and await _settles(pc.create_offer)


def _await_operations() -> None:
    settled = False
    try:
        settled = asyncio.run(_operations_settle())
    finally:
        # an error of an exit handler doesn't change the exit code
        if not settled:
            sys.stderr.write('an operation at exit failed or hung\n')
            sys.stderr.flush()
            os._exit(1)


@isolated
def test_operations_awaited_at_exit_settle() -> None:
    """Operations awaited by an exit handler settle rather than hang."""
    assert 'webrtc' not in sys.modules
    atexit.register(_await_operations)
    importlib.import_module('webrtc')


def _change_activity_while_a_thread_is_parked_in_a_release() -> None:
    import webrtc
    import wrtc
    from webrtc.utils import loops

    # a loop made after the library's exit handler ran, so not released by it
    loop = asyncio.new_event_loop()
    state = loops.LoopState.of(loop)
    loop.close()
    # before 3.14, a thread never returns from a native call once exit starts
    wrtc._testing.park('gil.exit')
    threading.Thread(target=state.release, daemon=True).start()
    parked = wrtc._testing.parked('gil.exit', 10)
    # an activity change visits every other state: it hung on the parked thread's lock
    pc = webrtc.RTCPeerConnection()
    pc.close()
    if not parked:
        sys.stderr.write('the releasing thread never parked\n')
        sys.stderr.flush()
        os._exit(1)


@pytest.mark.skipif(sys.version_info >= (3, 14), reason='from 3.14 on, a thread entering Python at exit ends there')
@isolated(timeout=30)
def test_activity_changed_at_exit_after_a_state_released_there() -> None:
    """Daemon release at exit doesn't block later handlers."""
    assert 'webrtc' not in sys.modules
    atexit.register(_change_activity_while_a_thread_is_parked_in_a_release)
    importlib.import_module('webrtc')
