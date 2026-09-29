#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Dict, Optional, Union

from webrtc import MediaStream, MediaTrackConstraints, wrtc
from webrtc.interfaces.media_stream_track import _selected

if TYPE_CHECKING:
    import webrtc


#: A value, or a constraint on it: a :obj:`dict` with any of ``exact``, ``ideal``, ``min`` and ``max``
Constrain = Union[float, Dict[str, float]]


def get_user_media(
    audio: bool = True,
    video: bool = False,
    *,
    width: Optional[Constrain] = None,
    height: Optional[Constrain] = None,
    frame_rate: Optional[Constrain] = None,
) -> 'webrtc.MediaStream':
    """Returns a stream of local media, as requested: an audio track of a synthetic microphone (quiet noise), and/or
    a video track of a synthetic camera, which draws a moving pattern (use :obj:`webrtc.VideoTrackGenerator` and
    :obj:`webrtc.MediaStreamTrackGenerator` for real media). The constraints given are the ones of the tracks (see
    :meth:`webrtc.MediaStreamTrack.get_constraints`).

    Args:
        audio (:obj:`bool`, optional): Whether the stream has an audio track.
        video (:obj:`bool`, optional): Whether the stream has a video track.
        width (:obj:`int` | :obj:`dict`, optional): The width of the video, or a constraint on it (see
            :obj:`Constrain`), 640 by default.
        height (:obj:`int` | :obj:`dict`, optional): The height of the video, or a constraint on it, 480 by default.
        frame_rate (:obj:`float` | :obj:`dict`, optional): The frames per second of the video, or a constraint on
            it, 30 by default.

    Returns:
        :obj:`webrtc.MediaStream`: The stream.

    Raises:
        :obj:`TypeError`: If neither audio nor video is requested.
        :obj:`ValueError`: If the size or the frame rate of the video isn't positive.
    """
    if not audio and not video:
        raise TypeError('audio or video must be requested')
    constraints = MediaTrackConstraints(width=width, height=height, frame_rate=frame_rate)
    # the defaults of a camera, within the range of a constraint that has neither an exact nor an ideal value
    width, height, frame_rate = _selected(width, 640), _selected(height, 480), _selected(frame_rate, 30.0)
    if video and (width <= 0 or height <= 0 or frame_rate <= 0):
        raise ValueError('the size and the frame rate of the video must be positive')
    stream = MediaStream._wrap(wrtc.getUserMedia(bool(audio), bool(video), width, height, float(frame_rate)))
    for track in stream.get_video_tracks():
        track._native_obj._constraints = constraints
    return stream


#: Alias for :func:`get_user_media`
getUserMedia = get_user_media
