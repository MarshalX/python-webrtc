#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import pytest

import webrtc


def test_1(pc):
    """add_transceiver with string argument as invalid kind should throw TypeError"""

    assert hasattr(pc, 'add_transceiver')

    with pytest.raises(TypeError):
        # invalid kind
        pc.add_transceiver('invalid')


def _create_and_test_transceiver(pc, kind):
    assert hasattr(pc, 'add_transceiver')

    transceiver = pc.add_transceiver(kind)

    assert isinstance(transceiver, webrtc.RTCRtpTransceiver), 'Expect transceiver to be instance of RTCRtpTransceiver'

    assert transceiver.mid is None
    assert transceiver.stopped is False
    assert transceiver.direction == webrtc.TransceiverDirection.sendrecv
    assert transceiver.current_direction is None

    assert [
        transceiver
    ] == pc.get_transceivers(), 'Expect added transceiver to be the only element in connection\'s list of transceivers'

    sender = transceiver.sender

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert sender.track is None

    assert [sender] == pc.get_senders(), 'Expect added sender to be the only element in connection\'s list of senders'

    receiver = transceiver.receiver
    assert isinstance(receiver, webrtc.RTCRtpReceiver)

    track = receiver.track
    assert isinstance(track, webrtc.MediaStreamTrack)

    assert track.kind == kind
    assert track.ready_state == webrtc.MediaStreamTrackState.live

    assert [
        receiver
    ] == pc.get_receivers(), 'Expect added receiver to be the only element in connection\'s list of receivers'


def test_2(pc):
    """add_transceiver('audio') should return an audio transceiver"""
    _create_and_test_transceiver(pc, webrtc.MediaType.audio)


def test_3(pc):
    """add_transceiver('video') should return a video transceiver"""
    _create_and_test_transceiver(pc, webrtc.MediaType.video)


def test_4(pc):
    """add_transceiver with direction inactive should have result transceiver.direction be the same"""
    init = webrtc.RtpTransceiverInit(direction=webrtc.TransceiverDirection.inactive)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.direction == webrtc.TransceiverDirection.inactive


def test_5(pc):
    """add_transceiver with invalid direction should throw TypeError"""
    with pytest.raises(TypeError):
        # invalid direction
        init = webrtc.RtpTransceiverInit(direction='invalid')
        pc.add_transceiver(webrtc.MediaType.audio, init)


def test_6(pc, audio_stream):
    """add_transceiver(track) should have result with sender.track be given track"""
    track, *_ = audio_stream.get_tracks()
    transceiver = pc.add_transceiver(track)
    sender, receiver = transceiver.sender, transceiver.receiver

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'
    assert isinstance(receiver, webrtc.RTCRtpReceiver), 'Expect receiver to be instance of RTCRtpReceiver'

    assert sender.track == track, 'Expect sender.track should be the track that is added'

    receiver_track = receiver.track

    assert isinstance(
        receiver_track, webrtc.MediaStreamTrack
    ), 'Expect receiver.track to be instance of MediaStreamTrack'
    assert (
        receiver_track.kind == webrtc.MediaType.audio
    ), 'receiver.track should have the same kind as added track\'s kind'

    assert receiver_track.ready_state == webrtc.MediaStreamTrackState.live

    assert [
        transceiver
    ] == pc.get_transceivers(), 'Expect added transceiver to be the only element in connection\'s list of transceivers'

    assert [sender] == pc.get_senders(), 'Expect added sender to be the only element in connection\'s list of senders'

    assert [
        receiver
    ] == pc.get_receivers(), 'Expect added receiver to be the only element in connection\'s list of receivers'


def test_7(pc, audio_stream):
    """add_transceiver(track) multiple times should create multiple transceivers"""
    track, *_ = audio_stream.get_tracks()
    transceiver1 = pc.add_transceiver(track)
    transceiver2 = pc.add_transceiver(track)

    assert transceiver1 != transceiver2

    sender1 = transceiver1.sender
    sender2 = transceiver2.sender

    assert sender1 != sender2
    assert transceiver1.sender.track == track
    assert transceiver2.sender.track == track

    transceivers = pc.get_transceivers()

    assert len(transceivers) == 2
    assert transceiver1 in transceivers
    assert transceiver2 in transceivers

    senders = pc.get_senders()

    assert len(senders) == 2
    assert sender1 in senders
    assert sender2 in senders


def test_8(pc):
    """add_transceiver with rid containing invalid non-alphanumeric characters should throw RTCException"""
    encodings = [webrtc.RtpEncodingParameters(rid="@Invalid!")]
    init = webrtc.RtpTransceiverInit(send_encodings=encodings)

    # will be changed to TypeError after reworking binding to rtc error?
    with pytest.raises(webrtc.RTCException):
        pc.add_transceiver(webrtc.MediaType.audio, init)


def test_9(pc):
    """add_transceiver with rid longer than 16 characters should throw RTCException"""
    encodings = [webrtc.RtpEncodingParameters(rid="a" * 17)]
    init = webrtc.RtpTransceiverInit(send_encodings=encodings)

    # will be changed to TypeError after reworking binding to rtc error?
    with pytest.raises(webrtc.RTCException):
        pc.add_transceiver(webrtc.MediaType.audio, init)


def test_10(pc):
    """add_transceiver with valid rid value should succeed"""
    encodings = [webrtc.RtpEncodingParameters(rid="foo")]
    init = webrtc.RtpTransceiverInit(send_encodings=encodings)
    pc.add_transceiver(webrtc.MediaType.audio, init)


def test_11(pc):
    """add_transceiver with valid sendEncodings should succeed"""
    encodings = [
        webrtc.RtpEncodingParameters(
            active=False, max_bitrate=1337, max_framerate=30, rid="foo", scale_resolution_down_by=2.0
        )
    ]
    init = webrtc.RtpTransceiverInit(send_encodings=encodings)
    pc.add_transceiver(webrtc.MediaType.audio, init)
