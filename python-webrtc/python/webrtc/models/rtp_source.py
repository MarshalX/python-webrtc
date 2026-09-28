#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RTCRtpContributingSource:
    """A source of the media an :obj:`webrtc.RTCRtpReceiver` received in the last 10 seconds.

    Args:
        timestamp (:obj:`float`): When the last packet from the source was received, in milliseconds since
            the Unix epoch, as the timestamps of :obj:`webrtc.RTCStats`.
        source (:obj:`int`): The CSRC or SSRC of the source.
        rtp_timestamp (:obj:`int`): The RTP timestamp of the last packet from the source.
        audio_level (:obj:`float`, optional): The audio level of the last packet, from 0 (silence) to 1
            (0 dBov), if the remote peer sent it.
    """

    timestamp: float
    source: int
    rtp_timestamp: int
    audio_level: Optional[float] = None

    @staticmethod
    def _audio_level(level: Optional[int]) -> Optional[float]:
        # RFC 6464 and RFC 6465 levels are -dBov, 127 being silence
        if level is None:
            return None
        return 0.0 if level >= 127 else 10 ** (-level / 20)


@dataclass(frozen=True)
class RTCRtpSynchronizationSource(RTCRtpContributingSource):
    """A synchronization source (SSRC) of the media an :obj:`webrtc.RTCRtpReceiver` received in the last
    10 seconds. See :obj:`webrtc.RTCRtpContributingSource` for its members."""
