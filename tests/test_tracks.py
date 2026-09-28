#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Remote tracks: their ids and labels, and ending with their transceiver."""

import asyncio

import pytest

import webrtc
from tests.helpers import exchange_offer_answer, wait_for_event


@pytest.mark.asyncio
async def test_remote_tracks_have_their_own_id_and_label():
    caller = webrtc.RTCPeerConnection()
    callees = [webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()]
    caller.add_transceiver(webrtc.MediaType.audio)
    caller.add_transceiver(webrtc.MediaType.video)
    await caller.set_local_description()

    tracks = []
    for callee in callees:
        await callee.set_remote_description(caller.local_description)
        tracks.append([t.receiver.track for t in callee.get_transceivers()])

    assert [t.label for t in tracks[0]] == ['remote audio', 'remote video']
    # every connection receiving the same description has other tracks
    assert {t.id for t in tracks[0]}.isdisjoint(t.id for t in tracks[1])
    assert tracks[0][0].clone().label == 'remote audio'
    for pc in (caller, *callees):
        pc.close()


@pytest.mark.asyncio
async def test_stopped_transceiver_ends_the_track_with_its_event():
    pc = webrtc.RTCPeerConnection()
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    track = transceiver.receiver.track
    ended = wait_for_event(track, 'ended')

    transceiver.stop()
    # as in a browser, the track ends when its event is delivered
    assert track.ready_state == webrtc.MediaStreamTrackState.live
    await ended
    assert track.ready_state == webrtc.MediaStreamTrackState.ended
    pc.close()


@pytest.mark.asyncio
async def test_rollback_ends_the_track_of_a_removed_transceiver():
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    caller.add_transceiver(webrtc.MediaType.audio)
    await caller.set_local_description()
    await callee.set_remote_description(caller.local_description)
    [transceiver] = callee.get_transceivers()

    await callee.set_remote_description({'type': 'rollback'})
    # the track is first used after it ended: its ended event is still delivered
    track = transceiver.receiver.track
    assert track.ready_state == webrtc.MediaStreamTrackState.live
    await wait_for_event(track, 'ended')
    assert track.ready_state == webrtc.MediaStreamTrackState.ended
    caller.close()
    callee.close()


@pytest.mark.asyncio
async def test_remove_track_of_another_connection():
    pc, other = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    sender = other.add_transceiver(webrtc.MediaType.audio).sender
    with pytest.raises(webrtc.InvalidAccessError):
        pc.remove_track(sender)
    pc.close()
    other.close()


def test_peer_reflexive_candidate_hides_its_address():
    init = {
        'candidate': 'candidate:1 1 udp 1853504767 redacted-ip.invalid 62341 typ prflx generation 0 ufrag a/b+',
        'sdp_mid': '0',
    }
    candidate = webrtc.RTCIceCandidate._peer_reflexive(init)
    assert candidate.candidate == ''
    assert candidate.type == webrtc.RTCIceCandidateType.prflx
    assert candidate.address is None
    assert candidate.port == 62341

    # an ufrag may have "/" and "+"
    host = webrtc.RTCIceCandidate('candidate:1 1 udp 2121940223 ::1 60645 typ host ufrag /h4t+', sdp_mid='0')
    assert host.type == webrtc.RTCIceCandidateType.host


@pytest.mark.asyncio
async def test_track_event_when_remote_streams_change():
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    events = []
    callee.on('track', lambda event: events.append(event))
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer_answer(caller, callee)
    assert len(events) == 1 and events[0].streams == []

    stream = webrtc.MediaStream()
    transceiver.sender.set_streams(stream)
    await exchange_offer_answer(caller, callee)
    await asyncio.sleep(0.05)
    # the same track, now associated with the stream
    assert len(events) == 2
    assert [s.id for s in events[1].streams] == [stream.id]
    assert events[1].track == events[0].track
    caller.close()
    callee.close()


@pytest.mark.asyncio
async def test_replace_track_is_chained_after_remove_track():
    pc = webrtc.RTCPeerConnection()
    first, second = (webrtc.get_user_media(audio=True).get_tracks()[0] for _ in range(2))
    sender = pc.add_track(first)
    replaced = asyncio.ensure_future(sender.replace_track(second))
    await asyncio.sleep(0)
    pc.remove_track(sender)
    await replaced
    # replaced after the removal, in a later task
    assert sender.track == second
    pc.close()
