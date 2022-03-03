#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING

from webrtc import wrtc, WebRTCObject

if TYPE_CHECKING:
    import webrtc


class RTCDtlsTransport(WebRTCObject):
    """The :obj:`webrtc.RTCDtlsTransport` interface provides access to information about the Datagram Transport
    Layer Security (DTLS) transport over which a :obj:`webrtc.RTCPeerConnection`'s RTP and RTCP packets are sent and
    received by its :obj:`webrtc.RTCRtpSender` and :obj:`webrtc.RTCRtpReceiver` objects."""

    _class = wrtc.RTCDtlsTransport

    @property
    def ice_transport(self) -> 'webrtc.RTCIceTransport':
        """:obj:`webrtc.RTCIceTransport`: Returns a reference to the underlying :obj:`webrtc.RTCIceTransport` object."""
        return self._native_obj.iceTransport

    @property
    def state(self) -> 'webrtc.DtlsTransportState':
        """:obj:`webrtc.DtlsTransportState`: Returns a member of :obj:`webrtc.DtlsTransportState` which describes the
        underlying Datagram Transport Layer Security (DTLS) transport state."""
        return self._native_obj.state

    #: Alias for :attr:`ice_transport`
    iceTransport = ice_transport
