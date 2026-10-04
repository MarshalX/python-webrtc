#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStreamTrack of Media Capture and Streams, and the constraints of its synthetic sources."""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Literal, Union, cast

from typing_extensions import override

from webrtc import (
    ConstrainBooleanOrDOMStringParameters,
    ConstrainBooleanParameters,
    ConstrainDOMStringParameters,
    ConstrainDoubleRange,
    ConstrainULongRange,
    DoubleRange,
    Event,
    MediaTrackCapabilities,
    MediaTrackConstraints,
    MediaTrackConstraintSet,
    MediaTrackSettings,
    OverconstrainedError,
    ULongRange,
    WebRTCObject,
    wrtc,
)
from webrtc.utils.events import UniformEventTarget

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
    device_id=CAMERA_DEVICE_ID,
    group_id=_GROUP_ID,
)
_MICROPHONE_CAPABILITIES = MediaTrackCapabilities(
    sample_rate=ULongRange(48000, 48000),
    sample_size=ULongRange(16, 16),
    channel_count=ULongRange(1, 1),
    echo_cancellation=[False],
    auto_gain_control=[False],
    noise_suppression=[False],
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
)


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
    if isinstance(capability, list):
        return exact in capability
    return exact == capability or (isinstance(exact, list) and capability in exact)


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


def _check_numbers(constraint_set: MediaTrackConstraintSet) -> None:
    """The WebIDL types of the numbers of a constraint set: finite, and not negative for unsigned longs."""
    for name in _ULONG_CONSTRAINTS + _DOUBLE_CONSTRAINTS:
        value = getattr(constraint_set, name)
        members = [value.exact, value.ideal, value.min, value.max] if isinstance(value, _RANGES) else [value]
        unsigned = name in _ULONG_CONSTRAINTS
        for member in members:
            if member is not None and not _valid_number(member, unsigned=unsigned):
                kind = 'a finite number that is not negative' if unsigned else 'a finite number'
                msg = f'{name} must be {kind}, not {member!r}'
                raise TypeError(msg)


def _valid_number(member: object, *, unsigned: bool) -> bool:
    if isinstance(member, bool) or not isinstance(member, (int, float)):
        return False
    return math.isfinite(member) and not (unsigned and member < 0)


def _unsatisfied(
    constraint_set: MediaTrackConstraintSet, capabilities: MediaTrackCapabilities, settings: MediaTrackSettings
) -> str | None:
    """The name of the first constraint of the set that can't be satisfied, if any."""
    for name in _CONSTRAINABLE:
        value = getattr(constraint_set, name)
        if value is not None and not _satisfied(value, getattr(capabilities, name), getattr(settings, name)):
            return name
    return None


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
        """:obj:`str`: The label of the source. It's empty for a local track.

        A remote track has ``'remote audio'`` or ``'remote video'``. A clone keeps the label.

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
        :meth:`webrtc.MediaDevices.get_user_media` also report the device. Members that aren't known yet are
        :obj:`None`.

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
            required constraint can't be satisfied, or with :obj:`TypeError` if a number isn't finite or an integer
            is negative. A failure leaves the track as it was.
        """
        future = asyncio.get_running_loop().create_future()
        try:
            self._apply_constraints(constraints if constraints is not None else MediaTrackConstraints())
            future.set_result(None)
        except (OverconstrainedError, TypeError) as e:
            future.set_exception(e)
        return future

    def _apply_constraints(self, constraints: MediaTrackConstraints) -> None:
        advanced: list[MediaTrackConstraintSet] = list(constraints.advanced) if constraints.advanced is not None else []
        for constraint_set in [constraints, *advanced]:
            _check_numbers(constraint_set)
        if self.ready_state == 'ended':
            return
        capabilities = self.get_capabilities()
        settings = self.get_settings()
        failed = _unsatisfied(constraints, capabilities, settings)
        if failed is not None:
            raise OverconstrainedError(failed, f"The constraint {failed} can't be satisfied")

        camera = self._native_obj._camera()
        if camera is not None:
            width, height, frame_rate = camera
            # the advanced sets that can be satisfied apply in order after the basic one
            satisfiable = [c for c in advanced if _unsatisfied(c, capabilities, settings) is None]
            for constraint_set in [constraints, *satisfiable]:
                width = _selected(constraint_set.width, width, capabilities.width)
                height = _selected(constraint_set.height, height, capabilities.height)
                frame_rate = _selected(constraint_set.frame_rate, frame_rate, capabilities.frame_rate)
            if (width, height, frame_rate) != camera:
                _ = self._native_obj._reconfigureCamera(int(width), int(height), float(frame_rate))
        self._native_obj._constraints = constraints

    def clone(self) -> webrtc.MediaStreamTrack:
        """Returns a new track with a new :attr:`id`, sharing the source of this one.

        The clone keeps :attr:`label` and the device, and is ended if this track is.

        See :mdn:`MediaStreamTrack/clone`.

        Returns:
            :obj:`webrtc.MediaStreamTrack`: The clone.
        """
        return self._wrap(self._native_obj.clone())

    def stop(self) -> None:
        """Stops the track and detaches it from its source. :attr:`ready_state` becomes ``ended`` with no event.

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
