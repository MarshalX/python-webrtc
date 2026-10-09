#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio
import gc
import os
import threading
from typing import TYPE_CHECKING

import pytest

import webrtc
from tests.helpers import release_stranded_candidates
from webrtc.utils import events

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.helpers import CreatePC


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption('--gc-on-emit', action='store_true', help='collect garbage on events of libwebrtc threads')
    parser.addoption('--stress', action='store_true', help='run the long stress tests too')


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption('--stress'):
        return
    skip = pytest.mark.skip(reason='a long stress test, run with --stress')
    for item in items:
        if 'stress' in item.keywords:
            item.add_marker(skip)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line('markers', 'stress: a long stress test, run with --stress')
    # macOS may block the LAN without Local Network permission
    os.environ['WRTC_ALLOW_LOOPBACK'] = '1'
    webrtc.allow_loopback()
    if not config.getoption('--gc-on-emit'):
        return
    # the collector runs on libwebrtc threads, as it may whenever they emit: whatever it releases must not block them
    emit = events._Listeners.__call__

    def collecting_emit(self: events._Listeners, name: str, *args: object) -> None:
        if threading.current_thread() is not threading.main_thread():
            gc.collect()
        emit(self, name, *args)

    events._Listeners.__call__ = collecting_emit


def pytest_runtest_setup() -> None:
    # before each test, so its leak checks don't see the connections an earlier test's tasks kept
    if release_stranded_candidates():
        gc.collect()


@pytest.fixture
def rtc_peer_connection() -> Iterator[webrtc.RTCPeerConnection]:
    pc = webrtc.RTCPeerConnection()
    yield pc
    pc.close()


pc = caller = callee = callee2 = rtc_peer_connection


@pytest.fixture
def create_pc(request: pytest.FixtureRequest) -> CreatePC:
    """Creates connections with a configuration, closed after the test."""

    def create(configuration: webrtc.RTCConfiguration | None = None) -> webrtc.RTCPeerConnection:
        pc = webrtc.RTCPeerConnection(configuration)
        request.addfinalizer(pc.close)
        return pc

    return create


def get_stream(constraints: dict[str, bool], request: pytest.FixtureRequest) -> webrtc.MediaStream:
    stream = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(**constraints)))

    def stop_tracks() -> None:
        for track in stream.get_tracks():
            track.stop()

    request.addfinalizer(stop_tracks)

    return stream


@pytest.fixture
def audio_stream(request: pytest.FixtureRequest) -> webrtc.MediaStream:
    return get_stream({'audio': True}, request)


audio_stream2 = audio_stream


@pytest.fixture
def video_stream(request: pytest.FixtureRequest) -> webrtc.MediaStream:
    return get_stream({'audio': False, 'video': True}, request)
