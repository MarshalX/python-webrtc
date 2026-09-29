#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Optional, Union

from webrtc import BinaryType, Blob, MessageEvent, RTCDataChannelState, RTCErrorEvent, WebRTCObject, wrtc
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc


class RTCDataChannel(WebRTCObject, EventTarget):
    """A bidirectional channel of messages between the peers, created with
    :meth:`webrtc.RTCPeerConnection.create_data_channel` or received with its ``datachannel`` event.

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
    _events = ('open', 'message', 'bufferedamountlow', 'error', 'closing', 'close')

    def _on_event(self, name: str, *args):
        # readyState changes along with the events
        if name in ('open', 'closing', 'close'):
            (state,) = args
            self._native_obj._surfaceState(state)
        elif name == '_sent':
            (size,) = args
            if self._native_obj._decreaseBufferedAmount(size):
                # in the same task as the decrease, before anything that arrived meanwhile
                self._dispatch('bufferedamountlow')

    def _create_event(self, name: str, *args):
        if name == 'open' and self.ready_state != RTCDataChannelState.open:
            # closed before it opened
            return None
        if name == 'message':
            (message,) = args
            data = message.data
            # binary_type as of delivery, per the specification
            if isinstance(data, bytes) and self._native_obj.binaryType == BinaryType.blob:
                data = Blob([data])
            return MessageEvent(name, data, target=self)
        if name == 'error':
            (error,) = args
            return RTCErrorEvent(name, error.toPython(), target=self)
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
    def max_packet_life_time(self) -> Optional[int]:
        """:obj:`int`, optional: How long in milliseconds a message is retransmitted in unreliable mode."""
        return self._native_obj.maxPacketLifeTime

    @property
    def max_retransmits(self) -> Optional[int]:
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
    def id(self) -> Optional[int]:
        """:obj:`int`, optional: The SCTP stream id of the channel, :obj:`None` until it's known."""
        return self._native_obj.id

    @property
    def priority(self) -> 'webrtc.RTCPriorityType':
        """:obj:`webrtc.RTCPriorityType`: The priority of the channel."""
        return self._native_obj.priority

    @property
    def ready_state(self) -> 'webrtc.RTCDataChannelState':
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
    def buffered_amount_low_threshold(self, value: int):
        if not 0 <= value < 2**64:
            raise ValueError(f'buffered_amount_low_threshold must be from 0 to 2**64-1, not {value}')
        self._native_obj.bufferedAmountLowThreshold = value

    @property
    def binary_type(self) -> BinaryType:
        """:obj:`webrtc.BinaryType`: What binary messages are delivered as: :obj:`bytes` (``arraybuffer``, the
        default) or :obj:`webrtc.Blob` (``blob``)."""
        return BinaryType(self._native_obj.binaryType)

    @binary_type.setter
    def binary_type(self, value: Union[BinaryType, str]):
        self._native_obj.binaryType = BinaryType(value).value

    def send(self, data: Union[str, bytes, bytearray, memoryview, Blob]) -> None:
        """Sends a message to the remote peer.

        Args:
            data (:obj:`str`, bytes-like or :obj:`webrtc.Blob`): A text message, or a binary one.

        Raises:
            :obj:`TypeError`: If the data is neither text, bytes nor a :obj:`webrtc.Blob`.
            :obj:`webrtc.InvalidStateError`: If the channel isn't open.
            :obj:`webrtc.OperationError`: If the message can't be queued, like when the queue is full.
        """
        if isinstance(data, str):
            self._native_obj.send(data.encode(), False)
        elif isinstance(data, (bytes, bytearray, memoryview, Blob)):
            self._native_obj.send(bytes(data), True)
        else:
            raise TypeError(f'data must be str, bytes-like or Blob, not {type(data).__name__}')

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
