#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The data channel, which carries text and binary messages between the peers over SCTP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, ClassVar, Literal, TypeVar, cast, overload

from typing_extensions import override

import wrtc
from webrtc.base import WebRTCObject
from webrtc.enums import BinaryType, RTCDataChannelState, RTCPriorityType
from webrtc.exceptions import _event_error
from webrtc.models.blob import Blob
from webrtc.models.dictionary import Dictionary
from webrtc.models.events import Event, MessageEvent, RTCErrorEvent, RTCErrorEventInit
from webrtc.utils.events import AnyHandler, EventTarget, HandlerDecorator
from webrtc.utils.names import Alias, alias
from webrtc.utils.strings import usv_string

if TYPE_CHECKING:
    import webrtc
    from webrtc.enums import BinaryTypeValue, RTCPriorityTypeValue

#: The largest unsigned short, which bounds the label, the protocol and the retransmission limits of a channel
MAX_UNSIGNED_SHORT = 65535


def check_utf8_length(name: str, value: str) -> None:
    """Checks that a string, like the label of a channel, is at most 65535 bytes in UTF-8.

    Args:
        name (:obj:`str`): The name of the string, for the error message.
        value (:obj:`str`): The string.

    Raises:
        TypeError: If it's longer.
    """
    if len(usv_string(value).encode()) > MAX_UNSIGNED_SHORT:
        msg = f'{name} is longer than {MAX_UNSIGNED_SHORT} bytes'
        raise TypeError(msg)


@dataclass
class RTCDataChannelInit(Dictionary):
    """The options of :meth:`webrtc.RTCPeerConnection.create_data_channel`.

    :meth:`webrtc.RTCPeerConnection.create_data_channel` checks them and raises :obj:`TypeError` for invalid ones.

    See :mdn:`RTCPeerConnection/createDataChannel`.

    Args:
        ordered (:obj:`bool`, optional): Whether messages arrive in the order they were sent, :obj:`True` by default.
        max_packet_life_time (:obj:`int`, optional): For how many milliseconds (0 to 65535) a message
            may be retransmitted. Setting it makes the channel unreliable.
        max_retransmits (:obj:`int`, optional): How many times (0 to 65535) a message may be
            retransmitted. Setting it makes the channel unreliable. It can't be set together with
            ``max_packet_life_time``.
        protocol (:obj:`str`, optional): The subprotocol name, up to 65535 bytes in UTF-8, empty by default.
        negotiated (:obj:`bool`, optional): Whether the application creates the channel on both peers with the
            same ``id``. Otherwise the connection announces it to the remote peer. :obj:`False` by default.
        id (:obj:`int`, optional): The SCTP stream id (0 to 65534) of a ``negotiated`` channel.
            It's required for such a channel and ignored otherwise, because the connection picks the id.
        priority (:obj:`webrtc.RTCPriorityType`, optional): The priority of the channel, ``'low'`` by default.
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
            TypeError: If a member is out of range, or both ``max_packet_life_time`` and ``max_retransmits`` are
                set, or ``negotiated`` is set without ``id``.
        """
        check_utf8_length('protocol', self.protocol)
        for name in ('max_packet_life_time', 'max_retransmits', 'id'):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= MAX_UNSIGNED_SHORT:
                msg = f'{name} must be from 0 to {MAX_UNSIGNED_SHORT}, not {value}'
                raise TypeError(msg)
        if self.max_packet_life_time is not None and self.max_retransmits is not None:
            msg = 'max_packet_life_time and max_retransmits can not both be set'
            raise TypeError(msg)
        if not self.negotiated:
            return
        if self.id is None:
            msg = 'a negotiated channel needs an id'
            raise TypeError(msg)
        # the last stream id is reserved
        if self.id == MAX_UNSIGNED_SHORT:
            msg = f'id must be from 0 to {MAX_UNSIGNED_SHORT - 1}, not {self.id}'
            raise TypeError(msg)

    #: Alias for :attr:`max_packet_life_time`
    maxPacketLifeTime: ClassVar[Alias[int | None]] = alias('max_packet_life_time')
    #: Alias for :attr:`max_retransmits`
    maxRetransmits: ClassVar[Alias[int | None]] = alias('max_retransmits')


_DataChannelStateEvent = Literal['open', 'bufferedamountlow', 'closing', 'close']
_DataChannelEvent = Literal[_DataChannelStateEvent, 'message', 'error']
_R = TypeVar('_R')


class RTCDataChannel(WebRTCObject[wrtc.RTCDataChannel], EventTarget[_DataChannelEvent]):
    """A bidirectional channel of text and binary messages between the peers.

    Created with :meth:`webrtc.RTCPeerConnection.create_data_channel`, or delivered by the ``datachannel`` event of
    the connection when the remote peer creates one.

    See :mdn:`RTCDataChannel`.

    Events:
        open (:obj:`webrtc.Event`): The channel is open and messages can be sent. It isn't emitted if the
            channel closes before it opens.
        message (:obj:`webrtc.MessageEvent`): A message arrived. Its ``data`` is a :obj:`str` for text, and
            :obj:`bytes` or a :obj:`webrtc.Blob` for binary, depending on :attr:`binary_type` at delivery.
        bufferedamountlow (:obj:`webrtc.Event`): :attr:`buffered_amount` dropped to
            :attr:`buffered_amount_low_threshold` or below.
        error (:obj:`webrtc.RTCErrorEvent`): The channel failed, and closes right after.
        closing (:obj:`webrtc.Event`): The channel started closing.
        close (:obj:`webrtc.Event`): The channel is closed.
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
        """Registers a handler of an event of the channel. Can be used as a decorator.

        The events are listed in :obj:`RTCDataChannel`.

        Args:
            name (:obj:`str`): The name of the event, like ``'message'``.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.
                If omitted, a decorator is returned.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            ValueError: If the channel has no such event.
            RuntimeError: If called outside of a running event loop.
        """
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
        """Registers a handler of the next occurrence of an event of the channel. Can be used as a decorator.

        The events are listed in :obj:`RTCDataChannel`. The handler is removed after its first call.

        Args:
            name (:obj:`str`): The name of the event, like ``'message'``.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.
                If omitted, a decorator is returned.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            ValueError: If the channel has no such event.
            RuntimeError: If called outside of a running event loop.
        """
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
        """:obj:`str`: The label the channel was created with. Several channels can share one.

        See :mdn:`RTCDataChannel/label`.
        """
        return self._native_obj.label

    @property
    def ordered(self) -> bool:
        """:obj:`bool`: Whether messages arrive in the order they were sent.

        See :mdn:`RTCDataChannel/ordered`.
        """
        return self._native_obj.ordered

    @property
    def max_packet_life_time(self) -> int | None:
        """:obj:`int`, optional: For how many milliseconds a message may be retransmitted, or :obj:`None` if unlimited.

        See :mdn:`RTCDataChannel/maxPacketLifeTime`.
        """
        return self._native_obj.maxPacketLifeTime

    @property
    def max_retransmits(self) -> int | None:
        """:obj:`int`, optional: How many times a message may be retransmitted, or :obj:`None` if unlimited.

        See :mdn:`RTCDataChannel/maxRetransmits`.
        """
        return self._native_obj.maxRetransmits

    @property
    def protocol(self) -> str:
        """:obj:`str`: The subprotocol name of the channel, or an empty string if there's none.

        See :mdn:`RTCDataChannel/protocol`.
        """
        return self._native_obj.protocol

    @property
    def negotiated(self) -> bool:
        """:obj:`bool`: Whether the application negotiated the channel.

        Otherwise the connection announced it to the remote peer.
        See :mdn:`RTCDataChannel/negotiated`.
        """
        return self._native_obj.negotiated

    @property
    def id(self) -> int | None:
        """:obj:`int`, optional: The SCTP stream id of the channel.

        It's :obj:`None` until the connection assigns it.
        See :mdn:`RTCDataChannel/id`.
        """
        return self._native_obj.id

    @property
    def priority(self) -> webrtc.RTCPriorityType:
        """:obj:`webrtc.RTCPriorityType`: The priority of the channel.

        See :mdn:`RTCDataChannel/priority`.
        """
        return self._native_obj.priority

    @property
    def ready_state(self) -> webrtc.RTCDataChannelState:
        """:obj:`webrtc.RTCDataChannelState`: The state of the channel. It changes along with its events.

        See :mdn:`RTCDataChannel/readyState`.
        """
        return self._native_obj.readyState

    @property
    def buffered_amount(self) -> int:
        """:obj:`int`: The bytes passed to :meth:`send` that aren't sent yet.

        See :mdn:`RTCDataChannel/bufferedAmount`.
        """
        return self._native_obj.bufferedAmount

    @property
    def buffered_amount_low_threshold(self) -> int:
        """:obj:`int`: The :attr:`buffered_amount` at or below which ``bufferedamountlow`` is emitted, 0 by default.

        Setting a value outside of 0 to 2**64-1 raises :obj:`ValueError`.

        See :mdn:`RTCDataChannel/bufferedAmountLowThreshold`.
        """
        return self._native_obj.bufferedAmountLowThreshold

    @buffered_amount_low_threshold.setter
    def buffered_amount_low_threshold(self, value: int) -> None:
        if not 0 <= value < 2**64:
            msg = f'buffered_amount_low_threshold must be from 0 to 2**64-1, not {value}'
            raise ValueError(msg)
        self._native_obj.bufferedAmountLowThreshold = value

    @property
    def binary_type(self) -> BinaryType:
        """:obj:`webrtc.BinaryType`: What binary messages are delivered as, ``'arraybuffer'`` by default.

        ``'arraybuffer'`` delivers :obj:`bytes` and ``'blob'`` a :obj:`webrtc.Blob`. Setting a value that isn't a
        member raises :obj:`ValueError`.

        See :mdn:`RTCDataChannel/binaryType`.
        """
        return BinaryType(self._native_obj.binaryType)

    @binary_type.setter
    def binary_type(self, value: BinaryType | BinaryTypeValue) -> None:
        self._native_obj.binaryType = BinaryType(value).value

    def send(self, data: str | bytes | bytearray | memoryview | Blob) -> None:
        """Queues a message to the remote peer, adding its size to :attr:`buffered_amount`.

        A :obj:`str` is sent as a text message in UTF-8, anything else as a binary one.

        See :mdn:`RTCDataChannel/send`.

        Args:
            data (:obj:`str`, bytes-like or :obj:`webrtc.Blob`): The message.

        Raises:
            TypeError: If the data is neither a :obj:`str`, bytes-like nor a :obj:`webrtc.Blob`, or the message is
                larger than the maximum message size of the SCTP transport.
            webrtc.InvalidStateError: If the channel isn't open.
            webrtc.OperationError: If the send queue is full.
        """
        if isinstance(data, str):
            self._native_obj.send(usv_string(data).encode(), binary=False)
        elif isinstance(data, (bytes, bytearray, memoryview, Blob)):
            self._native_obj.send(bytes(data), binary=True)
        else:
            msg = f'data must be str, bytes-like or Blob, not {type(data).__name__}'
            raise TypeError(msg)

    def close(self) -> None:
        """Starts closing the channel, but messages queued before are still sent.

        It does nothing if the channel is already closing.
        See :mdn:`RTCDataChannel/close`.
        """
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
