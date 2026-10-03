#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#
#  Ported from web-platform-tests, Copyright © web-platform-tests contributors,
#  under the 3-Clause BSD License in the THIRD_PARTY_LICENSES.md file in the root of the project.
#

from __future__ import annotations

import pytest

import webrtc
from tests.helpers import mistyped


def test_1(pc: webrtc.RTCPeerConnection) -> None:
    """add_transceiver with string argument as invalid kind should throw TypeError."""
    assert hasattr(pc, 'add_transceiver')

    with pytest.raises(TypeError):
        pc.add_transceiver(mistyped('invalid'))


def _create_and_test_transceiver(pc: webrtc.RTCPeerConnection, kind: webrtc.MediaType) -> None:
    assert hasattr(pc, 'add_transceiver')

    transceiver = pc.add_transceiver(kind)

    assert isinstance(transceiver, webrtc.RTCRtpTransceiver), 'Expect transceiver to be instance of RTCRtpTransceiver'

    assert transceiver.mid is None
    assert transceiver.stopped is False
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendrecv
    assert transceiver.current_direction is None

    assert [transceiver] == pc.get_transceivers(), (
        "Expect added transceiver to be the only element in connection's list of transceivers"
    )

    sender = transceiver.sender

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'

    assert sender.track is None

    assert [sender] == pc.get_senders(), "Expect added sender to be the only element in connection's list of senders"

    receiver = transceiver.receiver
    assert isinstance(receiver, webrtc.RTCRtpReceiver)

    track = receiver.track
    assert isinstance(track, webrtc.MediaStreamTrack)

    assert track.kind == kind
    assert track.ready_state == webrtc.MediaStreamTrackState.live

    assert [receiver] == pc.get_receivers(), (
        "Expect added receiver to be the only element in connection's list of receivers"
    )


def test_2(pc: webrtc.RTCPeerConnection) -> None:
    """add_transceiver('audio') should return an audio transceiver."""
    _create_and_test_transceiver(pc, webrtc.MediaType.audio)


def test_3(pc: webrtc.RTCPeerConnection) -> None:
    """add_transceiver('video') should return a video transceiver."""
    _create_and_test_transceiver(pc, webrtc.MediaType.video)


def test_4(pc: webrtc.RTCPeerConnection) -> None:
    """add_transceiver with direction inactive should have result transceiver.direction be the same."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.inactive)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.inactive


def test_5() -> None:
    """An init with an invalid direction can't be created, so add_transceiver can't get one."""
    with pytest.raises(ValueError, match='not a valid RTCRtpTransceiverDirection'):
        webrtc.RTCRtpTransceiverInit(direction=mistyped('invalid'))


def test_6(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_transceiver(track) should have result with sender.track be given track."""
    track, *_ = audio_stream.get_tracks()
    transceiver = pc.add_transceiver(track)
    sender, receiver = transceiver.sender, transceiver.receiver

    assert isinstance(sender, webrtc.RTCRtpSender), 'Expect sender to be instance of RTCRtpSender'
    assert isinstance(receiver, webrtc.RTCRtpReceiver), 'Expect receiver to be instance of RTCRtpReceiver'

    assert sender.track == track, 'Expect sender.track should be the track that is added'

    receiver_track = receiver.track

    assert isinstance(receiver_track, webrtc.MediaStreamTrack), (
        'Expect receiver.track to be instance of MediaStreamTrack'
    )
    assert receiver_track.kind == webrtc.MediaType.audio, (
        "receiver.track should have the same kind as added track's kind"
    )

    assert receiver_track.ready_state == webrtc.MediaStreamTrackState.live

    assert [transceiver] == pc.get_transceivers(), (
        "Expect added transceiver to be the only element in connection's list of transceivers"
    )

    assert [sender] == pc.get_senders(), "Expect added sender to be the only element in connection's list of senders"

    assert [receiver] == pc.get_receivers(), (
        "Expect added receiver to be the only element in connection's list of receivers"
    )


def test_7(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """add_transceiver(track) multiple times should create multiple transceivers."""
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


@pytest.mark.parametrize('kind', [webrtc.MediaType.video, webrtc.MediaType.audio])
def test_8(pc: webrtc.RTCPeerConnection, kind: webrtc.MediaType) -> None:
    """add_transceiver with rid containing invalid non-alphanumeric characters should throw ValueError."""
    encodings = [webrtc.RTCRtpEncodingParameters(rid='@Invalid!')]
    init = webrtc.RTCRtpTransceiverInit(send_encodings=encodings)

    with pytest.raises(ValueError, match='is not a valid rid'):
        pc.add_transceiver(kind, init)


@pytest.mark.parametrize('kind', [webrtc.MediaType.video, webrtc.MediaType.audio])
def test_9(pc: webrtc.RTCPeerConnection, kind: webrtc.MediaType) -> None:
    """add_transceiver with rid longer than 16 characters should throw ValueError."""
    encodings = [webrtc.RTCRtpEncodingParameters(rid='a' * 17)]
    init = webrtc.RTCRtpTransceiverInit(send_encodings=encodings)

    with pytest.raises(ValueError, match='is not a valid rid'):
        pc.add_transceiver(kind, init)


@pytest.mark.parametrize('kind', [webrtc.MediaType.video, webrtc.MediaType.audio])
def test_10(pc: webrtc.RTCPeerConnection, kind: webrtc.MediaType) -> None:
    """add_transceiver with valid rid value should succeed."""
    encodings = [webrtc.RTCRtpEncodingParameters(rid='foo')]
    init = webrtc.RTCRtpTransceiverInit(send_encodings=encodings)
    pc.add_transceiver(kind, init)


def test_11(pc: webrtc.RTCPeerConnection) -> None:
    """add_transceiver with valid sendEncodings should succeed."""
    # dtx and ptime from the original test aren't supported by RTCRtpEncodingParameters
    encodings = [webrtc.RTCRtpEncodingParameters(active=False, max_bitrate=8, max_framerate=25, rid='foo')]
    init = webrtc.RTCRtpTransceiverInit(send_encodings=encodings)
    pc.add_transceiver(webrtc.MediaType.video, init)


def test_12(pc: webrtc.RTCPeerConnection) -> None:
    """add_transceiver with direction sendonly should have result transceiver.direction be the same."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.sendonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendonly


def test_13(pc: webrtc.RTCPeerConnection) -> None:
    """add_transceiver with multiple rid values should succeed."""
    encodings = [webrtc.RTCRtpEncodingParameters(rid='a'), webrtc.RTCRtpEncodingParameters(rid='b')]
    init = webrtc.RTCRtpTransceiverInit(send_encodings=encodings)
    pc.add_transceiver(webrtc.MediaType.video, init)
