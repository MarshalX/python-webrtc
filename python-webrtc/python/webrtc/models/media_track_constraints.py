#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Settings, capabilities and constraints of tracks.

See :mdn:`Media_Capture_and_Streams_API/Constraints`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Union

from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias


@dataclass
class ULongRange(Dictionary):
    """A range of integers a source supports, in :obj:`MediaTrackCapabilities`.

    Args:
        min (:obj:`int`, optional): The lowest value, inclusive.
        max (:obj:`int`, optional): The highest value, inclusive.
    """

    min: int | None = None
    max: int | None = None


@dataclass
class DoubleRange(Dictionary):
    """A range of numbers a source supports, in :obj:`MediaTrackCapabilities`.

    Args:
        min (:obj:`float`, optional): The lowest value, inclusive.
        max (:obj:`float`, optional): The highest value, inclusive.
    """

    min: float | None = None
    max: float | None = None


@dataclass
class ConstrainULongRange(ULongRange):
    """A constraint on an integer, with required bounds or a required value, and a preferred value.

    The required members fail the constraints when the source's range doesn't allow them.

    Args:
        min (:obj:`int`, optional): The lowest value allowed, as a requirement.
        max (:obj:`int`, optional): The highest value allowed, as a requirement.
        exact (:obj:`int`, optional): The only value allowed, as a requirement.
        ideal (:obj:`int`, optional): The value to get as near as possible to. It never fails the constraints.
    """

    exact: int | None = None
    ideal: int | None = None


@dataclass
class ConstrainDoubleRange(DoubleRange):
    """A constraint on a number, with required bounds or a required value, and a preferred value.

    The required members fail the constraints when the source's range doesn't allow them.

    Args:
        min (:obj:`float`, optional): The lowest value allowed, as a requirement.
        max (:obj:`float`, optional): The highest value allowed, as a requirement.
        exact (:obj:`float`, optional): The only value allowed, as a requirement.
        ideal (:obj:`float`, optional): The value to get as near as possible to. It never fails the constraints.
    """

    exact: float | None = None
    ideal: float | None = None


@dataclass
class ConstrainBooleanParameters(Dictionary):
    """A constraint on a boolean, with a required value or a preferred one.

    Args:
        exact (:obj:`bool`, optional): The only value allowed, as a requirement.
        ideal (:obj:`bool`, optional): The value to get if possible. It never fails the constraints.
    """

    exact: bool | None = None
    ideal: bool | None = None


@dataclass
class ConstrainDOMStringParameters(Dictionary):
    """A constraint on a string, with required values or preferred ones.

    Args:
        exact (:obj:`str` or :obj:`list` of :obj:`str`, optional): The value or values allowed, as a requirement.
        ideal (:obj:`str` or :obj:`list` of :obj:`str`, optional): The value or values to get if possible. They
            never fail the constraints.
    """

    exact: str | list[str] | None = None
    ideal: str | list[str] | None = None


@dataclass
class ConstrainBooleanOrDOMStringParameters(Dictionary):
    """A constraint on a boolean or a string, with a required value or a preferred one.

    Args:
        exact (:obj:`bool` or :obj:`str`, optional): The only value allowed, as a requirement.
        ideal (:obj:`bool` or :obj:`str`, optional): The value to get if possible. It never fails the constraints.
    """

    exact: bool | str | None = None
    ideal: bool | str | None = None


#: A constraint on an integer, where a bare value is an ideal one
ConstrainULong = Union[int, ConstrainULongRange]
#: A constraint on a number, where a bare value is an ideal one
ConstrainDouble = Union[float, ConstrainDoubleRange]
#: A constraint on a boolean, where a bare value is an ideal one
ConstrainBoolean = Union[bool, ConstrainBooleanParameters]
#: A constraint on a string, where a bare string or a list of them is ideal
ConstrainDOMString = Union[str, list[str], ConstrainDOMStringParameters]
#: A constraint on a boolean or a string, where a bare value is an ideal one
ConstrainBooleanOrDOMString = Union[bool, str, ConstrainBooleanOrDOMStringParameters]


@dataclass
class MediaTrackSupportedConstraints(Dictionary):
    """The constraints the library recognizes, as :meth:`webrtc.MediaDevices.get_supported_constraints` returns.

    Every member is :obj:`True`. A recognized constraint that the source has no capability or setting for (like
    :attr:`facing_mode` on the synthetic camera) is ignored when ideal and fails when required.

    See :mdn:`MediaDevices/getSupportedConstraints`.

    Args:
        width (:obj:`bool`, optional): Whether ``width`` is recognized.
        height (:obj:`bool`, optional): Whether ``height`` is recognized.
        aspect_ratio (:obj:`bool`, optional): Whether ``aspect_ratio`` is recognized.
        frame_rate (:obj:`bool`, optional): Whether ``frame_rate`` is recognized.
        facing_mode (:obj:`bool`, optional): Whether ``facing_mode`` is recognized.
        resize_mode (:obj:`bool`, optional): Whether ``resize_mode`` is recognized.
        sample_rate (:obj:`bool`, optional): Whether ``sample_rate`` is recognized.
        sample_size (:obj:`bool`, optional): Whether ``sample_size`` is recognized.
        echo_cancellation (:obj:`bool`, optional): Whether ``echo_cancellation`` is recognized.
        auto_gain_control (:obj:`bool`, optional): Whether ``auto_gain_control`` is recognized.
        noise_suppression (:obj:`bool`, optional): Whether ``noise_suppression`` is recognized.
        latency (:obj:`bool`, optional): Whether ``latency`` is recognized.
        channel_count (:obj:`bool`, optional): Whether ``channel_count`` is recognized.
        device_id (:obj:`bool`, optional): Whether ``device_id`` is recognized.
        group_id (:obj:`bool`, optional): Whether ``group_id`` is recognized.
        background_blur (:obj:`bool`, optional): Whether ``background_blur`` is recognized.
    """

    width: bool = True
    height: bool = True
    aspect_ratio: bool = True
    frame_rate: bool = True
    facing_mode: bool = True
    resize_mode: bool = True
    sample_rate: bool = True
    sample_size: bool = True
    echo_cancellation: bool = True
    auto_gain_control: bool = True
    noise_suppression: bool = True
    latency: bool = True
    channel_count: bool = True
    device_id: bool = True
    group_id: bool = True
    background_blur: bool = True

    #: Alias for :attr:`aspect_ratio`
    aspectRatio: ClassVar[Alias[bool]] = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate: ClassVar[Alias[bool]] = alias('frame_rate')
    #: Alias for :attr:`facing_mode`
    facingMode: ClassVar[Alias[bool]] = alias('facing_mode')
    #: Alias for :attr:`resize_mode`
    resizeMode: ClassVar[Alias[bool]] = alias('resize_mode')
    #: Alias for :attr:`sample_rate`
    sampleRate: ClassVar[Alias[bool]] = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize: ClassVar[Alias[bool]] = alias('sample_size')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation: ClassVar[Alias[bool]] = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl: ClassVar[Alias[bool]] = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression: ClassVar[Alias[bool]] = alias('noise_suppression')
    #: Alias for :attr:`channel_count`
    channelCount: ClassVar[Alias[bool]] = alias('channel_count')
    #: Alias for :attr:`device_id`
    deviceId: ClassVar[Alias[bool]] = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId: ClassVar[Alias[bool]] = alias('group_id')
    #: Alias for :attr:`background_blur`
    backgroundBlur: ClassVar[Alias[bool]] = alias('background_blur')


@dataclass
class MediaTrackSettings(Dictionary):
    """What a track carries now, as :meth:`webrtc.MediaStreamTrack.get_settings` returns.

    Members are :obj:`None` when they don't apply to the track or aren't known yet. The library never fills
    :attr:`facing_mode`, :attr:`latency` or :attr:`background_blur`.

    See :mdn:`MediaTrackSettings`.

    Args:
        width (:obj:`int`, optional): The width of the video.
        height (:obj:`int`, optional): The height of the video.
        aspect_ratio (:obj:`float`, optional): The width divided by the height.
        frame_rate (:obj:`float`, optional): The frames per second, measured over the last frames.
        resize_mode (:obj:`str`, optional): How the source is resized. It's ``'none'`` for the synthetic camera.
        device_id (:obj:`str`, optional): The device of a track of :meth:`webrtc.MediaDevices.get_user_media`.
        group_id (:obj:`str`, optional): The group ID of the device.
        sample_rate (:obj:`int`, optional): The samples per second of the audio.
        sample_size (:obj:`int`, optional): The bits per sample of the audio.
        channel_count (:obj:`int`, optional): The channels of the audio.
        echo_cancellation (:obj:`bool` or :obj:`str`, optional): Whether echo is cancelled. It's :obj:`False` for the
            synthetic microphone.
        auto_gain_control (:obj:`bool`, optional): Whether the gain is controlled automatically.
        noise_suppression (:obj:`bool`, optional): Whether noise is suppressed.
        facing_mode (:obj:`str`, optional): Where the camera faces, like ``'user'``.
        latency (:obj:`float`, optional): The latency of the audio in seconds.
        background_blur (:obj:`bool`, optional): Whether the background is blurred.
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
    echo_cancellation: bool | str | None = None
    auto_gain_control: bool | None = None
    noise_suppression: bool | None = None
    facing_mode: str | None = None
    latency: float | None = None
    background_blur: bool | None = None

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
    echoCancellation: ClassVar[Alias[bool | str | None]] = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl: ClassVar[Alias[bool | None]] = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression: ClassVar[Alias[bool | None]] = alias('noise_suppression')
    #: Alias for :attr:`facing_mode`
    facingMode: ClassVar[Alias[str | None]] = alias('facing_mode')
    #: Alias for :attr:`background_blur`
    backgroundBlur: ClassVar[Alias[bool | None]] = alias('background_blur')


@dataclass
class MediaTrackCapabilities(Dictionary):
    """What the source of a track can do, as :meth:`webrtc.MediaStreamTrack.get_capabilities` returns.

    Only the synthetic camera and microphone of :meth:`webrtc.MediaDevices.get_user_media` have capabilities. The
    camera supports 1 to 4096 pixels each way at 1 to 120 frames per second. The microphone is 48 kHz 16-bit mono
    with no processing. For other tracks every member is :obj:`None`, because the library doesn't control their
    source.

    See :mdn:`MediaStreamTrack/getCapabilities`.

    Args:
        width (:obj:`ULongRange`, optional): The widths of the video.
        height (:obj:`ULongRange`, optional): The heights of the video.
        aspect_ratio (:obj:`DoubleRange`, optional): The aspect ratios of the video.
        frame_rate (:obj:`DoubleRange`, optional): The frame rates of the video.
        resize_mode (:obj:`list` of :obj:`str`, optional): The ways the source can be resized.
        device_id (:obj:`str`, optional): The device of the track.
        group_id (:obj:`str`, optional): The group ID of the device.
        sample_rate (:obj:`ULongRange`, optional): The sample rates of the audio.
        sample_size (:obj:`ULongRange`, optional): The bits per sample of the audio.
        channel_count (:obj:`ULongRange`, optional): The channels of the audio.
        echo_cancellation (:obj:`list` of :obj:`bool` or :obj:`str`, optional): Whether echo can be cancelled.
        auto_gain_control (:obj:`list` of :obj:`bool`, optional): Whether the gain can be controlled.
        noise_suppression (:obj:`list` of :obj:`bool`, optional): Whether noise can be suppressed.
        facing_mode (:obj:`list` of :obj:`str`, optional): Where the camera can face.
        latency (:obj:`DoubleRange`, optional): The latencies of the audio in seconds.
        background_blur (:obj:`list` of :obj:`bool`, optional): Whether the background can be blurred.
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
    echo_cancellation: list[bool | str] | None = None
    auto_gain_control: list[bool] | None = None
    noise_suppression: list[bool] | None = None
    facing_mode: list[str] | None = None
    latency: DoubleRange | None = None
    background_blur: list[bool] | None = None

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
    echoCancellation: ClassVar[Alias[list[bool | str] | None]] = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl: ClassVar[Alias[list[bool] | None]] = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression: ClassVar[Alias[list[bool] | None]] = alias('noise_suppression')
    #: Alias for :attr:`facing_mode`
    facingMode: ClassVar[Alias[list[str] | None]] = alias('facing_mode')
    #: Alias for :attr:`background_blur`
    backgroundBlur: ClassVar[Alias[list[bool] | None]] = alias('background_blur')


@dataclass
class MediaTrackConstraintSet(Dictionary):
    """A set of constraints on a track. It's the base of :obj:`MediaTrackConstraints` and of its advanced sets.

    Each member is either a bare value, which is ideal, or a constraint object with ``exact``, ``ideal``, ``min``
    and ``max``. The required parts fail the constraints if the source can't satisfy them, but the ideal ones never
    do.

    Args:
        width (:obj:`int` or :obj:`ConstrainULongRange`, optional): The width of the video.
        height (:obj:`int` or :obj:`ConstrainULongRange`, optional): The height of the video.
        aspect_ratio (:obj:`float` or :obj:`ConstrainDoubleRange`, optional): The aspect ratio of the video.
        frame_rate (:obj:`float` or :obj:`ConstrainDoubleRange`, optional): The frame rate of the video.
        resize_mode (:obj:`str` or :obj:`ConstrainDOMStringParameters`, optional): How the source is resized.
        device_id (:obj:`str` or :obj:`ConstrainDOMStringParameters`, optional): The device.
        group_id (:obj:`str` or :obj:`ConstrainDOMStringParameters`, optional): The group ID of the device.
        sample_rate (:obj:`int` or :obj:`ConstrainULongRange`, optional): The sample rate of the audio.
        sample_size (:obj:`int` or :obj:`ConstrainULongRange`, optional): The bits per sample of the audio.
        channel_count (:obj:`int` or :obj:`ConstrainULongRange`, optional): The channels of the audio.
        echo_cancellation (:obj:`bool` or :obj:`ConstrainBooleanOrDOMStringParameters`, optional): Whether echo is
            cancelled.
        auto_gain_control (:obj:`bool` or :obj:`ConstrainBooleanParameters`, optional): Whether the gain is
            controlled automatically.
        noise_suppression (:obj:`bool` or :obj:`ConstrainBooleanParameters`, optional): Whether noise is suppressed.
        facing_mode (:obj:`str` or :obj:`ConstrainDOMStringParameters`, optional): Where the camera faces.
        latency (:obj:`float` or :obj:`ConstrainDoubleRange`, optional): The latency of the audio in seconds.
        background_blur (:obj:`bool` or :obj:`ConstrainBooleanParameters`, optional): Whether the background is
            blurred.
    """

    _dictionaries: ClassVar = {
        'width': ConstrainULongRange,
        'height': ConstrainULongRange,
        'aspect_ratio': ConstrainDoubleRange,
        'frame_rate': ConstrainDoubleRange,
        'resize_mode': ConstrainDOMStringParameters,
        'device_id': ConstrainDOMStringParameters,
        'group_id': ConstrainDOMStringParameters,
        'sample_rate': ConstrainULongRange,
        'sample_size': ConstrainULongRange,
        'channel_count': ConstrainULongRange,
        'echo_cancellation': ConstrainBooleanOrDOMStringParameters,
        'auto_gain_control': ConstrainBooleanParameters,
        'noise_suppression': ConstrainBooleanParameters,
        'facing_mode': ConstrainDOMStringParameters,
        'latency': ConstrainDoubleRange,
        'background_blur': ConstrainBooleanParameters,
    }

    width: ConstrainULong | None = None
    height: ConstrainULong | None = None
    aspect_ratio: ConstrainDouble | None = None
    frame_rate: ConstrainDouble | None = None
    resize_mode: ConstrainDOMString | None = None
    device_id: ConstrainDOMString | None = None
    group_id: ConstrainDOMString | None = None
    sample_rate: ConstrainULong | None = None
    sample_size: ConstrainULong | None = None
    channel_count: ConstrainULong | None = None
    echo_cancellation: ConstrainBooleanOrDOMString | None = None
    auto_gain_control: ConstrainBoolean | None = None
    noise_suppression: ConstrainBoolean | None = None
    facing_mode: ConstrainDOMString | None = None
    latency: ConstrainDouble | None = None
    background_blur: ConstrainBoolean | None = None

    #: Alias for :attr:`aspect_ratio`
    aspectRatio: ClassVar[Alias[ConstrainDouble | None]] = alias('aspect_ratio')
    #: Alias for :attr:`frame_rate`
    frameRate: ClassVar[Alias[ConstrainDouble | None]] = alias('frame_rate')
    #: Alias for :attr:`resize_mode`
    resizeMode: ClassVar[Alias[ConstrainDOMString | None]] = alias('resize_mode')
    #: Alias for :attr:`device_id`
    deviceId: ClassVar[Alias[ConstrainDOMString | None]] = alias('device_id')
    #: Alias for :attr:`group_id`
    groupId: ClassVar[Alias[ConstrainDOMString | None]] = alias('group_id')
    #: Alias for :attr:`sample_rate`
    sampleRate: ClassVar[Alias[ConstrainULong | None]] = alias('sample_rate')
    #: Alias for :attr:`sample_size`
    sampleSize: ClassVar[Alias[ConstrainULong | None]] = alias('sample_size')
    #: Alias for :attr:`channel_count`
    channelCount: ClassVar[Alias[ConstrainULong | None]] = alias('channel_count')
    #: Alias for :attr:`echo_cancellation`
    echoCancellation: ClassVar[Alias[ConstrainBooleanOrDOMString | None]] = alias('echo_cancellation')
    #: Alias for :attr:`auto_gain_control`
    autoGainControl: ClassVar[Alias[ConstrainBoolean | None]] = alias('auto_gain_control')
    #: Alias for :attr:`noise_suppression`
    noiseSuppression: ClassVar[Alias[ConstrainBoolean | None]] = alias('noise_suppression')
    #: Alias for :attr:`facing_mode`
    facingMode: ClassVar[Alias[ConstrainDOMString | None]] = alias('facing_mode')
    #: Alias for :attr:`background_blur`
    backgroundBlur: ClassVar[Alias[ConstrainBoolean | None]] = alias('background_blur')


@dataclass
class MediaTrackConstraints(MediaTrackConstraintSet):
    """The constraints of a track, as given to :meth:`webrtc.MediaStreamTrack.apply_constraints`.

    They're also given per track to :meth:`webrtc.MediaDevices.get_user_media`. The members are the ones of
    :obj:`MediaTrackConstraintSet`, plus :attr:`advanced`.

    See :mdn:`MediaTrackConstraints`.

    Args:
        advanced (:obj:`list` of :obj:`MediaTrackConstraintSet`, optional): More sets to try in order after the basic
            one. A set is applied only if all of it can be satisfied. A set that can't be satisfied is skipped and
            doesn't fail the constraints.
    """

    _dictionaries: ClassVar = {**MediaTrackConstraintSet._dictionaries, 'advanced': MediaTrackConstraintSet}

    advanced: list[MediaTrackConstraintSet] | None = None


@dataclass
class MediaStreamConstraints(Dictionary):
    """Which tracks :meth:`webrtc.MediaDevices.get_user_media` returns, and their constraints.

    At least one of the two must be requested. See :mdn:`MediaDevices/getUserMedia`.

    Args:
        video (:obj:`bool` or :obj:`MediaTrackConstraints`, optional): Whether to get a video track, and its
            constraints.
        audio (:obj:`bool` or :obj:`MediaTrackConstraints`, optional): Whether to get an audio track, and its
            constraints.
    """

    video: bool | MediaTrackConstraints = False
    audio: bool | MediaTrackConstraints = False

    _dictionaries: ClassVar = {'video': MediaTrackConstraints, 'audio': MediaTrackConstraints}
