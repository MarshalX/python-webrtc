#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCSctpTransport of WebRTC."""

from __future__ import annotations

from typing import cast

from typing_extensions import override

import webrtc
from webrtc import WebRTCObject, wrtc
from webrtc.utils.events import EventTarget


class RTCSctpTransport(WebRTCObject[wrtc.RTCSctpTransport], EventTarget):
    """The Stream Control Transmission Protocol (SCTP) transport of a :obj:`webrtc.RTCPeerConnection`.

    It tells the limitations of the transport, and gives the Datagram Transport Layer Security (DTLS) transport
    over which the SCTP packets of all the data channels of the connection are sent and received.

    Events (see :meth:`on`):
        ``statechange`` (:obj:`webrtc.Event`): :attr:`state` changed.
    """

    _class = wrtc.RTCSctpTransport
    _events = ('statechange',)

    @override
    def _on_event(self, name: str, *args: object) -> None:
        (state,) = cast('tuple[webrtc.SctpTransportState]', args)
        # the state changes along with its event
        self._native_obj._surfaceState(state)

    @property
    def transport(self) -> webrtc.RTCDtlsTransport:
        """:obj:`webrtc.RTCDtlsTransport`: The DTLS transport the data packets are sent and received over."""
        return webrtc.RTCDtlsTransport._wrap(self._native_obj.transport)

    @property
    def state(self) -> webrtc.SctpTransportState:
        """:obj:`webrtc.SctpTransportState`: An enumerated value indicating the state of the SCTP transport."""
        return self._native_obj.state

    @property
    def max_message_size(self) -> float | None:
        """:obj:`float`, optional: The maximum size in bytes of a message :meth:`webrtc.RTCDataChannel.send` sends."""
        return self._native_obj.maxMessageSize

    @property
    def max_channels(self) -> int | None:
        """:obj:`int`, optional: The maximum number of :obj:`webrtc.RTCDataChannel` open at the same time."""
        return self._native_obj.maxChannels

    #: Alias for :attr:`max_message_size`
    maxMessageSize = max_message_size
    #: Alias for :attr:`max_channels`
    maxChannels = max_channels
