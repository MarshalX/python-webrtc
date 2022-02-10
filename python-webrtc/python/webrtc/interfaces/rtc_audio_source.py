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


class RTCAudioSource(WebRTCObject):
    """The :obj:`webrtc.MediaStreamTrack` interface represents a single media track within a stream;
    typically, these are audio or video tracks, but other track types may exist as well.
    """

    _class = wrtc.RTCAudioSource

    def create_track(self) -> 'webrtc.MediaStreamTrack':
        """Create :obj:`webrtc.MediaStreamTrack` whose source is the :obj:`webrtc.RTCAudioSource`.

        Returns:
            :obj:`webrtc.MediaStreamTrack`: A :obj:`webrtc.MediaStreamTrack` object representing the media track.
        """
        return MediaStreamTrack._wrap(self._native_obj.createTrack())

    def on_data(self, data: 'webrtc.RTCOnDataEvent'):
        """Push a new audio samples to every non-stopped local audio :obj:`webrtc.MediaStreamTrack`
        created with :attr:`createTrack`.

        Args:
            data (:obj:`webrtc.RTCOnDataEvent`): A :obj:`webrtc.RTCOnDataEvent` object representing new audio samples.

        Returns:
            :obj:`None`:
        """
        return self._native_obj.onData(data._native_obj)

    #: Alias for :attr:`create_track`
    createTrack = create_track
    #: Alias for :attr:`on_data`
    onData = on_data
