#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The type and the SDP of a description."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from webrtc import wrtc
from webrtc.enums import RTCSdpType
from webrtc.models.dictionary import Dictionary


@dataclass
class RTCSessionDescriptionInit(Dictionary):
    """The type and the SDP of a description.

    As :meth:`webrtc.RTCPeerConnection.create_offer` and :meth:`webrtc.RTCPeerConnection.create_answer` return them.

    Args:
        type (:obj:`webrtc.RTCSdpType`): The type of the description, or its value (like ``'offer'``).
        sdp (:obj:`str`, optional): The SDP of the description.

    Raises:
        ValueError: If the type isn't a member of :obj:`webrtc.RTCSdpType`.
        TypeError: If the SDP is :obj:`None`.
    """

    type: RTCSdpType
    sdp: str = ''

    def __post_init__(self) -> None:
        self.type = RTCSdpType(self.type)
        if self.sdp is None:
            msg = 'The SDP of a description may not be None'
            raise TypeError(msg)

    def _to_native(self) -> wrtc.RTCSessionDescriptionInit:
        return wrtc.RTCSessionDescriptionInit(self.type, self.sdp)

    def to_json(self) -> dict[str, str]:
        """The description as a JSON-serializable dictionary, to send to the remote peer.

        Returns:
            :obj:`dict`: ``type`` (like ``'offer'``) and ``sdp``.
        """
        return {'type': self.type.value, 'sdp': self.sdp}

    def __repr__(self) -> str:
        return f'RTCSessionDescriptionInit(type={self.type.value!r}, sdp={len(self.sdp)} characters)'

    #: Alias for :attr:`to_json`
    toJSON: ClassVar = to_json


@dataclass
class RTCLocalSessionDescriptionInit(Dictionary):
    """A local description, whose type may be left out (:meth:`webrtc.RTCPeerConnection.set_local_description`).

    Without a type, nor an SDP, the offer or the answer the signaling state calls for is created and set.

    Args:
        type (:obj:`webrtc.RTCSdpType`, optional): The type of the description, or its value (like ``'offer'``).
        sdp (:obj:`str`, optional): The SDP of the description.

    Raises:
        ValueError: If the type isn't a member of :obj:`webrtc.RTCSdpType`.
        TypeError: If the SDP is :obj:`None`.
    """

    type: RTCSdpType | None = None
    sdp: str = ''

    def __post_init__(self) -> None:
        if self.type is not None:
            self.type = RTCSdpType(self.type)
        if self.sdp is None:
            msg = 'The SDP of a description may not be None'
            raise TypeError(msg)
