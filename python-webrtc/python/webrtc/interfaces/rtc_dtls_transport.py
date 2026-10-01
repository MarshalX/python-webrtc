#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCDtlsTransport of WebRTC."""

from __future__ import annotations

from typing import cast

from typing_extensions import override

import webrtc
from webrtc import DtlsTransportState, RTCErrorEvent, WebRTCObject, wrtc
from webrtc.exceptions import _event_error
from webrtc.utils.events import EventTarget


class RTCDtlsTransport(WebRTCObject[wrtc.RTCDtlsTransport], EventTarget):
    """The Datagram Transport Layer Security (DTLS) transport of a :obj:`webrtc.RTCPeerConnection`.

    The RTP and RTCP packets of its :obj:`webrtc.RTCRtpSender` and :obj:`webrtc.RTCRtpReceiver` objects are sent and
    received over it.

    Events (see :meth:`on`):
        ``statechange`` (:obj:`webrtc.Event`): :attr:`state` changed.
        ``error`` (:obj:`webrtc.RTCErrorEvent`): The transport failed with an :obj:`webrtc.RTCError`.
    """

    _class = wrtc.RTCDtlsTransport
    _events = ('statechange', 'error')

    @override
    def _on_event(self, name: str, *args: object) -> None:
        # the state changes along with its event
        if name == 'statechange':
            (state,) = cast('tuple[DtlsTransportState]', args)
            self._native_obj._surfaceState(state)

    @override
    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        if name == 'error':
            (error,) = cast('tuple[wrtc.RTCCallbackException]', args)
            return RTCErrorEvent(name, _event_error(error), target=self)
        return super()._create_event(name, *args)

    @property
    def ice_transport(self) -> webrtc.RTCIceTransport:
        """:obj:`webrtc.RTCIceTransport`: Returns a reference to the underlying :obj:`webrtc.RTCIceTransport` object."""
        return webrtc.RTCIceTransport._wrap(self._native_obj.iceTransport)

    @property
    def state(self) -> webrtc.DtlsTransportState:
        """:obj:`webrtc.DtlsTransportState`: The state of the DTLS transport."""
        return self._native_obj.state

    def get_remote_certificates(self) -> list[bytes]:
        """Returns the certificates of the remote peer, once the DTLS handshake is done.

        Returns:
            :obj:`list` of :obj:`bytes`: The certificates in the DER format, the peer's first.
        """
        return list(self._native_obj.getRemoteCertificates())

    #: Alias for :attr:`get_remote_certificates`
    getRemoteCertificates = get_remote_certificates
    #: Alias for :attr:`ice_transport`
    iceTransport = ice_transport
