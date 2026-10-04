#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaDevices of Media Capture and Streams, which provides the synthetic microphone and camera of the library."""

from __future__ import annotations

import copy
import dataclasses
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, Literal, cast

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
    _camera_mode,
    _converted,
    _unsatisfied,
)
from webrtc.utils.events import UniformEventTarget
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc


class MediaDeviceInfo:
    """A media device, as listed by :meth:`MediaDevices.enumerate_devices`.

    See :mdn:`MediaDeviceInfo`.

    Args:
        device_id (:obj:`str`): The ID of the device.
        kind (:obj:`webrtc.MediaDeviceKind`): Whether it's a microphone, a speaker or a camera.
        label (:obj:`str`): The human-readable name of the device.
        group_id (:obj:`str`): The ID shared by the devices of one physical device.
    """

    def __init__(self, *, device_id: str, kind: webrtc.MediaDeviceKind, label: str, group_id: str) -> None:
        self._device_id = device_id
        self._kind = MediaDeviceKind(kind)
        self._label = label
        self._group_id = group_id

    @property
    def device_id(self) -> str:
        """:obj:`str`: The ID of the device. It's ``'synthetic-microphone'`` or ``'synthetic-camera'``.

        See :mdn:`MediaDeviceInfo/deviceId`.
        """
        return self._device_id

    @property
    def kind(self) -> webrtc.MediaDeviceKind:
        """:obj:`webrtc.MediaDeviceKind`: Whether it's a microphone, a speaker or a camera.

        See :mdn:`MediaDeviceInfo/kind`.
        """
        return self._kind

    @property
    def label(self) -> str:
        """:obj:`str`: The human-readable name of the device. It's always given, since no permission is needed.

        See :mdn:`MediaDeviceInfo/label`.
        """
        return self._label

    @property
    def group_id(self) -> str:
        """:obj:`str`: The ID shared by the devices of one physical device. Both devices use ``'synthetic'``.

        See :mdn:`MediaDeviceInfo/groupId`.
        """
        return self._group_id

    def to_json(self) -> dict[str, str]:
        """Returns the device as a JSON-serializable dictionary.

        See :mdn:`MediaDeviceInfo/toJSON`.

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
    """An input device, which is the synthetic microphone or the synthetic camera.

    See :mdn:`InputDeviceInfo`.

    Args:
        device_id (:obj:`str`): The ID of the device.
        kind (:obj:`webrtc.MediaDeviceKind`): Whether it's a microphone or a camera.
        label (:obj:`str`): The human-readable name of the device.
        group_id (:obj:`str`): The ID shared by the devices of one physical device.
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
        """Returns what the device can do. This matches :meth:`webrtc.MediaStreamTrack.get_capabilities` of its tracks.

        See :mdn:`InputDeviceInfo/getCapabilities`.

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


def _check_satisfiable(constraints: MediaTrackConstraints, device: InputDeviceInfo) -> None:
    kind = 'audio' if device.kind == MediaDeviceKind.audioinput else 'video'
    failed = _unsatisfied(constraints, device.get_capabilities(), MediaTrackSettings(), kind=kind)
    if failed is not None:
        raise OverconstrainedError(failed, f"The constraint {failed} can't be satisfied")


def _capture_mode(
    video: MediaTrackConstraints | None, camera: webrtc.MediaTrackCapabilities
) -> tuple[float, float, float]:
    """The width, height and frame rate of the camera: its defaults, within the constraints and its capabilities."""
    constraints = video if video is not None else MediaTrackConstraints()
    return _camera_mode(constraints, camera, MediaTrackSettings(), current=(640, 480, 30.0))


class MediaDevices(UniformEventTarget[Literal['devicechange'], DeviceChangeEvent]):
    """The media devices of the library, which are a synthetic microphone and camera. Use :data:`webrtc.media_devices`.

    No hardware is opened. The microphone plays quiet noise and the camera draws a moving pattern. To send real
    media, write it to a :obj:`webrtc.VideoTrackGenerator` or :obj:`webrtc.MediaStreamTrackGenerator`.

    See :mdn:`MediaDevices`.

    Events:
        devicechange (:obj:`webrtc.DeviceChangeEvent`): The devices changed. It never fires, because the
            devices are fixed.
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

    async def enumerate_devices(self) -> list[webrtc.MediaDeviceInfo]:
        """Lists the synthetic microphone and camera. Labels are included and no permission prompt is shown.

        See :mdn:`MediaDevices/enumerateDevices`.

        Returns:
            :obj:`list` of :obj:`webrtc.MediaDeviceInfo`: The devices, all of them :obj:`webrtc.InputDeviceInfo`.
        """
        return list(self._devices)

    def get_supported_constraints(self) -> webrtc.MediaTrackSupportedConstraints:
        """Returns the constraints the library recognizes, which are all of them.

        See :mdn:`MediaDevices/getSupportedConstraints`.

        Returns:
            :obj:`webrtc.MediaTrackSupportedConstraints`: The constraints, with every member set to :obj:`True`.
        """
        return MediaTrackSupportedConstraints(**dict.fromkeys(self._supported, True))

    async def get_user_media(self, constraints: webrtc.MediaStreamConstraints | None = None) -> webrtc.MediaStream:
        """Returns a stream with a track of the synthetic microphone, the synthetic camera, or both.

        The camera starts at 640x480 and 30 frames per second, adjusted to fit the constraints. The microphone has a
        fixed format. The constraints become the constraints of the tracks, as
        :meth:`webrtc.MediaStreamTrack.get_constraints` shows.

        See :mdn:`MediaDevices/getUserMedia`.

        Args:
            constraints (:obj:`webrtc.MediaStreamConstraints`, optional): Whether to get an audio and a video track,
                and the constraints of each.

        Returns:
            :obj:`webrtc.MediaStream`: The stream.

        Raises:
            TypeError: If neither audio nor video is requested, or a double isn't finite.
            webrtc.OverconstrainedError: If an ``exact``, ``min`` or ``max`` value is beyond what the device can
                do, like a camera more than 4096 pixels wide or faster than 120 frames per second. Other values
                are clamped to the capabilities.
        """
        constraints = constraints if constraints is not None else MediaStreamConstraints()
        audio = _track_constraints(constraints, 'audio')
        video = _track_constraints(constraints, 'video')
        if audio is None and video is None:
            msg = 'audio or video must be requested'
            raise TypeError(msg)
        microphone, camera = cast('list[InputDeviceInfo]', self._devices)
        audio = _converted(audio) if audio is not None else None
        video = _converted(video) if video is not None else None
        for requested, device in ((audio, microphone), (video, camera)):
            if requested is not None:
                _check_satisfiable(requested, device)
        width, height, frame_rate = _capture_mode(video, camera.get_capabilities())
        stream = MediaStream._wrap(wrtc.getUserMedia(audio is not None, video is not None, width, height, frame_rate))
        for track in stream.get_audio_tracks():
            track._native_obj._setLabel(microphone.label)
            track._native_obj._constraints = audio
        for track in stream.get_video_tracks():
            track._native_obj._setLabel(camera.label)
            track._native_obj._constraints = video
        return stream

    #: Alias for :meth:`enumerate_devices`
    enumerateDevices = enumerate_devices
    #: Alias for :meth:`get_supported_constraints`
    getSupportedConstraints = get_supported_constraints
    #: Alias for :meth:`get_user_media`
    getUserMedia = get_user_media


#: The media devices of the library, ``navigator.mediaDevices`` in a browser. See :mdn:`Navigator/mediaDevices`.
media_devices = MediaDevices()
#: Alias for :data:`media_devices`
mediaDevices = media_devices
