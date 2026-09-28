#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import pytest

import webrtc
from tests.helpers import connect, wait_for_event


def test_get_user_media_video():
    stream = webrtc.get_user_media(audio=False, video=True, width=320, height=240)
    (track,) = stream.get_tracks()
    assert track.kind == webrtc.MediaType.video
    assert stream.get_video_tracks() == [track]
    track.stop()
    with pytest.raises(TypeError):
        webrtc.get_user_media(audio=False, video=False)


def test_media_stream_constructor():
    tracks = webrtc.get_user_media(video=True).get_tracks()
    stream = webrtc.MediaStream(tracks)
    assert len(stream.get_tracks()) == 2
    copy = webrtc.MediaStream(stream)
    assert copy.id != stream.id and len(copy.get_tracks()) == 2
    assert webrtc.MediaStream().get_tracks() == []
    for track in tracks:
        track.stop()


def test_video_source_frames():
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


@pytest.mark.asyncio
async def test_remote_video_track(caller, callee):
    stream = webrtc.get_user_media(audio=False, video=True)
    caller.add_track(stream.get_tracks()[0], stream)
    track_event = wait_for_event(callee, 'track')
    await connect(caller, callee)
    event = await track_event

    assert event.track.kind == webrtc.MediaType.video
    assert [s.id for s in event.streams] == [stream.id]
    assert event.transceiver.receiver == event.receiver
    stream.get_tracks()[0].stop()
