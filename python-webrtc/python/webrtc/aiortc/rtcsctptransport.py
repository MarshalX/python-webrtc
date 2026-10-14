#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyee.asyncio import AsyncIOEventEmitter

from webrtc.aiortc._utils import _ORTC, _emitter, _media_lines, _sdp_of

if TYPE_CHECKING:
    from typing_extensions import Self

    from webrtc.aiortc.rtcdtlstransport import RTCDtlsTransport
    from webrtc.aiortc.rtcpeerconnection import RTCPeerConnection

# attributes are never on the first line, and a newline before them is much faster to find than a line start
_SCTP_PORT = re.compile(r'\na=sctp-port:(\d+)')


@dataclass
class RTCSctpCapabilities:
    maxMessageSize: int


class RTCSctpTransport(AsyncIOEventEmitter):
    _pc: RTCPeerConnection

    def __init__(self, transport: RTCDtlsTransport, port: int = 5000) -> None:  # pyrefly: ignore[missing-super-call]
        raise NotImplementedError(_ORTC)

    @classmethod
    def _of(cls, pc: RTCPeerConnection) -> Self:
        transport = _emitter(cls)
        transport._pc = pc
        return transport

    @classmethod
    def getCapabilities(cls) -> RTCSctpCapabilities:
        return RTCSctpCapabilities(maxMessageSize=65536)

    @property
    def maxChannels(self) -> int | None:
        native = self._pc._native.sctp
        return native.max_channels if native is not None else None

    @property
    def mid(self) -> str | None:
        native = self._pc._native
        local = native.local_description
        sdp = _sdp_of(local if local is not None else native.remote_description)
        return next((mid for kind, mid in _media_lines(sdp) if kind == 'application'), None)

    @property
    def port(self) -> int:
        found = _SCTP_PORT.search(_sdp_of(self._pc._native.local_description))
        return int(found.group(1)) if found is not None else 5000

    @property
    def state(self) -> str:
        native = self._pc._native.sctp
        return native.state.value if native is not None else 'new'

    @property
    def transport(self) -> RTCDtlsTransport | None:
        native = self._pc._native.sctp
        return self._pc._dtls_transport(native.transport) if native is not None else None

    async def stop(self) -> None:
        for channel in list(self._pc._channels):
            channel.close()


__all__ = ['RTCSctpCapabilities', 'RTCSctpTransport']
