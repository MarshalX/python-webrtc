#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Remote tracks: their ids and labels, their events and streams, and ending with their transceiver."""

from __future__ import annotations

import asyncio
import gc
import weakref

import pytest

import webrtc
from tests.helpers import (
    QUIET_PERIOD,
    collect,
    connect,
    exchange_offer,
    exchange_offer_answer,
    wait_for_event,
    wait_until_unmuted,
)


@pytest.mark.asyncio
async def test_remote_tracks_have_their_own_id_and_label(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, callee2: webrtc.RTCPeerConnection
) -> None:
    """Every connection receiving the same description has other tracks, labeled by their kind."""
    caller.add_transceiver(webrtc.MediaType.audio)
    caller.add_transceiver(webrtc.MediaType.video)
    await caller.set_local_description()

    tracks: list[list[webrtc.MediaStreamTrack]] = []
    assert caller.local_description is not None
    for pc in (callee, callee2):
        await pc.set_remote_description(caller.local_description)
        tracks.append([t.receiver.track for t in pc.get_transceivers()])

    assert [t.label for t in tracks[0]] == ['remote audio', 'remote video']
    assert {t.id for t in tracks[0]}.isdisjoint(t.id for t in tracks[1])
    assert tracks[0][0].clone().label == 'remote audio'


@pytest.mark.asyncio
async def test_stopped_transceiver_ends_the_track_with_its_event(pc: webrtc.RTCPeerConnection) -> None:
    """The track of a stopped transceiver ends when its ended event is delivered."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    track = transceiver.receiver.track
    ended = wait_for_event(track, 'ended')

    transceiver.stop()
    assert track.ready_state == webrtc.MediaStreamTrackState.live
    await ended
    assert track.ready_state == webrtc.MediaStreamTrackState.ended


@pytest.mark.asyncio
async def test_ended_track_is_not_kept_by_its_handlers(
    pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """Ended track fires no events and isn't kept alive."""
    calls: list[str] = []
    remote = pc.add_transceiver(webrtc.MediaType.audio)
    remote_track = remote.receiver.track
    remote_track.on('mute', lambda event: calls.append(event.type))
    ended = wait_for_event(remote_track, 'ended')
    remote.stop()
    await ended
    assert remote_track.listeners('mute') != []
    ref = weakref.ref(remote_track)
    del remote_track
    # the task step the event woke still holds the event, and so the track
    await asyncio.sleep(0)
    collect()
    assert ref() is None

    local_track = audio_stream.get_tracks()[0]
    local_track.on('mute', lambda event: calls.append(event.type))
    local_track.stop()
    local_track.on('ended', lambda event: calls.append(event.type))
    assert local_track.listeners('ended') != []
    await asyncio.sleep(QUIET_PERIOD)
    assert calls == []


@pytest.mark.asyncio
async def test_rollback_ends_the_track_of_a_removed_transceiver(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A rollback ends the track of the transceiver it removes, with its event, even if first used after that."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer(caller, callee)
    [transceiver] = callee.get_transceivers()

    await callee.set_remote_description(webrtc.RTCSessionDescriptionInit('rollback'))
    track = transceiver.receiver.track
    assert track.ready_state == webrtc.MediaStreamTrackState.live
    await wait_for_event(track, 'ended')
    assert track.ready_state == webrtc.MediaStreamTrackState.ended


def test_remove_track_of_another_connection(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """A connection can't remove a sender of another one."""
    sender = callee.add_transceiver(webrtc.MediaType.audio).sender
    with pytest.raises(webrtc.InvalidAccessError):
        caller.remove_track(sender)


@pytest.mark.asyncio
async def test_remove_track_of_a_negotiated_stopped_transceiver(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Removing a stopped sender does nothing."""
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer_answer(caller, callee)
    transceiver.stop()
    await exchange_offer_answer(caller, callee)
    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.stopped
    caller.remove_track(transceiver.sender)


@pytest.mark.asyncio
async def test_remove_track_of_a_rolled_back_transceiver(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Removing a rolled back sender does nothing."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer(caller, callee)
    [transceiver] = callee.get_transceivers()
    await callee.set_remote_description(webrtc.RTCSessionDescriptionInit('rollback'))
    callee.remove_track(transceiver.sender)


@pytest.mark.asyncio
async def test_track_event_when_remote_streams_change(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A track event fires again for the same track when its remote streams change, before the description is set."""
    events: list[webrtc.RTCTrackEvent] = []
    callee.on('track', events.append)
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer_answer(caller, callee)
    assert len(events) == 1
    assert events[0].streams == []

    stream = webrtc.MediaStream()
    transceiver.sender.set_streams(stream)
    await exchange_offer_answer(caller, callee)
    assert len(events) == 2
    assert [s.id for s in events[1].streams] == [stream.id]
    assert events[1].track == events[0].track


@pytest.mark.asyncio
async def test_replace_track_is_chained_after_remove_track(
    pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream, audio_stream2: webrtc.MediaStream
) -> None:
    """replace_track is an operation of the connection: called before remove_track, it replaces the track after it."""
    (first,), (second,) = audio_stream.get_tracks(), audio_stream2.get_tracks()
    sender = pc.add_track(first)
    replaced = asyncio.ensure_future(sender.replace_track(second))
    await asyncio.sleep(0)  # let the task start
    pc.remove_track(sender)
    await replaced
    assert sender.track == second


@pytest.mark.asyncio
async def test_remote_track_mute_and_stream_events(
    *,
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    audio_stream: webrtc.MediaStream,
    video_stream: webrtc.MediaStream,
) -> None:
    """A remote track that no longer receives media is removed from its stream and muted."""
    (audio,), (video,) = audio_stream.get_tracks(), video_stream.get_tracks()
    stream = webrtc.MediaStream([audio, video])
    caller.add_track(audio, stream)
    transceiver = caller.add_transceiver(video, webrtc.RTCRtpTransceiverInit(streams=[stream]))
    events: list[webrtc.RTCTrackEvent] = []
    callee.on('track', events.append)
    await connect(caller, callee)

    remote_stream = events[0].streams[0]
    assert len(remote_stream.get_tracks()) == 2
    removed = wait_for_event(remote_stream, 'removetrack')
    remote_video = next(e.track for e in events if e.track.kind == webrtc.MediaType.video)
    # a track that is muted already doesn't fire mute
    await wait_until_unmuted(remote_video)
    muted = wait_for_event(remote_video, 'mute')

    transceiver.direction = webrtc.RTCRtpTransceiverDirection.inactive
    await exchange_offer(caller, callee)

    removed_event = await removed
    assert isinstance(removed_event, webrtc.MediaStreamTrackEvent)
    assert removed_event.track == remote_video
    await muted
    assert remote_video.muted


def test_remote_track_keeps_its_id_after_close(pc: webrtc.RTCPeerConnection) -> None:
    """A kept remote track keeps its id."""
    track = pc.add_transceiver(webrtc.MediaType.audio).receiver.track
    before = track.id
    pc.close()
    gc.collect()
    _ = pc.get_transceivers()
    assert (track.id, track.label) == (before, 'remote audio')


@pytest.mark.parametrize(('kind', 'hint'), [(webrtc.MediaType.audio, 'speech'), (webrtc.MediaType.video, 'detail')])
def test_clone_copies_enabled_and_content_hint(pc: webrtc.RTCPeerConnection, kind: webrtc.MediaType, hint: str) -> None:
    """Clones keep enabled and content hint."""
    track = pc.add_transceiver(kind).receiver.track
    track.enabled = False
    track.content_hint = hint
    clones = [track.clone(), webrtc.MediaStream([track]).clone().get_tracks()[0]]
    assert [(clone.enabled, clone.content_hint) for clone in clones] == [(False, hint)] * 2
