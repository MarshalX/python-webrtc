#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from webrtc import MediaStreamTrack, WebRTCObject, wrtc

if TYPE_CHECKING:
    import webrtc


@dataclass
class RTCVideoFrame:
    """A video frame in the I420 format.

    Args:
        width (:obj:`int`): The width in pixels.
        height (:obj:`int`): The height in pixels.
        data (:obj:`bytes`): The Y plane (``width * height`` bytes), then the U and V planes
            (``ceil(width / 2) * ceil(height / 2)`` bytes each), without padding.
        rotation (:obj:`int`, optional): How the frame is to be rotated clockwise to be shown: 0, 90, 180 or 270.
        timestamp_us (:obj:`int`, optional): When the frame was captured, in microseconds of a monotonic clock.
            The time it's pushed at by default.
    """

    width: int
    height: int
    data: bytes
    rotation: int = 0
    timestamp_us: Optional[int] = None


class RTCVideoSource(WebRTCObject):
    """A source of video the application produces: every frame pushed with :meth:`on_frame` is sent on the tracks
    of the source.

    Args:
        is_screencast (:obj:`bool`, optional): Whether the video is a screen capture, which encoders optimize
            for sharpness rather than motion.
        needs_denoising (:obj:`bool`, optional): Whether encoders should denoise the video, their default if omitted.
    """

    _class = wrtc.RTCVideoSource

    def __init__(self, is_screencast: bool = False, needs_denoising: Optional[bool] = None, *, _native_obj=None):
        super().__init__(_native_obj or self._class(is_screencast, needs_denoising))

    @classmethod
    def _wrap(cls, item) -> 'RTCVideoSource':
        return cls(_native_obj=item)

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

    #: Alias for :attr:`create_track`
    createTrack = create_track
    #: Alias for :attr:`on_frame`
    onFrame = on_frame
