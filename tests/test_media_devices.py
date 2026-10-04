#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaDevices: the synthetic microphone and camera."""

from __future__ import annotations

import pytest

import webrtc


@pytest.mark.asyncio
async def test_enumerate_devices() -> None:
    """The microphone and the camera are input devices, with the capabilities of their tracks."""
    microphone, camera = await webrtc.media_devices.enumerate_devices()
    assert isinstance(microphone, webrtc.InputDeviceInfo)
    assert isinstance(camera, webrtc.InputDeviceInfo)
    assert microphone.kind == webrtc.MediaDeviceKind.audioinput
    assert camera.kind == webrtc.MediaDeviceKind.videoinput
    assert camera.to_json() == {
        'deviceId': camera.device_id,
        'kind': 'videoinput',
        'label': camera.label,
        'groupId': camera.group_id,
    }
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    for track, device in zip(stream.get_tracks(), (microphone, camera)):
        assert track.get_capabilities() == device.get_capabilities()
        assert track.get_settings().device_id == device.device_id
        track.stop()


def test_supported_constraints() -> None:
    supported = webrtc.media_devices.get_supported_constraints()
    assert supported.width
    assert supported.facingMode


@pytest.mark.asyncio
async def test_audio_constraints() -> None:
    """Audio constraints are checked against the microphone, and kept as the ones of the track."""
    with pytest.raises(webrtc.OverconstrainedError):
        await webrtc.media_devices.get_user_media(
            webrtc.MediaStreamConstraints(
                audio=webrtc.MediaTrackConstraints(sample_rate=webrtc.ConstrainULongRange(exact=8000))
            )
        )
    constraints = webrtc.MediaTrackConstraints(channel_count=1)
    (track,) = (
        await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=constraints))
    ).get_tracks()
    assert track.get_constraints() == constraints
    track.stop()


@pytest.mark.asyncio
async def test_facing_mode_of_a_camera_without_one() -> None:
    """The camera faces nowhere, so a required facing mode can't be satisfied."""
    video = webrtc.MediaTrackConstraints(facing_mode=webrtc.ConstrainDOMStringParameters(exact='user'))
    with pytest.raises(webrtc.OverconstrainedError):
        await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=video))


def test_constraints_from_json() -> None:
    constraints = webrtc.MediaStreamConstraints.from_json({'audio': True, 'video': {'width': 320}})
    assert constraints == webrtc.MediaStreamConstraints(audio=True, video=webrtc.MediaTrackConstraints(width=320))


@pytest.mark.asyncio
async def test_devicechange_handler() -> None:
    """Devices never change, but a handler can be registered like on any target."""
    assert (await webrtc.media_devices.enumerate_devices()) != []
    handler = webrtc.media_devices.on('devicechange', lambda _: None)
    webrtc.media_devices.off('devicechange', handler)
    assert webrtc.DeviceChangeEvent('devicechange').devices == []


@pytest.mark.asyncio
async def test_tracks_have_the_label_of_their_device() -> None:
    """Tracks and their clones have the label of their device."""
    microphone, camera = await webrtc.media_devices.enumerate_devices()
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    audio, video = stream.get_tracks()
    assert (audio.label, video.label) == (microphone.label, camera.label)
    assert [t.label for t in stream.clone().get_tracks()] == [microphone.label, camera.label]
    for track in stream.get_tracks():
        track.stop()


@pytest.mark.asyncio
async def test_satisfiable_advanced_constraints_apply() -> None:
    """Satisfiable advanced sets apply in order, the others are skipped."""
    constraints = webrtc.MediaTrackConstraints(
        advanced=[
            webrtc.MediaTrackConstraintSet(width=1280),
            webrtc.MediaTrackConstraintSet(width=webrtc.ConstrainULongRange(min=100_000)),
            webrtc.MediaTrackConstraintSet(height=720),
        ]
    )
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=constraints))
    (track,) = stream.get_tracks()
    settings = track.get_settings()
    assert (settings.width, settings.height) == (1280, 720)
    track.stop()


@pytest.mark.asyncio
async def test_stream_clone_clones_each_track() -> None:
    """A stream clone keeps the label, device and ended state of each track."""
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    audio, video = stream.get_tracks()
    audio.stop()
    clone = stream.clone()
    cloned_audio, cloned_video = clone.get_tracks()
    assert clone.id != stream.id
    assert {cloned_audio.id, cloned_video.id}.isdisjoint({audio.id, video.id})
    assert cloned_audio.ready_state == webrtc.MediaStreamTrackState.ended
    assert cloned_video.ready_state == webrtc.MediaStreamTrackState.live
    assert cloned_video.label == video.label
    assert cloned_video.get_capabilities() == video.get_capabilities()
    await cloned_video.apply_constraints(webrtc.MediaTrackConstraints(width=320))
    assert cloned_video.get_settings().width == 320
    video.stop()
    cloned_video.stop()


@pytest.mark.asyncio
async def test_overconstrained_names_the_webidl_constraint() -> None:
    """OverconstrainedError.constraint is the WebIDL name, like 'frameRate'."""
    constraints = webrtc.MediaTrackConstraints(frame_rate=webrtc.ConstrainDoubleRange(min=100, max=10))
    with pytest.raises(webrtc.OverconstrainedError) as error:
        await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=constraints))
    assert error.value.constraint == 'frameRate'


@pytest.mark.asyncio
async def test_negative_sizes_clamp_to_zero() -> None:
    """A negative max clamps to 0 ([Clamp]), which is overconstrained."""
    constraints = webrtc.MediaTrackConstraints(width=webrtc.ConstrainULongRange(max=-1))
    with pytest.raises(webrtc.OverconstrainedError) as error:
        await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(video=constraints))
    assert error.value.constraint == 'width'


@pytest.mark.asyncio
async def test_constraints_of_the_other_kind_are_ignored() -> None:
    """Constraints of the other kind are ignored."""
    audio = webrtc.MediaTrackConstraints(width=webrtc.ConstrainULongRange(exact=10**6))
    video = webrtc.MediaTrackConstraints(sample_rate=webrtc.ConstrainULongRange(exact=1))
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=audio, video=video))
    assert len(stream.get_tracks()) == 2
    for track in stream.get_tracks():
        track.stop()


@pytest.mark.asyncio
async def test_microphone_settings_before_samples() -> None:
    """The microphone reports its format before samples flow."""
    (track,) = (await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True))).get_tracks()
    settings = track.get_settings()
    assert (settings.sample_rate, settings.sample_size, settings.channel_count) == (48000, 16, 1)
    track.stop()


@pytest.mark.asyncio
async def test_latency_voice_isolation_and_facing_mode() -> None:
    """Microphone latency and voice isolation, camera facing mode."""
    assert webrtc.media_devices.get_supported_constraints().voice_isolation
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    audio, video = stream.get_tracks()
    assert audio.get_capabilities().latency == webrtc.DoubleRange(0.01, 0.01)
    assert audio.get_capabilities().voice_isolation == [False]
    settings = audio.get_settings()
    assert (settings.latency, settings.voice_isolation) == (0.01, False)
    assert video.get_capabilities().facing_mode == []
    assert video.get_settings().facing_mode is None
    with pytest.raises(webrtc.OverconstrainedError) as error:
        await audio.apply_constraints(
            webrtc.MediaTrackConstraints(voice_isolation=webrtc.ConstrainBooleanParameters(exact=True))
        )
    assert error.value.constraint == 'voiceIsolation'
    for track in stream.get_tracks():
        track.stop()
