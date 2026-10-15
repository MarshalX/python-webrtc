#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""aiortc's Opus, bitrate, codec and orientation behavior over loopback."""

from __future__ import annotations

import re
from typing import cast

import pytest

import webrtc
from tests.aiortc.test_media import (
    CONFIGURATION,
    close,
    local_description,
    negotiate,
    next_track,
    received_tracks,
    recv_video,
)
from tests.helpers import wait_until
from webrtc.aiortc import (
    AudioStreamTrack,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
    VideoStreamTrack,
)
from webrtc.aiortc.codecs import vpx

ORIENTATION = 'urn:3gpp:video-orientation'
OPUS_FMTP = re.compile(r'a=rtpmap:(\d+) opus/.*?a=fmtp:\1 ([^\r\n]*)', re.DOTALL)


async def outbound(pc: RTCPeerConnection, kind: str) -> webrtc.RTCOutboundRtpStreamStats:
    stats = (await pc._native.get_stats()).values()
    return next(s for s in stats if isinstance(s, webrtc.RTCOutboundRtpStreamStats) and s.kind == kind)


async def target_bitrate(pc: RTCPeerConnection) -> float | None:
    return (await outbound(pc, 'video')).target_bitrate


async def sent_codec(pc: RTCPeerConnection, kind: str) -> str:
    report = await pc._native.get_stats()
    codec_id = next(
        s.codec_id for s in report.values() if isinstance(s, webrtc.RTCOutboundRtpStreamStats) and s.kind == kind
    )
    assert codec_id is not None
    return cast('webrtc.RTCCodecStats', report[codec_id]).mime_type


def opus_fmtp(sdp: str) -> str:
    found = OPUS_FMTP.search(sdp)
    assert found is not None
    return found.group(2)


@pytest.mark.asyncio
async def test_opus_negotiates_as_in_the_core() -> None:
    """Offers and answers carry the core's Opus parameters, and the applied answer gets none added."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    core = webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[]))
    try:
        caller.addTrack(AudioStreamTrack())
        core.add_transceiver('audio')
        offer = await caller.createOffer()
        assert opus_fmtp(offer.sdp) == opus_fmtp((await core.create_offer()).sdp)

        await caller.setLocalDescription(offer)
        offer = local_description(caller)
        await callee.setRemoteDescription(offer)
        answer = await callee.createAnswer()
        core_offer = webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.offer, offer.sdp)
        await core.set_remote_description(core_offer)
        assert opus_fmtp(answer.sdp) == opus_fmtp((await core.create_answer()).sdp)

        await callee.setLocalDescription(answer)
        await caller.setRemoteDescription(local_description(callee))
        applied = caller._native.remote_description
        assert applied is not None
        assert opus_fmtp(applied.sdp) == opus_fmtp(answer.sdp)
    finally:
        core.close()
        await close(caller, callee)


@pytest.mark.asyncio
async def test_failed_remote_description_keeps_the_added_parameters_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """A remote description that fails leaves the current one reading as the peer sent it."""
    monkeypatch.setattr(vpx, 'MAX_BITRATE', 200_000)
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    try:
        caller.addTrack(VideoStreamTrack())
        await negotiate(caller, callee)
        # the rejected description adds nothing, so it must not replace what the applied one added
        monkeypatch.undo()
        rejected = local_description(callee).sdp.replace('a=fingerprint:', 'a=x-fingerprint:')
        with pytest.raises(webrtc.InvalidAccessError):
            await caller.setRemoteDescription(RTCSessionDescription(rejected, 'offer'))

        remote, applied = caller.remoteDescription, caller._native.remote_description
        assert remote is not None
        assert applied is not None
        assert 'x-google-max-bitrate' in applied.sdp
        assert 'x-google-max-bitrate' not in remote.sdp
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_changed_bitrate_constants_cap_video(monkeypatch: pytest.MonkeyPatch) -> None:
    """A changed codecs.vpx bitrate shapes the sent video, and unchanged ones leave libwebrtc's."""
    monkeypatch.setattr(vpx, 'MAX_BITRATE', 200_000)
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        caller.addTrack(VideoStreamTrack())
        await negotiate(caller, callee)
        _ = await recv_video(await next_track(tracks))

        remote, applied = caller.remoteDescription, caller._native.remote_description
        assert remote is not None
        assert applied is not None
        assert 'x-google-max-bitrate=200' in applied.sdp
        assert 'x-google-start-bitrate' not in applied.sdp
        assert 'x-google' not in remote.sdp
        await wait_until(lambda: target_bitrate(caller), 'the encoder')
        target = await target_bitrate(caller)
        assert target is not None
        assert 0 < target <= 200_000
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_answerer_sends_its_preferred_codec() -> None:
    """An answerer with codec preferences sends the first codec of its answer."""
    h264 = [c for c in RTCRtpSender.getCapabilities('video').codecs if c.mimeType == 'video/H264']
    if h264 == []:
        pytest.skip('no H.264 encoder')
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(caller)
    try:
        caller.addTransceiver('video', direction='recvonly')
        await caller.setLocalDescription(await caller.createOffer())
        await callee.setRemoteDescription(local_description(caller))
        sender = callee.addTrack(VideoStreamTrack())
        next(t for t in callee.getTransceivers() if t.sender == sender).setCodecPreferences(h264)
        await callee.setLocalDescription(await callee.createAnswer())
        await caller.setRemoteDescription(local_description(callee))
        _ = await recv_video(await next_track(tracks))

        assert await sent_codec(callee, 'video') == 'video/H264'
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_no_orientation_extension() -> None:
    """Offers and answers leave out the orientation extension, so senders rotate frames themselves."""
    core = webrtc.RTCPeerConnection(webrtc.RTCConfiguration())
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    try:
        core.add_transceiver('video')
        caller.addTransceiver('video')
        offer = await core.create_offer()
        await callee.setRemoteDescription(RTCSessionDescription(offer.sdp, 'offer'))
        answer = await callee.createAnswer()

        assert ORIENTATION in offer.sdp
        assert ORIENTATION not in answer.sdp
        assert ORIENTATION not in (await caller.createOffer()).sdp
    finally:
        core.close()
        await close(caller, callee)


@pytest.mark.asyncio
async def test_send_keyframe() -> None:
    """_send_keyframe() makes the encoder send a key frame."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    tracks = received_tracks(callee)
    try:
        sender = caller.addTrack(VideoStreamTrack())
        await negotiate(caller, callee)
        remote = await next_track(tracks)
        _ = await recv_video(remote)
        before = (await outbound(caller, 'video')).key_frames_encoded

        sender._send_keyframe()
        for _ in range(30):
            _ = await recv_video(remote)

        after = (await outbound(caller, 'video')).key_frames_encoded
        assert before is not None
        assert after is not None
        assert after > before
    finally:
        await close(caller, callee)
