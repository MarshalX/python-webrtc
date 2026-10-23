#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from pyee.asyncio import AsyncIOEventEmitter
from typing_extensions import Never, override

import webrtc
from webrtc.aiortc._utils import _ORTC, _ReadOnly
from webrtc.aiortc.rtcsctptransport import RTCSctpTransport

if TYPE_CHECKING:
    from webrtc.aiortc.rtcpeerconnection import RTCPeerConnection

_MAX_THRESHOLD = 2**32 - 1
# bound to the core once heard: an unheard core event costs nothing
_CHANNEL_EVENTS = ('open', 'message', 'bufferedamountlow')
_NO_HANDLERS: dict[Callable[..., object], Callable[..., object]] = {}
_NO_KWARGS: dict[str, object] = {}


@dataclass
class RTCDataChannelParameters:
    label: str = ''
    maxPacketLifeTime: int | None = None
    maxRetransmits: int | None = None
    ordered: bool = True
    protocol: str = ''
    negotiated: bool = False
    id: int | None = None


def _returned(value: object) -> object:
    """Returns a handler's coroutine unchanged, so the emitter schedules it."""
    return value


class RTCDataChannel(AsyncIOEventEmitter):
    _native: webrtc.RTCDataChannel
    _pc: RTCPeerConnection
    _local: bool
    _closed = False
    _heard: set[str]
    _bound: set[str]
    negotiated: _ReadOnly[bool] = _ReadOnly('_native.negotiated')
    id: _ReadOnly[int | None] = _ReadOnly('_native.id')
    label: _ReadOnly[str] = _ReadOnly('_native.label')
    ordered: _ReadOnly[bool] = _ReadOnly('_native.ordered')
    maxPacketLifeTime: _ReadOnly[int | None] = _ReadOnly('_native.max_packet_life_time')
    maxRetransmits: _ReadOnly[int | None] = _ReadOnly('_native.max_retransmits')
    protocol: _ReadOnly[str] = _ReadOnly('_native.protocol')

    def __init__(
        self, transport: RTCSctpTransport, parameters: RTCDataChannelParameters, send_open: bool = True
    ) -> None:
        if not isinstance(transport, RTCSctpTransport):
            raise NotImplementedError(_ORTC)
        super().__init__()
        init = webrtc.RTCDataChannelInit(
            ordered=parameters.ordered,
            max_packet_life_time=parameters.maxPacketLifeTime,
            max_retransmits=parameters.maxRetransmits,
            protocol=parameters.protocol,
            negotiated=parameters.negotiated,
            id=parameters.id,
        )
        try:
            native = transport._pc._native.create_data_channel(parameters.label, init)
        except (TypeError, webrtc.OperationError) as e:
            raise ValueError(str(e)) from e
        self._init(native, transport._pc, local=send_open)

    def _init(self, native: webrtc.RTCDataChannel, pc: RTCPeerConnection, *, local: bool) -> None:
        self._native = native
        self._pc = pc
        self._local = local
        self._heard = {'close'}
        self._bound = set()
        pc._channels.append(self)
        pc._adopt(self)

    @override
    def _add_event_handler(self, event: str, k: Callable[..., object], v: Callable[..., object]) -> None:
        super()._add_event_handler(event, k, v)
        if event not in _CHANNEL_EVENTS or event in self._heard:
            return
        # a channel the remote peer created is open when announced
        if event == 'open' and not self._local:
            return
        self._heard.add(event)
        self._pc._adopt(self)

    def _attach(self) -> None:
        handlers: dict[str, Callable[[Never], object]] = {
            'open': lambda _event: self.emit('open'),
            'message': self._received,
            'bufferedamountlow': lambda _event: self.emit('bufferedamountlow'),
            'close': lambda _event: self._emit_close(),
        }
        for event in self._heard - self._bound:
            self._native.on(event, handlers[event])  # pyrefly: ignore[no-matching-overload]
        self._bound |= self._heard

    def _received(self, event: webrtc.MessageEvent) -> None:
        # emit() without its lock and copy, and a task only for a coroutine: this runs per message
        data = event.data
        for handler in tuple(self._events.get('message', _NO_HANDLERS).values()):
            try:
                result: object = handler(data)
            except Exception as e:  # ruff: ignore[blind-except, try-except-in-loop]
                self.emit('error', e)
            else:
                if result is not None:
                    self._emit_run(_returned, (result,), _NO_KWARGS)

    def _emit_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._pc._channels.remove(self)
        self.emit('close')
        self.remove_all_listeners()

    @property
    def bufferedAmount(self) -> int:
        return self._native.buffered_amount

    @property
    def bufferedAmountLowThreshold(self) -> int:
        return self._native.buffered_amount_low_threshold

    @bufferedAmountLowThreshold.setter
    def bufferedAmountLowThreshold(self, value: int) -> None:
        if not 0 <= value <= _MAX_THRESHOLD:
            msg = f'bufferedAmountLowThreshold must be in range 0 - {_MAX_THRESHOLD}'
            raise ValueError(msg)
        self._native.buffered_amount_low_threshold = value

    @property
    def readyState(self) -> str:
        return 'closed' if self._closed else self._native.ready_state.value

    @property
    def transport(self) -> RTCSctpTransport | None:
        return self._pc.sctp

    def close(self) -> None:
        self._native.close()
        # a channel with no transport yet closes at once
        if self._pc._native.sctp is None:
            self._emit_close()

    def send(self, data: str | bytes) -> None:
        try:
            self._native.send(data)
        except TypeError:
            if isinstance(data, (str, bytes, bytearray, memoryview)):
                raise
            msg = f'Cannot send unsupported data type: {type(data)}'
            raise ValueError(msg) from None


__all__ = ['RTCDataChannel', 'RTCDataChannelParameters']
