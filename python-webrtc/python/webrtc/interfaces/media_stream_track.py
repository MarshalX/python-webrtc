#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStreamTrack of Media Capture and Streams, and the constraints of its synthetic sources."""

from __future__ import annotations

import asyncio
import copy
import math
from typing import TYPE_CHECKING, Literal, TypeVar, Union, cast

from typing_extensions import override

import wrtc
from webrtc.base import WebRTCObject
from webrtc.exceptions import OverconstrainedError
from webrtc.models.events import Event
from webrtc.models.media_track_constraints import (
    ConstrainBooleanOrDOMStringParameters,
    ConstrainBooleanParameters,
    ConstrainDOMStringParameters,
    ConstrainDoubleRange,
    ConstrainULongRange,
    DoubleRange,
    MediaTrackCapabilities,
    MediaTrackConstraints,
    MediaTrackConstraintSet,
    MediaTrackSettings,
    ULongRange,
)
from webrtc.utils.events import UniformEventTarget
from webrtc.utils.names import camel_case

if TYPE_CHECKING:
    import webrtc

_Parameters = Union[
    ConstrainULongRange,
    ConstrainDoubleRange,
    ConstrainBooleanParameters,
    ConstrainDOMStringParameters,
    ConstrainBooleanOrDOMStringParameters,
]

#: The device ID of the synthetic camera, which feeds the video tracks of :meth:`webrtc.MediaDevices.get_user_media`
CAMERA_DEVICE_ID = 'synthetic-camera'
#: The device ID of the synthetic microphone, which feeds the audio tracks of
#: :meth:`webrtc.MediaDevices.get_user_media`
MICROPHONE_DEVICE_ID = 'synthetic-microphone'
_GROUP_ID = 'synthetic'

_CAMERA_CAPABILITIES = MediaTrackCapabilities(
    width=ULongRange(1, 4096),
    height=ULongRange(1, 4096),
    aspect_ratio=DoubleRange(1 / 4096, 4096),
    frame_rate=DoubleRange(1, 120),
    resize_mode=['none'],
    facing_mode=[],
    device_id=CAMERA_DEVICE_ID,
    group_id=_GROUP_ID,
)
# sample rate, sample size, channel count
_MICROPHONE_FORMAT = (48000, 16, 1)
_MICROPHONE_LATENCY = 0.01  # a 10 ms libwebrtc frame
_MICROPHONE_CAPABILITIES = MediaTrackCapabilities(
    sample_rate=ULongRange(_MICROPHONE_FORMAT[0], _MICROPHONE_FORMAT[0]),
    sample_size=ULongRange(_MICROPHONE_FORMAT[1], _MICROPHONE_FORMAT[1]),
    channel_count=ULongRange(_MICROPHONE_FORMAT[2], _MICROPHONE_FORMAT[2]),
    echo_cancellation=[False],
    auto_gain_control=[False],
    noise_suppression=[False],
    latency=DoubleRange(_MICROPHONE_LATENCY, _MICROPHONE_LATENCY),
    voice_isolation=[False],
    device_id=MICROPHONE_DEVICE_ID,
    group_id=_GROUP_ID,
)

_CONSTRAINABLE = (
    'width',
    'height',
    'aspect_ratio',
    'frame_rate',
    'resize_mode',
    'device_id',
    'group_id',
    'sample_rate',
    'sample_size',
    'channel_count',
    'echo_cancellation',
    'auto_gain_control',
    'noise_suppression',
    'facing_mode',
    'latency',
    'background_blur',
    'voice_isolation',
)
# ignored by the other kind
_VIDEO_CONSTRAINTS = frozenset({
    'width',
    'height',
    'aspect_ratio',
    'frame_rate',
    'resize_mode',
    'facing_mode',
    'background_blur',
})
_AUDIO_CONSTRAINTS = frozenset({
    'sample_rate',
    'sample_size',
    'channel_count',
    'echo_cancellation',
    'auto_gain_control',
    'noise_suppression',
    'latency',
    'voice_isolation',
})


# the constraints with required parts, the others are ideal values
_PARAMETERS = (
    ConstrainULongRange,
    ConstrainDoubleRange,
    ConstrainBooleanParameters,
    ConstrainDOMStringParameters,
    ConstrainBooleanOrDOMStringParameters,
)
_RANGES = (ConstrainULongRange, ConstrainDoubleRange)


def _satisfied(value: object, capability: object, current: float | str | None) -> bool:
    """Whether the required parts of a constraint (exact, min, max) are satisfiable.

    They're satisfiable within the capability of the source if it has one, by the current setting if it doesn't.

    Returns:
        :obj:`bool`: Whether they are.
    """
    required = isinstance(value, _PARAMETERS) and any(
        getattr(value, name, None) is not None for name in ('exact', 'min', 'max')
    )
    if not required:
        return True
    if isinstance(value, _RANGES) and isinstance(capability, (ULongRange, DoubleRange)):
        return _within_range(value, capability)
    if capability is None:
        return _satisfied_by_setting(value, current)
    return _matches(value.exact, capability)


def _within_range(value: ConstrainULongRange | ConstrainDoubleRange, capability: ULongRange | DoubleRange) -> bool:
    exact, low, high = value.exact, value.min, value.max
    low_cap = capability.min if capability.min is not None else float('-inf')
    high_cap = capability.max if capability.max is not None else float('inf')
    exact_within = exact is None or low_cap <= exact <= high_cap
    bounds_within = (low is None or low <= high_cap) and (high is None or high >= low_cap)
    return exact_within and bounds_within and (low is None or high is None or low <= high)


def _matches(exact: object, capability: object) -> bool:
    """Whether an exact value (or one of a list of them) is the capability, or one of a list of them."""
    if exact is None:
        return True
    exacts = exact if isinstance(exact, list) else [exact]
    capabilities = capability if isinstance(capability, list) else [capability]
    return any(value in capabilities for value in exacts)


def _satisfied_by_setting(value: _Parameters, current: float | str | None) -> bool:
    if current is None or not _matches(value.exact, current):
        return False
    low, high = getattr(value, 'min', None), getattr(value, 'max', None)
    return (low is None or low <= current) and (high is None or current <= high)


def _selected(
    value: float | ConstrainULongRange | ConstrainDoubleRange | None, current: float, capability: object = None
) -> float:
    """The value a constraint selects (exact, ideal or current), the nearest within its range and the capability."""
    low, high = float('-inf'), float('inf')
    if isinstance(capability, (ULongRange, DoubleRange)):
        low = capability.min if capability.min is not None else low
        high = capability.max if capability.max is not None else high
    if value is None:
        selected = current
    elif not isinstance(value, _RANGES):
        selected = value
    elif value.exact is not None:
        selected = value.exact
    else:
        low = max(low, value.min) if value.min is not None else low
        high = min(high, value.max) if value.max is not None else high
        selected = value.ideal if value.ideal is not None else current
    return min(max(selected, low), high)


# the members of constraints that are numbers: unsigned longs, and restricted doubles
_ULONG_CONSTRAINTS = ('width', 'height', 'sample_rate', 'sample_size', 'channel_count')
_DOUBLE_CONSTRAINTS = ('aspect_ratio', 'frame_rate', 'latency')
_MAX_ULONG = 2**32 - 1

_SetT = TypeVar('_SetT', bound=MediaTrackConstraintSet)


def _clamped(member: object, name: str) -> int:
    """WebIDL [Clamp] unsigned long."""
    if isinstance(member, bool) or not isinstance(member, (int, float)):
        msg = f'{name} must be a number, not {member!r}'
        raise TypeError(msg)
    if math.isnan(member):
        return 0
    if math.isinf(member):
        return 0 if member < 0 else _MAX_ULONG
    return min(max(round(member), 0), _MAX_ULONG)


def _restricted(member: object, name: str) -> float:
    """WebIDL restricted double."""
    if isinstance(member, bool) or not isinstance(member, (int, float)) or not math.isfinite(member):
        msg = f'{name} must be a finite number, not {member!r}'
        raise TypeError(msg)
    return member


def _converted_set(constraint_set: _SetT) -> _SetT:
    """A copy with WebIDL-converted numbers."""
    converted = copy.copy(constraint_set)
    for name in _ULONG_CONSTRAINTS + _DOUBLE_CONSTRAINTS:
        value = getattr(constraint_set, name)
        convert = _clamped if name in _ULONG_CONSTRAINTS else _restricted
        if isinstance(value, _RANGES):
            value = copy.copy(value)
            parts = {part: getattr(value, part) for part in ('exact', 'ideal', 'min', 'max')}
            for part, member in ((p, m) for p, m in parts.items() if m is not None):
                setattr(value, part, convert(member, name))
            setattr(converted, name, value)
        elif value is not None:
            setattr(converted, name, convert(value, name))
    return converted


def _converted(constraints: MediaTrackConstraints) -> MediaTrackConstraints:
    """A copy with WebIDL-converted numbers, advanced sets included."""
    converted = _converted_set(constraints)
    if constraints.advanced is not None:
        converted.advanced = [_converted_set(c) for c in constraints.advanced]
    return converted


def _as_exact(constraint_set: MediaTrackConstraintSet) -> MediaTrackConstraintSet:
    """An advanced set, whose bare values are exact."""
    exact = copy.copy(constraint_set)
    for name in _CONSTRAINABLE:
        value: object = getattr(constraint_set, name)
        if value is not None and not isinstance(value, _PARAMETERS):
            constraint = cast('type[_Parameters]', MediaTrackConstraintSet._dictionaries[name])
            setattr(exact, name, constraint.from_json({'exact': value}))
    return exact


def _unsatisfied(
    constraint_set: MediaTrackConstraintSet,
    capabilities: MediaTrackCapabilities,
    settings: MediaTrackSettings,
    *,
    kind: str,
) -> str | None:
    """The WebIDL name of the first unsatisfiable constraint."""
    ignored = _AUDIO_CONSTRAINTS if kind == 'video' else _VIDEO_CONSTRAINTS
    for name in _CONSTRAINABLE:
        value = getattr(constraint_set, name)
        if name in ignored or value is None:
            continue
        if not _satisfied(value, getattr(capabilities, name), getattr(settings, name)):
            return camel_case(name)
    return None


def _camera_mode(
    constraints: MediaTrackConstraints,
    capabilities: MediaTrackCapabilities,
    settings: MediaTrackSettings,
    *,
    current: tuple[float, float, float],
) -> tuple[float, float, float]:
    """The camera size and frame rate: the basic set, then each satisfiable advanced set."""
    width, height, frame_rate = current
    advanced: list[MediaTrackConstraintSet] = []
    if constraints.advanced is not None:
        advanced = [_as_exact(c) for c in constraints.advanced]
    satisfiable = [c for c in advanced if _unsatisfied(c, capabilities, settings, kind='video') is None]
    for constraint_set in [constraints, *satisfiable]:
        width = _selected(constraint_set.width, width, capabilities.width)
        height = _selected(constraint_set.height, height, capabilities.height)
        frame_rate = _selected(constraint_set.frame_rate, frame_rate, capabilities.frame_rate)
    return width, height, frame_rate


class MediaStreamTrack(
    WebRTCObject[wrtc.MediaStreamTrack], UniformEventTarget[Literal['mute', 'unmute', 'ended'], Event]
):
    """A single audio or video track. It comes from a synthetic device or a generator, or from a remote peer.

    See :mdn:`MediaStreamTrack`.

    Events:
        mute and unmute (:obj:`webrtc.Event`): The value of :attr:`muted` changed. A remote track is muted
            until media arrives, and again when it's no longer negotiated.
        ended (:obj:`webrtc.Event`): The track ended for a reason other than :meth:`stop`, for example because
            the remote peer stopped sending it.

    An ended track fires no more events, so its handlers are released then.
    """

    _class = wrtc.MediaStreamTrack

    @override
    def _on_event(self, name: str, *args: object) -> None:
        # muted changes along with the events
        if name in {'mute', 'unmute'}:
            (muted,) = cast('tuple[bool]', args)
            self._native_obj._surfaceMuted(muted)
        elif name == 'ended':
            self._native_obj._surfaceEnded()

    @property
    def enabled(self) -> bool:
        """:obj:`bool`: Whether the track carries its source. A disabled track carries silence or black frames.

        It can still be set after the track has ended, but that has no effect.

        See :mdn:`MediaStreamTrack/enabled`.
        """
        return self._native_obj.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._native_obj.enabled = value

    @property
    def id(self) -> str:
        """:obj:`str`: The ID of the track. A remote track gets a random UUID and doesn't use the ID its peer gave.

        See :mdn:`MediaStreamTrack/id`.
        """
        return self._native_obj.id

    @property
    def label(self) -> str:
        """:obj:`str`: The label of the source. It's empty for a generated track.

        A track of :meth:`webrtc.MediaDevices.get_user_media` has the label of its device, and a remote track has
        ``'remote audio'`` or ``'remote video'``. A clone keeps the label.

        See :mdn:`MediaStreamTrack/label`.
        """
        return self._native_obj.label

    @property
    def kind(self) -> webrtc.MediaType:
        """:obj:`webrtc.MediaType`: Whether the track carries audio or video. It stays set after the track ends.

        See :mdn:`MediaStreamTrack/kind`.
        """
        return self._native_obj.kind

    @property
    def ready_state(self) -> webrtc.MediaStreamTrackState:
        """:obj:`webrtc.MediaStreamTrackState`: Whether the track is ``live`` or has ``ended``. Ending is final.

        See :mdn:`MediaStreamTrack/readyState`.
        """
        return self._native_obj.readyState

    @property
    def muted(self) -> bool:
        """:obj:`bool`: Whether the source can't provide media for now. A remote track is muted until media arrives.

        Unlike :attr:`enabled`, the application can't change it.

        See :mdn:`MediaStreamTrack/muted`.
        """
        return self._native_obj.muted

    @property
    def content_hint(self) -> str:
        """:obj:`str`: What the track carries, so encoders can optimize for it. The default is empty, for unknown.

        Audio accepts ``'speech'``, ``'speaking'`` and ``'music'``. Video accepts ``'motion'``, ``'detail'`` and
        ``'text'``. Other values are ignored, as are the values meant for the other kind.

        See :mdn:`MediaStreamTrack/contentHint`.
        """
        return self._native_obj.contentHint

    @content_hint.setter
    def content_hint(self, value: str) -> None:
        self._native_obj.contentHint = str(value)

    def get_settings(self) -> MediaTrackSettings:
        """Returns what the track carries now.

        The settings hold the size and frame rate of the last frames seen and the format of the audio. Tracks of
        :meth:`webrtc.MediaDevices.get_user_media` also report the device, and its format before media flows.
        Members that aren't known yet are :obj:`None`.

        See :mdn:`MediaStreamTrack/getSettings`.

        Returns:
            :obj:`webrtc.MediaTrackSettings`: The settings.
        """
        native = self._native_obj._settings()
        settings = MediaTrackSettings()
        # the size, and the format of the audio, come together
        width, height = native.get('width'), native.get('height')
        if width is not None and height is not None:
            settings.width, settings.height = width, height
            settings.aspect_ratio = width / height if height != 0 else None
            settings.frame_rate = native.get('frame_rate')
        if 'sample_rate' in native:
            settings.sample_rate = native.get('sample_rate')
            settings.sample_size = native.get('sample_size')
            settings.channel_count = native.get('channel_count')
        device = native.get('device')
        if device == 'camera':
            settings.resize_mode = 'none'
            settings.device_id, settings.group_id = CAMERA_DEVICE_ID, _GROUP_ID
        elif device == 'microphone':
            settings.device_id, settings.group_id = MICROPHONE_DEVICE_ID, _GROUP_ID
            settings.echo_cancellation = settings.auto_gain_control = settings.noise_suppression = False
            settings.voice_isolation = False
            settings.latency = _MICROPHONE_LATENCY
            if settings.sample_rate is None:
                settings.sample_rate, settings.sample_size, settings.channel_count = _MICROPHONE_FORMAT
        return settings

    def get_capabilities(self) -> MediaTrackCapabilities:
        """Returns what the source of the track can do.

        Only the synthetic camera and microphone of :meth:`webrtc.MediaDevices.get_user_media` have capabilities.
        For remote and generated tracks every member is :obj:`None`.

        See :mdn:`MediaStreamTrack/getCapabilities`.

        Returns:
            :obj:`webrtc.MediaTrackCapabilities`: The capabilities.
        """
        device = self._native_obj._settings().get('device')
        if device == 'camera':
            return _CAMERA_CAPABILITIES
        if device == 'microphone':
            return _MICROPHONE_CAPABILITIES
        return MediaTrackCapabilities()

    def get_constraints(self) -> MediaTrackConstraints:
        """Returns the last constraints of :meth:`apply_constraints` or :meth:`~webrtc.MediaDevices.get_user_media`.

        See :mdn:`MediaStreamTrack/getConstraints`.

        Returns:
            :obj:`webrtc.MediaTrackConstraints`: The constraints, none by default.
        """
        constraints = self._native_obj._constraints
        return constraints if constraints is not None else MediaTrackConstraints()

    def apply_constraints(self, constraints: MediaTrackConstraints | None = None) -> asyncio.Future[None]:
        """Applies constraints to the track, checking them against :meth:`get_capabilities` or the current settings.

        Only the synthetic camera of :meth:`webrtc.MediaDevices.get_user_media` reacts, by changing its size and
        frame rate. The sources of other tracks stay as they are, and the constraints are only checked and kept. On
        an ended track, only the numbers are checked and the constraints aren't kept.

        See :mdn:`MediaStreamTrack/applyConstraints`.

        Args:
            constraints (:obj:`webrtc.MediaTrackConstraints`, optional): The constraints, none to remove them.

        Returns:
            :obj:`asyncio.Future`: Done once applied. It fails with :obj:`webrtc.OverconstrainedError` if a
            required constraint can't be satisfied, or with :obj:`TypeError` if a double isn't finite. A failure
            leaves the track as it was.
        """
        future = asyncio.get_running_loop().create_future()
        try:
            self._apply_constraints(constraints if constraints is not None else MediaTrackConstraints())
            future.set_result(None)
        except (OverconstrainedError, TypeError) as e:
            future.set_exception(e)
        return future

    def _apply_constraints(self, constraints: MediaTrackConstraints) -> None:
        constraints = _converted(constraints)
        if self.ready_state == 'ended':
            return
        capabilities = self.get_capabilities()
        settings = self.get_settings()
        failed = _unsatisfied(constraints, capabilities, settings, kind=self.kind)
        if failed is not None:
            raise OverconstrainedError(failed, f"The constraint {failed} can't be satisfied")

        camera = self._native_obj._camera()
        if camera is not None:
            width, height, frame_rate = _camera_mode(constraints, capabilities, settings, current=camera)
            if (width, height, frame_rate) != camera:
                _ = self._native_obj._reconfigureCamera(int(width), int(height), float(frame_rate))
        self._native_obj._constraints = constraints

    def clone(self) -> webrtc.MediaStreamTrack:
        """Returns a new track with a new :attr:`id`, sharing the source of this one.

        The clone keeps :attr:`label`, :attr:`enabled`, :attr:`content_hint`, the constraints and the device, and ends
        if this does.

        See :mdn:`MediaStreamTrack/clone`.

        Returns:
            :obj:`webrtc.MediaStreamTrack`: The clone.
        """
        native = self._native_obj.clone()
        native._constraints = copy.deepcopy(self._native_obj._constraints)
        return self._wrap(native)

    def stop(self) -> None:
        """Stops the track and detaches it from its source. :attr:`ready_state` becomes ``ended`` with no event.

        Its sender sends silence or a black frame a second; clones keep their media.
        See :mdn:`MediaStreamTrack/stop`.
        """
        self._native_obj.stop()

    #: Alias for :attr:`ready_state`
    readyState = ready_state
    #: Alias for :attr:`content_hint`
    contentHint = content_hint
    #: Alias for :meth:`get_settings`
    getSettings = get_settings
    #: Alias for :meth:`get_capabilities`
    getCapabilities = get_capabilities
    #: Alias for :meth:`get_constraints`
    getConstraints = get_constraints
    #: Alias for :meth:`apply_constraints`
    applyConstraints = apply_constraints
