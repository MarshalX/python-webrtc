#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaDevices of Media Capture and Streams: the synthetic camera and microphone of the library."""

from __future__ import annotations

import copy
import dataclasses
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, Literal

from typing_extensions import override

from webrtc import (
    DeviceChangeEvent,
    MediaDeviceKind,
    MediaStream,
    MediaStreamConstraints,
    MediaTrackConstraints,
    MediaTrackSettings,
    MediaTrackSupportedConstraints,
    OverconstrainedError,
    wrtc,
)
from webrtc.interfaces.media_stream_track import (
    _CAMERA_CAPABILITIES,
    _GROUP_ID,
    _MICROPHONE_CAPABILITIES,
    CAMERA_DEVICE_ID,
    MICROPHONE_DEVICE_ID,
    _check_numbers,
    _selected,
    _unsatisfied,
)
from webrtc.utils.events import UniformEventTarget
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc


class MediaDeviceInfo:
    """A media device, as :meth:`MediaDevices.enumerate_devices` lists it.

    Args:
        device_id (:obj:`str`): The id of the device.
        kind (:obj:`webrtc.MediaDeviceKind`): Whether it's a microphone, a speaker or a camera.
        label (:obj:`str`): The name of the device.
        group_id (:obj:`str`): The id of the physical device it belongs to.
    """

    def __init__(self, *, device_id: str, kind: webrtc.MediaDeviceKind, label: str, group_id: str) -> None:
        self._device_id = device_id
        self._kind = MediaDeviceKind(kind)
        self._label = label
        self._group_id = group_id

    @property
    def device_id(self) -> str:
        """:obj:`str`: The id of the device."""
        return self._device_id

    @property
    def kind(self) -> webrtc.MediaDeviceKind:
        """:obj:`webrtc.MediaDeviceKind`: Whether it's a microphone, a speaker or a camera."""
        return self._kind

    @property
    def label(self) -> str:
        """:obj:`str`: The name of the device."""
        return self._label

    @property
    def group_id(self) -> str:
        """:obj:`str`: The id of the physical device it belongs to."""
        return self._group_id

    def to_json(self) -> dict[str, str]:
        """Returns the device as a JSON-serializable dictionary.

        Returns:
            :obj:`dict`: ``deviceId``, ``kind``, ``label`` and ``groupId``.
        """
        return {'deviceId': self.device_id, 'kind': self.kind.value, 'label': self.label, 'groupId': self.group_id}

    def __repr__(self) -> str:
        return f'{type(self).__name__}(device_id={self.device_id!r}, kind={self.kind.value!r}, label={self.label!r})'

    #: Alias for :attr:`device_id`
    deviceId: ClassVar[Alias[str]] = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId: ClassVar[Alias[str]] = alias('group_id')
    #: Alias for :meth:`to_json`
    toJSON = to_json


class InputDeviceInfo(MediaDeviceInfo):
    """An input device: the synthetic camera or microphone.

    Args:
        device_id (:obj:`str`): The id of the device.
        kind (:obj:`webrtc.MediaDeviceKind`): Whether it's a microphone or a camera.
        label (:obj:`str`): The name of the device.
        group_id (:obj:`str`): The id of the physical device it belongs to.
        capabilities (:obj:`webrtc.MediaTrackCapabilities`): What the device can do.
    """

    def __init__(
        self,
        *,
        device_id: str,
        kind: webrtc.MediaDeviceKind,
        label: str,
        group_id: str,
        capabilities: webrtc.MediaTrackCapabilities,
    ) -> None:
        super().__init__(device_id=device_id, kind=kind, label=label, group_id=group_id)
        self._capabilities = capabilities

    def get_capabilities(self) -> webrtc.MediaTrackCapabilities:
        """Returns what the device can do, as the tracks of it have.

        Returns:
            :obj:`webrtc.MediaTrackCapabilities`: A copy of the capabilities.
        """
        return copy.deepcopy(self._capabilities)

    #: Alias for :meth:`get_capabilities`
    getCapabilities = get_capabilities


def _devices() -> list[MediaDeviceInfo]:
    return [
        InputDeviceInfo(
            device_id=MICROPHONE_DEVICE_ID,
            kind=MediaDeviceKind.audioinput,
            label='Synthetic microphone',
            group_id=_GROUP_ID,
            capabilities=_MICROPHONE_CAPABILITIES,
        ),
        InputDeviceInfo(
            device_id=CAMERA_DEVICE_ID,
            kind=MediaDeviceKind.videoinput,
            label='Synthetic camera',
            group_id=_GROUP_ID,
            capabilities=_CAMERA_CAPABILITIES,
        ),
    ]


def _track_constraints(constraints: webrtc.MediaStreamConstraints, kind: str) -> MediaTrackConstraints | None:
    """The constraints of a requested kind of track, :obj:`None` if it isn't requested."""
    value: bool | MediaTrackConstraints = getattr(constraints, kind)
    if isinstance(value, MediaTrackConstraints):
        return value
    return MediaTrackConstraints() if value else None


def _check_satisfiable(constraints: MediaTrackConstraints, capabilities: webrtc.MediaTrackCapabilities) -> None:
    _check_numbers(constraints)
    failed = _unsatisfied(constraints, capabilities, MediaTrackSettings())
    if failed is not None:
        raise OverconstrainedError(failed, f"The constraint {failed} can't be satisfied")


def _capture_mode(
    video: MediaTrackConstraints | None, camera: webrtc.MediaTrackCapabilities
) -> tuple[float, float, float]:
    """The width, height and frame rate of the camera: its defaults, within the constraints and its capabilities."""
    constraints = video if video is not None else MediaTrackConstraints()
    return (
        _selected(constraints.width, 640, camera.width),
        _selected(constraints.height, 480, camera.height),
        _selected(constraints.frame_rate, 30.0, camera.frame_rate),
    )


class MediaDevices(UniformEventTarget[Literal['devicechange'], DeviceChangeEvent]):
    """The media devices of the library: a synthetic microphone and camera, as :data:`webrtc.media_devices`.

    The microphone plays quiet noise, the camera draws a moving pattern (use :obj:`webrtc.VideoTrackGenerator` and
    :obj:`webrtc.MediaStreamTrackGenerator` for real media).

    Events (see :meth:`on`):
        ``devicechange`` (:obj:`webrtc.DeviceChangeEvent`): The devices changed, which they never do.
    """

    def __init__(self) -> None:
        # the listeners of the events, which a native object holds for other targets
        self._native = SimpleNamespace(_listeners=None)
        # the devices never change
        self._devices = _devices()
        self._supported = [field.name for field in dataclasses.fields(MediaTrackSupportedConstraints)]

    @property
    @override
    def _native_obj(self) -> SimpleNamespace:
        return self._native

    def _capabilities(self) -> dict[webrtc.MediaDeviceKind, webrtc.MediaTrackCapabilities]:
        return {d.kind: d.get_capabilities() for d in self._devices if isinstance(d, InputDeviceInfo)}

    async def enumerate_devices(self) -> list[webrtc.MediaDeviceInfo]:
        """Lists the devices: the synthetic microphone and camera.

        Returns:
            :obj:`list` of :obj:`webrtc.MediaDeviceInfo`: The devices, :obj:`webrtc.InputDeviceInfo` ones.
        """
        return list(self._devices)

    def get_supported_constraints(self) -> webrtc.MediaTrackSupportedConstraints:
        """Returns the constraints the library recognizes: all of them.

        Returns:
            :obj:`webrtc.MediaTrackSupportedConstraints`: The constraints.
        """
        return MediaTrackSupportedConstraints(**dict.fromkeys(self._supported, True))

    async def get_user_media(self, constraints: webrtc.MediaStreamConstraints | None = None) -> webrtc.MediaStream:
        """Returns a stream of the synthetic microphone and/or camera, as requested.

        The constraints given are the ones of the tracks (see :meth:`webrtc.MediaStreamTrack.get_constraints`).

        Args:
            constraints (:obj:`webrtc.MediaStreamConstraints`, optional): Whether to get an audio and a video track,
                and the constraints of each.

        Returns:
            :obj:`webrtc.MediaStream`: The stream.

        Raises:
            TypeError: If neither audio nor video is requested, or a value isn't a finite number (negative for
                the size).
            webrtc.OverconstrainedError: If a required value (``exact``, ``min``, ``max``) is beyond what the
                device can do, like more than 4096 pixels wide or 120 frames per second for the camera. Other
                values are brought within that.
        """
        constraints = constraints if constraints is not None else MediaStreamConstraints()
        audio = _track_constraints(constraints, 'audio')
        video = _track_constraints(constraints, 'video')
        if audio is None and video is None:
            msg = 'audio or video must be requested'
            raise TypeError(msg)
        capabilities = self._capabilities()
        for requested, kind in ((audio, MediaDeviceKind.audioinput), (video, MediaDeviceKind.videoinput)):
            if requested is not None:
                _check_satisfiable(requested, capabilities[kind])
        width, height, frame_rate = _capture_mode(video, capabilities[MediaDeviceKind.videoinput])
        stream = MediaStream._wrap(wrtc.getUserMedia(audio is not None, video is not None, width, height, frame_rate))
        for track in stream.get_audio_tracks():
            track._native_obj._constraints = audio
        for track in stream.get_video_tracks():
            track._native_obj._constraints = video
        return stream

    #: Alias for :meth:`enumerate_devices`
    enumerateDevices = enumerate_devices
    #: Alias for :meth:`get_supported_constraints`
    getSupportedConstraints = get_supported_constraints
    #: Alias for :meth:`get_user_media`
    getUserMedia = get_user_media


#: The media devices of the library, ``navigator.mediaDevices`` in a browser
media_devices = MediaDevices()
#: Alias for :data:`media_devices`
mediaDevices = media_devices
