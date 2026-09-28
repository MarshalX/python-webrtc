#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Events: on/once/off, delivery on the event loop, and states that change along with their events."""

import asyncio

import pytest

import webrtc
from tests.helpers import connect, wait_for_event


@pytest.mark.asyncio
async def test_on_decorator_once_and_off():
    pc = webrtc.RTCPeerConnection()
    calls = []

    @pc.on('negotiationneeded')
    def decorated(event):
        calls.append(('decorated', event.type, event.target is pc))

    pc.once('negotiationneeded', lambda event: calls.append(('once', event.type, None)))
    removed = pc.on('negotiationneeded', lambda event: calls.append(('removed', None, None)))
    pc.off('negotiationneeded', removed)

    pc.add_transceiver(webrtc.MediaType.audio)
    await wait_for_event(pc, 'negotiationneeded')

    assert ('decorated', 'negotiationneeded', True) in calls
    assert ('once', 'negotiationneeded', None) in calls
    assert all(name != 'removed' for name, _, _ in calls)
    pc.close()


@pytest.mark.asyncio
async def test_async_handlers_run_as_tasks():
    pc = webrtc.RTCPeerConnection()
    done = asyncio.get_running_loop().create_future()

    @pc.on('negotiationneeded')
    async def handler(event):
        await asyncio.sleep(0)
        done.set_result(event.type)

    pc.create_data_channel('events')
    assert await asyncio.wait_for(done, 5) == 'negotiationneeded'
    pc.close()


def test_unknown_event_and_no_loop():
    pc = webrtc.RTCPeerConnection()
    with pytest.raises(ValueError):
        pc.on('nosuchevent', lambda event: None)
    # handlers are called on the loop they were registered from
    with pytest.raises(RuntimeError):
        pc.on('track', lambda event: None)
    pc.close()


@pytest.mark.asyncio
async def test_signaling_state_changes_with_its_event():
    pc = webrtc.RTCPeerConnection()
    states = []
    pc.on('signalingstatechange', lambda event: states.append(pc.signaling_state))
    pc.add_transceiver(webrtc.MediaType.audio)

    await pc.set_local_description()
    await pc.set_local_description({'type': 'rollback'})
    await asyncio.sleep(0.1)

    assert states == [webrtc.RTCSignalingState.have_local_offer, webrtc.RTCSignalingState.stable]
    pc.close()


@pytest.mark.asyncio
async def test_closed_connection_emits_nothing():
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    events = []
    for name in ('connectionstatechange', 'iceconnectionstatechange', 'signalingstatechange'):
        caller.on(name, lambda event: events.append(event.type))

    caller.create_data_channel('media')
    await connect(caller, callee)
    events.clear()
    caller.close()
    callee.close()
    await asyncio.sleep(0.3)

    assert events == []
    assert caller.connection_state == webrtc.RTCPeerConnectionState.closed


@pytest.mark.asyncio
async def test_ice_candidates_and_end_of_candidates():
    pc = webrtc.RTCPeerConnection()
    candidates = []
    done = asyncio.get_running_loop().create_future()

    @pc.on('icecandidate')
    def on_candidate(event):
        candidates.append(event.candidate)
        if event.candidate is None:
            done.set_result(None)

    pc.add_transceiver(webrtc.MediaType.audio)
    await pc.set_local_description()
    await asyncio.wait_for(done, 10)

    gathered = [c for c in candidates if c is not None and c.candidate]
    assert gathered and all(c.type is not None for c in gathered), candidates
    # every transport ends its candidates with an empty one, before the final None
    assert any(c is not None and c.candidate == '' for c in candidates), candidates
    assert 'a=end-of-candidates' in pc.local_description.sdp, pc.local_description.sdp
    pc.close()


@pytest.mark.asyncio
async def test_ice_transport_candidates_parameters_and_role():
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    caller.create_data_channel('ice')
    await caller.set_local_description()
    ice = caller.sctp.transport.ice_transport
    # the role is known once an answer is applied
    assert ice.role == webrtc.RTCIceRole.unknown
    assert ice.get_remote_parameters() is None

    await connect(caller, callee)
    await asyncio.sleep(0.2)
    assert ice.role == webrtc.RTCIceRole.controlling
    local, remote = ice.get_local_parameters(), ice.get_remote_parameters()
    assert isinstance(local, webrtc.RTCIceParameters) and local.username_fragment and local.password
    assert remote.username_fragment == callee.sctp.transport.ice_transport.get_local_parameters().username_fragment
    assert ice.get_local_candidates() and all(c.candidate for c in ice.get_local_candidates())
    assert {c.candidate for c in ice.get_remote_candidates()} <= {
        c.candidate for c in callee.sctp.transport.ice_transport.get_local_candidates()
    }
    caller.close()
    callee.close()


@pytest.mark.asyncio
async def test_close_keeps_ice_gathering_state():
    pc = webrtc.RTCPeerConnection()
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    await pc.set_local_description()
    ice = transceiver.sender.transport.ice_transport
    state = ice.gathering_state
    pc.close()
    # closing closes the transport, it doesn't complete gathering
    assert ice.state == webrtc.RTCIceTransportState.closed
    assert ice.gathering_state == state


@pytest.mark.asyncio
async def test_descriptions_change_with_signaling_events():
    pc1, pc2 = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    await pc1.set_local_description(await pc1.create_offer())
    seen = []
    pc1.on(
        'signalingstatechange',
        lambda event: seen.append((pc1.signaling_state, pc1.pending_local_description, pc1.pending_remote_description)),
    )
    # an offer in have-local-offer rolls the local one back first
    await pc1.set_remote_description(await pc2.create_offer())
    await asyncio.sleep(0.05)
    (rolled_back, *_), (received, *_) = seen
    assert rolled_back == webrtc.RTCSignalingState.stable and seen[0][1:] == (None, None)
    assert received == webrtc.RTCSignalingState.have_remote_offer and seen[1][1] is None
    assert seen[1][2].type == webrtc.RTCSdpType.offer
    pc1.close()
    pc2.close()


@pytest.mark.asyncio
async def test_restart_ice_before_negotiation_needs_nothing():
    pc = webrtc.RTCPeerConnection()
    events = []
    pc.on('negotiationneeded', lambda event: events.append(event))
    pc.restart_ice()
    await asyncio.sleep(0.1)
    assert events == []
    pc.close()
