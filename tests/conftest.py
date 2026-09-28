#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import pytest

import webrtc


@pytest.fixture
def rtc_peer_connection(request):
    pc = webrtc.RTCPeerConnection()

    def close_pc():
        pc.close()

    request.addfinalizer(close_pc)

    return pc


pc = caller = callee = callee2 = rtc_peer_connection


@pytest.fixture
def create_pc(request):
    """Creates connections with a configuration, closed after the test"""

    def create(configuration=None):
        pc = webrtc.RTCPeerConnection(configuration)
        request.addfinalizer(pc.close)
        return pc

    return create


def get_stream(constraints, request):
    stream = webrtc.get_user_media(**constraints)

    def stop_tracks():
        for track in stream.get_tracks():
            track.stop()

    request.addfinalizer(stop_tracks)

    return stream


@pytest.fixture
def audio_stream(request):
    return get_stream({'audio': True}, request)


audio_stream2 = audio_stream


@pytest.fixture
def video_stream(request):
    return get_stream({'audio': False, 'video': True}, request)
