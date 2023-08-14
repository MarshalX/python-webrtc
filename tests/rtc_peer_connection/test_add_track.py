#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import pytest

import webrtc

from tests.helpers import exchange_offer_answer


def test_1(pc, audio_stream):
    """addTrack when pc is closed should throw PythonWebRTCException with invalid state"""
    track, *_ = audio_stream.get_audio_tracks()
    pc.close()

    with pytest.raises(webrtc.PythonWebRTCException):
        # invalid pc state
        pc.add_track(track, audio_stream)


def test_2(pc, audio_stream):
    """add_track with single track argument and no stream should succeed"""
    track, *_ = audio_stream.get_tracks()

    sender = pc.add_track(track)

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert track == sender.track, 'Expect sender\'s track to be the added track'

    transceivers = pc.get_transceivers()
    assert len(transceivers) == 1, 'Expect only one transceiver with sender added'

    transceiver, *_ = transceivers
    assert transceiver.sender == sender, 'Expect only one sender with given track added'

    assert [sender] == pc.get_senders()

    receiver = transceiver.receiver
    assert receiver.track.kind == webrtc.MediaType.audio

    assert [receiver] == pc.get_receivers(), 'Expect only one receiver associated with transceiver added'


def test_3(pc, audio_stream):
    """add_track with single track argument and single stream should succeed"""
    track, *_ = audio_stream.get_tracks()

    sender = pc.add_track(track, audio_stream)

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert sender.track == track, 'Expect sender\'s track to be the added track'


def test_4(pc, audio_stream):
    """add_track with single track argument and multiple streams should succeed"""
    track, *_ = audio_stream.get_tracks()

    # FIXME
    return

    stream2 = webrtc.MediaStream(track)
    sender = pc.add_track(track, [audio_stream, stream2])

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert sender.track == track, 'Expect sender\'s track to be the added track'


def test_5(pc, audio_stream):
    """Adding the same track multiple times should throw RTCException"""
    track, *_ = audio_stream.get_tracks()

    pc.add_track(track, audio_stream)

    with pytest.raises(webrtc.RTCException):
        pc.add_track(track, audio_stream)


def test_6(pc, audio_stream):
    """add_track with existing sender with None track, same kind, and recvonly direction should reuse sender"""
    init = webrtc.RtpTransceiverInit(direction=webrtc.TransceiverDirection.recvonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.sender.track is None
    assert transceiver.direction == webrtc.TransceiverDirection.recvonly

    track, *_ = audio_stream.get_tracks()
    sender = pc.add_track(track)

    assert sender == transceiver.sender
    assert sender.track == track
    assert transceiver.direction == webrtc.TransceiverDirection.sendrecv
    assert [sender] == pc.get_senders()


def test_7(pc, audio_stream):
    """add_track with existing sender that has not been used to send should reuse the sender"""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    assert transceiver.sender.track is None
    assert transceiver.direction == webrtc.TransceiverDirection.sendrecv

    track, *_ = audio_stream.get_tracks()
    sender = pc.add_track(track)

    assert sender.track == track
    assert sender == transceiver.sender


@pytest.mark.asyncio
async def test_8(caller, callee, audio_stream):
    """add_track with existing sender that has been used to send should create new sender"""
    track, *_ = audio_stream.get_tracks()
    transceiver = caller.add_transceiver(track)

    await exchange_offer_answer(caller, callee)

    assert transceiver.current_direction == webrtc.TransceiverDirection.sendonly

    # TODO when remove track method will be ready
    return
    caller.remove_track(transceiver.sender)

    # .... and more


def test_9(pc, audio_stream):
    """add_track with existing sender with null track, different kind,
    and recvonly direction should create new sender"""
    init = webrtc.RtpTransceiverInit(direction=webrtc.TransceiverDirection.recvonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.video, init)

    assert transceiver.sender.track is None
    assert transceiver.direction == webrtc.TransceiverDirection.recvonly

    track, *_ = audio_stream.get_tracks()
    sender = pc.add_track(track)

    assert sender.track == track
    assert sender != transceiver.sender

    senders = pc.get_senders()

    assert len(senders) == 2, 'Expect 2 senders added to connection'
    assert sender in senders, 'Expect senders list to include sender'
    assert transceiver.sender in senders, 'Expect senders list to include first transceiver\'s sender'


@pytest.mark.asyncio
async def test_10(caller, callee, audio_stream, audio_stream2):
    """Adding more tracks does not generate more candidates if bundled"""
    track, *_ = audio_stream.get_tracks()
    transceiver = caller.add_transceiver(track)

    await exchange_offer_answer(caller, callee)

    assert transceiver.current_direction == webrtc.TransceiverDirection.sendonly

    # TODO need to wait for icegatheringstatechange with complete event!

    second_track, *_ = audio_stream2.get_tracks()

    # TODO onicecandidate event should not be occurred

    caller.add_track(second_track)

    await exchange_offer_answer(caller, callee)

    first_transceiver, second_transceiver, *_ = caller.get_transceivers()
    assert first_transceiver.receiver.transport == second_transceiver.receiver.transport
    assert first_transceiver.sender.transport == second_transceiver.sender.transport
