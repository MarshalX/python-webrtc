#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING

from webrtc import wrtc, WebRTCObject, MediaStreamTrack

if TYPE_CHECKING:
    import webrtc


class RTCRtpReceiver(WebRTCObject):
    """The :obj:`webrtc.RTCRtpReceiver` interface of the WebRTC API manages the reception and decoding of data
    for a :obj:`webrtc.MediaStreamTrack` on an :obj:`webrtc.RTCPeerConnection`."""

    _class = wrtc.RTCRtpReceiver

    @property
    def track(self) -> 'webrtc.MediaStreamTrack':
        """:obj:`webrtc.MediaStreamTrack`: The :obj:`webrtc.MediaStreamTrack` associated with the current
        :obj:`webrtc.RTCRtpReceiver` instance."""
        track = self._native_obj.track

        return MediaStreamTrack._wrap(track)
