#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStreamTrack of Media Capture and Streams, and the constraints of its synthetic sources."""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Any

from webrtc import (
    DoubleRange,
    MediaTrackCapabilities,
    MediaTrackConstraints,
    MediaTrackSettings,
    OverconstrainedError,
    ULongRange,
    WebRTCObject,
    wrtc,
)
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc

#: The device of the video tracks of :func:`webrtc.get_user_media`
CAMERA_DEVICE_ID = 'synthetic-camera'
#: The device of the audio tracks of :func:`webrtc.get_user_media`
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
)


def _satisfied(value: object, capability: object, current: float | str | None) -> bool:
    """Whether the required parts of a constraint (exact, min, max) are satisfiable.

    They're satisfiable within the capability of the source if it has one, by the current setting if it doesn't.

    Returns:
        :obj:`bool`: Whether they are.
    """
    if not isinstance(value, dict) or all(value.get(key) is None for key in ('exact', 'min', 'max')):
        return True
    if isinstance(capability, (ULongRange, DoubleRange)):
        return _within_range(value, capability)
    if capability is None:
        return _satisfied_by_setting(value, current)
    return _matches(value.get('exact'), capability)


def _within_range(value: dict[str, float], capability: ULongRange | DoubleRange) -> bool:
    exact, low, high = value.get('exact'), value.get('min'), value.get('max')
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


def _satisfied_by_setting(value: dict[str, float], current: float | str | None) -> bool:
    if current is None or not _matches(value.get('exact'), current):
        return False
    low, high = value.get('min'), value.get('max')
    return (low is None or low <= current) and (high is None or current <= high)


def _selected(value: float | dict[str, float] | None, current: float, capability: object = None) -> float:
    """The value a constraint selects (exact, ideal or current), the nearest within its range and the capability."""
    low, high = float('-inf'), float('inf')
    if isinstance(capability, (ULongRange, DoubleRange)):
        low = capability.min if capability.min is not None else low
        high = capability.max if capability.max is not None else high
    if value is None:
        selected = current
    elif not isinstance(value, dict):
        selected = value
    elif value.get('exact') is not None:
        selected = value['exact']
    else:
        low = max(low, value['min']) if value.get('min') is not None else low
        high = min(high, value['max']) if value.get('max') is not None else high
        selected = value['ideal'] if value.get('ideal') is not None else current
    return min(max(selected, low), high)


# the members of constraints that are numbers: unsigned longs, and restricted doubles
_ULONG_CONSTRAINTS = ('width', 'height', 'sample_rate', 'sample_size', 'channel_count')
_DOUBLE_CONSTRAINTS = ('aspect_ratio', 'frame_rate')


def _check_numbers(constraint_set: MediaTrackConstraints) -> None:
    """The WebIDL types of the numbers of a constraint set: finite, and not negative for unsigned longs."""
    for name in _ULONG_CONSTRAINTS + _DOUBLE_CONSTRAINTS:
        value = getattr(constraint_set, name)
        members = [value.get(key) for key in ('exact', 'ideal', 'min', 'max')] if isinstance(value, dict) else [value]
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
    constraint_set: MediaTrackConstraints, capabilities: MediaTrackCapabilities, settings: MediaTrackSettings
) -> str | None:
    """The name of the first constraint of the set that can't be satisfied, if any."""
    for name in _CONSTRAINABLE:
        value = getattr(constraint_set, name)
        if value is not None and not _satisfied(value, getattr(capabilities, name), getattr(settings, name)):
            return name
    return None


class MediaStreamTrack(WebRTCObject[wrtc.MediaStreamTrack], EventTarget):
    """A single audio or video track of media, within a stream.

    Events (see :meth:`on`):
        ``mute`` and ``unmute`` (:obj:`webrtc.Event`): :attr:`muted` changed: a remote track is muted until media
        arrives, and when it's no longer negotiated.
        ``ended`` (:obj:`webrtc.Event`): The track ended, other than with :meth:`stop`, like when the remote peer
        stopped sending it.
    """

    _class = wrtc.MediaStreamTrack
    _events = ('mute', 'unmute', 'ended')

    def _on_event(self, name: str, *args: object) -> None:
        # muted changes along with the events
        if name in {'mute', 'unmute'}:
            (muted,) = args
            self._native_obj._surfaceMuted(muted)
        elif name == 'ended':
            self._native_obj._surfaceEnded()

    @property
    def enabled(self) -> bool:
        """:obj:`bool`: Whether the track renders its source, rather than silence or blackness.

        Once the track is disconnected, it can still be changed, to no effect.
        """
        return self._native_obj.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._native_obj.enabled = value

    @property
    def id(self) -> str:
        """:obj:`str`: A unique identifier (GUID) for the track."""
        return self._native_obj.id

    @property
    def label(self) -> str:
        """:obj:`str`: The label of the source, ``'remote audio'`` or ``'remote video'`` for a remote track."""
        return self._native_obj.label

    @property
    def kind(self) -> webrtc.MediaType:
        """:obj:`webrtc.MediaType`: The kind of media, audio or video, even once detached from the source."""
        return self._native_obj.kind

    @property
    def ready_state(self) -> webrtc.MediaStreamTrackState:
        """:obj:`webrtc.MediaStreamTrackState`: Returns an enumerated value giving the status of the track."""
        return self._native_obj.readyState

    @property
    def muted(self) -> bool:
        """:obj:`bool`: Whether the track can't provide media, due to a technical issue."""
        return self._native_obj.muted

    @property
    def content_hint(self) -> str:
        """:obj:`str`: What the track carries, which encoders optimize for, empty if unknown (the default).

        ``'speech'``, ``'speaking'`` or ``'music'`` for audio, ``'motion'``, ``'detail'`` or ``'text'`` for video.
        Other values, and the ones of the other kind, are ignored.
        """
        return self._native_obj.contentHint

    @content_hint.setter
    def content_hint(self, value: str) -> None:
        self._native_obj.contentHint = str(value)

    def get_settings(self) -> MediaTrackSettings:
        """Returns what the track carries.

        The size and frame rate of the frames last seen, the format of the audio, and the device of the tracks of
        :func:`webrtc.get_user_media`.

        Returns:
            :obj:`webrtc.MediaTrackSettings`: The settings.
        """
        native: dict[str, Any] = self._native_obj._settings()
        settings = MediaTrackSettings()
        if 'width' in native:
            settings.width, settings.height = native['width'], native['height']
            settings.aspect_ratio = native['width'] / native['height'] if native['height'] else None
            settings.frame_rate = native.get('frame_rate')
        if 'sample_rate' in native:
            settings.sample_rate = native['sample_rate']
            settings.sample_size = native['sample_size']
            settings.channel_count = native['channel_count']
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

        The synthetic camera and microphone of :func:`webrtc.get_user_media` have capabilities, other tracks (remote,
        generated) have none.

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
        """Returns the constraints applied last, with :meth:`apply_constraints` or :func:`webrtc.get_user_media`.

        Returns:
            :obj:`webrtc.MediaTrackConstraints`: The constraints, none by default.
        """
        constraints = self._native_obj._constraints
        return constraints if constraints is not None else MediaTrackConstraints()

    def apply_constraints(
        self, constraints: MediaTrackConstraints | dict[str, Any] | None = None
    ) -> asyncio.Future[None]:
        """Applies constraints to the track.

        The synthetic camera of :func:`webrtc.get_user_media` changes its size and frame rate, the source of other
        tracks stays as it is.

        Args:
            constraints (:obj:`webrtc.MediaTrackConstraints` or :obj:`dict`, optional): The constraints, none to
                remove them.

        Returns:
            :obj:`asyncio.Future`: Done once applied, failed with :obj:`webrtc.OverconstrainedError` if a required
            constraint can't be satisfied, which leaves the track as it was.
        """
        future = asyncio.get_running_loop().create_future()
        try:
            self._apply_constraints(MediaTrackConstraints._parse(constraints))
            future.set_result(None)
        except (OverconstrainedError, TypeError) as e:
            future.set_exception(e)
        return future

    def _apply_constraints(self, constraints: MediaTrackConstraints) -> None:
        advanced = [MediaTrackConstraints._parse(constraint_set) for constraint_set in constraints.advanced or ()]
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
                self._native_obj._reconfigureCamera(int(width), int(height), float(frame_rate))
        self._native_obj._constraints = constraints

    def clone(self) -> webrtc.MediaStreamTrack:
        """Returns a duplicate of the :obj:`webrtc.MediaStreamTrack`."""
        return self._wrap(self._native_obj.clone())

    def stop(self) -> None:
        """Stops the track, detached from its source: its :attr:`ready_state` becomes ended."""
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
