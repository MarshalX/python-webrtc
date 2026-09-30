#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, List, Optional

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

if TYPE_CHECKING:
    import webrtc


class RTCRtpReceiver(WebRTCObject):
    """The :obj:`webrtc.RTCRtpReceiver` interface of the WebRTC API manages the reception and decoding of data
    for a :obj:`webrtc.MediaStreamTrack` on an :obj:`webrtc.RTCPeerConnection`."""

    _class = wrtc.RTCRtpReceiver

    def _sources(self, synchronization: bool) -> List['webrtc.RTCRtpContributingSource']:
        cls = RTCRtpSynchronizationSource if synchronization else RTCRtpContributingSource
        # each native source starts with whether it's an SSRC
        return [cls._from_native(source) for source in self._native_obj._getSources() if source[0] == synchronization]

    @property
    def track(self) -> 'webrtc.MediaStreamTrack':
        """:obj:`webrtc.MediaStreamTrack`: The :obj:`webrtc.MediaStreamTrack` associated with the current
        :obj:`webrtc.RTCRtpReceiver` instance."""
        from webrtc import MediaStreamTrack

        return MediaStreamTrack._wrap(self._native_obj.track)

    @property
    def transport(self) -> Optional['webrtc.RTCDtlsTransport']:
        """:obj:`webrtc.RTCDtlsTransport`, optional: An object representing the underlying transport being used by
        the receiver to exchange packets with the remote peer, or :obj:`None` if the receiver isn't yet connected
        to transport."""
        from webrtc import RTCDtlsTransport

        return RTCDtlsTransport._wrap_optional(self._native_obj.transport)

    @property
    def jitter_buffer_target(self) -> Optional[float]:
        """:obj:`float`, optional: How many milliseconds of media the receiver should buffer (0 to 4000),
        trading latency for smoothness. :obj:`None` for the default."""
        return self._native_obj.jitterBufferTarget

    @jitter_buffer_target.setter
    def jitter_buffer_target(self, value: Optional[float]):
        if value is not None and not 0 <= value <= 4000:
            raise InvalidRangeError(f'jitter_buffer_target must be from 0 to 4000 milliseconds, not {value}')
        self._native_obj.jitterBufferTarget = value

    def get_parameters(self) -> 'webrtc.RTCRtpReceiveParameters':
        """Returns the parameters the receiver receives with.

        Returns:
            :obj:`webrtc.RTCRtpReceiveParameters`: The parameters.
        """
        return RTCRtpReceiveParameters._from_native(self._native_obj.getParameters())

    @staticmethod
    def get_capabilities(kind: 'webrtc.MediaType') -> Optional['webrtc.RTCRtpCapabilities']:
        """Returns the codecs and header extensions receivers of a kind support.

        Args:
            kind (:obj:`webrtc.MediaType`): Audio or video.

        Returns:
            :obj:`webrtc.RTCRtpCapabilities`, optional: The capabilities, :obj:`None` for another kind.
        """
        return RTCRtpCapabilities._supported(wrtc.RTCRtpReceiver, kind)

    async def get_stats(self) -> 'webrtc.RTCStatsReport':
        """Collects the stats of the receiver, and of the objects its stats refer to.

        Returns:
            :obj:`webrtc.RTCStatsReport`: The stats.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the connection is closed.
        """
        return RTCStatsReport._from_native(await call_native(self._native_obj.getStats), [self])

    def get_synchronization_sources(self) -> List['webrtc.RTCRtpSynchronizationSource']:
        """Returns the synchronization sources (SSRCs) of the media received in the last 10 seconds.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpSynchronizationSource`: The sources, the most recent first.
        """
        return self._sources(synchronization=True)

    def get_contributing_sources(self) -> List['webrtc.RTCRtpContributingSource']:
        """Returns the contributing sources (CSRCs, like the participants mixed by a conference server) of the
        media received in the last 10 seconds.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpContributingSource`: The sources, the most recent first.
        """
        return self._sources(synchronization=False)

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
