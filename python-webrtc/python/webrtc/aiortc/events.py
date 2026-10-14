#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from webrtc.aiortc.mediastreams import MediaStreamTrack
    from webrtc.aiortc.rtcrtpreceiver import RTCRtpReceiver
    from webrtc.aiortc.rtcrtptransceiver import RTCRtpTransceiver


@dataclass
class RTCTrackEvent:
    receiver: RTCRtpReceiver
    track: MediaStreamTrack
    transceiver: RTCRtpTransceiver


__all__ = ['RTCTrackEvent']
