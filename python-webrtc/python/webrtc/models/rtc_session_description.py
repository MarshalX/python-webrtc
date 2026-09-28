#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Any, Dict, Union

from webrtc import RTCSessionDescriptionInit, WebRTCObject, wrtc

if TYPE_CHECKING:
    import webrtc


class RTCSessionDescription(WebRTCObject):
    """The :obj:`webrtc.RTCSessionDescription` interface describes one end of a connection or potential
    connection and how it's configured. Each :obj:`webrtc.RTCSessionDescription` consists of
    a description type indicating which part of the offer/answer negotiation process it describes
    and of the SDP descriptor of the session.

    The process of negotiating a connection between two peers involves exchanging :obj:`webrtc.RTCSessionDescription`
    objects back and forth, with each description suggesting one combination of connection configuration options
    that the sender of the description supports. Once the two peers agree upon a configuration
    for the connection, negotiation is complete.

    Note:
        :meth:`webrtc.RTCPeerConnection.set_local_description` and
        :meth:`webrtc.RTCPeerConnection.set_remote_description` also take an
        :obj:`webrtc.RTCSessionDescriptionInit` or a :obj:`dict`, so creating an
        :obj:`webrtc.RTCSessionDescription` isn't necessary.

    Args:
        type (:obj:`webrtc.RTCSdpType`): The type of the description. An :obj:`webrtc.RTCSessionDescriptionInit`
            or its JSON form (a :obj:`dict` with ``type`` and ``sdp`` keys) is accepted too.
        sdp (:obj:`str`, optional): The SDP of the description. It's parsed when the description is set.
    """

    _class = wrtc.RTCSessionDescription

    def __init__(
        self,
        type: Union['webrtc.RTCSdpType', 'webrtc.RTCSessionDescriptionInit', Dict[str, Any]],
        sdp: str = '',
    ):
        if isinstance(type, dict):
            type, sdp = type['type'], type.get('sdp') or ''
        init = type if isinstance(type, RTCSessionDescriptionInit) else RTCSessionDescriptionInit(type, sdp)
        super().__init__(self._class(init._native_obj))

    def to_json(self) -> Dict[str, str]:
        """The description as a JSON-serializable dictionary, to send to the remote peer.

        Returns:
            :obj:`dict`: ``type`` (like ``'offer'``) and ``sdp``.
        """
        return {'type': self.type.value, 'sdp': self.sdp}

    @property
    def type(self) -> 'webrtc.RTCSdpType':
        """:obj:`webrtc.RTCSdpType`: A member of the :obj:`webrtc.RTCSdpType` enum."""
        return self._native_obj.type

    @property
    def sdp(self):
        """:obj:`str`: A string containing a SDP message describing the session."""
        return self._native_obj.sdp

    #: Alias for :attr:`to_json`
    toJSON = to_json
