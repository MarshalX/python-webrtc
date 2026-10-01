#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Stats of a connection, its senders and its receivers."""

from __future__ import annotations

import json
import time

import pytest

import webrtc
from tests.helpers import connect, wait_for_event, wait_until, wait_until_unmuted


async def send_audio(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, stream: webrtc.MediaStream
) -> webrtc.MediaStreamTrack:
    """Connects, sending the audio of the stream, and returns the remote track once media arrives."""
    caller.add_track(stream.get_tracks()[0], stream)
    track_event = wait_for_event(callee, 'track')
    await connect(caller, callee)
    event = await track_event
    assert isinstance(event, webrtc.RTCTrackEvent)
    remote = event.track
    await wait_until_unmuted(remote)
    return remote


@pytest.mark.asyncio
async def test_connection_stats(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """A report of the connection has its stats, as the dictionaries of their types, with timestamps in milliseconds."""
    await send_audio(caller, callee, audio_stream)

    report = await caller.get_stats()
    assert isinstance(report, webrtc.RTCStatsReport)
    assert all(isinstance(stats, webrtc.RTCPeerConnectionStats) for stats in report.of_type('peer-connection'))
    outbound = report.of_type(webrtc.RTCStatsType.outbound_rtp)[0]
    assert isinstance(outbound, webrtc.RTCOutboundRtpStreamStats)
    assert outbound.kind == 'audio'
    assert outbound.type is webrtc.RTCStatsType.outbound_rtp
    assert abs(outbound.timestamp - time.time() * 1000) < 60_000
    [transport] = report.of_type('transport')
    assert isinstance(transport, webrtc.RTCTransportStats)
    assert transport.dtls_state is webrtc.RTCDtlsTransportState.connected
    assert transport.dtlsState is transport.dtls_state
    [source] = report.of_type('media-source')
    assert isinstance(source, webrtc.RTCAudioSourceStats)


@pytest.mark.asyncio
async def test_sender_stats(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """A report of a sender has the stats of what it sends, and is the one of its track."""
    await send_audio(caller, callee, audio_stream)

    sender_report = await caller.get_senders()[0].get_stats()
    assert len(sender_report.of_type('outbound-rtp')) > 0
    assert len(sender_report.of_type('inbound-rtp')) == 0
    assert len(await caller.get_stats(audio_stream.get_tracks()[0])) == len(sender_report)


@pytest.mark.asyncio
async def test_receiver_stats(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """A report of a receiver has the stats of what it receives."""
    await send_audio(caller, callee, audio_stream)
    receiver = callee.get_receivers()[0]

    async def receives() -> list[webrtc.RTCStats]:
        return (await receiver.get_stats()).of_type('inbound-rtp')

    await wait_until(receives, 'inbound-rtp stats')
    [inbound] = await receives()
    assert isinstance(inbound, webrtc.RTCInboundRtpStreamStats)
    assert inbound.track_identifier == receiver.track.id


@pytest.mark.asyncio
async def test_stats_of_a_track_the_connection_does_not_send(
    pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream, audio_stream2: webrtc.MediaStream
) -> None:
    """Only the track of a sender of the connection selects stats."""
    pc.add_track(audio_stream.get_tracks()[0])
    with pytest.raises(webrtc.InvalidAccessError):
        await pc.get_stats(audio_stream2.get_tracks()[0])


@pytest.mark.asyncio
async def test_closed_connection_has_stats(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """A closed connection still has stats."""
    await send_audio(caller, callee, audio_stream)
    caller.close()
    assert len((await caller.get_stats()).of_type('peer-connection')) > 0


@pytest.mark.asyncio
async def test_remote_audio_is_played_out(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """The audio device pulls playout, so received audio is decoded like in a browser playing it."""
    await send_audio(caller, callee, audio_stream)
    receiver = callee.get_receivers()[0]

    async def decoded() -> bool:
        inbound = (await receiver.get_stats()).of_type('inbound-rtp')
        if len(inbound) == 0:
            return False
        assert isinstance(inbound[0], webrtc.RTCInboundRtpStreamStats)
        received = inbound[0].total_samples_received
        return received is not None and received > 0

    await wait_until(decoded, 'decoded remote audio')


def report_of(*entries: dict[str, object]) -> webrtc.RTCStatsReport:
    """A report from the JSON of libwebrtc, with timestamps in microseconds."""
    return webrtc.RTCStatsReport._from_native(json.dumps(list(entries)))


CODEC = {
    'type': 'codec',
    'id': 'C',
    'timestamp': 1_000_000,
    'payloadType': 111,
    'transportId': 'T',
    'mimeType': 'audio/opus',
}


@pytest.mark.parametrize(
    ('entry', 'dictionary'),
    [
        (CODEC, webrtc.RTCCodecStats),
        ({'type': 'inbound-rtp', 'ssrc': 1, 'kind': 'audio', 'trackIdentifier': 't'}, webrtc.RTCInboundRtpStreamStats),
        ({'type': 'outbound-rtp', 'ssrc': 1, 'kind': 'video'}, webrtc.RTCOutboundRtpStreamStats),
        ({'type': 'remote-inbound-rtp', 'ssrc': 1, 'kind': 'audio'}, webrtc.RTCRemoteInboundRtpStreamStats),
        ({'type': 'remote-outbound-rtp', 'ssrc': 1, 'kind': 'audio'}, webrtc.RTCRemoteOutboundRtpStreamStats),
        ({'type': 'media-source', 'trackIdentifier': 't', 'kind': 'audio'}, webrtc.RTCAudioSourceStats),
        ({'type': 'media-source', 'trackIdentifier': 't', 'kind': 'video'}, webrtc.RTCVideoSourceStats),
        ({'type': 'media-playout', 'kind': 'audio'}, webrtc.RTCAudioPlayoutStats),
        ({'type': 'peer-connection'}, webrtc.RTCPeerConnectionStats),
        ({'type': 'data-channel', 'state': 'open'}, webrtc.RTCDataChannelStats),
        ({'type': 'transport', 'dtlsState': 'new'}, webrtc.RTCTransportStats),
        (
            {
                'type': 'candidate-pair',
                'transportId': 'T',
                'localCandidateId': 'L',
                'remoteCandidateId': 'R',
                'state': 'frozen',
            },
            webrtc.RTCIceCandidatePairStats,
        ),
        ({'type': 'local-candidate', 'transportId': 'T', 'candidateType': 'host'}, webrtc.RTCIceCandidateStats),
        ({'type': 'remote-candidate', 'transportId': 'T', 'candidateType': 'prflx'}, webrtc.RTCIceCandidateStats),
        (
            {'type': 'certificate', 'fingerprint': 'AB', 'fingerprintAlgorithm': 'sha-256', 'base64Certificate': 'MII'},
            webrtc.RTCCertificateStats,
        ),
    ],
)
def test_stats_are_the_dictionary_of_their_type(entry: dict[str, object], dictionary: type[webrtc.RTCStats]) -> None:
    """Each type of stats is the dictionary the specification defines for it."""
    report = report_of({**entry, 'id': 'S', 'timestamp': 1_500_000})
    stats = report['S']
    assert type(stats) is dictionary
    assert stats.id == 'S'
    assert stats.timestamp == 1500
    assert report.of_type(str(entry['type'])) == [stats]


def test_stats_members() -> None:
    """Members have snake_case names and camelCase aliases, enums are converted, and unknown members are dropped."""
    report = report_of(
        {
            'type': 'outbound-rtp',
            'id': 'O',
            'timestamp': 0,
            'ssrc': 1,
            'kind': 'video',
            'bytesSent': 10,
            'qualityLimitationReason': 'cpu',
            'qualityLimitationDurations': {'cpu': 1.5, 'none': 0},
            'googSomething': 'x',
        },
        {
            'type': 'local-candidate',
            'id': 'L',
            'timestamp': 0,
            'transportId': 'T',
            'candidateType': 'host',
            'address': '',
        },
    )
    outbound = report['O']
    assert isinstance(outbound, webrtc.RTCOutboundRtpStreamStats)
    assert outbound.bytes_sent == outbound.bytesSent == 10
    assert outbound.packets_sent is None
    assert outbound.quality_limitation_reason is webrtc.RTCQualityLimitationReason.cpu
    assert outbound.quality_limitation_durations == {'cpu': 1.5, 'none': 0}
    assert not hasattr(outbound, 'goog_something')
    assert outbound.to_json() == {
        'timestamp': 0,
        'type': 'outbound-rtp',
        'id': 'O',
        'ssrc': 1,
        'kind': 'video',
        'bytesSent': 10,
        'qualityLimitationReason': 'cpu',
        'qualityLimitationDurations': {'cpu': 1.5, 'none': 0},
    }
    candidate = report['L']
    assert isinstance(candidate, webrtc.RTCIceCandidateStats)
    # libwebrtc leaves addresses it doesn't expose empty
    assert candidate.address is None
    assert candidate.candidate_type is webrtc.RTCIceCandidateType.host


def test_unknown_values_are_kept() -> None:
    """An enum value or a type of stats the specification lacks stays a str, and the type has the common members."""
    report = report_of(
        {'type': 'data-channel', 'id': 'D', 'timestamp': 0, 'state': 'opening'},
        {'type': 'csrc', 'id': 'X', 'timestamp': 0, 'contributorSsrc': 1},
    )
    channel = report['D']
    assert isinstance(channel, webrtc.RTCDataChannelStats)
    assert channel.state == 'opening'
    assert not isinstance(channel.state, webrtc.RTCDataChannelState)
    unknown = report['X']
    assert type(unknown) is webrtc.RTCStats
    assert unknown.type == 'csrc'
    assert unknown.to_json() == {'timestamp': 0, 'type': 'csrc', 'id': 'X'}


def test_stats_lacking_a_required_member() -> None:
    """Stats libwebrtc reports without a required member of their dictionary have the common members only."""
    report = report_of({'type': 'codec', 'id': 'C', 'timestamp': 0, 'payloadType': 111})
    assert type(report['C']) is webrtc.RTCStats


def test_stats_dictionaries() -> None:
    """Stats dictionaries take keyword members, require the required ones, and convert from and to JSON."""
    codec = webrtc.RTCCodecStats.from_json({**CODEC, 'clockRate': 48000})
    assert codec == webrtc.RTCCodecStats(
        id='C',
        type='codec',
        timestamp=1_000_000,
        payload_type=111,
        transport_id='T',
        mime_type='audio/opus',
        clock_rate=48000,
    )
    assert codec.type is webrtc.RTCStatsType.codec
    assert codec.channels is None
    assert webrtc.RTCCodecStats.from_json(codec.to_json()) == codec
    with pytest.raises(TypeError, match='missing the required member'):
        webrtc.RTCCodecStats(id='C', type='codec', timestamp=0, payload_type=111, transport_id='T')
    with pytest.raises(TypeError, match='has no member'):
        webrtc.RTCStats(id='C', type='codec', timestamp=0, bytes_sent=1)
