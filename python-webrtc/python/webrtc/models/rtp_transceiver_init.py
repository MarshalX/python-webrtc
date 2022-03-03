#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Optional, List

from webrtc import wrtc, WebRTCObject


if TYPE_CHECKING:
    import webrtc


class RtpTransceiverInit(WebRTCObject):
    """A model for specifying any options when creating the new transceiver."""

    _class = wrtc.RtpTransceiverInit

    def __init__(
        self,
        direction: Optional['webrtc.RtpTransceiverDirection'] = None,
        send_encodings: Optional[List['webrtc.RtpEncodingParameters']] = None,
        streams: Optional[List['webrtc.MediaStream']] = None,
    ):
        super().__init__()

        if direction:
            self.direction = direction
        if send_encodings:
            self.send_encodings = send_encodings

        self.__original_streams = None
        if streams:
            self.streams = streams

    @property
    def direction(self) -> 'webrtc.TransceiverDirection':
        """:obj:`webrtc.TransceiverDirection`: The new transceiver's preferred directionality.
        This value is used to initialize the new :obj:`webrtc.RTCRtpTransceiver` object's
        :attr:`webrtc.RTCRtpTransceiver.direction` property."""
        return self._native_obj.direction

    @direction.setter
    def direction(self, value: 'webrtc.TransceiverDirection'):
        self._native_obj.direction = value

    @property
    def send_encodings(self) -> List['webrtc.RtpEncodingParameters']:
        """:obj:`list` of :obj:`webrtc.RtpEncodingParameters`: A list of encodings to allow when sending RTP media
        from the :obj:`webrtc.RTCRtpSender`. Each entry is of type :obj:`webrtc.RtpEncodingParameters`."""
        from webrtc import RtpEncodingParameters

        return RtpEncodingParameters._wrap_many(self._native_obj.sendEncodings)

    @send_encodings.setter
    def send_encodings(self, value: List['webrtc.RtpEncodingParameters']):
        self._native_obj.sendEncodings = [param._native_obj for param in value]

    @property
    def streams(self) -> List['webrtc.MediaStream']:
        """:obj:`list` of :obj:`webrtc.MediaStream`: A list of :obj:`webrtc.MediaStream` objects to add to the
        transceiver's :obj:`webrtc.RTCRtpReceiver`; when the remote peer's :obj:`webrtc.RTCPeerConnection`'s track
        event occurs, these are the streams that will be specified by that event."""
        return self.__original_streams

    @streams.setter
    def streams(self, value: List['webrtc.MediaStream']):
        self.__original_streams = value

        self._native_obj.streamIds = [stream.id for stream in value]

    #: Alias for :attr:`send_encodings`
    sendEncodings = send_encodings
