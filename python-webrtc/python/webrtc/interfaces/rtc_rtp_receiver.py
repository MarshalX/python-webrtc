#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The receiver that receives and decodes remote media."""

from __future__ import annotations

from typing import TypeVar

import webrtc
import wrtc
from webrtc.base import WebRTCObject
from webrtc.exceptions import InvalidRangeError
from webrtc.interfaces.rtc_rtp_sender import _native_transform
from webrtc.models.rtc_stats import RTCStatsReport
from webrtc.models.rtp_parameters import RTCRtpCapabilities, RTCRtpReceiveParameters
from webrtc.models.rtp_source import RTCRtpContributingSource, RTCRtpSynchronizationSource
from webrtc.utils.native_calls import call_native

_SourceT = TypeVar('_SourceT', bound=RTCRtpContributingSource)

#: The maximum jitter_buffer_target, in milliseconds
_MAX_JITTER_BUFFER_TARGET = 4000


class RTCRtpReceiver(WebRTCObject[wrtc.RTCRtpReceiver]):
    """Receives and decodes remote media into a :obj:`webrtc.MediaStreamTrack`.

    Each :obj:`webrtc.RTCRtpTransceiver` of an :obj:`webrtc.RTCPeerConnection` has one.

    See :mdn:`RTCRtpReceiver`.
    """

    _class = wrtc.RTCRtpReceiver

    def _sources(self, cls: type[_SourceT]) -> list[_SourceT]:
        synchronization = cls is RTCRtpSynchronizationSource
        # each native source starts with whether it's an SSRC
        return [cls._from_native(source) for source in self._native_obj._getSources() if source[0] == synchronization]

    @property
    def track(self) -> webrtc.MediaStreamTrack:
        """:obj:`webrtc.MediaStreamTrack`: The track the received media plays on. It exists from the start.

        See :mdn:`RTCRtpReceiver/track`.
        """
        return webrtc.MediaStreamTrack._wrap(self._native_obj.track)

    @property
    def transport(self) -> webrtc.RTCDtlsTransport | None:
        """:obj:`webrtc.RTCDtlsTransport`, optional: The transport the packets come over.

        It's :obj:`None` until there's one.
        See :mdn:`RTCRtpReceiver/transport`.
        """
        return webrtc.RTCDtlsTransport._wrap_optional(self._native_obj.transport)

    @property
    def transform(self) -> webrtc.RTCRtpScriptTransform | webrtc.RTCRtpSFrameDecryptor | None:
        """:obj:`webrtc.RTCRtpScriptTransform` or :obj:`webrtc.RTCRtpSFrameDecryptor`, optional: The frame transform.

        It changes the encoded frames before they're decoded. With :obj:`None`, frames are decoded as received.
        A transform serves one sender or receiver for its lifetime, so once attached it can't be set elsewhere.

        See :mdn:`RTCRtpReceiver/transform`.

        Raises:
            TypeError: If the value set isn't a transform of a receiver.
            webrtc.InvalidStateError: If the transform set had a sender or receiver.
        """
        native = self._native_obj.transform
        if isinstance(native, wrtc.SFrameTransform):
            return webrtc.RTCRtpSFrameDecryptor._wrap(native)
        return webrtc.RTCRtpScriptTransform._of_native(native)

    @transform.setter
    def transform(self, transform: webrtc.RTCRtpScriptTransform | webrtc.RTCRtpSFrameDecryptor | None) -> None:
        self._native_obj.transform = _native_transform(transform, webrtc.RTCRtpSFrameDecryptor)

    @property
    def jitter_buffer_target(self) -> float | None:
        """:obj:`float`, optional: The target delay of the jitter buffer in milliseconds, from 0 to 4000.

        A higher value adds latency for smoother playback. :obj:`None` leaves it to the receiver.

        See :mdn:`RTCRtpReceiver/jitterBufferTarget`.

        Raises:
            webrtc.InvalidRangeError: If the value set is outside 0 to 4000.
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

        See :mdn:`RTCRtpReceiver/getParameters`.

        Returns:
            :obj:`webrtc.RTCRtpReceiveParameters`: The parameters.
        """
        return RTCRtpReceiveParameters._from_native(self._native_obj.getParameters())

    @staticmethod
    def get_capabilities(kind: webrtc.MediaType | webrtc.MediaTypeValue) -> webrtc.RTCRtpCapabilities | None:
        """Returns the codecs and header extensions receivers of a kind support.

        See :mdn:`RTCRtpReceiver/getCapabilities_static`.

        Args:
            kind (:obj:`webrtc.MediaType`): Audio or video.

        Returns:
            :obj:`webrtc.RTCRtpCapabilities`, optional: The capabilities, or :obj:`None` for another kind.
        """
        return RTCRtpCapabilities._supported(wrtc.RTCRtpReceiver, kind)

    async def get_stats(self) -> webrtc.RTCStatsReport:
        """Collects the stats of the receiver and of the objects they refer to.

        See :mdn:`RTCRtpReceiver/getStats`.

        Returns:
            :obj:`webrtc.RTCStatsReport`: The stats.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
        """
        return RTCStatsReport._from_native(await call_native(self._native_obj.getStats), [self])

    def get_synchronization_sources(self) -> list[webrtc.RTCRtpSynchronizationSource]:
        """Returns the synchronization sources (SSRCs) of the media received in the last 10 seconds.

        See :mdn:`RTCRtpReceiver/getSynchronizationSources`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpSynchronizationSource`: The sources, the most recent first.
        """
        return self._sources(RTCRtpSynchronizationSource)

    def get_contributing_sources(self) -> list[webrtc.RTCRtpContributingSource]:
        """Returns the contributing sources (CSRCs) of the media received in the last 10 seconds.

        These are the original streams a mixer, like a conference server, combined into the received one.

        See :mdn:`RTCRtpReceiver/getContributingSources`.

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
