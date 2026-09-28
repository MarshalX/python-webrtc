#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from dataclasses import dataclass
from typing import Optional, Tuple

from webrtc.utils.names import alias


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

    @classmethod
    def _from_native(cls, native: Tuple[bool, int, float, int, Optional[int]]) -> 'RTCRtpContributingSource':
        """A source from the native one: whether it's an SSRC, the source, timestamp, RTP timestamp and level."""
        _, source, timestamp, rtp_timestamp, level = native
        # RFC 6464 and RFC 6465 levels are -dBov, 127 being silence
        if level is not None:
            level = 0.0 if level >= 127 else 10 ** (-level / 20)
        return cls(timestamp, source, rtp_timestamp, level)

    #: Alias for :attr:`rtp_timestamp`
    rtpTimestamp = alias('rtp_timestamp')
    #: Alias for :attr:`audio_level`
    audioLevel = alias('audio_level')


@dataclass(frozen=True)
class RTCRtpSynchronizationSource(RTCRtpContributingSource):
    """A synchronization source (SSRC) of the media an :obj:`webrtc.RTCRtpReceiver` received in the last
    10 seconds. See :obj:`webrtc.RTCRtpContributingSource` for its members."""
