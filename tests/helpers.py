#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio
import inspect

import webrtc


async def exchange_offer(caller, callee):
    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)


async def exchange_answer(caller, callee):
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    await caller.set_remote_description(answer)


async def exchange_offer_answer(caller, callee):
    await exchange_offer(caller, callee)
    await exchange_answer(caller, callee)


async def generate_answer(offer):
    pc = webrtc.RTCPeerConnection()

    await pc.set_remote_description(offer)
    answer = await pc.create_answer()

    pc.close()

    return answer


#: How long a test waits to see that something doesn't happen
QUIET_PERIOD = 0.3


async def _called(function):
    result = function()
    return await result if inspect.isawaitable(result) else result


async def wait_until(predicate, what, timeout=10):
    """Polls until the predicate (a function or a coroutine function) is true, or raises TimeoutError naming what
    it waited for"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not await _called(predicate):
        if loop.time() > deadline:
            raise TimeoutError(f'Timed out waiting for {what}')
        await asyncio.sleep(0.05)


async def wait_for_ice_gathering_complete(pc, timeout=10):
    await wait_until(lambda: pc.ice_gathering_state == webrtc.RTCIceGatheringState.complete, 'ICE gathering', timeout)


def wait_for_event(target, name, timeout=10, predicate=None):
    """Registers for the next event of a type (the next one the predicate accepts, if given) right away, and returns
    an awaitable of it"""
    future = asyncio.get_running_loop().create_future()

    def on_event(event):
        if not future.done() and (predicate is None or predicate(event)):
            target.off(name, on_event)
            future.set_result(event)

    target.on(name, on_event)
    return asyncio.wait_for(future, timeout)


async def next_task():
    """Lets the current task end, like awaiting a timer: what a task keeps until it ends (like the parameters of a
    sender) expires, and callbacks posted meanwhile run. asyncio.sleep(0) doesn't end it: the code it resumes is like
    a microtask of the same task."""
    loop = asyncio.get_running_loop()
    timer = loop.create_future()
    loop.call_later(0, timer.set_result, None)
    await timer


# tasks adding candidates, kept until done (the loop only keeps a weak reference to a task)
_adding_candidates = set()


async def _add_ice_candidate(pc, candidate):
    try:
        await pc.add_ice_candidate(candidate)
    except webrtc.InvalidStateError:
        # a test may close the connection before the candidates of the other one are added
        if pc.signaling_state != webrtc.RTCSignalingState.closed:
            raise


def exchange_ice_candidates(caller, callee):
    """Trickles the candidates of each connection to the other one"""
    for pc, other in ((caller, callee), (callee, caller)):

        def on_candidate(event, other=other):
            if event.candidate is not None:
                task = asyncio.ensure_future(_add_ice_candidate(other, event.candidate))
                _adding_candidates.add(task)
                task.add_done_callback(_adding_candidates.discard)

        pc.on('icecandidate', on_candidate)


async def connect(caller, callee, timeout=10):
    """Negotiates and waits until both connections are connected"""
    exchange_ice_candidates(caller, callee)
    await exchange_offer_answer(caller, callee)

    def connected():
        return all(pc.connection_state == webrtc.RTCPeerConnectionState.connected for pc in (caller, callee))

    await wait_until(connected, 'both connections to connect', timeout)


async def wait_until_unmuted(track, timeout=10):
    """Waits until media arrives on a remote track, which may take longer than connecting"""
    if track.muted:
        await wait_for_event(track, 'unmute', timeout)
