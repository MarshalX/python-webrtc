#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Stats of a connection, its senders and its receivers."""

from __future__ import annotations

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
    """A report of the connection has its stats, as dictionaries and attributes, with timestamps in milliseconds."""
    await send_audio(caller, callee, audio_stream)

    report = await caller.get_stats()
    assert isinstance(report, webrtc.RTCStatsReport)
    assert len(report.of_type('peer-connection')) > 0
    outbound = report.of_type('outbound-rtp')[0]
    assert outbound['kind'] == outbound.kind == 'audio'
    assert abs(outbound.timestamp - time.time() * 1000) < 60_000


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
        received = inbound[0].get('totalSamplesReceived', 0)
        assert isinstance(received, int)
        return received > 0

    await wait_until(decoded, 'decoded remote audio')
