#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio

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


async def wait_for_ice_gathering_complete(pc, timeout=10):
    async def _wait():
        while pc.ice_gathering_state != webrtc.RTCIceGatheringState.complete:
            await asyncio.sleep(0.05)

    await asyncio.wait_for(_wait(), timeout)


def wait_for_event(target, name, timeout=10):
    """Registers for the next event of a type right away, and returns an awaitable of it"""
    future = asyncio.get_running_loop().create_future()
    target.once(name, lambda event: future.done() or future.set_result(event))
    return asyncio.wait_for(future, timeout)


def exchange_ice_candidates(caller, callee):
    """Trickles the candidates of each connection to the other one"""
    for pc, other in ((caller, callee), (callee, caller)):

        def on_candidate(event, other=other):
            if event.candidate is not None:
                asyncio.ensure_future(other.add_ice_candidate(event.candidate))

        pc.on('icecandidate', on_candidate)


async def connect(caller, callee, timeout=10):
    """Negotiates and waits until both connections are connected"""
    exchange_ice_candidates(caller, callee)
    await exchange_offer_answer(caller, callee)

    async def _wait():
        while webrtc.RTCPeerConnectionState.connected not in {caller.connection_state} or (
            callee.connection_state != webrtc.RTCPeerConnectionState.connected
        ):
            await asyncio.sleep(0.05)

    await asyncio.wait_for(_wait(), timeout)
