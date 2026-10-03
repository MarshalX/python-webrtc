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
