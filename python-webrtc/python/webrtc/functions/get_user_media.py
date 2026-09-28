#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Dict, Union

from webrtc import MediaStream, wrtc

if TYPE_CHECKING:
    import webrtc


#: A value, or a constraint on it: a :obj:`dict` with any of ``exact``, ``ideal``, ``min`` and ``max``
Constrain = Union[float, Dict[str, float]]


def _constrained(value: Constrain, default: float) -> float:
    """The value a constraint selects: the exact or ideal one, otherwise the default within the range."""
    if not isinstance(value, dict):
        return value
    if value.get('exact') is not None:
        return value['exact']
    if value.get('ideal') is not None:
        return value['ideal']
    if value.get('max') is not None:
        default = min(default, value['max'])
    if value.get('min') is not None:
        default = max(default, value['min'])
    return default


def get_user_media(
    audio: bool = True,
    video: bool = False,
    *,
    width: Constrain = 640,
    height: Constrain = 480,
    frame_rate: Constrain = 30.0,
) -> 'webrtc.MediaStream':
    """Returns a stream of local media, as requested: an audio track of the default audio device, and/or a video
    track of a synthetic camera, which draws a moving pattern (use :obj:`webrtc.RTCVideoSource` for real video).

    Args:
        audio (:obj:`bool`, optional): Whether the stream has an audio track.
        video (:obj:`bool`, optional): Whether the stream has a video track.
        width (:obj:`int` | :obj:`dict`, optional): The width of the video, or a constraint on it (see
            :obj:`Constrain`).
        height (:obj:`int` | :obj:`dict`, optional): The height of the video, or a constraint on it.
        frame_rate (:obj:`float` | :obj:`dict`, optional): The frames per second of the video, or a constraint on
            it.

    Returns:
        :obj:`webrtc.MediaStream`: The stream.

    Raises:
        :obj:`TypeError`: If neither audio nor video is requested.
        :obj:`ValueError`: If the size or the frame rate of the video isn't positive.
    """
    if not audio and not video:
        raise TypeError('audio or video must be requested')
    # the defaults of a camera, within the range of a constraint that has neither an exact nor an ideal value
    width, height, frame_rate = _constrained(width, 640), _constrained(height, 480), _constrained(frame_rate, 30.0)
    if video and (width <= 0 or height <= 0 or frame_rate <= 0):
        raise ValueError('the size and the frame rate of the video must be positive')
    return MediaStream._wrap(wrtc.getUserMedia(bool(audio), bool(video), width, height, float(frame_rate)))


#: Alias for :func:`get_user_media`
getUserMedia = get_user_media
