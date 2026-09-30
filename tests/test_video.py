#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Video: the synthetic camera of get_user_media, video sources and remote video tracks."""

from __future__ import annotations

import pytest

import webrtc
from tests.helpers import capture_mode, connect, wait_for_event


def test_get_user_media_video() -> None:
    """A stream of video only has one video track."""
    stream = webrtc.get_user_media(audio=False, video=True, width=320, height=240)
    (track,) = stream.get_tracks()
    assert track.kind == webrtc.MediaType.video
    assert stream.get_video_tracks() == [track]
    track.stop()


def test_get_user_media_needs_audio_or_video() -> None:
    """A stream of nothing isn't a request."""
    with pytest.raises(TypeError):
        webrtc.get_user_media(audio=False, video=False)


@pytest.mark.parametrize(
    ('constraints', 'error'),
    [
        ({'width': {'exact': 0}}, webrtc.OverconstrainedError),
        ({'frame_rate': {'max': 0}}, webrtc.OverconstrainedError),
        ({'width': {'min': 0, 'max': -1}}, TypeError),
    ],
    ids=['exact', 'max', 'negative'],
)
def test_get_user_media_constraint_beyond_the_camera(constraints: dict[str, object], error: type[Exception]) -> None:
    """A required value the camera can't have is overconstrained, a negative size isn't an unsigned long."""
    with pytest.raises(error):
        webrtc.get_user_media(audio=False, video=True, **constraints)


def test_get_user_media_ideal_beyond_the_camera() -> None:
    """An ideal value selects the nearest one the camera can have."""
    (track,) = webrtc.get_user_media(audio=False, video=True, height={'ideal': 0}).get_tracks()
    assert capture_mode(track) == (640, 1, 30)
    track.stop()


def test_get_user_media_constraints() -> None:
    """Constraints that select a positive value are accepted."""
    stream = webrtc.get_user_media(
        audio=False, video=True, width={'ideal': 320}, height={'min': 100, 'max': 240}, frame_rate={'exact': 15}
    )
    for track in stream.get_tracks():
        track.stop()


def test_media_stream_constructor(audio_stream: webrtc.MediaStream, video_stream: webrtc.MediaStream) -> None:
    """A stream is created from tracks or from another stream, which it copies, or empty."""
    tracks = [*audio_stream.get_tracks(), *video_stream.get_tracks()]
    stream = webrtc.MediaStream(tracks)
    assert len(stream.get_tracks()) == 2
    copy = webrtc.MediaStream(stream)
    assert copy.id != stream.id
    assert len(copy.get_tracks()) == 2
    assert webrtc.MediaStream().get_tracks() == []


@pytest.mark.asyncio
async def test_remote_video_track(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, video_stream: webrtc.MediaStream
) -> None:
    """The remote end of a video track has its kind and stream."""
    caller.add_track(video_stream.get_tracks()[0], video_stream)
    track_event = wait_for_event(callee, 'track')
    await connect(caller, callee)
    event = await track_event

    assert event.track.kind == webrtc.MediaType.video
    assert [s.id for s in event.streams] == [video_stream.id]
    assert event.transceiver.receiver == event.receiver
