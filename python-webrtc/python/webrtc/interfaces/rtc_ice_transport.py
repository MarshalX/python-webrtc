#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING

from webrtc import wrtc, WebRTCObject

if TYPE_CHECKING:
    import webrtc


class RTCIceTransport(WebRTCObject):
    """The :obj:`webrtc.RTCIceTransport` interface provides access to information about the ICE transport layer
    over which the data is being sent and received. This is particularly useful if you need to access state
    information about the connection."""

    _class = wrtc.RTCIceTransport

    @property
    def component(self) -> 'webrtc.RTCIceComponent':
        """The ICE component being used by the transport. The value is one of the strings from
        the :obj:`webrtc.RTCIceComponent` enumerated type: "RTP" or "RTSP"."""
        return self._native_obj.component

    @property
    def gathering_state(self) -> 'webrtc.CricketIceGatheringState':
        """A member of :obj:`webrtc.CricketIceGatheringState` enum, indicating which current
        gathering state of the ICE agent"""
        return self._native_obj.gatheringState

    @property
    def role(self) -> 'webrtc.RTCIceRole':
        """A member of :obj:`webrtc.RTCIceRole`; this indicates whether the ICE agent is the one that makes the
        final decision as to the candidate pair to use or not."""
        return self._native_obj.role

    @property
    def state(self) -> 'webrtc.RTCIceTransportState':
        """A member of :obj:`webrtc.RTCIceTransportState` indicating what the current state of the ICE agent is.

        Note:
            For more details of values: https://developer.mozilla.org/en-US/docs/Web/API/RTCIceTransportState
        """
        return self._native_obj.state

    #: Alias for :attr:`gathering_state`
    gatheringState = gathering_state
