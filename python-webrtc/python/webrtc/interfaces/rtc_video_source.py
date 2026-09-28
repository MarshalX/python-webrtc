#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Optional

from webrtc import MediaStreamTrack, RTCVideoFrame, WebRTCObject, wrtc

if TYPE_CHECKING:
    import webrtc


class RTCVideoSource(WebRTCObject):
    """A source of video the application produces: every frame pushed with :meth:`on_frame` is sent on the tracks
    of the source.

    Args:
        is_screencast (:obj:`bool`, optional): Whether the video is a screen capture, which encoders optimize
            for sharpness rather than motion.
        needs_denoising (:obj:`bool`, optional): Whether encoders should denoise the video, their default if omitted.
    """

    _class = wrtc.RTCVideoSource

    def __init__(self, is_screencast: bool = False, needs_denoising: Optional[bool] = None):
        super().__init__(self._class(is_screencast, needs_denoising))

    @property
    def is_screencast(self) -> bool:
        """:obj:`bool`: Whether the video is a screen capture."""
        return self._native_obj.isScreencast

    @property
    def needs_denoising(self) -> Optional[bool]:
        """:obj:`bool`, optional: Whether encoders should denoise the video."""
        return self._native_obj.needsDenoising

    def create_track(self) -> 'webrtc.MediaStreamTrack':
        """Creates a video track of the source.

        Returns:
            :obj:`webrtc.MediaStreamTrack`: The track.
        """
        return MediaStreamTrack._wrap(self._native_obj.createTrack())

    def on_frame(self, frame: RTCVideoFrame) -> None:
        """Pushes a frame to the tracks of the source.

        Args:
            frame (:obj:`webrtc.RTCVideoFrame`): The frame.

        Raises:
            :obj:`webrtc.InvalidAccessError`: If the data doesn't have the size of an I420 frame of the given size.
            :obj:`webrtc.InvalidRangeError`: If the size isn't positive or the rotation isn't a multiple of 90.
        """
        self._native_obj.onFrame(frame.width, frame.height, bytes(frame.data), frame.rotation, frame.timestamp_us)

    #: Alias for :attr:`is_screencast`
    isScreencast = is_screencast
    #: Alias for :attr:`needs_denoising`
    needsDenoising = needs_denoising
    #: Alias for :attr:`create_track`
    createTrack = create_track
    #: Alias for :attr:`on_frame`
    onFrame = on_frame
