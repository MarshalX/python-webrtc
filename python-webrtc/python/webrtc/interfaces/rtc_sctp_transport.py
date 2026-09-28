#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Optional

from webrtc import WebRTCObject, wrtc
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc


class RTCSctpTransport(WebRTCObject, EventTarget):
    """The :obj:`webrtc.RTCSctpTransport` interface provides information which describes a Stream Control
    Transmission Protocol (SCTP) transport. This provides information about limitations of the transport,
    but also provides a way to access the underlying Datagram Transport Layer Security (DTLS) transport over
    which SCTP packets for all of an :obj:`webrtc.RTCPeerConnection`'s data channels are sent and received.

    Events (see :meth:`on`):
        ``statechange`` (:obj:`webrtc.Event`): :attr:`state` changed.
    """

    _class = wrtc.RTCSctpTransport
    _events = ('statechange',)

    def _on_event(self, name: str, *args):
        (state,) = args
        # the state changes along with its event
        self._native_obj._surfaceState(state)

    @property
    def transport(self) -> 'webrtc.RTCDtlsTransport':
        """:obj:`webrtc.RTCDtlsTransport`: An object representing the DTLS transport used for the transmission
        and receipt of data packets."""
        from webrtc import RTCDtlsTransport

        return RTCDtlsTransport._wrap(self._native_obj.transport)

    @property
    def state(self) -> 'webrtc.SctpTransportState':
        """:obj:`webrtc.SctpTransportState`: An enumerated value indicating the state of the SCTP transport."""
        return self._native_obj.state

    @property
    def max_message_size(self) -> Optional[float]:
        """:obj:`float`, optional: The maximum size, in bytes, of a message which can be sent using the
        :meth:`webrtc.RTCDataChannel.send` method."""
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
