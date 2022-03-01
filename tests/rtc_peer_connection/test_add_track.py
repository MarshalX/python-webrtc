#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import pytest

import webrtc


def test_on_closed_pc(pc, audio_stream):
    track, *_ = audio_stream.get_audio_tracks()
    pc.close()

    with pytest.raises(webrtc.PythonWebRTCException):
        pc.add_track(track, audio_stream)


def test_sender_creation(pc, audio_stream):
    track, *_ = audio_stream.get_audio_tracks()

    sender = pc.add_track(track, audio_stream)

    assert isinstance(sender, webrtc.RTCRtpSender)


def test_adding_of_the_same_track(pc, audio_stream):
    track, *_ = audio_stream.get_audio_tracks()

    pc.add_track(track, audio_stream)

    with pytest.raises(webrtc.RTCException):
        pc.add_track(track, audio_stream)


def test_sender_and_transceivers(pc, audio_stream):
    track, *_ = audio_stream.get_audio_tracks()

    sender = pc.add_track(track, audio_stream)

    assert isinstance(sender, webrtc.RTCRtpSender)

    assert track == sender.track

    # when we ready in cpp
    transceivers = pc.get_transceivers()
    assert len(transceivers) == 1

    transceiver, *_ = transceivers
    assert transceiver.sender == sender

    assert [sender] == pc.get_senders()

    # assert kind and list of receivers
