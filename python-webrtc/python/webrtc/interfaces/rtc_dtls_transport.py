#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The DTLS transport that RTP and SCTP packets go over."""

from __future__ import annotations

from typing import Callable, Literal, TypeVar, cast, overload

from typing_extensions import override

import webrtc
import wrtc
from webrtc.base import WebRTCObject
from webrtc.enums import RTCDtlsTransportState
from webrtc.exceptions import _event_error
from webrtc.models.events import Event, RTCErrorEvent, RTCErrorEventInit
from webrtc.utils.events import AnyHandler, EventTarget, HandlerDecorator

_DtlsTransportEvent = Literal['statechange', 'error']
_R = TypeVar('_R')


class RTCDtlsTransport(WebRTCObject[wrtc.RTCDtlsTransport], EventTarget[_DtlsTransportEvent]):
    """The DTLS transport that secures the packets of a :obj:`webrtc.RTCPeerConnection`.

    The RTP and RTCP packets of its senders and receivers, and the SCTP packets of its data channels, go over it.

    See :mdn:`RTCDtlsTransport`.

    Events:
        statechange (:obj:`webrtc.Event`): :attr:`state` changed.
        error (:obj:`webrtc.RTCErrorEvent`): The transport failed. The event carries the
            :obj:`webrtc.RTCError` that explains why.
    """

    __slots__ = ()

    _class = wrtc.RTCDtlsTransport

    @overload
    def on(self, name: Literal['statechange'], handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def on(self, name: Literal['statechange'], handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def on(self, name: Literal['error'], handler: None = None) -> HandlerDecorator[RTCErrorEvent]: ...

    @overload
    def on(self, name: Literal['error'], handler: Callable[[RTCErrorEvent], _R]) -> Callable[[RTCErrorEvent], _R]: ...

    def on(self, name: _DtlsTransportEvent, handler: AnyHandler | None = None) -> object:
        """Adds a handler of an event, called each time. See :meth:`webrtc.UniformEventTarget.on`."""
        return self._add(name, handler, once=False)

    @overload
    def once(self, name: Literal['statechange'], handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def once(self, name: Literal['statechange'], handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def once(self, name: Literal['error'], handler: None = None) -> HandlerDecorator[RTCErrorEvent]: ...

    @overload
    def once(self, name: Literal['error'], handler: Callable[[RTCErrorEvent], _R]) -> Callable[[RTCErrorEvent], _R]: ...

    def once(self, name: _DtlsTransportEvent, handler: AnyHandler | None = None) -> object:
        """Adds a handler of an event, called once. See :meth:`webrtc.UniformEventTarget.once`."""
        return self._add(name, handler, once=True)

    @override
    def _on_event(self, name: str, *args: object) -> None:
        # the state changes along with its event
        if name == 'statechange':
            (state,) = cast('tuple[RTCDtlsTransportState]', args)
            self._native_obj._surfaceState(state)

    @override
    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        if name == 'error':
            (error,) = cast('tuple[wrtc.RTCCallbackException]', args)
            return RTCErrorEvent(name, RTCErrorEventInit(_event_error(error)))
        return super()._create_event(name, *args)

    @override
    def _activity(self) -> str | None:
        state = self.state
        closed = state in {RTCDtlsTransportState.closed, RTCDtlsTransportState.failed} or not self._open()
        if closed or len(self.event_names()) == 0:
            return None
        return f'{state.value} with handlers'

    @property
    def ice_transport(self) -> webrtc.RTCIceTransport:
        """:obj:`webrtc.RTCIceTransport`: The ICE transport the DTLS packets go over.

        See :mdn:`RTCDtlsTransport/iceTransport`.
        """
        return webrtc.RTCIceTransport._wrap(self._native_obj.iceTransport, connection=self._connection)

    @property
    def state(self) -> webrtc.RTCDtlsTransportState:
        """:obj:`webrtc.RTCDtlsTransportState`: How far the DTLS handshake got, or whether it failed or closed.

        See :mdn:`RTCDtlsTransport/state`.
        """
        return self._native_obj.state

    def get_remote_certificates(self) -> list[bytes]:
        """Returns the certificates the remote peer presented in the DTLS handshake, once it is done.

        See :mdn:`RTCDtlsTransport/getRemoteCertificates`.

        Returns:
            :obj:`list` of :obj:`bytes`: The DER-encoded certificates, with the peer's own first. The list
            is empty before the handshake.
        """
        return list(self._native_obj.getRemoteCertificates())

    #: Alias for :attr:`get_remote_certificates`
    getRemoteCertificates = get_remote_certificates
    #: Alias for :attr:`ice_transport`
    iceTransport = ice_transport
