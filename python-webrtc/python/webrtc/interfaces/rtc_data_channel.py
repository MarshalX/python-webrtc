#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCDataChannel of WebRTC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, ClassVar, Literal, TypeVar, cast, overload

from typing_extensions import override

from webrtc import (
    BinaryType,
    Blob,
    Event,
    MessageEvent,
    RTCDataChannelState,
    RTCErrorEvent,
    RTCErrorEventInit,
    RTCPriorityType,
    WebRTCObject,
    wrtc,
)
from webrtc.exceptions import _event_error
from webrtc.models.dictionary import Dictionary
from webrtc.utils.events import AnyHandler, EventTarget, HandlerDecorator
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc
    from webrtc.enums import BinaryTypeValue, RTCPriorityTypeValue

#: The maximum of an unsigned short, which limits the members of the init
MAX_UNSIGNED_SHORT = 65535


def check_utf8_length(name: str, value: str) -> None:
    """Checks a string of the init fits in an unsigned short number of bytes, as the specification requires.

    Raises:
        ValueError: If it doesn't.
    """
    if len(value.encode()) > MAX_UNSIGNED_SHORT:
        msg = f'{name} is longer than {MAX_UNSIGNED_SHORT} bytes'
        raise ValueError(msg)


@dataclass
class RTCDataChannelInit(Dictionary):
    """How :meth:`webrtc.RTCPeerConnection.create_data_channel` creates a channel.

    Args:
        ordered (:obj:`bool`, optional): Whether messages are delivered in order.
        max_packet_life_time (:obj:`int`, optional): Makes the channel unreliable: how long in milliseconds
            a message is retransmitted.
        max_retransmits (:obj:`int`, optional): Makes the channel unreliable: how many times a message is
            retransmitted. Can't be set along with ``max_packet_life_time``.
        protocol (:obj:`str`, optional): The subprotocol name, up to 65535 bytes in UTF-8.
        negotiated (:obj:`bool`, optional): Whether the application creates the channel on both ends
            with the same ``id``, instead of announcing it to the remote peer.
        id (:obj:`int`, optional): The SCTP stream id (0 to 65534) of a ``negotiated`` channel, which requires it.
            Ignored otherwise, as the connection picks the id.
        priority (:obj:`webrtc.RTCPriorityType`, optional): The priority of the channel.
    """

    ordered: bool = True
    max_packet_life_time: int | None = None
    max_retransmits: int | None = None
    protocol: str = ''
    negotiated: bool = False
    id: int | None = None
    priority: RTCPriorityType | RTCPriorityTypeValue = RTCPriorityType.low

    def _check(self) -> None:
        """Checks the members, as the specification requires.

        Raises:
            ValueError: If a member is out of range, or both ``max_packet_life_time`` and ``max_retransmits`` are
                set, or ``negotiated`` is set without ``id``.
        """
        check_utf8_length('protocol', self.protocol)
        for name in ('max_packet_life_time', 'max_retransmits'):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= MAX_UNSIGNED_SHORT:
                msg = f'{name} must be from 0 to {MAX_UNSIGNED_SHORT}, not {value}'
                raise ValueError(msg)
        if self.max_packet_life_time is not None and self.max_retransmits is not None:
            msg = 'max_packet_life_time and max_retransmits can not both be set'
            raise ValueError(msg)
        if not self.negotiated:
            return
        if self.id is None:
            msg = 'a negotiated channel needs an id'
            raise ValueError(msg)
        # the last stream id is reserved
        if not 0 <= self.id < MAX_UNSIGNED_SHORT:
            msg = f'id must be from 0 to {MAX_UNSIGNED_SHORT - 1}, not {self.id}'
            raise ValueError(msg)

    #: Alias for :attr:`max_packet_life_time`
    maxPacketLifeTime: ClassVar[Alias[int | None]] = alias('max_packet_life_time')
    #: Alias for :attr:`max_retransmits`
    maxRetransmits: ClassVar[Alias[int | None]] = alias('max_retransmits')


_DataChannelStateEvent = Literal['open', 'bufferedamountlow', 'closing', 'close']
_DataChannelEvent = Literal[_DataChannelStateEvent, 'message', 'error']
_R = TypeVar('_R')


class RTCDataChannel(WebRTCObject[wrtc.RTCDataChannel], EventTarget[_DataChannelEvent]):
    """A bidirectional channel of messages between the peers.

    It's created with :meth:`webrtc.RTCPeerConnection.create_data_channel` or received with its ``datachannel``
    event.

    Events (see :meth:`on`):
        ``open`` (:obj:`webrtc.Event`): The channel can be used to send messages.
        ``message`` (:obj:`webrtc.MessageEvent`): A message arrived, its ``data`` is :obj:`str`, or :obj:`bytes`
        or :obj:`webrtc.Blob` (see :attr:`binary_type`).
        ``bufferedamountlow`` (:obj:`webrtc.Event`): :attr:`buffered_amount` dropped to
        :attr:`buffered_amount_low_threshold`.
        ``error`` (:obj:`webrtc.RTCErrorEvent`): The channel failed, it's closed right after.
        ``closing`` (:obj:`webrtc.Event`): The channel started closing.
        ``close`` (:obj:`webrtc.Event`): The channel is closed.
    """

    _class = wrtc.RTCDataChannel

    @overload
    def on(self, name: _DataChannelStateEvent, handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def on(self, name: _DataChannelStateEvent, handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def on(self, name: Literal['message'], handler: None = None) -> HandlerDecorator[MessageEvent]: ...

    @overload
    def on(self, name: Literal['message'], handler: Callable[[MessageEvent], _R]) -> Callable[[MessageEvent], _R]: ...

    @overload
    def on(self, name: Literal['error'], handler: None = None) -> HandlerDecorator[RTCErrorEvent]: ...

    @overload
    def on(self, name: Literal['error'], handler: Callable[[RTCErrorEvent], _R]) -> Callable[[RTCErrorEvent], _R]: ...

    def on(self, name: _DataChannelEvent, handler: AnyHandler | None = None) -> object:
        """See :meth:`webrtc.UniformEventTarget.on`."""
        return self._add(name, handler, once=False)

    @overload
    def once(self, name: _DataChannelStateEvent, handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def once(self, name: _DataChannelStateEvent, handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def once(self, name: Literal['message'], handler: None = None) -> HandlerDecorator[MessageEvent]: ...

    @overload
    def once(self, name: Literal['message'], handler: Callable[[MessageEvent], _R]) -> Callable[[MessageEvent], _R]: ...

    @overload
    def once(self, name: Literal['error'], handler: None = None) -> HandlerDecorator[RTCErrorEvent]: ...

    @overload
    def once(self, name: Literal['error'], handler: Callable[[RTCErrorEvent], _R]) -> Callable[[RTCErrorEvent], _R]: ...

    def once(self, name: _DataChannelEvent, handler: AnyHandler | None = None) -> object:
        """See :meth:`webrtc.UniformEventTarget.once`."""
        return self._add(name, handler, once=True)

    @override
    def _on_event(self, name: str, *args: object) -> None:
        # readyState changes along with the events
        if name in {'open', 'closing', 'close'}:
            (state,) = cast('tuple[RTCDataChannelState]', args)
            self._native_obj._surfaceState(state)
        elif name == '_sent':
            (size,) = cast('tuple[int]', args)
            if self._native_obj._decreaseBufferedAmount(size):
                # in the same task as the decrease, before anything that arrived meanwhile
                self._dispatch('bufferedamountlow')

    @override
    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        if name == 'open' and self.ready_state != RTCDataChannelState.open:
            # closed before it opened
            return None
        if name == 'message':
            (message,) = cast('tuple[wrtc.DataChannelMessage]', args)
            data: str | bytes | Blob = message.data
            # binary_type as of delivery, per the specification
            if isinstance(data, bytes) and self._native_obj.binaryType == BinaryType.blob:
                data = Blob([data])
            return MessageEvent(name, data)
        if name == 'error':
            (error,) = cast('tuple[wrtc.RTCCallbackException]', args)
            return RTCErrorEvent(name, RTCErrorEventInit(_event_error(error)))
        return super()._create_event(name, *args)

    @property
    def label(self) -> str:
        """:obj:`str`: The name of the channel, not necessarily unique."""
        return self._native_obj.label

    @property
    def ordered(self) -> bool:
        """:obj:`bool`: Whether messages are delivered in the order they were sent."""
        return self._native_obj.ordered

    @property
    def max_packet_life_time(self) -> int | None:
        """:obj:`int`, optional: How long in milliseconds a message is retransmitted in unreliable mode."""
        return self._native_obj.maxPacketLifeTime

    @property
    def max_retransmits(self) -> int | None:
        """:obj:`int`, optional: How many times a message is retransmitted in unreliable mode."""
        return self._native_obj.maxRetransmits

    @property
    def protocol(self) -> str:
        """:obj:`str`: The subprotocol name of the channel, empty if none."""
        return self._native_obj.protocol

    @property
    def negotiated(self) -> bool:
        """:obj:`bool`: Whether the application negotiated the channel, rather than the connection."""
        return self._native_obj.negotiated

    @property
    def id(self) -> int | None:
        """:obj:`int`, optional: The SCTP stream id of the channel, :obj:`None` until it's known."""
        return self._native_obj.id

    @property
    def priority(self) -> webrtc.RTCPriorityType:
        """:obj:`webrtc.RTCPriorityType`: The priority of the channel."""
        return self._native_obj.priority

    @property
    def ready_state(self) -> webrtc.RTCDataChannelState:
        """:obj:`webrtc.RTCDataChannelState`: The state of the channel."""
        return self._native_obj.readyState

    @property
    def buffered_amount(self) -> int:
        """:obj:`int`: The number of bytes queued to be sent."""
        return self._native_obj.bufferedAmount

    @property
    def buffered_amount_low_threshold(self) -> int:
        """:obj:`int`: The :attr:`buffered_amount` at which the ``bufferedamountlow`` event is emitted, 0 by default."""
        return self._native_obj.bufferedAmountLowThreshold

    @buffered_amount_low_threshold.setter
    def buffered_amount_low_threshold(self, value: int) -> None:
        if not 0 <= value < 2**64:
            msg = f'buffered_amount_low_threshold must be from 0 to 2**64-1, not {value}'
            raise ValueError(msg)
        self._native_obj.bufferedAmountLowThreshold = value

    @property
    def binary_type(self) -> BinaryType:
        """:obj:`webrtc.BinaryType`: What binary messages are delivered as, :obj:`bytes` by default.

        :obj:`bytes` for ``arraybuffer``, :obj:`webrtc.Blob` for ``blob``.
        """
        return BinaryType(self._native_obj.binaryType)

    @binary_type.setter
    def binary_type(self, value: BinaryType | BinaryTypeValue) -> None:
        self._native_obj.binaryType = BinaryType(value).value

    def send(self, data: str | bytes | bytearray | memoryview | Blob) -> None:
        """Sends a message to the remote peer.

        Args:
            data (:obj:`str`, bytes-like or :obj:`webrtc.Blob`): A text message, or a binary one.

        Raises:
            TypeError: If the data is neither text, bytes nor a :obj:`webrtc.Blob`.
            webrtc.InvalidStateError: If the channel isn't open.
            webrtc.OperationError: If the message can't be queued, like when the queue is full.
        """
        if isinstance(data, str):
            self._native_obj.send(data.encode(), binary=False)
        elif isinstance(data, (bytes, bytearray, memoryview, Blob)):
            self._native_obj.send(bytes(data), binary=True)
        else:
            msg = f'data must be str, bytes-like or Blob, not {type(data).__name__}'
            raise TypeError(msg)

    def close(self) -> None:
        """Closes the channel. Messages queued before are still sent."""
        self._native_obj.close()

    #: Alias for :attr:`binary_type`
    binaryType = binary_type
    #: Alias for :attr:`max_packet_life_time`
    maxPacketLifeTime = max_packet_life_time
    #: Alias for :attr:`max_retransmits`
    maxRetransmits = max_retransmits
    #: Alias for :attr:`ready_state`
    readyState = ready_state
    #: Alias for :attr:`buffered_amount`
    bufferedAmount = buffered_amount
    #: Alias for :attr:`buffered_amount_low_threshold`
    bufferedAmountLowThreshold = buffered_amount_low_threshold
