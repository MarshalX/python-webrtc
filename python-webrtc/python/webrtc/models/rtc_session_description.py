#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The description of one end of a connection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from webrtc import RTCSessionDescriptionInit, WebRTCObject, wrtc

if TYPE_CHECKING:
    import webrtc


class RTCSessionDescription(WebRTCObject[wrtc.RTCSessionDescription]):
    """One end of a connection or potential connection and how it's configured.

    Each :obj:`webrtc.RTCSessionDescription` consists of
    a description type indicating which part of the offer/answer negotiation process it describes
    and of the SDP descriptor of the session.

    The process of negotiating a connection between two peers involves exchanging :obj:`webrtc.RTCSessionDescription`
    objects back and forth, with each description suggesting one combination of connection configuration options
    that the sender of the description supports. Once the two peers agree upon a configuration
    for the connection, negotiation is complete.

    Note:
        :meth:`webrtc.RTCPeerConnection.set_local_description` and
        :meth:`webrtc.RTCPeerConnection.set_remote_description` also take an
        :obj:`webrtc.RTCSessionDescriptionInit`, so creating an
        :obj:`webrtc.RTCSessionDescription` isn't necessary.

    Args:
        type (:obj:`webrtc.RTCSdpType`): The type of the description, required as in the specification.
            An :obj:`webrtc.RTCSessionDescriptionInit` is accepted too (see
            :meth:`webrtc.RTCSessionDescriptionInit.from_json` for its JSON form).
        sdp (:obj:`str`, optional): The SDP of the description, empty by default. It's parsed when the description
            is set.

    Raises:
        ValueError: If the type isn't a member of :obj:`webrtc.RTCSdpType`.
        TypeError: If the SDP is :obj:`None`.
    """

    _class = wrtc.RTCSessionDescription

    def __init__(
        self,
        type: webrtc.RTCSdpType | webrtc.RTCSdpTypeValue | webrtc.RTCSessionDescriptionInit,
        sdp: str = '',
    ) -> None:
        init = type if isinstance(type, RTCSessionDescriptionInit) else RTCSessionDescriptionInit(type, sdp)
        super().__init__(wrtc.RTCSessionDescription(init._to_native()))

    def to_json(self) -> dict[str, str]:
        """The description as a JSON-serializable dictionary, to send to the remote peer.

        Returns:
            :obj:`dict`: ``type`` (like ``'offer'``) and ``sdp``.
        """
        return {'type': self.type.value, 'sdp': self.sdp}

    @property
    def type(self) -> webrtc.RTCSdpType:
        """:obj:`webrtc.RTCSdpType`: A member of the :obj:`webrtc.RTCSdpType` enum."""
        return self._native_obj.type

    @property
    def sdp(self) -> str:
        """:obj:`str`: A string containing a SDP message describing the session."""
        return self._native_obj.sdp

    #: Alias for :attr:`to_json`
    toJSON = to_json
