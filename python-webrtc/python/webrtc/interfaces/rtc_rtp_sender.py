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


class RTCRtpSender(WebRTCObject):
    """The :obj:`webrtc.MediaStreamTrack` interface represents a single media track within a stream;
    typically, these are audio or video tracks, but other track types may exist as well.
    """

    _class = wrtc.RTCRtpSender

    @property
    def track(self) -> Optional['webrtc.MediaStreamTrack']:
        """:obj:`webrtc.MediaStreamTrack`, optional: The :obj:`webrtc.MediaStreamTrack` which is being handled by
        the :obj:`webrtc.RTCRtpSender`. If track is :obj:`None`, the :obj:`webrtc.RTCRtpSender`
        doesn't transmit anything."""
        from webrtc import MediaStreamTrack

        track = self._native_obj.track
        if track:
            return MediaStreamTrack._wrap(track)

        return None

    @property
    def transport(self) -> Optional['webrtc.RTCDtlsTransport']:
        """:obj:`webrtc.RTCDtlsTransport`: An object representing the underlying transport being used by the sender
        to exchange packets with the remote peer, or null if the sender isn't yet connected to transport."""
        from webrtc import RTCDtlsTransport

        transport = self._native_obj.transport
        if transport:
            return RTCDtlsTransport._wrap(transport)

        return None
