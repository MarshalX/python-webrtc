#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyee.asyncio import AsyncIOEventEmitter

import webrtc
from webrtc.aiortc._ice_servers import (
    STUN_REGEX as STUN_REGEX,
    TURN_REGEX as TURN_REGEX,
    connection_kwargs as connection_kwargs,
    parse_stun_turn_uri as parse_stun_turn_uri,
)
from webrtc.aiortc._utils import _emitter, _ice_state, _ReadOnly
from webrtc.aiortc.rtcconfiguration import RTCIceServer

if TYPE_CHECKING:
    from typing_extensions import Self

_STANDALONE_ICE = 'a standalone ICE transport is not supported, the transports come from RTCPeerConnection'


@dataclass
class RTCIceCandidate:
    component: int
    foundation: str
    ip: str
    port: int
    priority: int
    protocol: str
    type: str
    relatedAddress: str | None = None
    relatedPort: int | None = None
    sdpMid: str | None = None
    sdpMLineIndex: int | None = None
    tcpType: str | None = None


@dataclass
class RTCIceParameters:
    usernameFragment: str | None = None
    password: str | None = None
    iceLite: bool = False


def _candidate(native: webrtc.RTCIceCandidate) -> RTCIceCandidate:
    # the vendored module imports this one
    from webrtc.aiortc.sdp import candidate_from_sdp  # ruff: ignore[import-outside-top-level]

    # the parser takes the attribute's value, without its 'candidate:' prefix
    value = native.candidate.split(':', 1)[1]
    candidate = candidate_from_sdp(value)
    candidate.sdpMid = native.sdp_mid
    candidate.sdpMLineIndex = native.sdp_m_line_index
    return candidate


class RTCIceGatherer(AsyncIOEventEmitter):
    _native: webrtc.RTCIceTransport

    def __init__(  # pyrefly: ignore[missing-super-call]
        self,
        iceServers: list[RTCIceServer] | None = None,
        local_username: str | None = None,
        local_password: str | None = None,
    ) -> None:
        raise NotImplementedError(_STANDALONE_ICE)

    @classmethod
    def _of(cls, native: webrtc.RTCIceTransport) -> Self:
        gatherer = _emitter(cls)
        gatherer._native = native
        return gatherer

    @classmethod
    def getDefaultIceServers(cls) -> list[RTCIceServer]:
        return [RTCIceServer('stun:stun.l.google.com:19302')]

    @property
    def state(self) -> str:
        state = self._native.gathering_state
        return 'completed' if state == webrtc.RTCIceGathererState.complete else state.value

    def getLocalCandidates(self) -> list[RTCIceCandidate]:
        return [_candidate(c) for c in self._native.get_local_candidates()]

    def getLocalParameters(self) -> RTCIceParameters:
        parameters = self._native.get_local_parameters()
        if parameters is None:
            return RTCIceParameters()
        return RTCIceParameters(parameters.username_fragment, parameters.password)


class RTCIceTransport(AsyncIOEventEmitter):
    _native: webrtc.RTCIceTransport
    _gatherer: RTCIceGatherer
    _emitted = 'new'
    iceGatherer: _ReadOnly[RTCIceGatherer] = _ReadOnly('_gatherer')

    def __init__(self, gatherer: RTCIceGatherer) -> None:  # pyrefly: ignore[missing-super-call]
        raise NotImplementedError(_STANDALONE_ICE)

    @classmethod
    def _of(cls, native: webrtc.RTCIceTransport) -> Self:
        transport = _emitter(cls)
        transport._native = native
        transport._gatherer = RTCIceGatherer._of(native)
        return transport

    def _watch(self) -> None:
        gatherer = self._gatherer
        self._native.on('statechange', self._state_changed)
        self._native.on('gatheringstatechange', lambda _event: gatherer.emit('statechange'))

    def _state_changed(self, _event: webrtc.Event) -> None:
        state = self.state
        if state != self._emitted:
            self._emitted = state
            self.emit('statechange')

    @property
    def role(self) -> str:
        role = self._native.role
        return role.value if role == webrtc.RTCIceRole.controlling else 'controlled'

    @property
    def state(self) -> str:
        return _ice_state(self._native.state)

    def getRemoteCandidates(self) -> list[RTCIceCandidate]:
        return [_candidate(c) for c in self._native.get_remote_candidates()]


__all__ = ['RTCIceCandidate', 'RTCIceGatherer', 'RTCIceParameters', 'RTCIceTransport']
