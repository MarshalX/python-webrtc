#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The stats of the WebRTC Statistics specification."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Union

from webrtc.utils.names import camel_case

if TYPE_CHECKING:
    import webrtc

_CANDIDATE_TYPES = frozenset({'local-candidate', 'remote-candidate'})
# a value of the JSON libwebrtc serializes the stats to
StatsValue = Union[str, int, float, bool, None, list['StatsValue'], dict[str, 'StatsValue']]


class RTCStats(dict[str, StatsValue]):
    """Stats of one object, like an outbound RTP stream.

    A :obj:`dict` of the members of the stats dictionary of the WebRTC Statistics specification, by their names
    there (like ``'bytesSent'``).

    Members can also be read as attributes with snake_case names::

        stats['bytesSent'] == stats.bytes_sent

    ``id``, ``type`` and ``timestamp`` (milliseconds since the epoch) are always present.
    """

    def __getattr__(self, name: str) -> StatsValue:
        key = camel_case(name)
        try:
            return self[key]
        except KeyError:
            msg = f'{type(self).__name__} of type {self.get("type")!r} has no {name!r}'
            raise AttributeError(msg) from None

    @property
    def id(self) -> str:
        """:obj:`str`: Identifies the stats in its report."""
        return self['id']

    @property
    def type(self) -> str:
        """:obj:`str`: The type of the stats, like ``'outbound-rtp'``."""
        return self['type']

    @property
    def timestamp(self) -> float:
        """:obj:`float`: When the stats were collected, in milliseconds since the epoch."""
        return self['timestamp']


class RTCStatsReport(Mapping[str, RTCStats]):
    """The stats of a connection, or of a sender or a receiver.

    A read-only mapping of their ids to :obj:`webrtc.RTCStats`.
    """

    def __init__(self, stats: Mapping[str, RTCStats]) -> None:
        self._stats = dict(stats)

    @classmethod
    def _from_native(cls, report: str, receivers: Iterable[webrtc.RTCRtpReceiver] = ()) -> RTCStatsReport:
        """The report from the JSON libwebrtc serializes it to, with the receivers whose tracks it refers to."""
        # remote tracks have their own ids, rather than the libwebrtc ones in the stats
        track_ids = {receiver.track._native_obj._nativeId: receiver.track.id for receiver in receivers}
        stats = [RTCStats(entry) for entry in json.loads(report or '[]')]
        for entry in stats:
            # libwebrtc serializes microseconds
            entry['timestamp'] /= 1000
            if entry.get('type') == 'inbound-rtp' and entry.get('trackIdentifier') in track_ids:
                entry['trackIdentifier'] = track_ids[entry['trackIdentifier']]
            # libwebrtc leaves the addresses of candidates it doesn't expose (like peer-reflexive ones) empty
            if (
                entry.get('type') in {'local-candidate', 'remote-candidate'}
                and 'address' in entry
                and not entry['address']
            ):
                entry['address'] = None
        return cls({entry['id']: entry for entry in stats})

    def __getitem__(self, stats_id: str) -> RTCStats:
        return self._stats[stats_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._stats)

    def __len__(self) -> int:
        return len(self._stats)

    def of_type(self, stats_type: str) -> list[RTCStats]:
        """Returns the stats of a type.

        Args:
            stats_type (:obj:`str`): The type, like ``'inbound-rtp'``.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCStats`: The stats of the type.
        """
        return [stats for stats in self._stats.values() if stats['type'] == stats_type]

    def __repr__(self) -> str:
        return f'RTCStatsReport({len(self)} stats)'

    #: Alias for :attr:`of_type`
    ofType = of_type
