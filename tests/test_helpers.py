#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The helpers of the tests."""

from __future__ import annotations

import asyncio
import gc
import warnings

import webrtc
import wrtc
from tests.helpers import exchange_ice_candidates, release_stranded_candidates, wait_until


async def gather_as_the_loop_closes(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    caller.create_data_channel('candidates')
    exchange_ice_candidates(caller, callee)
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        gathered = asyncio.get_running_loop().create_future()
        caller.on('icecandidate', lambda _event: gathered.done() or gathered.set_result(None))
        await caller.set_local_description()
        offer = caller.local_description
        assert offer is not None
        await callee.set_remote_description(offer)
        await gathered
        raise


def close_a_loop_as_candidates_come() -> None:
    """Closes a loop the way asyncio.Runner does while candidates come, then the connections, like a sync fixture."""
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(gather_as_the_loop_closes(caller, callee))
        loop.run_until_complete(asyncio.sleep(0))
        task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
    finally:
        loop.close()
    caller.close()
    callee.close()


def test_stranded_candidates_are_released() -> None:
    """A candidate that comes while a test's loop closes leaves a task, whose connections are released then."""
    baseline = wrtc._alive()['RTCPeerConnection']

    close_a_loop_as_candidates_come()
    # pytest keeps the warnings of a test, and the coroutines they come from, until it ends
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        assert release_stranded_candidates()

        def released() -> bool:
            gc.collect()
            return wrtc._alive()['RTCPeerConnection'] <= baseline

        asyncio.run(wait_until(released, 'the connections released'))
