#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import starmap
from typing import TYPE_CHECKING

from pyee.asyncio import AsyncIOEventEmitter

import wrtc
from webrtc.aiortc._utils import _ORTC, _datetime, _emitter, _ReadOnly, _sdp_of
from webrtc.aiortc.rtcicetransport import RTCIceTransport

if TYPE_CHECKING:
    import datetime as dt

    from typing_extensions import Self

    import webrtc
    from webrtc.aiortc.rtcpeerconnection import RTCPeerConnection

# attributes are never on the first line, and a newline before them is much faster to find than a line start
_FINGERPRINT = re.compile(r'\na=fingerprint:(\S+) (\S+)')


@dataclass
class RTCDtlsFingerprint:
    algorithm: str
    value: str


@dataclass
class RTCDtlsParameters:
    fingerprints: list[RTCDtlsFingerprint] = field(default_factory=list)
    role: str = 'auto'


class RTCCertificate:
    _native: wrtc.RTCCertificate

    def __init__(self, key: object, cert: object) -> None:
        msg = 'a certificate can only be generated, with RTCCertificate.generateCertificate()'
        raise NotImplementedError(msg)

    @classmethod
    def generateCertificate(cls) -> Self:
        certificate = cls.__new__(cls)
        certificate._native = wrtc.RTCCertificate.generate('ecdsa', 0, 0, None)
        return certificate

    @property
    def expires(self) -> dt.datetime:
        return _datetime(self._native.expires)

    def getFingerprints(self) -> list[RTCDtlsFingerprint]:
        return list(starmap(RTCDtlsFingerprint, self._native.fingerprints()))


class RTCDtlsTransport(AsyncIOEventEmitter):
    _native: webrtc.RTCDtlsTransport
    _pc: RTCPeerConnection
    _ice: RTCIceTransport | None = None
    _watched = False
    state: _ReadOnly[str] = _ReadOnly('_native.state.value')

    def __init__(self, transport: RTCIceTransport, certificates: list[RTCCertificate]) -> None:  # pyrefly: ignore[missing-super-call]
        raise NotImplementedError(_ORTC)

    @classmethod
    def _of(cls, native: webrtc.RTCDtlsTransport, pc: RTCPeerConnection) -> Self:
        transport = _emitter(cls)
        transport._native = native
        transport._pc = pc
        return transport

    def _watch(self) -> None:
        if not self._watched:
            self._watched = True
            self._native.on('statechange', self._state_changed)
            if self._ice is not None:
                self._ice._watch()

    def _state_changed(self, _event: webrtc.Event) -> None:
        self._pc._dtls_state_changed()
        self.emit('statechange')

    @property
    def transport(self) -> RTCIceTransport:
        if self._ice is None:
            self._ice = RTCIceTransport._of(self._native.ice_transport)
            if self._watched:
                self._ice._watch()
        return self._ice

    def getLocalParameters(self) -> RTCDtlsParameters:
        found = _FINGERPRINT.findall(_sdp_of(self._pc._native.local_description))
        return RTCDtlsParameters(fingerprints=list(starmap(RTCDtlsFingerprint, dict.fromkeys(found))))


__all__ = ['RTCCertificate', 'RTCDtlsFingerprint', 'RTCDtlsParameters', 'RTCDtlsTransport']
