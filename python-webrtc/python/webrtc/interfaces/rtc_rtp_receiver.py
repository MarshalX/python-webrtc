#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Optional

from webrtc import wrtc, WebRTCObject

if TYPE_CHECKING:
    import webrtc


class RTCRtpReceiver(WebRTCObject):
    """The :obj:`webrtc.RTCRtpReceiver` interface of the WebRTC API manages the reception and decoding of data
    for a :obj:`webrtc.MediaStreamTrack` on an :obj:`webrtc.RTCPeerConnection`."""

    _class = wrtc.RTCRtpReceiver

    @property
    def track(self) -> 'webrtc.MediaStreamTrack':
        """:obj:`webrtc.MediaStreamTrack`: The :obj:`webrtc.MediaStreamTrack` associated with the current
        :obj:`webrtc.RTCRtpReceiver` instance."""
        from webrtc import MediaStreamTrack

        return MediaStreamTrack._wrap(self._native_obj.track)

    @property
    def transport(self) -> Optional['webrtc.RTCDtlsTransport']:
        """:obj:`webrtc.RTCDtlsTransport`: An object representing the underlying transport being used by the
        receiver to exchange packets with the remote peer, or null if the receiver isn't yet connected to transport."""
        from webrtc import RTCDtlsTransport

        transport = self._native_obj.transport
        if transport:
            return RTCDtlsTransport._wrap(transport)

        return None
