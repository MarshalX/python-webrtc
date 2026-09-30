#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Settings, capabilities and constraints of tracks.

See https://developer.mozilla.org/en-US/docs/Web/API/Media_Capture_and_Streams_API/Constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, ClassVar, Union

from webrtc.utils.names import Alias, alias, snake_case

#: A value, or a constraint on it: a :obj:`dict` with any of ``exact``, ``ideal``, ``min`` and ``max``
ConstrainValue = Union[float, int, str, bool, dict[str, Any]]


@dataclass
class ULongRange:
    """A range of integers.

    Args:
        min (:obj:`int`, optional): The lowest value.
        max (:obj:`int`, optional): The highest value.
    """

    min: int | None = None
    max: int | None = None


@dataclass
class DoubleRange:
    """A range of numbers.

    Args:
        min (:obj:`float`, optional): The lowest value.
        max (:obj:`float`, optional): The highest value.
    """

    min: float | None = None
    max: float | None = None


@dataclass
class MediaTrackSettings:
    """What a track carries, as far as it's known (:meth:`webrtc.MediaStreamTrack.get_settings`).

    Members are :obj:`None` when they don't apply to the track.

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

    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None
    frame_rate: float | None = None
    resize_mode: str | None = None
    device_id: str | None = None
    group_id: str | None = None
    sample_rate: int | None = None
    sample_size: int | None = None
    channel_count: int | None = None
    echo_cancellation: bool | None = None
    auto_gain_control: bool | None = None
    noise_suppression: bool | None = None

    #: Alias for :attr:`aspect_ratio`
    aspectRatio: ClassVar[Alias[float | None]] = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate: ClassVar[Alias[float | None]] = alias('frame_rate')
    #: Alias for :attr:`resize_mode`
    resizeMode: ClassVar[Alias[str | None]] = alias('resize_mode')
    #: Alias for :attr:`device_id`
    deviceId: ClassVar[Alias[str | None]] = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId: ClassVar[Alias[str | None]] = alias('group_id')
    #: Alias for :attr:`sample_rate`
    sampleRate: ClassVar[Alias[int | None]] = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize: ClassVar[Alias[int | None]] = alias('sample_size')
    #: Alias for :attr:`channel_count`
    channelCount: ClassVar[Alias[int | None]] = alias('channel_count')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation: ClassVar[Alias[bool | None]] = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl: ClassVar[Alias[bool | None]] = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression: ClassVar[Alias[bool | None]] = alias('noise_suppression')


@dataclass
class MediaTrackCapabilities:
    """What the source of a track can do (:meth:`webrtc.MediaStreamTrack.get_capabilities`).

    The synthetic camera and microphone of :func:`webrtc.get_user_media` have capabilities, other tracks don't control
    their source.

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

    width: ULongRange | None = None
    height: ULongRange | None = None
    aspect_ratio: DoubleRange | None = None
    frame_rate: DoubleRange | None = None
    resize_mode: list[str] | None = None
    device_id: str | None = None
    group_id: str | None = None
    sample_rate: ULongRange | None = None
    sample_size: ULongRange | None = None
    channel_count: ULongRange | None = None
    echo_cancellation: list[bool] | None = None
    auto_gain_control: list[bool] | None = None
    noise_suppression: list[bool] | None = None

    #: Alias for :attr:`aspect_ratio`
    aspectRatio: ClassVar[Alias[DoubleRange | None]] = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate: ClassVar[Alias[DoubleRange | None]] = alias('frame_rate')
    #: Alias for :attr:`resize_mode`
    resizeMode: ClassVar[Alias[list[str] | None]] = alias('resize_mode')
    #: Alias for :attr:`device_id`
    deviceId: ClassVar[Alias[str | None]] = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId: ClassVar[Alias[str | None]] = alias('group_id')
    #: Alias for :attr:`sample_rate`
    sampleRate: ClassVar[Alias[ULongRange | None]] = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize: ClassVar[Alias[ULongRange | None]] = alias('sample_size')
    #: Alias for :attr:`channel_count`
    channelCount: ClassVar[Alias[ULongRange | None]] = alias('channel_count')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation: ClassVar[Alias[list[bool] | None]] = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl: ClassVar[Alias[list[bool] | None]] = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression: ClassVar[Alias[list[bool] | None]] = alias('noise_suppression')


@dataclass
class MediaTrackConstraints:
    """What a track is asked to be (:meth:`webrtc.MediaStreamTrack.apply_constraints`).

    Each member is a value (an ideal one) or a :obj:`dict` of ``exact``, ``ideal``, ``min`` and ``max``: the required
    ones make the constraints fail if the source can't satisfy them.

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

    width: ConstrainValue | None = None
    height: ConstrainValue | None = None
    aspect_ratio: ConstrainValue | None = None
    frame_rate: ConstrainValue | None = None
    resize_mode: ConstrainValue | None = None
    device_id: ConstrainValue | None = None
    group_id: ConstrainValue | None = None
    sample_rate: ConstrainValue | None = None
    sample_size: ConstrainValue | None = None
    channel_count: ConstrainValue | None = None
    echo_cancellation: ConstrainValue | None = None
    auto_gain_control: ConstrainValue | None = None
    noise_suppression: ConstrainValue | None = None
    advanced: list[dict[str, Any]] | None = None

    @classmethod
    def _parse(cls, value: object) -> MediaTrackConstraints:
        """Constraints from an instance or a dictionary, with snake_case or camelCase names."""
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            msg = f'{value!r} is not a MediaTrackConstraints'
            raise TypeError(msg)
        names = {f.name for f in fields(cls)}
        members = {snake_case(k): v for k, v in value.items()}
        # unknown members are ignored, as the specification says
        return cls(**{k: v for k, v in members.items() if k in names})

    #: Alias for :attr:`aspect_ratio`
    aspectRatio: ClassVar[Alias[ConstrainValue | None]] = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate: ClassVar[Alias[ConstrainValue | None]] = alias('frame_rate')
    #: Alias for :attr:`resize_mode`
    resizeMode: ClassVar[Alias[ConstrainValue | None]] = alias('resize_mode')
    #: Alias for :attr:`device_id`
    deviceId: ClassVar[Alias[ConstrainValue | None]] = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId: ClassVar[Alias[ConstrainValue | None]] = alias('group_id')
    #: Alias for :attr:`sample_rate`
    sampleRate: ClassVar[Alias[ConstrainValue | None]] = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize: ClassVar[Alias[ConstrainValue | None]] = alias('sample_size')
    #: Alias for :attr:`channel_count`
    channelCount: ClassVar[Alias[ConstrainValue | None]] = alias('channel_count')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation: ClassVar[Alias[ConstrainValue | None]] = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl: ClassVar[Alias[ConstrainValue | None]] = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression: ClassVar[Alias[ConstrainValue | None]] = alias('noise_suppression')
