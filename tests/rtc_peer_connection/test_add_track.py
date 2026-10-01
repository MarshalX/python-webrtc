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
from tests.helpers import exchange_offer_answer, wait_for_ice_gathering_complete


def test_1(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """AddTrack when pc is closed should throw PythonWebRTCException with invalid state."""
    track, *_ = audio_stream.get_audio_tracks()
    pc.close()

    with pytest.raises(webrtc.PythonWebRTCException):
        pc.add_track(track, audio_stream)


def test_2(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_track with single track argument and no stream should succeed."""
    track, *_ = audio_stream.get_tracks()

    sender = pc.add_track(track)

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert track == sender.track, "Expect sender's track to be the added track"

    transceivers = pc.get_transceivers()
    assert len(transceivers) == 1, 'Expect only one transceiver with sender added'

    transceiver, *_ = transceivers
    assert transceiver.sender == sender, 'Expect only one sender with given track added'

    assert [sender] == pc.get_senders()

    receiver = transceiver.receiver
    assert receiver.track.kind == webrtc.MediaType.audio

    assert [receiver] == pc.get_receivers(), 'Expect only one receiver associated with transceiver added'


def test_3(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_track with single track argument and single stream should succeed."""
    track, *_ = audio_stream.get_tracks()

    sender = pc.add_track(track, audio_stream)

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert sender.track == track, "Expect sender's track to be the added track"


def test_4(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_track with single track argument and multiple streams should succeed."""
    track, *_ = audio_stream.get_tracks()

    stream2 = audio_stream.clone()
    stream2.add_track(track)
    sender = pc.add_track(track, audio_stream, stream2)

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert sender.track == track, "Expect sender's track to be the added track"


def test_5(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """Adding the same track multiple times should throw RTCException."""
    track, *_ = audio_stream.get_tracks()

    pc.add_track(track, audio_stream)

    with pytest.raises(webrtc.RTCException):
        pc.add_track(track, audio_stream)


def test_6(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_track with existing sender with None track, same kind, and recvonly direction should reuse sender."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.recvonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.sender.track is None
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.recvonly

    track, *_ = audio_stream.get_tracks()
    sender = pc.add_track(track)

    assert sender == transceiver.sender
    assert sender.track == track
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendrecv
    assert [sender] == pc.get_senders()


def test_7(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_track with existing sender that has not been used to send should reuse the sender."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    assert transceiver.sender.track is None
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendrecv

    track, *_ = audio_stream.get_tracks()
    sender = pc.add_track(track)

    assert sender.track == track
    assert sender == transceiver.sender


@pytest.mark.asyncio
async def test_8(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """add_track with existing sender that has been used to send should create new sender."""
    track, *_ = audio_stream.get_tracks()
    transceiver = caller.add_transceiver(track)

    await exchange_offer_answer(caller, callee)

    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.sendonly

    caller.remove_track(transceiver.sender)

    await exchange_offer_answer(caller, callee)

    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.recvonly
    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.inactive

    # transceiver.sender is currently not used for sending,
    # but it should not be reused because it has been used for sending before
    sender = caller.add_track(track)

    assert sender is not None
    assert sender != transceiver.sender


def test_9(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_track with existing recvonly sender with null track of a different kind should create new sender."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.recvonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.video, init)

    assert transceiver.sender.track is None
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.recvonly

    track, *_ = audio_stream.get_tracks()
    sender = pc.add_track(track)

    assert sender.track == track
    assert sender != transceiver.sender

    senders = pc.get_senders()

    assert len(senders) == 2, 'Expect 2 senders added to connection'
    assert sender in senders, 'Expect senders list to include sender'
    assert transceiver.sender in senders, "Expect senders list to include first transceiver's sender"


@pytest.mark.asyncio
async def test_10(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    audio_stream: webrtc.MediaStream,
    *,
    audio_stream2: webrtc.MediaStream,
) -> None:
    """Adding more tracks does not generate more candidates if bundled."""
    track, *_ = audio_stream.get_tracks()
    transceiver = caller.add_transceiver(track)

    await exchange_offer_answer(caller, callee)

    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.sendonly

    await wait_for_ice_gathering_complete(caller)
    await wait_for_ice_gathering_complete(callee)

    second_track, *_ = audio_stream2.get_tracks()
    candidates: list[webrtc.RTCIceCandidate | None] = []

    def on_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
        candidates.append(event.candidate)

    caller.on('icecandidate', on_candidate)

    caller.add_track(second_track)

    await exchange_offer_answer(caller, callee)
    await asyncio.sleep(0.1)
    assert len(candidates) == 0, 'Expect no icecandidate events after adding a bundled track'

    first_transceiver, second_transceiver, *_ = caller.get_transceivers()
    assert first_transceiver.receiver.transport == second_transceiver.receiver.transport
    assert first_transceiver.sender.transport == second_transceiver.sender.transport


@pytest.mark.asyncio
async def test_11(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """add_track while set_remote_description(offer) is pending should reuse the transceiver the offer creates."""
    track, *_ = audio_stream.get_tracks()

    caller.add_track(track)
    offer = await caller.create_offer()

    # we do not await here; we want to ensure that the transceiver this creates
    # is untouched by add_track, and that add_track creates _another_ transceiver
    srd_task = asyncio.ensure_future(callee.set_remote_description(offer))
    await asyncio.sleep(0)  # let the task start

    sender = callee.add_track(track)

    await srd_task

    transceivers = callee.get_transceivers()
    assert len(transceivers) == 1, 'Should have 1 transceiver'
    assert transceivers[0].sender == sender, 'The transceiver should be the one added by add_track'
