#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio

import pytest

import webrtc
from tests.helpers import wait_for_ice_gathering_complete, wait_until

TIMEOUT = 20


async def set_local_and_gather(
    pc: webrtc.RTCPeerConnection, description: webrtc.RTCSessionDescriptionInit
) -> webrtc.RTCSessionDescription | None:
    """Non-trickle ICE: returns the local description once all candidates are gathered."""
    await pc.set_local_description(description)
    await wait_for_ice_gathering_complete(pc, TIMEOUT)
    return pc.local_description


@pytest.mark.asyncio
async def test_peers_connect_and_send_audio(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Two peer connections negotiate, connect over ICE/DTLS and stream audio."""
    track = webrtc.MediaStreamTrackGenerator('audio')
    caller.add_track(track)

    assert caller.local_description is None
    assert caller.signaling_state == webrtc.RTCSignalingState.stable

    offer = await set_local_and_gather(caller, await caller.create_offer())
    assert offer.type == webrtc.RTCSdpType.offer
    assert 'a=candidate:' in offer.sdp, 'Expect gathered candidates in local description'
    assert 'a=end-of-candidates' in offer.sdp, 'Expect the end of candidates once gathering is complete'
    assert caller.signaling_state == webrtc.RTCSignalingState.have_local_offer

    await callee.set_remote_description(offer)
    # libwebrtc drops a=end-of-candidates when it serializes a remote description
    assert callee.remote_description.sdp == offer.sdp.replace('a=end-of-candidates\r\n', '')
    answer = await set_local_and_gather(callee, await callee.create_answer())
    await caller.set_remote_description(answer)

    for pc in (caller, callee):
        await wait_until(
            lambda pc=pc: pc.connection_state == webrtc.RTCPeerConnectionState.connected, 'connection', TIMEOUT
        )
        assert pc.signaling_state == webrtc.RTCSignalingState.stable
        assert pc.ice_connection_state in {
            webrtc.RTCIceConnectionState.connected,
            webrtc.RTCIceConnectionState.completed,
        }

    receivers = callee.get_receivers()
    assert len(receivers) == 1
    assert receivers[0].track.kind == webrtc.MediaType.audio

    # 100 ms of 16-bit mono silence at 48 kHz, in 10 ms frames
    writer = track.writable.get_writer()
    for i in range(10):
        await writer.write(
            webrtc.AudioData(
                format='s16',
                sample_rate=48000,
                number_of_frames=480,
                number_of_channels=1,
                timestamp=i * 10_000,
                data=bytes(480 * 2),
            )
        )
        await asyncio.sleep(0.01)

    caller.close()
    assert caller.connection_state == webrtc.RTCPeerConnectionState.closed
    track.stop()
