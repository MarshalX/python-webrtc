#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import gc
import threading

import pytest

import webrtc
from webrtc.utils import events


def pytest_addoption(parser):
    parser.addoption('--gc-on-emit', action='store_true', help='collect garbage on events of libwebrtc threads')
    parser.addoption('--stress', action='store_true', help='run the long stress tests too')


def pytest_collection_modifyitems(config, items):
    if config.getoption('--stress'):
        return
    skip = pytest.mark.skip(reason='a long stress test, run with --stress')
    for item in items:
        if 'stress' in item.keywords:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line('markers', 'stress: a long stress test, run with --stress')
    if not config.getoption('--gc-on-emit'):
        return
    # the collector runs on libwebrtc threads, as it may whenever they emit: whatever it releases must not block them
    emit = events._Listeners.__call__

    def collecting_emit(self, name, *args):
        if threading.current_thread() is not threading.main_thread():
            gc.collect()
        emit(self, name, *args)

    events._Listeners.__call__ = collecting_emit


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
