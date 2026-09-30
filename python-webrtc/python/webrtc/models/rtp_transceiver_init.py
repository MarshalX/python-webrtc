#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The options of a new transceiver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from webrtc import WebRTCObject, wrtc

if TYPE_CHECKING:
    import webrtc


class RtpTransceiverInit(WebRTCObject):
    """The options of a new transceiver, for :meth:`webrtc.RTCPeerConnection.add_transceiver`.

    Args:
        direction (:obj:`webrtc.TransceiverDirection`, optional): The direction of the transceiver, ``sendrecv``
            by default.
        send_encodings (:obj:`list` of :obj:`webrtc.RTCRtpEncodingParameters`, optional): The encodings of its
            sender, one per simulcast layer.
        streams (:obj:`list` of :obj:`webrtc.MediaStream`, optional): The streams the remote peer receives the track
            of its sender in.
    """

    _class = wrtc.RtpTransceiverInit

    def __init__(
        self,
        direction: webrtc.TransceiverDirection | None = None,
        send_encodings: list[webrtc.RTCRtpEncodingParameters] | None = None,
        streams: list[webrtc.MediaStream] | None = None,
    ) -> None:
        super().__init__()
        self.__send_encodings = []

        if direction:
            self.direction = direction
        if send_encodings:
            self.send_encodings = send_encodings

        self.__original_streams = None
        if streams:
            self.streams = streams

    @property
    def direction(self) -> webrtc.TransceiverDirection:
        """:obj:`webrtc.TransceiverDirection`: The new transceiver's preferred directionality.

        This value is used to initialize the new :obj:`webrtc.RTCRtpTransceiver` object's
        :attr:`webrtc.RTCRtpTransceiver.direction` property.
        """
        return self._native_obj.direction

    @direction.setter
    def direction(self, value: webrtc.TransceiverDirection) -> None:
        self._native_obj.direction = value

    @property
    def send_encodings(self) -> list[webrtc.RTCRtpEncodingParameters]:
        """:obj:`list` of :obj:`webrtc.RTCRtpEncodingParameters`: The encodings of the sender.

        The encodings to allow when sending RTP media from the :obj:`webrtc.RTCRtpSender`, one per simulcast layer.
        """
        return list(self.__send_encodings)

    @send_encodings.setter
    def send_encodings(self, value: list[webrtc.RTCRtpEncodingParameters]) -> None:
        self.__send_encodings = list(value)
        self._native_obj.sendEncodings = [param._to_native() for param in value]

    @property
    def streams(self) -> list[webrtc.MediaStream]:
        """:obj:`list` of :obj:`webrtc.MediaStream`: The streams of the track of the sender.

        When the remote peer's :obj:`webrtc.RTCPeerConnection`'s track event occurs, these are the streams that will be
        specified by that event.
        """
        return self.__original_streams

    @streams.setter
    def streams(self, value: list[webrtc.MediaStream]) -> None:
        self.__original_streams = value

        self._native_obj.streamIds = [stream.id for stream in value]

    #: Alias for :attr:`send_encodings`
    sendEncodings = send_encodings
