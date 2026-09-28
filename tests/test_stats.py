#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Stats of a connection, its senders and its receivers."""

import time

import pytest

import webrtc
from tests.helpers import connect, wait_for_event, wait_until, wait_until_unmuted


async def send_audio(caller, callee, stream):
    """Connects, sending the audio of the stream, and returns the remote track once media arrives"""
    caller.add_track(stream.get_tracks()[0], stream)
    track_event = wait_for_event(callee, 'track')
    await connect(caller, callee)
    remote = (await track_event).track
    await wait_until_unmuted(remote)
    return remote


@pytest.mark.asyncio
async def test_connection_stats(caller, callee, audio_stream):
    """A report of the connection has its stats, as dictionaries and attributes, with timestamps in milliseconds"""
    await send_audio(caller, callee, audio_stream)

    report = await caller.get_stats()
    assert isinstance(report, webrtc.RTCStatsReport)
    assert report.of_type('peer-connection')
    outbound = report.of_type('outbound-rtp')[0]
    assert outbound['kind'] == outbound.kind == 'audio'
    assert abs(outbound.timestamp - time.time() * 1000) < 60_000


@pytest.mark.asyncio
async def test_sender_stats(caller, callee, audio_stream):
    """A report of a sender has the stats of what it sends, and is the one of its track"""
    await send_audio(caller, callee, audio_stream)

    sender_report = await caller.get_senders()[0].get_stats()
    assert sender_report.of_type('outbound-rtp') and not sender_report.of_type('inbound-rtp')
    assert len(await caller.get_stats(audio_stream.get_tracks()[0])) == len(sender_report)


@pytest.mark.asyncio
async def test_receiver_stats(caller, callee, audio_stream):
    """A report of a receiver has the stats of what it receives"""
    await send_audio(caller, callee, audio_stream)
    receiver = callee.get_receivers()[0]

    async def receives():
        return (await receiver.get_stats()).of_type('inbound-rtp')

    await wait_until(receives, 'inbound-rtp stats')


@pytest.mark.asyncio
async def test_stats_of_a_track_the_connection_does_not_send(pc, audio_stream, audio_stream2):
    """Only the track of a sender of the connection selects stats"""
    pc.add_track(audio_stream.get_tracks()[0])
    with pytest.raises(webrtc.InvalidAccessError):
        await pc.get_stats(audio_stream2.get_tracks()[0])


@pytest.mark.asyncio
async def test_closed_connection_has_stats(caller, callee, audio_stream):
    """A closed connection still has stats"""
    await send_audio(caller, callee, audio_stream)
    caller.close()
    assert (await caller.get_stats()).of_type('peer-connection')
