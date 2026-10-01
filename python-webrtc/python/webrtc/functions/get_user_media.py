#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""getUserMedia of Media Capture and Streams, with a synthetic microphone and camera."""

from __future__ import annotations

from typing import TYPE_CHECKING

from webrtc import MediaStream, MediaTrackConstraints, MediaTrackSettings, OverconstrainedError, wrtc
from webrtc.interfaces.media_stream_track import _CAMERA_CAPABILITIES, _check_numbers, _selected, _unsatisfied

if TYPE_CHECKING:
    import webrtc
    from webrtc.models.media_track_constraints import ConstrainDouble, ConstrainULong


def get_user_media(
    *,
    audio: bool = True,
    video: bool = False,
    width: ConstrainULong | None = None,
    height: ConstrainULong | None = None,
    frame_rate: ConstrainDouble | None = None,
) -> webrtc.MediaStream:
    """Returns a stream of local media, as requested: a synthetic microphone and/or camera.

    The audio track is quiet noise, the video track draws a moving pattern (use :obj:`webrtc.VideoTrackGenerator`
    and :obj:`webrtc.MediaStreamTrackGenerator` for real media). The constraints given are the ones of the tracks
    (see :meth:`webrtc.MediaStreamTrack.get_constraints`).

    Args:
        audio (:obj:`bool`, optional): Whether the stream has an audio track.
        video (:obj:`bool`, optional): Whether the stream has a video track.
        width (:obj:`int` or :obj:`webrtc.ConstrainULongRange`, optional): The width of the video, or a constraint
            on it, 640 by default.
        height (:obj:`int` or :obj:`webrtc.ConstrainULongRange`, optional): The height of the video, or a constraint
            on it, 480 by default.
        frame_rate (:obj:`float` or :obj:`webrtc.ConstrainDoubleRange`, optional): The frames per second of the
            video, or a constraint on it, 30 by default.

    Returns:
        :obj:`webrtc.MediaStream`: The stream.

    Raises:
        TypeError: If neither audio nor video is requested, or a value isn't a finite number (negative for
            the size).
        webrtc.OverconstrainedError: If a required value (``exact``, ``min``, ``max``) is beyond what the
            camera can do: 1 to 4096 pixels wide and high, 1 to 120 frames per second. Other values are brought
            within that.
    """
    if not audio and not video:
        msg = 'audio or video must be requested'
        raise TypeError(msg)
    constraints = MediaTrackConstraints(width=width, height=height, frame_rate=frame_rate)
    _check_numbers(constraints)
    if video:
        failed = _unsatisfied(constraints, _CAMERA_CAPABILITIES, MediaTrackSettings())
        if failed is not None:
            raise OverconstrainedError(failed, f"The constraint {failed} can't be satisfied")
    # the camera's defaults, within the constraints and the camera's capabilities
    capabilities = _CAMERA_CAPABILITIES
    selected_width = _selected(width, 640, capabilities.width)
    selected_height = _selected(height, 480, capabilities.height)
    selected_frame_rate = _selected(frame_rate, 30.0, capabilities.frame_rate)
    stream = MediaStream._wrap(
        wrtc.getUserMedia(bool(audio), bool(video), selected_width, selected_height, float(selected_frame_rate))
    )
    for track in stream.get_video_tracks():
        track._native_obj._constraints = constraints
    return stream


#: Alias for :func:`get_user_media`
getUserMedia = get_user_media
