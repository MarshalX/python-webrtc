#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCRtpReceiver of WebRTC."""

from __future__ import annotations

from typing import TypeVar

import webrtc
from webrtc import (
    InvalidRangeError,
    RTCRtpCapabilities,
    RTCRtpContributingSource,
    RTCRtpReceiveParameters,
    RTCRtpSynchronizationSource,
    RTCStatsReport,
    WebRTCObject,
    wrtc,
)
from webrtc.utils.native_calls import call_native

_SourceT = TypeVar('_SourceT', bound=RTCRtpContributingSource)

#: The maximum jitter_buffer_target, in milliseconds
_MAX_JITTER_BUFFER_TARGET = 4000


class RTCRtpReceiver(WebRTCObject[wrtc.RTCRtpReceiver]):
    """Receives and decodes the media of a :obj:`webrtc.MediaStreamTrack` of an :obj:`webrtc.RTCPeerConnection`."""

    _class = wrtc.RTCRtpReceiver

    def _sources(self, cls: type[_SourceT]) -> list[_SourceT]:
        synchronization = cls is RTCRtpSynchronizationSource
        # each native source starts with whether it's an SSRC
        return [cls._from_native(source) for source in self._native_obj._getSources() if source[0] == synchronization]

    @property
    def track(self) -> webrtc.MediaStreamTrack:
        """:obj:`webrtc.MediaStreamTrack`: The track of the received media."""
        return webrtc.MediaStreamTrack._wrap(self._native_obj.track)

    @property
    def transport(self) -> webrtc.RTCDtlsTransport | None:
        """:obj:`webrtc.RTCDtlsTransport`, optional: The transport of the packets, :obj:`None` until there's one."""
        return webrtc.RTCDtlsTransport._wrap_optional(self._native_obj.transport)

    @property
    def jitter_buffer_target(self) -> float | None:
        """:obj:`float`, optional: How many milliseconds of media the receiver should buffer (0 to 4000).

        It trades latency for smoothness. :obj:`None` for the default.
        """
        return self._native_obj.jitterBufferTarget

    @jitter_buffer_target.setter
    def jitter_buffer_target(self, value: float | None) -> None:
        if value is not None and not 0 <= value <= _MAX_JITTER_BUFFER_TARGET:
            msg = f'jitter_buffer_target must be from 0 to 4000 milliseconds, not {value}'
            raise InvalidRangeError(msg)
        self._native_obj.jitterBufferTarget = value

    def get_parameters(self) -> webrtc.RTCRtpReceiveParameters:
        """Returns the parameters the receiver receives with.

        Returns:
            :obj:`webrtc.RTCRtpReceiveParameters`: The parameters.
        """
        return RTCRtpReceiveParameters._from_native(self._native_obj.getParameters())

    @staticmethod
    def get_capabilities(kind: webrtc.MediaType | webrtc.MediaTypeValue) -> webrtc.RTCRtpCapabilities | None:
        """Returns the codecs and header extensions receivers of a kind support.

        Args:
            kind (:obj:`webrtc.MediaType`): Audio or video.

        Returns:
            :obj:`webrtc.RTCRtpCapabilities`, optional: The capabilities, :obj:`None` for another kind.
        """
        return RTCRtpCapabilities._supported(wrtc.RTCRtpReceiver, kind)

    async def get_stats(self) -> webrtc.RTCStatsReport:
        """Collects the stats of the receiver, and of the objects its stats refer to.

        Returns:
            :obj:`webrtc.RTCStatsReport`: The stats.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
        """
        return RTCStatsReport._from_native(await call_native(self._native_obj.getStats), [self])

    def get_synchronization_sources(self) -> list[webrtc.RTCRtpSynchronizationSource]:
        """Returns the synchronization sources (SSRCs) of the media received in the last 10 seconds.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpSynchronizationSource`: The sources, the most recent first.
        """
        return self._sources(RTCRtpSynchronizationSource)

    def get_contributing_sources(self) -> list[webrtc.RTCRtpContributingSource]:
        """Returns the contributing sources (CSRCs) of the media received in the last 10 seconds.

        Like the participants a conference server mixes.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpContributingSource`: The sources, the most recent first.
        """
        return self._sources(RTCRtpContributingSource)

    #: Alias for :attr:`get_stats`
    getStats = get_stats
    #: Alias for :attr:`get_synchronization_sources`
    getSynchronizationSources = get_synchronization_sources
    #: Alias for :attr:`get_contributing_sources`
    getContributingSources = get_contributing_sources
    #: Alias for :attr:`jitter_buffer_target`
    jitterBufferTarget = jitter_buffer_target
    #: Alias for :attr:`get_parameters`
    getParameters = get_parameters
    #: Alias for :attr:`get_capabilities`
    getCapabilities = get_capabilities
