#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Dict

from webrtc import WebRTCObject, wrtc

if TYPE_CHECKING:
    import webrtc


class RTCSessionDescriptionInit(WebRTCObject):
    """The type and the SDP of a description, as :meth:`webrtc.RTCPeerConnection.create_offer` and
    :meth:`webrtc.RTCPeerConnection.create_answer` return them.

    Args:
        type (:obj:`webrtc.RTCSdpType`): The type of the description, or its value (like ``'offer'``).
        sdp (:obj:`str`, optional): The SDP of the description.
    """

    _class = wrtc.RTCSessionDescriptionInit

    def __init__(self, type: 'webrtc.RTCSdpType', sdp: str = ''):
        super().__init__(self._class(type, sdp))

    @property
    def type(self) -> 'webrtc.RTCSdpType':
        """:obj:`webrtc.RTCSdpType`: A member of the :obj:`webrtc.RTCSdpType` enum."""
        return self._native_obj.type

    @type.setter
    def type(self, value: 'webrtc.RTCSdpType'):
        self._native_obj.type = value

    @property
    def sdp(self) -> str:
        """:obj:`str`: A string containing a SDP message describing the session.
        This value is an empty string by default and may not be :obj:`None`."""
        return self._native_obj.sdp

    @sdp.setter
    def sdp(self, value: str):
        self._native_obj.sdp = value

    def to_json(self) -> Dict[str, str]:
        """The description as a JSON-serializable dictionary, to send to the remote peer.

        Returns:
            :obj:`dict`: ``type`` (like ``'offer'``) and ``sdp``.
        """
        return {'type': self.type.value, 'sdp': self.sdp}

    def __repr__(self):
        return f'RTCSessionDescriptionInit(type={self.type.value!r}, sdp={len(self.sdp)} characters)'

    #: Alias for :attr:`to_json`
    toJSON = to_json
