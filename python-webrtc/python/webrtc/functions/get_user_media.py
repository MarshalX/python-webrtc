#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import TYPE_CHECKING, Dict, Optional, Union

from webrtc import MediaStream, MediaTrackConstraints, MediaTrackSettings, OverconstrainedError, wrtc
from webrtc.interfaces.media_stream_track import _CAMERA_CAPABILITIES, _check_numbers, _selected, _unsatisfied

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
        :obj:`TypeError`: If neither audio nor video is requested, or a value isn't a finite number (negative for
            the size).
        :obj:`webrtc.OverconstrainedError`: If a required value (``exact``, ``min``, ``max``) is beyond what the
            camera can do: 1 to 4096 pixels wide and high, 1 to 120 frames per second. Other values are brought
            within that.
    """
    if not audio and not video:
        raise TypeError('audio or video must be requested')
    constraints = MediaTrackConstraints(width=width, height=height, frame_rate=frame_rate)
    _check_numbers(constraints)
    if video:
        failed = _unsatisfied(constraints, _CAMERA_CAPABILITIES, MediaTrackSettings())
        if failed is not None:
            raise OverconstrainedError(failed, f"The constraint {failed} can't be satisfied")
    # the camera's defaults, within the constraints and the camera's capabilities
    capabilities = _CAMERA_CAPABILITIES
    width = _selected(width, 640, capabilities.width)
    height = _selected(height, 480, capabilities.height)
    frame_rate = _selected(frame_rate, 30.0, capabilities.frame_rate)
    stream = MediaStream._wrap(wrtc.getUserMedia(bool(audio), bool(video), width, height, float(frame_rate)))
    for track in stream.get_video_tracks():
        track._native_obj._constraints = constraints
    return stream


#: Alias for :func:`get_user_media`
getUserMedia = get_user_media
