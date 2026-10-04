#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The options of a new transceiver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import wrtc
from webrtc.enums import RTCRtpTransceiverDirection, RTCRtpTransceiverDirectionValue
from webrtc.models.dictionary import Dictionary
from webrtc.models.rtp_parameters import RTCRtpEncodingParameters
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc


@dataclass
class RTCRtpTransceiverInit(Dictionary):
    """The options of a new transceiver, for :meth:`webrtc.RTCPeerConnection.add_transceiver`.

    It isn't changed by the call, so it can be reused. See :mdn:`RTCPeerConnection/addTransceiver`.

    Args:
        direction (:obj:`webrtc.RTCRtpTransceiverDirection`, optional): The preferred direction of the transceiver,
            or its value. It's ``sendrecv`` by default.
        streams (:obj:`list` of :obj:`webrtc.MediaStream`, optional): The local streams that the remote peer
            receives the sender's track in. They're signaled by their ids.
        send_encodings (:obj:`list` of :obj:`webrtc.RTCRtpEncodingParameters`, optional): The encodings of the
            sender, one per simulcast layer. With several, each needs a distinct ``rid``.

    Raises:
        ValueError: If the direction isn't a member of :obj:`webrtc.RTCRtpTransceiverDirection`.
    """

    direction: RTCRtpTransceiverDirection | RTCRtpTransceiverDirectionValue = RTCRtpTransceiverDirection.sendrecv
    streams: list[webrtc.MediaStream] = field(default_factory=list)
    send_encodings: list[RTCRtpEncodingParameters] = field(default_factory=list)

    _dictionaries: ClassVar = {'send_encodings': RTCRtpEncodingParameters}

    def __post_init__(self) -> None:
        self.direction = RTCRtpTransceiverDirection(self.direction)

    def _to_native(self, encodings: list[RTCRtpEncodingParameters]) -> wrtc.RtpTransceiverInit:
        """The native init, with the encodings to send (those of the init, adapted to the kind of the track)."""
        native = wrtc.RtpTransceiverInit()
        native.direction = self.direction
        native.sendEncodings = [encoding._to_native() for encoding in encodings]
        native.streamIds = [stream.id for stream in self.streams]
        return native

    #: Alias for :attr:`send_encodings`
    sendEncodings: ClassVar[Alias[list[RTCRtpEncodingParameters]]] = alias('send_encodings')
