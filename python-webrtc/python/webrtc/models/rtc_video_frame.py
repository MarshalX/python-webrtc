#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from dataclasses import dataclass
from typing import Optional

from webrtc.utils.names import alias


@dataclass
class RTCVideoFrame:
    """A video frame in the I420 format, pushed with :meth:`webrtc.RTCVideoSource.on_frame`.

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

    #: Alias for :attr:`timestamp_us`
    timestampUs = alias('timestamp_us')
