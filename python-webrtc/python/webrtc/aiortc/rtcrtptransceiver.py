#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import webrtc
from webrtc.aiortc._utils import _MSID, _ORTC, _media_formats, _media_section, _ReadOnly
from webrtc.aiortc.rtcrtpreceiver import RTCRtpReceiver
from webrtc.aiortc.rtcrtpsender import RTCRtpSender
from webrtc.aiortc.sdp import parameters_to_sdp

if TYPE_CHECKING:
    from typing_extensions import Self

    from webrtc.aiortc.rtcpeerconnection import RTCPeerConnection
    from webrtc.aiortc.rtcrtpparameters import RTCRtpCodecCapability


def _native_codec(codec: RTCRtpCodecCapability) -> webrtc.RTCRtpCodec:
    fmtp = parameters_to_sdp(codec.parameters)
    return webrtc.RTCRtpCodec(codec.mimeType, codec.clockRate, codec.channels, fmtp if fmtp != '' else None)


class RTCRtpTransceiver:
    _native: webrtc.RTCRtpTransceiver
    _pc: RTCPeerConnection
    _kind: str
    _sender: RTCRtpSender
    _receiver: RTCRtpReceiver
    _stopped = False
    # a stopped transceiver keeps its last direction
    _direction: str | None = None
    _preferred = False
    kind: _ReadOnly[str] = _ReadOnly('_kind')
    mid: _ReadOnly[str | None] = _ReadOnly('_native.mid')
    receiver: _ReadOnly[RTCRtpReceiver] = _ReadOnly('_receiver')
    sender: _ReadOnly[RTCRtpSender] = _ReadOnly('_sender')
    stopped: _ReadOnly[bool] = _ReadOnly('_stopped')

    def __init__(self, kind: str, receiver: RTCRtpReceiver, sender: RTCRtpSender, direction: str = 'sendrecv') -> None:
        raise NotImplementedError(_ORTC)

    @classmethod
    def _of(cls, native: webrtc.RTCRtpTransceiver, pc: RTCPeerConnection) -> Self:
        transceiver = cls.__new__(cls)
        transceiver._native = native
        transceiver._pc = pc
        transceiver._kind = str(native.receiver.track.kind)
        transceiver._sender = RTCRtpSender._of(native.sender, transceiver)
        transceiver._receiver = RTCRtpReceiver._of(native.receiver, transceiver)
        return transceiver

    @property
    def currentDirection(self) -> str | None:
        direction = self._native.current_direction
        return str(direction) if direction is not None else None

    @property
    def direction(self) -> str:
        return self._direction if self._direction is not None else str(self._native.direction)

    @direction.setter
    def direction(self, direction: str) -> None:
        self._native.direction = webrtc.RTCRtpTransceiverDirection(direction)

    def setCodecPreferences(self, codecs: list[RTCRtpCodecCapability]) -> None:
        sent, received = RTCRtpSender.getCapabilities(self.kind), RTCRtpReceiver.getCapabilities(self.kind)
        capabilities = [*sent.codecs, *received.codecs]
        unique: list[RTCRtpCodecCapability] = []
        for codec in reversed(codecs):
            if codec not in capabilities:
                msg = 'Codec is not in capabilities'
                raise ValueError(msg)
            if codec not in unique:
                unique.insert(0, codec)
        try:
            self._native.set_codec_preferences([_native_codec(c) for c in unique])
        except webrtc.InvalidModificationError as e:
            raise ValueError(str(e)) from None
        self._preferred = unique != []

    async def stop(self) -> None:
        await self._receiver.stop()
        await self._sender.stop()
        self._direction = self.direction
        if not self._pc._closed:
            self._native.stop()
        self._stopped = True

    def _announced_track_id(self, sdp: str) -> str | None:
        found = _MSID.search(_media_section(sdp, self.mid)) if self.mid is not None else None
        if found is not None:
            return found.group(1)
        # before negotiation, the sender of a track the application added is announced with the track's id
        sent = self._sender._sent
        return sent.id if sent is not None else None

    async def _send_first_answered_codec(self, answer: str) -> None:
        # the core sends the offer's first codec it can, and some peers only take the answer's (RFC 3264 6.1)
        sender = self._sender._native
        for payload_type in _media_formats(_media_section(answer, self.mid)):
            parameters = sender.get_parameters()
            codec = next((c for c in parameters.codecs if str(c.payload_type) == payload_type), None)
            if codec is None or parameters.encodings == []:
                continue
            parameters.encodings[0].codec = webrtc.RTCRtpCodec(
                codec.mime_type, codec.clock_rate, codec.channels, codec.sdp_fmtp_line
            )
            with contextlib.suppress(webrtc.InvalidModificationError):
                await sender.set_parameters(parameters)
                return

    def _sending(self) -> bool:
        connected = self._pc._native.connection_state == webrtc.RTCPeerConnectionState.connected
        return connected and self.currentDirection in {'sendrecv', 'sendonly'}


__all__ = ['RTCRtpTransceiver']
