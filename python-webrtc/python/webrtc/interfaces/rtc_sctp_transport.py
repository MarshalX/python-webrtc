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


class RTCSctpTransport(WebRTCObject):
    """The :obj:`webrtc.RTCSctpTransport` interface provides information which describes a Stream Control
    Transmission Protocol (SCTP) transport. This provides information about limitations of the transport,
    but also provides a way to access the underlying Datagram Transport Layer Security (DTLS) transport over
    which SCTP packets for all of an :obj:`webrtc.RTCPeerConnection`'s data channels are sent and received."""

    _class = wrtc.RTCSctpTransport

    @property
    def transport(self) -> 'webrtc.RTCDtlsTransport':
        """:obj:`webrtc.RTCDtlsTransport`: An object representing the DTLS transport used for the transmission
        and receipt of data packets."""
        from webrtc import RTCDtlsTransport

        return RTCDtlsTransport._wrap(self._native_obj.transport)

    @property
    def state(self) -> 'webrtc.SctpTransportState':
        """:obj:`webrtc.SctpTransportState`: A enumerated value indicating the state of the SCTP transport."""
        return self._native_obj.state

    @property
    def max_message_size(self) -> Optional[float]:
        """:obj:`float`, optional: An integer value indicating the maximum size, in bytes, of a message which can be
        sent using the :attr:`webrtc.RTCDataChannel.send` method."""
        return self._native_obj.maxMessageSize

    @property
    def max_channels(self) -> Optional[int]:
        """:obj:`int`, optional: An integer value indicating the maximum number of :obj:`webrtc.RTCDataChannel` that
        can be open simultaneously."""
        return self._native_obj.maxChannels

    #: Alias for :attr:`max_message_size`
    maxMessageSize = max_message_size
    #: Alias for :attr:`max_channels`
    maxChannels = max_channels
