#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#
#  Ported from web-platform-tests, Copyright © web-platform-tests contributors,
#  under the 3-Clause BSD License in the THIRD_PARTY_LICENSES.md file in the root of the project.
#

from __future__ import annotations

import pytest

import webrtc
from tests.helpers import exchange_offer_answer


@pytest.mark.asyncio
async def test_1(pc: webrtc.RTCPeerConnection) -> None:
    """A transceiver added and stopped before the initial offer should not get an m-section in it."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.sendonly)
    pc.add_transceiver(webrtc.MediaType.audio, init)
    pc.add_transceiver(webrtc.MediaType.video)
    pc.get_transceivers()[0].stop()

    offer = await pc.create_offer()

    assert 'm=audio' not in offer.sdp, 'offer should not contain an audio m-section'
    assert 'm=video' in offer.sdp, 'offer should contain a video m-section'


def test_2(pc: webrtc.RTCPeerConnection) -> None:
    """A transceiver added and stopped should not crash when getting receiver's transport."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.sendonly)
    pc.add_transceiver(webrtc.MediaType.audio, init)
    pc.add_transceiver(webrtc.MediaType.video)

    assert pc.get_transceivers()[1].receiver.transport is None
    pc.get_transceivers()[1].stop()
    assert pc.get_transceivers()[1].receiver.transport is None


@pytest.mark.asyncio
async def test_3(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """During renegotiation, a transceiver added and stopped should not get an m-section in the offer."""
    caller.add_transceiver(webrtc.MediaType.audio)

    await exchange_offer_answer(caller, callee)

    caller.add_transceiver(webrtc.MediaType.video)

    caller.get_transceivers()[0].stop()
    caller.get_transceivers()[1].stop()

    offer = await caller.create_offer()

    assert 'm=audio' in offer.sdp, 'offer should contain an audio m-section'
    assert 'm=audio 0' in offer.sdp, 'The audio m-section should be rejected'

    assert 'm=video' not in offer.sdp, 'offer should not contain a video m-section'


async def _test_inactive_m_section(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, direction: webrtc.RTCRtpTransceiverDirection
) -> None:
    caller.add_transceiver(webrtc.MediaType.audio)

    await exchange_offer_answer(caller, callee)

    caller.get_transceivers()[0].direction = direction
    caller.get_transceivers()[0].stop()

    offer = await caller.create_offer()

    assert 'a=inactive' in offer.sdp, 'The audio m-section should be inactive'


@pytest.mark.asyncio
async def test_4(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """A stopped sendonly transceiver should generate an inactive m-section in the offer."""
    await _test_inactive_m_section(caller, callee, webrtc.RTCRtpTransceiverDirection.sendonly)


@pytest.mark.asyncio
async def test_5(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """A stopped inactive transceiver should generate an inactive m-section in the offer."""
    await _test_inactive_m_section(caller, callee, webrtc.RTCRtpTransceiverDirection.inactive)


@pytest.mark.asyncio
async def test_6(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """If a transceiver is stopped locally, setting a locally generated answer should still work."""
    caller.add_transceiver(webrtc.MediaType.audio)

    await exchange_offer_answer(caller, callee)
    caller.get_transceivers()[0].stop()
    await exchange_offer_answer(caller, callee)

    await caller.set_local_description(await caller.create_offer())


@pytest.mark.asyncio
async def test_7(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """If a transceiver is stopped remotely, setting a locally generated answer should still work."""
    caller.add_transceiver(webrtc.MediaType.audio)

    await exchange_offer_answer(caller, callee)
    callee.get_transceivers()[0].stop()
    await exchange_offer_answer(callee, caller)  # switched args

    await caller.set_local_description(await caller.create_offer())


@pytest.mark.asyncio
async def test_8(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """If a transceiver is stopped, transceivers, senders and receivers should disappear after offer/answer."""
    caller.add_transceiver(webrtc.MediaType.audio)

    await exchange_offer_answer(caller, callee)

    assert len(caller.get_transceivers()) == 1
    assert len(callee.get_transceivers()) == 1

    caller.get_transceivers()[0].stop()

    await exchange_offer_answer(caller, callee)

    assert len(caller.get_transceivers()) == 0
    assert len(callee.get_transceivers()) == 0

    assert len(caller.get_senders()) == 0, 'caller senders'
    assert len(callee.get_senders()) == 0, 'callee senders'

    assert len(caller.get_receivers()) == 0, 'caller receivers'
    assert len(callee.get_receivers()) == 0, 'callee receivers'


@pytest.mark.asyncio
async def test_9(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """If a transceiver is stopped, transceivers should end up in state stopped."""
    caller.add_transceiver(webrtc.MediaType.audio)

    await exchange_offer_answer(caller, callee)

    assert len(caller.get_transceivers()) == 1
    assert len(callee.get_transceivers()) == 1

    caller_transceiver = caller.get_transceivers()[0]
    callee_transceiver = callee.get_transceivers()[0]

    caller_transceiver.stop()

    await exchange_offer_answer(caller, callee)

    assert caller_transceiver.direction == webrtc.RTCRtpTransceiverDirection.stopped
    assert callee_transceiver.direction == webrtc.RTCRtpTransceiverDirection.stopped
