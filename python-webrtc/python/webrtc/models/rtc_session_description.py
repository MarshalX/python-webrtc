#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING

from webrtc import wrtc, WebRTCObject, RTCSessionDescriptionInit

if TYPE_CHECKING:
    import webrtc


# TODO drop constructor with Init from cpp part (behavior should be like in the note)
class RTCSessionDescription(WebRTCObject):
    """The :obj:`webrtc.RTCSessionDescription` interface describes one end of a connection or potential
    connection and how it's configured. Each :obj:`webrtcRTCSessionDescription` consists of
    a description type indicating which part of the offer/answer negotiation process it describes
    and of the SDP descriptor of the session.

    The process of negotiating a connection between two peers involves exchanging :obj:`webrtc.RTCSessionDescription`
    objects back and forth, with each description suggesting one combination of connection configuration options
    that the sender of the description supports. Once the two peers agree upon a configuration
    for the connection, negotiation is complete.

    Note:
        Note: Constructor with :obj:`webrtc.RTCSessionDescriptionInit` is no longer necessary,
        however; :obj:`RTCPeerConnection.setLocalDescription()` and other methods
        which take SDP as input now directly accept an object conforming to the :obj:webrtc.RTCSessionDescriptionInit`
        object, so you don't have to instantiate an :obj:`webrtc.RTCSessionDescription` yourself.

    Warning:
        Deprecated: Constructor with :obj:`webrtc.RTCSessionDescriptionInit` is no longer recommended.
        Though some browsers might still support it, it may have already been removed from the relevant web standards,
        may be in the process of being dropped, or may only be kept for compatibility purposes.
    """

    _class = wrtc.RTCSessionDescription

    def __init__(self, rtc_session_description_init: 'webrtc.RTCSessionDescriptionInit'):
        # TODO remove tmp solution with Init obj after changes in cpp part
        if isinstance(rtc_session_description_init, RTCSessionDescriptionInit):
            self._set_native_obj(self._class(rtc_session_description_init._native_obj))
        else:
            super().__init__(rtc_session_description_init)

    @property
    def type(self) -> 'webrtc.RTCSdpType':
        """:obj:`webrtc.RTCSdpType`: A member of the :obj:`webrtc.RTCSdpType` enum."""
        return self._native_obj.type

    @property
    def sdp(self):
        """:obj:`str`: A string containing a SDP message describing the session."""
        return self._native_obj.sdp
