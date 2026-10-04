#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Session descriptions as plain data, to set on a connection or to exchange with the remote peer."""

from __future__ import annotations

from dataclasses import dataclass

import wrtc
from webrtc.enums import RTCSdpType, RTCSdpTypeValue
from webrtc.models.dictionary import Dictionary


@dataclass
class RTCSessionDescriptionInit(Dictionary):
    """The type and the SDP of a session description, as plain data.

    :meth:`webrtc.RTCPeerConnection.create_offer` and :meth:`webrtc.RTCPeerConnection.create_answer` return it, and
    the methods that set a description take it. :meth:`from_json` creates it from a message of the remote peer.
    See :mdn:`RTCSessionDescription/RTCSessionDescription`.

    Args:
        type (:obj:`webrtc.RTCSdpType`): The type of the description, or its value (like ``'offer'``).
        sdp (:obj:`str`, optional): The SDP of the description, empty by default.

    Raises:
        ValueError: If the type isn't a member of :obj:`webrtc.RTCSdpType`.
        TypeError: If the SDP is :obj:`None`.
    """

    type: RTCSdpType | RTCSdpTypeValue
    sdp: str = ''

    def __post_init__(self) -> None:
        self.type = RTCSdpType(self.type)
        if self.sdp is None:
            msg = 'The SDP of a description may not be None'
            raise TypeError(msg)

    def _to_native(self) -> wrtc.RTCSessionDescriptionInit:
        return wrtc.RTCSessionDescriptionInit(self.type, self.sdp)

    def __repr__(self) -> str:
        return f'RTCSessionDescriptionInit(type={RTCSdpType(self.type).value!r}, sdp={len(self.sdp)} characters)'


@dataclass
class RTCLocalSessionDescriptionInit(Dictionary):
    """A description for :meth:`webrtc.RTCPeerConnection.set_local_description`, whose type may be left out.

    Without an SDP, the connection creates and sets the description itself. It uses the given type, or else the
    offer or answer that its signaling state calls for. See :mdn:`RTCPeerConnection/setLocalDescription`.

    Args:
        type (:obj:`webrtc.RTCSdpType`, optional): The type of the description, or its value (like ``'offer'``).
            Required when an SDP is given.
        sdp (:obj:`str`, optional): The SDP of the description, empty by default.

    Raises:
        ValueError: If the type isn't a member of :obj:`webrtc.RTCSdpType`.
        TypeError: If the SDP is :obj:`None`.
    """

    type: RTCSdpType | RTCSdpTypeValue | None = None
    sdp: str = ''

    def __post_init__(self) -> None:
        if self.type is not None:
            self.type = RTCSdpType(self.type)
        if self.sdp is None:
            msg = 'The SDP of a description may not be None'
            raise TypeError(msg)
