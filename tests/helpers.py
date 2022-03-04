#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

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

