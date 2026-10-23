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

import pytest

import webrtc
import wrtc
from tests.helpers import delivered, exchange_ice_candidates, next_task, release_stranded_candidates, wait_until


async def gather_as_the_loop_closes(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    caller.create_data_channel('candidates')
    exchange_ice_candidates(caller, callee)
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        gathered = asyncio.get_running_loop().create_future()

        def on_candidate(_event: webrtc.RTCPeerConnectionIceEvent) -> None:
            if not gathered.done():
                gathered.set_result(None)

        caller.on('icecandidate', on_candidate)
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


@pytest.mark.asyncio
async def test_delivered_waits_for_queued_events(pc: webrtc.RTCPeerConnection) -> None:
    """Events libwebrtc queued before it are delivered, their handlers called, once it returns."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    calls: list[str] = []
    transceiver.receiver.track.on('ended', lambda event: calls.append(event.type))

    # the event's record waits in the mailbox: nothing wakes the loop for it
    wrtc._testing.park('dispatcher.wake')
    try:
        transceiver.stop()
        await next_task()
        assert calls == []

        await delivered()
        assert calls == ['ended']
    finally:
        wrtc._testing.release('dispatcher.wake')
