#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import datetime as dt
import logging
import operator
import re
from typing import TYPE_CHECKING, Generic, TypeVar, overload

import av
from pyee.asyncio import AsyncIOEventEmitter
from typing_extensions import override

if TYPE_CHECKING:
    import asyncio

    from typing_extensions import Self

    import webrtc

logger = logging.getLogger('webrtc.aiortc')
logger.addHandler(logging.NullHandler())

_ORTC = 'ORTC below ICE is not supported, the transports and channels come from RTCPeerConnection'
# attributes are never on the first line, and a newline before them is much faster to find than a line start
_MID = re.compile(r'\na=mid:(\S+)')
_MSID = re.compile(r'\na=msid:\S+ (\S+)')
_KINDS = ('audio', 'video')
_DEFAULT_SAMPLE_RATE = 48000
_T = TypeVar('_T')


class _ReadOnly(property, Generic[_T]):
    # a property that reads an attribute path such as '_native.label'
    def __init__(self, path: str) -> None:
        super().__init__(operator.attrgetter(path))

    if TYPE_CHECKING:

        @overload
        @override
        def __get__(self, instance: None, owner: type, /) -> Self: ...
        @overload
        def __get__(self, instance: object, owner: type | None = None, /) -> _T: ...


class _Resampler:
    def __init__(self) -> None:
        self._source: tuple[str, str, int] | None = None
        self._resampler: av.AudioResampler | None = None

    def resample(self, frame: av.AudioFrame, layout: str, rate: int, frame_size: int | None) -> list[av.AudioFrame]:
        source = (frame.format.name, frame.layout.name, frame.sample_rate)
        if self._resampler is None or source != self._source:
            # a resampler takes one input shape, and the first chunks of a track can have another rate
            self._source = source
            self._resampler = av.AudioResampler(format='s16', layout=layout, rate=rate, frame_size=frame_size)
        return self._resampler.resample(frame)


def _log_failure(call: str, task: asyncio.Future[None]) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.warning('%s failed: %s', call, task.exception())


def _datetime(milliseconds: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(milliseconds / 1000, dt.timezone.utc)


_E = TypeVar('_E', bound=AsyncIOEventEmitter)


def _emitter(cls: type[_E]) -> _E:
    # skips the public constructor, which is ORTC's
    emitter = cls.__new__(cls)
    AsyncIOEventEmitter.__init__(emitter)  # ruff: ignore[unnecessary-dunder-call]
    return emitter


def _ice_state(state: webrtc.RTCIceTransportState | webrtc.RTCIceConnectionState) -> str:
    # success is 'completed', and 'disconnected' (which only follows success) is never reported
    if state in {'connected', 'disconnected'}:
        return 'completed'
    return state.value


def _sdp_of(description: webrtc.RTCSessionDescription | None) -> str:
    return description.sdp if description is not None else ''


def _split(sdp: str) -> tuple[str, list[str]]:
    """The session part of an SDP and its media sections."""
    parts: list[str] = []
    start = 0
    index = sdp.find('\nm=')
    while index >= 0:
        parts.append(sdp[start : index + 1])
        start = index + 1
        index = sdp.find('\nm=', start)
    parts.append(sdp[start:])
    return parts[0], parts[1:]


def _media_section(sdp: str, mid: str | None) -> str:
    _, sections = _split(sdp)
    for section in sections:
        found = _MID.search(section)
        if found is not None and found.group(1) == mid:
            return section
    return ''


def _found(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.search(text)
    return found.group(1) if found is not None else None


def _media_kind(section: str) -> str:
    """The media of an ``m=`` section: audio, video or application."""
    return section[2:].split(' ', 1)[0]


def _media_lines(sdp: str) -> list[tuple[str, str | None]]:
    _, sections = _split(sdp)
    return [(_media_kind(section), _found(_MID, section)) for section in sections]


def _media_formats(section: str) -> list[str]:
    """The payload types of an ``m=`` line, which follow its media, port and protocol."""
    m_line = section.partition('\n')[0]
    return m_line.split()[3:]
