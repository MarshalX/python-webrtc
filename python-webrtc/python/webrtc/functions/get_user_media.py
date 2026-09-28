#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING

import wrtc
from webrtc import MediaStream

if TYPE_CHECKING:
    import webrtc


def get_user_media(
    audio: bool = True,
    video: bool = False,
    *,
    width: int = 640,
    height: int = 480,
    frame_rate: float = 30.0,
) -> 'webrtc.MediaStream':
    """Returns a stream of local media: an audio track of the default audio device, and a video track
    of a synthetic camera, which draws a moving pattern (use :obj:`webrtc.RTCVideoSource` for real video).

    Args:
        audio (:obj:`bool`, optional): Whether the stream has an audio track.
        video (:obj:`bool`, optional): Whether the stream has a video track.
        width (:obj:`int`, optional): The width of the video.
        height (:obj:`int`, optional): The height of the video.
        frame_rate (:obj:`float`, optional): The frames per second of the video.

    Returns:
        :obj:`webrtc.MediaStream`: The stream.

    Raises:
        :obj:`TypeError`: If neither audio nor video is requested.
        :obj:`ValueError`: If the size or the frame rate of the video isn't positive.
    """
    if not audio and not video:
        raise TypeError('audio or video must be requested')
    if video and (width <= 0 or height <= 0 or frame_rate <= 0):
        raise ValueError('the size and the frame rate of the video must be positive')
    return MediaStream._wrap(wrtc.getUserMedia(bool(audio), bool(video), width, height, float(frame_rate)))


#: Alias for :func:`get_user_media`
getUserMedia = get_user_media
