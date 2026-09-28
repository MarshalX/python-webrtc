#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""ICE transports of their own (the WebRTC ICE extension): gathering, starting and connecting."""

import asyncio

import pytest

import webrtc
from tests.helpers import wait_for_event


@pytest.mark.asyncio
async def test_two_transports_connect():
    local, remote = webrtc.RTCIceTransport(), webrtc.RTCIceTransport()
    assert local.role is None and local.state == webrtc.RTCIceTransportState.new
    assert local.get_local_parameters() and local.get_remote_parameters() is None

    for a, b in ((local, remote), (remote, local)):
        a.on('icecandidate', lambda event, b=b: event.candidate and b.add_remote_candidate(event.candidate))
    connected = [wait_for_event(t, 'statechange') for t in (local, remote)]
    local.gather()
    remote.gather()
    assert local.gathering_state == webrtc.CricketIceGatheringState.gathering
    # both take the controlling role: one of them switches
    local.start(remote.get_local_parameters(), 'controlling')
    remote.start(local.get_local_parameters(), 'controlling')
    await asyncio.gather(*connected)

    assert local.state == remote.state == webrtc.RTCIceTransportState.connected
    assert {local.role, remote.role} == {webrtc.RTCIceRole.controlling, webrtc.RTCIceRole.controlled}
    pair = local.get_selected_candidate_pair()
    assert pair.local.candidate in [c.candidate for c in local.get_local_candidates()]
    assert pair.remote.candidate in [c.candidate for c in local.get_remote_candidates()]

    local.stop()
    assert local.state == webrtc.RTCIceTransportState.closed
    assert local.get_selected_candidate_pair() is None
    with pytest.raises(webrtc.InvalidStateError):
        local.gather()
    remote.stop()


def test_start_validation():
    transport = webrtc.RTCIceTransport()
    with pytest.raises(webrtc.InvalidSyntaxError):
        transport.start(webrtc.RTCIceParameters('ab', 'p' * 22))
    with pytest.raises(webrtc.InvalidSyntaxError):
        transport.start(webrtc.RTCIceParameters('abcd', 'short'))
    transport.start(webrtc.RTCIceParameters('abcd', 'p' * 22))
    assert transport.role == webrtc.RTCIceRole.controlled
    with pytest.raises(webrtc.InvalidStateError):
        transport.start(webrtc.RTCIceParameters('abcd', 'p' * 22), 'controlling')
    with pytest.raises(webrtc.OperationError):
        transport.add_remote_candidate(webrtc.RTCIceCandidate('invalid', sdp_mid=''))

    candidate = webrtc.RTCIceCandidate('candidate:1 1 udp 2113929471 203.0.113.100 10100 typ host', sdp_mid='')
    transport.add_remote_candidate(candidate)
    assert transport.state == webrtc.RTCIceTransportState.checking
    assert transport.get_remote_candidates() == [candidate]
    # other remote parameters are another remote agent
    transport.start(webrtc.RTCIceParameters('efgh', 'q' * 22))
    assert transport.state == webrtc.RTCIceTransportState.new
    assert transport.get_remote_candidates() == []
    transport.stop()
