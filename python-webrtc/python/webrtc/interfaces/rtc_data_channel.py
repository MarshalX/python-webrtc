#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import enum
from typing import TYPE_CHECKING, Optional, Union

from webrtc import WebRTCObject, wrtc
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc

RTCDataChannelState = wrtc.RTCDataChannelState


class RTCPriorityType(str, enum.Enum):
    """The priority of a data channel or an encoding, relative to the others."""

    very_low = 'very-low'
    low = 'low'
    medium = 'medium'
    high = 'high'

    @property
    def _native(self) -> int:
        # RFC 8831 priorities, as libwebrtc takes them
        return {'very-low': 128, 'low': 256, 'medium': 512, 'high': 1024}[self.value]

    @classmethod
    def _from_native(cls, value: int) -> 'RTCPriorityType':
        # the ranges Chromium maps libwebrtc priorities to
        if value <= 192:
            return cls.very_low
        if value <= 384:
            return cls.low
        if value <= 768:
            return cls.medium
        return cls.high


class RTCDataChannel(WebRTCObject, EventTarget):
    """A bidirectional channel of messages between the peers, created with
    :meth:`webrtc.RTCPeerConnection.create_data_channel` or received with its ``datachannel`` event.

    Events (see :meth:`on`):
        ``open`` (:obj:`webrtc.Event`): The channel can be used to send messages.
        ``message`` (:obj:`webrtc.MessageEvent`): A message arrived, its ``data`` is :obj:`str` or :obj:`bytes`.
        ``bufferedamountlow`` (:obj:`webrtc.Event`): :attr:`buffered_amount` dropped to
        :attr:`buffered_amount_low_threshold`.
        ``error`` (:obj:`webrtc.RTCErrorEvent`): The channel failed, it's closed right after.
        ``closing`` (:obj:`webrtc.Event`): The channel started closing.
        ``close`` (:obj:`webrtc.Event`): The channel is closed.

    Events of a channel aren't lost before handlers can be registered: they start to be delivered on the next
    iteration of the event loop after :meth:`webrtc.RTCPeerConnection.create_data_channel`, or after
    the handlers of the ``datachannel`` event have run.
    """

    _class = wrtc.RTCDataChannel
    _events = ('open', 'message', 'bufferedamountlow', 'error', 'closing', 'close')

    def _on_event(self, name: str, *args):
        # readyState changes along with the events
        if name in ('open', 'closing', 'close'):
            self._native_obj._surface(args[0])
        elif name == '_sent' and self._native_obj._decreaseBufferedAmount(args[0]):
            # in the same task as the decrease, before anything that arrived meanwhile
            self._dispatch('bufferedamountlow')

    def _create_event(self, name: str, *args):
        import webrtc

        if name == 'open' and self.ready_state != RTCDataChannelState.open:
            # closed before it opened
            return None
        if name == 'message':
            return webrtc.MessageEvent(name, args[0].data, target=self)
        if name == 'error':
            return webrtc.RTCErrorEvent(name, args[0].to_python(), target=self)
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
    def priority(self) -> RTCPriorityType:
        """:obj:`webrtc.RTCPriorityType`: The priority of the channel."""
        return RTCPriorityType._from_native(self._native_obj.priority)

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
            raise ValueError(f'buffered_amount_low_threshold must not be negative, not {value}')
        self._native_obj.bufferedAmountLowThreshold = value

    def send(self, data: Union[str, bytes, bytearray, memoryview]) -> None:
        """Sends a message to the remote peer.

        Args:
            data (:obj:`str` or bytes-like): A text message, or a binary one.

        Raises:
            :obj:`TypeError`: If the data is neither text nor bytes.
            :obj:`webrtc.InvalidStateError`: If the channel isn't open.
            :obj:`webrtc.OperationError`: If the message can't be queued, like when the queue is full.
        """
        if isinstance(data, str):
            self._native_obj.send(data.encode(), False)
        elif isinstance(data, (bytes, bytearray, memoryview)):
            self._native_obj.send(bytes(data), True)
        else:
            raise TypeError(f'data must be str or bytes-like, not {type(data).__name__}')

    def close(self) -> None:
        """Closes the channel. Messages queued before are still sent."""
        self._native_obj.close()

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
