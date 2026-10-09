#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The interpreter exits while objects are alive and busy: no hang, no crash."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import os
import sys
import threading
import time
import warnings
from typing import Callable

import pytest

import webrtc
from tests.helpers import connect
from tests.isolation import isolated

# kept alive until the interpreter finalizes
_kept: list[object] = []


def _start(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


async def _keep_busy_objects() -> None:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    for track in stream.get_tracks():
        caller.add_track(track, stream)
    channel = caller.create_data_channel('exit')
    await connect(caller, callee)

    def spin() -> None:
        while True:
            _ = caller.connection_state, caller.get_transceivers(), callee.get_receivers()
            with contextlib.suppress(Exception):
                channel.send('busy')

    _start(spin)
    await asyncio.sleep(0.3)
    _kept.extend((caller, callee, channel))


@pytest.mark.parametrize('_attempt', range(5))
@isolated(timeout=30)
def test_exit_while_objects_are_busy(_attempt: int) -> None:
    """Wrappers released by the last collection must not block on threads hung in the GIL."""
    asyncio.run(_keep_busy_objects())


def _ignore(_result: object) -> None:
    pass


@pytest.mark.parametrize('_attempt', range(5))
@isolated(timeout=30)
def test_exit_while_operations_are_pending(_attempt: int) -> None:
    """Callbacks of operations completing at exit are dropped, not run by a libwebrtc thread taking the GIL."""
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver('audio')

    def spin() -> None:
        while True:
            pc._native_obj.getStats(_ignore, _ignore)
            time.sleep(0)

    for _ in range(4):
        _start(spin)
    time.sleep(0.3)
    _kept.append(pc)


async def _use() -> None:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    track = (await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=True))).get_tracks()[0]
    caller.add_track(track)
    await asyncio.wait_for(connect(caller, callee), 10)
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
    frame = (await asyncio.wait_for(reader.read(), 5)).value
    assert frame is not None
    frame.close()
    track.stop()
    caller.close()
    callee.close()


def _forked_child_works() -> bool:
    if sys.platform == 'darwin':
        try:
            webrtc.RTCPeerConnection()
        except RuntimeError:
            return True
        return False
    asyncio.run(_use())
    return True


def _exit_code_within(pid: int, seconds: float) -> int | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done != 0:
            return os.waitstatus_to_exitcode(status)
        time.sleep(0.05)
    os.kill(pid, 9)
    return None


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='no fork')
@isolated(timeout=60)
def test_forked_child_leaves_the_objects_of_its_parent_alone() -> None:
    """The child of a fork doesn't block on its parent's threads; new objects work (raise on macOS)."""
    warnings.simplefilter('ignore', DeprecationWarning)  # fork with threads
    constraints = webrtc.MediaStreamConstraints(audio=True, video=True)
    parent = [webrtc.RTCPeerConnection(), asyncio.run(webrtc.media_devices.get_user_media(constraints))]
    asyncio.run(_use())
    pid = os.fork()
    if pid == 0:
        parent.clear()
        gc.collect()
        sys.exit(0 if _forked_child_works() else 1)

    assert _exit_code_within(pid, 30) == 0
