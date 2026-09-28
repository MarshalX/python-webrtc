#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio
import time

import pytest

import webrtc
from tests.helpers import connect, wait_for_event


@pytest.mark.asyncio
async def test_stats_of_connection_sender_and_receiver(caller, callee):
    stream = webrtc.get_user_media(audio=True)
    (track,) = stream.get_tracks()
    caller.add_track(track, stream)
    remote_track = wait_for_event(callee, 'track')
    await connect(caller, callee)
    remote = (await remote_track).track
    if remote.muted:
        await wait_for_event(remote, 'unmute')

    report = await caller.get_stats()
    assert isinstance(report, webrtc.RTCStatsReport)
    assert report.of_type('peer-connection')
    outbound = report.of_type('outbound-rtp')[0]
    assert outbound['kind'] == outbound.kind == 'audio'
    assert abs(outbound.timestamp - time.time() * 1000) < 60_000

    sender_report = await caller.get_senders()[0].get_stats()
    assert sender_report.of_type('outbound-rtp') and not sender_report.of_type('inbound-rtp')
    assert len(await caller.get_stats(track)) == len(sender_report)

    await asyncio.sleep(0.2)
    receiver_report = await callee.get_receivers()[0].get_stats()
    assert receiver_report.of_type('inbound-rtp')

    with pytest.raises(webrtc.InvalidAccessError):
        await caller.get_stats(webrtc.get_user_media().get_tracks()[0])

    caller.close()
    # a closed connection still has stats
    assert (await caller.get_stats()).of_type('peer-connection')
    track.stop()


@pytest.mark.asyncio
async def test_remote_track_mute_and_stream_events(caller, callee):
    stream = webrtc.get_user_media(audio=True, video=True)
    audio, video = stream.get_audio_tracks()[0], stream.get_video_tracks()[0]
    caller.add_track(audio, stream)
    transceiver = caller.add_transceiver(video, webrtc.RtpTransceiverInit(streams=[stream]))
    events = []
    callee.on('track', lambda event: events.append(event))
    await connect(caller, callee)
    await asyncio.sleep(0.2)

    remote_stream = events[0].streams[0]
    assert len(remote_stream.get_tracks()) == 2
    removed = wait_for_event(remote_stream, 'removetrack')
    remote_video = [e.track for e in events if e.track.kind == webrtc.MediaType.video][0]
    muted = wait_for_event(remote_video, 'mute')

    # the video isn't sent anymore
    transceiver.direction = webrtc.TransceiverDirection.inactive
    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)

    assert (await removed).track == remote_video
    await muted
    assert remote_video.muted
    for track in (audio, video):
        track.stop()


@pytest.mark.asyncio
async def test_dtmf(caller, callee):
    stream = webrtc.get_user_media(audio=True)
    sender = caller.add_track(stream.get_tracks()[0], stream)
    await connect(caller, callee)
    dtmf = sender.dtmf
    assert dtmf is not None and dtmf.can_insert_dtmf

    tones = []
    done = asyncio.get_running_loop().create_future()

    @dtmf.on('tonechange')
    def on_tone(event):
        tones.append(event.tone)
        if event.tone == '':
            done.set_result(None)

    with pytest.raises(webrtc.InvalidCharacterError):
        dtmf.insert_dtmf('12X')
    dtmf.insert_dtmf('1a#', duration=70, inter_tone_gap=50)
    assert dtmf.tone_buffer == '1A#'
    await asyncio.wait_for(done, 5)
    assert tones == ['1', 'A', '#', '']
    stream.get_tracks()[0].stop()


@pytest.mark.asyncio
async def test_synchronization_sources(caller, callee):
    stream = webrtc.get_user_media(audio=False, video=True)
    (track,) = stream.get_tracks()
    caller.add_track(track, stream)
    remote_track = wait_for_event(callee, 'track')
    await connect(caller, callee)
    receiver = (await remote_track).receiver

    # sources are known once media is decoded (audio is only played out by a real audio device)
    deadline = time.monotonic() + 5
    while not receiver.get_synchronization_sources() and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    [source] = receiver.get_synchronization_sources()
    inbound = (await receiver.get_stats()).of_type('inbound-rtp')[0]
    assert isinstance(source, webrtc.RTCRtpSynchronizationSource)
    assert source.source == inbound.ssrc
    assert abs(source.timestamp - time.time() * 1000) < 5_000
    assert 0 <= source.rtp_timestamp < 2**32
    assert source.audio_level is None
    assert receiver.get_contributing_sources() == []
    track.stop()
