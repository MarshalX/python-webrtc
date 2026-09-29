#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Settings, capabilities and constraints of tracks
(https://developer.mozilla.org/en-US/docs/Web/API/Media_Capture_and_Streams_API/Constraints)."""

from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional, Union

from webrtc.utils.names import alias, snake_case

#: A value, or a constraint on it: a :obj:`dict` with any of ``exact``, ``ideal``, ``min`` and ``max``
ConstrainValue = Union[float, int, str, bool, Dict[str, Any]]


@dataclass
class ULongRange:
    """A range of integers.

    Args:
        min (:obj:`int`, optional): The lowest value.
        max (:obj:`int`, optional): The highest value.
    """

    min: Optional[int] = None
    max: Optional[int] = None


@dataclass
class DoubleRange:
    """A range of numbers.

    Args:
        min (:obj:`float`, optional): The lowest value.
        max (:obj:`float`, optional): The highest value.
    """

    min: Optional[float] = None
    max: Optional[float] = None


@dataclass
class MediaTrackSettings:
    """What a track carries, as far as it's known (:meth:`webrtc.MediaStreamTrack.get_settings`). Members are
    :obj:`None` when they don't apply to the track.

    Args:
        width (:obj:`int`, optional): The width of the video.
        height (:obj:`int`, optional): The height of the video.
        aspect_ratio (:obj:`float`, optional): The width divided by the height.
        frame_rate (:obj:`float`, optional): The frames per second, measured over the last frames.
        resize_mode (:obj:`str`, optional): How the source is resized, ``'none'`` for the synthetic camera.
        device_id (:obj:`str`, optional): The device of the track, for :func:`webrtc.get_user_media`.
        group_id (:obj:`str`, optional): The group of the device.
        sample_rate (:obj:`int`, optional): The samples per second of the audio.
        sample_size (:obj:`int`, optional): The bits per sample of the audio.
        channel_count (:obj:`int`, optional): The channels of the audio.
        echo_cancellation (:obj:`bool`, optional): Whether echo is cancelled.
        auto_gain_control (:obj:`bool`, optional): Whether the gain is controlled.
        noise_suppression (:obj:`bool`, optional): Whether noise is suppressed.
    """

    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    frame_rate: Optional[float] = None
    resize_mode: Optional[str] = None
    device_id: Optional[str] = None
    group_id: Optional[str] = None
    sample_rate: Optional[int] = None
    sample_size: Optional[int] = None
    channel_count: Optional[int] = None
    echo_cancellation: Optional[bool] = None
    auto_gain_control: Optional[bool] = None
    noise_suppression: Optional[bool] = None

    #: Alias for :attr:`aspect_ratio`
    aspectRatio = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate = alias('frame_rate')
    #: Alias for :attr:`resize_mode`
    resizeMode = alias('resize_mode')
    #: Alias for :attr:`device_id`
    deviceId = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId = alias('group_id')
    #: Alias for :attr:`sample_rate`
    sampleRate = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize = alias('sample_size')
    #: Alias for :attr:`channel_count`
    channelCount = alias('channel_count')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression = alias('noise_suppression')


@dataclass
class MediaTrackCapabilities:
    """What the source of a track can do (:meth:`webrtc.MediaStreamTrack.get_capabilities`): the synthetic camera and
    microphone of :func:`webrtc.get_user_media` have capabilities, other tracks don't control their source.

    Args:
        width (:obj:`ULongRange`, optional): The widths of the video.
        height (:obj:`ULongRange`, optional): The heights of the video.
        aspect_ratio (:obj:`DoubleRange`, optional): The aspect ratios of the video.
        frame_rate (:obj:`DoubleRange`, optional): The frame rates of the video.
        resize_mode (:obj:`list` of :obj:`str`, optional): The ways the source is resized.
        device_id (:obj:`str`, optional): The device of the track.
        group_id (:obj:`str`, optional): The group of the device.
        sample_rate (:obj:`ULongRange`, optional): The sample rates of the audio.
        sample_size (:obj:`ULongRange`, optional): The bits per sample of the audio.
        channel_count (:obj:`ULongRange`, optional): The channels of the audio.
        echo_cancellation (:obj:`list` of :obj:`bool`, optional): Whether echo can be cancelled.
        auto_gain_control (:obj:`list` of :obj:`bool`, optional): Whether the gain can be controlled.
        noise_suppression (:obj:`list` of :obj:`bool`, optional): Whether noise can be suppressed.
    """

    width: Optional[ULongRange] = None
    height: Optional[ULongRange] = None
    aspect_ratio: Optional[DoubleRange] = None
    frame_rate: Optional[DoubleRange] = None
    resize_mode: Optional[List[str]] = None
    device_id: Optional[str] = None
    group_id: Optional[str] = None
    sample_rate: Optional[ULongRange] = None
    sample_size: Optional[ULongRange] = None
    channel_count: Optional[ULongRange] = None
    echo_cancellation: Optional[List[bool]] = None
    auto_gain_control: Optional[List[bool]] = None
    noise_suppression: Optional[List[bool]] = None

    #: Alias for :attr:`aspect_ratio`
    aspectRatio = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate = alias('frame_rate')
    #: Alias for :attr:`resize_mode`
    resizeMode = alias('resize_mode')
    #: Alias for :attr:`device_id`
    deviceId = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId = alias('group_id')
    #: Alias for :attr:`sample_rate`
    sampleRate = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize = alias('sample_size')
    #: Alias for :attr:`channel_count`
    channelCount = alias('channel_count')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression = alias('noise_suppression')


@dataclass
class MediaTrackConstraints:
    """What a track is asked to be (:meth:`webrtc.MediaStreamTrack.apply_constraints`). Each member is a value (an
    ideal one) or a :obj:`dict` of ``exact``, ``ideal``, ``min`` and ``max``: the required ones make the constraints
    fail if the source can't satisfy them.

    Args:
        width (optional): The width of the video.
        height (optional): The height of the video.
        aspect_ratio (optional): The aspect ratio of the video.
        frame_rate (optional): The frame rate of the video.
        resize_mode (optional): How the source is resized.
        device_id (optional): The device.
        group_id (optional): The group of the device.
        sample_rate (optional): The sample rate of the audio.
        sample_size (optional): The bits per sample of the audio.
        channel_count (optional): The channels of the audio.
        echo_cancellation (optional): Whether echo is cancelled.
        auto_gain_control (optional): Whether the gain is controlled.
        noise_suppression (optional): Whether noise is suppressed.
        advanced (:obj:`list` of :obj:`dict`, optional): Sets of constraints tried in order, each applied if it can
            be satisfied.
    """

    width: Optional[ConstrainValue] = None
    height: Optional[ConstrainValue] = None
    aspect_ratio: Optional[ConstrainValue] = None
    frame_rate: Optional[ConstrainValue] = None
    resize_mode: Optional[ConstrainValue] = None
    device_id: Optional[ConstrainValue] = None
    group_id: Optional[ConstrainValue] = None
    sample_rate: Optional[ConstrainValue] = None
    sample_size: Optional[ConstrainValue] = None
    channel_count: Optional[ConstrainValue] = None
    echo_cancellation: Optional[ConstrainValue] = None
    auto_gain_control: Optional[ConstrainValue] = None
    noise_suppression: Optional[ConstrainValue] = None
    advanced: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def _parse(cls, value: Any) -> 'MediaTrackConstraints':
        """Constraints from an instance or a dictionary, with snake_case or camelCase names"""
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError(f'{value!r} is not a MediaTrackConstraints')
        names = {f.name for f in fields(cls)}
        members = {snake_case(k): v for k, v in value.items()}
        # unknown members are ignored, as the specification says
        return cls(**{k: v for k, v in members.items() if k in names})

    #: Alias for :attr:`aspect_ratio`
    aspectRatio = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate = alias('frame_rate')
    #: Alias for :attr:`resize_mode`
    resizeMode = alias('resize_mode')
    #: Alias for :attr:`device_id`
    deviceId = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId = alias('group_id')
    #: Alias for :attr:`sample_rate`
    sampleRate = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize = alias('sample_size')
    #: Alias for :attr:`channel_count`
    channelCount = alias('channel_count')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression = alias('noise_suppression')
