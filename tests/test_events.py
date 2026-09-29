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
from tests.helpers import QUIET_PERIOD, connect, wait_for_event


@pytest.mark.asyncio
async def test_on_decorator_once_and_off(pc):
    """Handlers registered with the decorator and once are called, a handler removed with off isn't"""
    calls = []

    @pc.on('negotiationneeded')
    def decorated(event):
        calls.append(('decorated', event.type, event.target is pc))

    def once(event):
        calls.append(('once', event.type))

    def removed(event):
        calls.append(('removed',))

    pc.once('negotiationneeded', once)
    pc.on('negotiationneeded', removed)
    pc.off('negotiationneeded', removed)

    pc.add_transceiver(webrtc.MediaType.audio)
    await wait_for_event(pc, 'negotiationneeded')

    assert ('decorated', 'negotiationneeded', True) in calls
    assert ('once', 'negotiationneeded') in calls
    assert ('removed',) not in calls


@pytest.mark.asyncio
async def test_async_handlers_run_as_tasks(pc):
    """A coroutine function handler is run as a task on the loop"""
    done = asyncio.get_running_loop().create_future()

    @pc.on('negotiationneeded')
    async def handler(event):
        await asyncio.sleep(0)
        if not done.done():
            done.set_result(event.type)

    pc.create_data_channel('events')
    assert await asyncio.wait_for(done, 5) == 'negotiationneeded'


def test_unknown_event(pc):
    """Registering a handler of an event the object doesn't have is a ValueError"""
    with pytest.raises(ValueError):
        pc.on('nosuchevent', lambda event: None)


def test_handlers_need_a_running_loop(pc):
    """Handlers are called on the loop they were registered from, so registering needs a running loop"""
    with pytest.raises(RuntimeError):
        pc.on('track', lambda event: None)


@pytest.mark.asyncio
async def test_signaling_state_changes_with_its_event(pc):
    """Every signalingstatechange event sees its state, and comes before the operation that changed it resolves"""
    states = []

    def on_change(event):
        states.append(pc.signaling_state)

    pc.on('signalingstatechange', on_change)
    pc.add_transceiver(webrtc.MediaType.audio)

    await pc.set_local_description()
    assert states == [webrtc.RTCSignalingState.have_local_offer]
    await pc.set_local_description({'type': 'rollback'})
    assert states == [webrtc.RTCSignalingState.have_local_offer, webrtc.RTCSignalingState.stable]


@pytest.mark.asyncio
async def test_closed_connection_emits_nothing(caller, callee):
    """Closing a connection changes its states without emitting their events"""
    events = []

    def on_event(event):
        events.append(event.type)

    for name in ('connectionstatechange', 'iceconnectionstatechange', 'signalingstatechange'):
        caller.on(name, on_event)

    caller.create_data_channel('media')
    await connect(caller, callee)
    events.clear()
    caller.close()
    callee.close()
    await asyncio.sleep(QUIET_PERIOD)

    assert events == []
    assert caller.connection_state == webrtc.RTCPeerConnectionState.closed


@pytest.mark.asyncio
async def test_ice_candidates_and_end_of_candidates(pc):
    """Candidates are parsed, each transport ends with an empty one, and the final None adds a=end-of-candidates"""
    candidates = []

    def on_candidate(event):
        candidates.append(event.candidate)

    pc.on('icecandidate', on_candidate)
    gathered = wait_for_event(pc, 'icecandidate', predicate=lambda event: event.candidate is None)
    pc.add_transceiver(webrtc.MediaType.audio)
    await pc.set_local_description()
    await gathered

    host = [c for c in candidates if c is not None and c.candidate]
    assert host and all(c.type is not None for c in host), candidates
    assert any(c is not None and c.candidate == '' for c in candidates), candidates
    assert 'a=end-of-candidates' in pc.local_description.sdp, pc.local_description.sdp


@pytest.mark.asyncio
async def test_descriptions_change_with_signaling_events(caller, callee):
    """An offer received in have-local-offer rolls back first: each signalingstatechange sees its descriptions"""
    await caller.set_local_description(await caller.create_offer())
    seen = []

    def on_change(event):
        seen.append(
            {
                'state': caller.signaling_state,
                'local': caller.pending_local_description,
                'remote': caller.pending_remote_description,
            }
        )

    caller.on('signalingstatechange', on_change)
    await caller.set_remote_description(await callee.create_offer())

    rolled_back, received = seen
    assert rolled_back == {'state': webrtc.RTCSignalingState.stable, 'local': None, 'remote': None}
    assert received['state'] == webrtc.RTCSignalingState.have_remote_offer
    assert received['local'] is None
    assert received['remote'].type == webrtc.RTCSdpType.offer


@pytest.mark.asyncio
async def test_restart_ice_before_negotiation_needs_nothing(pc):
    """restart_ice before the first negotiation doesn't fire negotiationneeded"""
    events = []
    pc.on('negotiationneeded', events.append)
    pc.restart_ice()
    await asyncio.sleep(QUIET_PERIOD)
    assert events == []


def test_objects_used_from_another_loop_see_their_events():
    """Once its first loop is closed, an object is updated on the loop of its handlers"""
    objects = {}

    async def first():
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        channel = caller.create_data_channel('loops')
        opened = wait_for_event(channel, 'open')
        await connect(caller, callee)
        await opened
        objects.update(caller=caller, callee=callee, channel=channel)

    async def second():
        channel = objects['channel']
        closed = wait_for_event(channel, 'close')
        objects['callee'].close()
        await closed
        assert channel.ready_state == webrtc.RTCDataChannelState.closed
        objects['caller'].close()

    asyncio.run(first())
    asyncio.run(second())
