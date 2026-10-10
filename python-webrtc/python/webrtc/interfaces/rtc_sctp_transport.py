#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The SCTP transport that data channels go over."""

from __future__ import annotations

from typing import Literal, cast

from typing_extensions import override

import webrtc
import wrtc
from webrtc.base import WebRTCObject
from webrtc.enums import RTCSctpTransportState
from webrtc.models.events import Event
from webrtc.utils.events import UniformEventTarget


class RTCSctpTransport(WebRTCObject[wrtc.RTCSctpTransport], UniformEventTarget[Literal['statechange'], Event]):
    """The SCTP transport the data channels of a :obj:`webrtc.RTCPeerConnection` share.

    It reports the negotiated limits of the data channels, and the DTLS transport its packets go over.

    See :mdn:`RTCSctpTransport`.

    Events:
        statechange (:obj:`webrtc.Event`): :attr:`state` changed.
    """

    __slots__ = ()

    _class = wrtc.RTCSctpTransport

    @override
    def _on_event(self, name: str, *args: object) -> None:
        (state,) = cast('tuple[webrtc.RTCSctpTransportState]', args)
        # the state changes along with its event
        self._native_obj._surfaceState(state)

    @override
    def _activity(self) -> str | None:
        state = self.state
        if state == RTCSctpTransportState.closed or not self._open() or len(self.event_names()) == 0:
            return None
        return f'{state.value} with handlers'

    @property
    def transport(self) -> webrtc.RTCDtlsTransport:
        """:obj:`webrtc.RTCDtlsTransport`: The DTLS transport the SCTP packets go over.

        See :mdn:`RTCSctpTransport/transport`.
        """
        return webrtc.RTCDtlsTransport._wrap(self._native_obj.transport, connection=self._connection)

    @property
    def state(self) -> webrtc.RTCSctpTransportState:
        """:obj:`webrtc.RTCSctpTransportState`: Whether the SCTP association is connecting, connected or closed.

        See :mdn:`RTCSctpTransport/state`.
        """
        return self._native_obj.state

    @property
    def max_message_size(self) -> float | None:
        """:obj:`float`, optional: The largest message in bytes :meth:`webrtc.RTCDataChannel.send` accepts.

        It's ``math.inf`` when there's no limit and :obj:`None` while it isn't known.

        See :mdn:`RTCSctpTransport/maxMessageSize`.
        """
        return self._native_obj.maxMessageSize

    @property
    def max_channels(self) -> int | None:
        """:obj:`int`, optional: How many data channels can be open at once.

        It's :obj:`None` until the transport is connected.
        See :mdn:`RTCSctpTransport/maxChannels`.
        """
        return self._native_obj.maxChannels

    #: Alias for :attr:`max_message_size`
    maxMessageSize = max_message_size
    #: Alias for :attr:`max_channels`
    maxChannels = max_channels
