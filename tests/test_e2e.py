#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio

import pytest

import webrtc

TIMEOUT = 20


async def wait_for(predicate, what):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TIMEOUT
    while not predicate():
        if loop.time() > deadline:
            raise TimeoutError(f'Timed out waiting for {what}')
        await asyncio.sleep(0.05)


async def set_local_and_gather(pc, description):
    """Non-trickle ICE: returns the local description once all candidates are gathered."""
    await pc.set_local_description(description)
    await wait_for(lambda: pc.ice_gathering_state == webrtc.RTCIceGatheringState.complete, 'ICE gathering')
    return pc.local_description


@pytest.mark.asyncio
async def test_peers_connect_and_send_audio(caller, callee):
    """Two peer connections negotiate, connect over ICE/DTLS and stream audio."""
    source = webrtc.RTCAudioSource()
    track = source.create_track()
    caller.add_track(track)

    assert caller.local_description is None
    assert caller.signaling_state == webrtc.RTCSignalingState.stable

    offer = await set_local_and_gather(caller, await caller.create_offer())
    assert offer.type == webrtc.RTCSdpType.offer
    assert 'a=candidate:' in offer.sdp, 'Expect gathered candidates in local description'
    assert caller.signaling_state == webrtc.RTCSignalingState.have_local_offer

    await callee.set_remote_description(offer)
    assert callee.remote_description.sdp == offer.sdp
    answer = await set_local_and_gather(callee, await callee.create_answer())
    await caller.set_remote_description(answer)

    for pc in (caller, callee):
        await wait_for(lambda pc=pc: pc.connection_state == webrtc.RTCPeerConnectionState.connected, 'connection')
        assert pc.signaling_state == webrtc.RTCSignalingState.stable
        assert pc.ice_connection_state in (
            webrtc.RTCIceConnectionState.connected,
            webrtc.RTCIceConnectionState.completed,
        )

    receivers = callee.get_receivers()
    assert len(receivers) == 1
    assert receivers[0].track.kind == webrtc.MediaType.audio

    # 100 ms of 16-bit mono silence at 48 kHz, in 10 ms frames
    frame = webrtc.RTCOnDataEvent(bytes(480 * 2), 480)
    frame.sample_rate = 48000
    frame.channel_count = 1
    frame.bits_per_sample = 16
    for _ in range(10):
        source.on_data(frame)
        await asyncio.sleep(0.01)

    caller.close()
    assert caller.connection_state == webrtc.RTCPeerConnectionState.closed
    track.stop()
