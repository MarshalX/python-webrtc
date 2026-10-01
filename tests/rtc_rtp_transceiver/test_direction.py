#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import pytest

import webrtc
from tests.helpers import generate_answer


def test_1(pc: webrtc.RTCPeerConnection) -> None:
    """Setting direction should change transceiver.direction."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)

    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendrecv
    assert transceiver.current_direction is None

    transceiver.direction = webrtc.RTCRtpTransceiverDirection.recvonly
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.recvonly
    assert transceiver.current_direction is None, 'Expect transceiver.currentDirection to not change'


def test_2(pc: webrtc.RTCPeerConnection) -> None:
    """Setting direction with same direction should have no effect."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.sendonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendonly
    transceiver.direction = webrtc.RTCRtpTransceiverDirection.sendonly
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendonly


@pytest.mark.asyncio
async def test_3(pc: webrtc.RTCPeerConnection) -> None:
    """Setting direction should change transceiver.direction independent of transceiver.currentDirection."""
    init = webrtc.RTCRtpTransceiverInit(direction=webrtc.RTCRtpTransceiverDirection.recvonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.recvonly
    assert transceiver.current_direction is None

    offer = await pc.create_offer()
    await pc.set_local_description(offer)
    await pc.set_remote_description(await generate_answer(offer))

    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.inactive

    transceiver.direction = webrtc.RTCRtpTransceiverDirection.sendrecv
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendrecv

    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.inactive
