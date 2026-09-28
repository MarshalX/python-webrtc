#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Video: the synthetic camera of get_user_media, video sources and remote video tracks."""

import pytest

import webrtc
from tests.helpers import connect, wait_for_event


def test_get_user_media_video():
    """A stream of video only has one video track"""
    stream = webrtc.get_user_media(audio=False, video=True, width=320, height=240)
    (track,) = stream.get_tracks()
    assert track.kind == webrtc.MediaType.video
    assert stream.get_video_tracks() == [track]
    track.stop()


def test_get_user_media_needs_audio_or_video():
    """A stream of nothing isn't a request"""
    with pytest.raises(TypeError):
        webrtc.get_user_media(audio=False, video=False)


@pytest.mark.parametrize(
    'constraints',
    [{'width': {'exact': 0}}, {'height': {'ideal': 0}}, {'frame_rate': {'max': 0}}, {'width': {'min': 0, 'max': -1}}],
    ids=['exact', 'ideal', 'max', 'min and max'],
)
def test_get_user_media_constraint_selects_a_value(constraints):
    """A constraint selects its exact or ideal value, else the default within its range: here a non-positive one"""
    with pytest.raises(ValueError):
        webrtc.get_user_media(audio=False, video=True, **constraints)


def test_get_user_media_constraints():
    """Constraints that select a positive value are accepted"""
    stream = webrtc.get_user_media(
        audio=False, video=True, width={'ideal': 320}, height={'min': 100, 'max': 240}, frame_rate={'exact': 15}
    )
    for track in stream.get_tracks():
        track.stop()


def test_media_stream_constructor(audio_stream, video_stream):
    """A stream is created from tracks or from another stream, which it copies, or empty"""
    tracks = [*audio_stream.get_tracks(), *video_stream.get_tracks()]
    stream = webrtc.MediaStream(tracks)
    assert len(stream.get_tracks()) == 2
    copy = webrtc.MediaStream(stream)
    assert copy.id != stream.id and len(copy.get_tracks()) == 2
    assert webrtc.MediaStream().get_tracks() == []


def test_video_source_frames():
    """A video source takes I420 frames of the size they claim, rotated by a multiple of 90 degrees"""
    source = webrtc.RTCVideoSource(is_screencast=True)
    assert source.is_screencast and source.needs_denoising is None
    track = source.create_track()
    assert track.kind == webrtc.MediaType.video

    width, height = 5, 3
    size = width * height + 2 * 3 * 2
    source.on_frame(webrtc.RTCVideoFrame(width, height, bytes(size)))
    with pytest.raises(webrtc.InvalidAccessError):
        source.on_frame(webrtc.RTCVideoFrame(width, height, bytes(size - 1)))
    with pytest.raises(webrtc.InvalidRangeError):
        source.on_frame(webrtc.RTCVideoFrame(width, height, bytes(size), rotation=45))
    track.stop()


@pytest.mark.asyncio
async def test_remote_video_track(caller, callee, video_stream):
    """The remote end of a video track has its kind and stream"""
    caller.add_track(video_stream.get_tracks()[0], video_stream)
    track_event = wait_for_event(callee, 'track')
    await connect(caller, callee)
    event = await track_event

    assert event.track.kind == webrtc.MediaType.video
    assert [s.id for s in event.streams] == [video_stream.id]
    assert event.transceiver.receiver == event.receiver
