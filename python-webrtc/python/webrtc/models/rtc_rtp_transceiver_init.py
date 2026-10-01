#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The options of a new transceiver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from webrtc import wrtc
from webrtc.enums import TransceiverDirection, TransceiverDirectionValue
from webrtc.models.dictionary import Dictionary
from webrtc.models.rtp_parameters import RTCRtpEncodingParameters
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc


@dataclass
class RTCRtpTransceiverInit(Dictionary):
    """The options of a new transceiver, for :meth:`webrtc.RTCPeerConnection.add_transceiver`.

    Args:
        direction (:obj:`webrtc.TransceiverDirection`, optional): The direction of the transceiver, ``sendrecv``
            by default.
        streams (:obj:`list` of :obj:`webrtc.MediaStream`, optional): The streams the remote peer receives the track
            of its sender in.
        send_encodings (:obj:`list` of :obj:`webrtc.RTCRtpEncodingParameters`, optional): The encodings of its
            sender, one per simulcast layer.

    Raises:
        ValueError: If the direction isn't a member of :obj:`webrtc.TransceiverDirection`.
    """

    direction: TransceiverDirection | TransceiverDirectionValue = TransceiverDirection.sendrecv
    streams: list[webrtc.MediaStream] = field(default_factory=list)
    send_encodings: list[RTCRtpEncodingParameters] = field(default_factory=list)

    _dictionaries: ClassVar = {'send_encodings': RTCRtpEncodingParameters}

    def __post_init__(self) -> None:
        self.direction = TransceiverDirection(self.direction)

    def _to_native(self, encodings: list[RTCRtpEncodingParameters]) -> wrtc.RtpTransceiverInit:
        """The native init, with the encodings to send (those of the init, adapted to the kind of the track)."""
        native = wrtc.RtpTransceiverInit()
        native.direction = self.direction
        native.sendEncodings = [encoding._to_native() for encoding in encodings]
        native.streamIds = [stream.id for stream in self.streams]
        return native

    #: Alias for :attr:`send_encodings`
    sendEncodings: ClassVar[Alias[list[RTCRtpEncodingParameters]]] = alias('send_encodings')
