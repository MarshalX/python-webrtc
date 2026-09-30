#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""ICE transports: the ones of a connection, and ones of their own.

The ones of their own (the WebRTC ICE extension) gather, start and connect without a connection.
"""

from __future__ import annotations

import asyncio

import pytest

import webrtc
from tests.helpers import connect, wait_for_event, wait_until


@pytest.mark.asyncio
async def test_candidates_parameters_and_role(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A connection's transport learns its role from the answer, and has the signaled parameters and candidates."""
    caller.create_data_channel('ice')
    await caller.set_local_description()
    ice = caller.sctp.transport.ice_transport
    assert ice.role == webrtc.RTCIceRole.unknown
    assert ice.get_remote_parameters() is None

    await connect(caller, callee)
    await wait_until(lambda: ice.role == webrtc.RTCIceRole.controlling, 'the controlling role')
    remote_ice = callee.sctp.transport.ice_transport
    local, remote = ice.get_local_parameters(), ice.get_remote_parameters()
    assert isinstance(local, webrtc.RTCIceParameters)
    assert local.username_fragment
    assert local.password
    assert remote.username_fragment == remote_ice.get_local_parameters().username_fragment
    assert ice.get_local_candidates()
    assert all(c.candidate for c in ice.get_local_candidates())
    assert {c.candidate for c in ice.get_remote_candidates()} <= {
        c.candidate for c in remote_ice.get_local_candidates()
    }


@pytest.mark.asyncio
async def test_component(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """RTP and RTCP are multiplexed on the transport of the RTP component."""
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    await connect(caller, callee)
    assert transceiver.sender.transport.ice_transport.component == webrtc.RTCIceComponent.rtp


@pytest.mark.asyncio
async def test_close_keeps_gathering_state(pc: webrtc.RTCPeerConnection) -> None:
    """Closing a connection closes its transports, it doesn't complete their gathering."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    await pc.set_local_description()
    ice = transceiver.sender.transport.ice_transport
    state = ice.gathering_state
    pc.close()
    assert ice.state == webrtc.RTCIceTransportState.closed
    assert ice.gathering_state == state


@pytest.mark.asyncio
async def test_two_transports_connect() -> None:
    """Two transports gather, start with each other's parameters and connect, one switching to the controlled role."""
    local, remote = webrtc.RTCIceTransport(), webrtc.RTCIceTransport()
    assert local.role is None
    assert local.state == webrtc.RTCIceTransportState.new
    assert local.get_local_parameters()
    assert local.get_remote_parameters() is None

    for transport, other in ((local, remote), (remote, local)):

        def on_candidate(event: webrtc.RTCPeerConnectionIceEvent, other: webrtc.RTCIceTransport = other) -> None:
            if event.candidate:
                other.add_remote_candidate(event.candidate)

        transport.on('icecandidate', on_candidate)
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


def test_start_validation() -> None:
    """Start checks the remote parameters and the role, and other remote parameters restart the checks."""
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
