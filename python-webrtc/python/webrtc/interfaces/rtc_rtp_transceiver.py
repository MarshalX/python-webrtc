#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Optional

from webrtc import wrtc, WebRTCObject

if TYPE_CHECKING:
    import webrtc


class RTCRtpTransceiver(WebRTCObject):
    """The WebRTC interface :obj:`webrtc.RTCRtpTransceiver` describes a permanent pairing of
    an :obj:`webrtc.RTCRtpSender` and an :obj:`webrtc.RTCRtpReceiver`, along with some shared state.
    """

    _class = wrtc.RTCRtpTransceiver

    @property
    def mid(self) -> Optional[str]:
        """A :obj:`str` which uniquely identifies the pairing of source and destination of the transceiver's stream.
        Its value is taken from the media ID of the SDP m-line. This value is :obj:`None` if negotiation
        has not completed."""
        return self._native_obj.mid

    @property
    def receiver(self) -> 'webrtc.RTCRtpReceiver':
        """A :obj:`webrtc.RTCRtpReceiver` object which is responsible for receiving and decoding incoming media data
        whose media ID is the same as the current value of :attr:`mid`."""
        from webrtc import RTCRtpReceiver

        return RTCRtpReceiver._wrap(self._native_obj.receiver)

    @property
    def sender(self) -> 'webrtc.RTCRtpSender':
        """A :obj:`webrtc.RTCRtpSender` object used to encode and send media whose media ID matches
        the current value of :attr:`mid`."""
        from webrtc import RTCRtpSender

        return RTCRtpSender._wrap(self._native_obj.sender)

    @property
    def stopped(self) -> bool:
        """A :obj:`bool` value which is :obj:`True` if the transceiver's :attr:`sender` will no longer send data,
        and its :attr:`receiver` will no longer receive data. If either or both are still at work,
        the result is :obj:`False`.

        Warning:
            Deprecated: This feature is no longer recommended.
        """
        return self._native_obj.stopped

    @property
    def direction(self) -> 'webrtc.TransceiverDirection':
        """A member of :obj:`webrtc.TransceiverDirection` enum, indicating the transceiver's preferred direction.

        Note:
            The transceiver's current direction is indicated by the :attr:`currentDirection` property.
        """
        return self._native_obj.direction

    @direction.setter
    def direction(self, new_direction: 'webrtc.TransceiverDirection'):
        self._native_obj.direction = new_direction

    @property
    def current_direction(self) -> Optional['webrtc.TransceiverDirection']:
        """A member of :obj:`webrtc.TransceiverDirection` enum, indicating
        the current directionality of the transceiver."""
        return self._native_obj.currentDirection

    def stop(self) -> None:
        """Permanently stops the transceiver by stopping both the associated :obj:`webrtc.RTCRtpSender`
        and :obj:`webrtc.RTCRtpReceiver`.

        Note:
            The :attr:`stopped` property was provided to return :obj:`True` if the connection is stopped.
            That property has been deprecated and will be removed at some point. Instead, check the value
            of :attr:`currentDirection`. If it's :obj:`webrtc.TransceiverDirection.stopped`, the transceiver
            has been stopped.
        """
        self._native_obj.stop()

    #: Alias for :attr:`current_direction`
    currentDirection = current_direction
