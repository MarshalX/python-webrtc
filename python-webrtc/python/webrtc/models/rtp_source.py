#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The contributing and synchronization sources of the media a receiver received."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import Self

from dataclasses import dataclass
from typing import ClassVar

from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

# RFC 6464 and RFC 6465 levels are -dBov, 127 being silence
_SILENT_LEVEL = 127


@dataclass(frozen=True)
class RTCRtpContributingSource(Dictionary):
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
    audio_level: float | None = None

    @classmethod
    def _from_native(cls, native: tuple[bool, int, float, int, int | None]) -> Self:
        """A source from the native one: whether it's an SSRC, the source, timestamp, RTP timestamp and level."""
        _, source, timestamp, rtp_timestamp, level = native
        if level is not None:
            level = 0.0 if level >= _SILENT_LEVEL else 10 ** (-level / 20)
        return cls(timestamp, source, rtp_timestamp, level)

    #: Alias for :attr:`rtp_timestamp`
    rtpTimestamp: ClassVar[Alias[int]] = alias('rtp_timestamp')
    #: Alias for :attr:`audio_level`
    audioLevel: ClassVar[Alias[float | None]] = alias('audio_level')


@dataclass(frozen=True)
class RTCRtpSynchronizationSource(RTCRtpContributingSource):
    """A synchronization source (SSRC) of the media an :obj:`webrtc.RTCRtpReceiver` received in the last 10 s.

    See :obj:`webrtc.RTCRtpContributingSource` for its members.
    """
