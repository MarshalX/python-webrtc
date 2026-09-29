#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Settings, capabilities, constraints and content hints of tracks."""

import pytest

import webrtc
from tests.helpers import connect_track, wait_until


@pytest.mark.asyncio
async def test_camera_settings_and_capabilities():
    """A camera track has the size and measured frame rate of its frames, and the capabilities of the camera"""
    stream = webrtc.get_user_media(audio=False, video=True, width=320, height=240, frame_rate=30)
    track = stream.get_tracks()[0]

    await wait_until(lambda: track.get_settings().frame_rate is not None, 'the frame rate')
    settings = track.get_settings()
    assert (settings.width, settings.height, settings.aspect_ratio) == (320, 240, 320 / 240)
    assert abs(settings.frame_rate - 30) < 5
    assert settings.device_id == 'synthetic-camera' and settings.resize_mode == 'none'

    capabilities = track.get_capabilities()
    assert capabilities.width == webrtc.ULongRange(1, 4096)
    assert capabilities.frame_rate.max >= 60
    assert track.get_constraints() == webrtc.MediaTrackConstraints(width=320, height=240, frame_rate=30)
    track.stop()


@pytest.mark.asyncio
async def test_microphone_settings(audio_stream):
    """A microphone track has the format of its samples, and no constraints"""
    track = audio_stream.get_tracks()[0]
    await wait_until(lambda: track.get_settings().sample_rate is not None, 'the audio format')
    settings = track.get_settings()
    assert (settings.sample_rate, settings.channel_count, settings.sample_size) == (48000, 1, 16)
    assert settings.echo_cancellation is False and settings.device_id == 'synthetic-microphone'
    assert track.get_capabilities().sample_rate == webrtc.ULongRange(48000, 48000)
    assert track.get_constraints() == webrtc.MediaTrackConstraints()


@pytest.mark.asyncio
async def test_apply_constraints_to_the_camera(video_stream):
    """Constraints change the size and frame rate of the camera, and are kept by the track"""
    track = video_stream.get_tracks()[0]
    await track.apply_constraints({'width': 160, 'height': {'exact': 120}, 'frameRate': {'max': 10}})
    await wait_until(lambda: track.get_settings().width == 160, 'the new size')
    await wait_until(lambda: (track.get_settings().frame_rate or 0) < 12, 'the new frame rate')
    assert track.get_settings().height == 120
    assert track.getConstraints().height == {'exact': 120}

    clone = track.clone()
    assert clone.get_settings().device_id == 'synthetic-camera'
    clone.stop()


@pytest.mark.asyncio
async def test_overconstrained(video_stream, audio_stream):
    """A required constraint the source can't satisfy fails, leaving the track as it was"""
    video = video_stream.get_tracks()[0]
    await video.apply_constraints({'width': 320})
    with pytest.raises(webrtc.OverconstrainedError) as error:
        await video.apply_constraints({'width': {'min': 100000}})
    assert error.value.constraint == 'width'
    assert video.get_constraints().width == 320

    audio = audio_stream.get_tracks()[0]
    with pytest.raises(webrtc.OverconstrainedError):
        await audio.apply_constraints({'sampleRate': {'exact': 44100}})
    with pytest.raises(webrtc.OverconstrainedError):
        await audio.apply_constraints({'width': {'exact': 640}})
    # ideal values are satisfied as far as possible
    await audio.apply_constraints({'sampleRate': 44100, 'echoCancellation': True})


@pytest.mark.asyncio
async def test_remote_track_settings(caller, callee, video_stream):
    """A remote track has the settings of what arrives, and no capabilities"""
    remote = await connect_track(caller, callee, video_stream.get_tracks()[0])
    await wait_until(lambda: remote.get_settings().width is not None, 'frames')
    settings = remote.get_settings()
    assert (settings.width, settings.height) == (640, 480)
    assert settings.device_id is None
    assert remote.get_capabilities() == webrtc.MediaTrackCapabilities()
    with pytest.raises(webrtc.OverconstrainedError):
        await remote.apply_constraints({'width': {'exact': 100}})


@pytest.mark.asyncio
async def test_content_hint(audio_stream, video_stream):
    """Hints of the kind of the track are kept, others are ignored"""
    video, audio = video_stream.get_tracks()[0], audio_stream.get_tracks()[0]
    assert video.content_hint == audio.contentHint == ''
    video.content_hint = 'text'
    audio.content_hint = 'music'
    video.content_hint = 'speech'
    audio.content_hint = 'detail'
    assert (video.content_hint, audio.content_hint) == ('text', 'music')
    video.content_hint = ''
    assert video.content_hint == ''


@pytest.mark.asyncio
async def test_constraints_of_an_ended_track(video_stream):
    """Constraints of an ended track are accepted, even ones it couldn't satisfy"""
    track = video_stream.get_tracks()[0]
    track.stop()
    await track.apply_constraints({'width': {'exact': 100000}})
