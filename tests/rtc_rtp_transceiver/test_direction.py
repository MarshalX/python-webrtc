#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import pytest

import webrtc

from tests.helpers import generate_answer


def test_1(pc):
    """setting direction should change transceiver.direction"""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)

    assert transceiver.direction == webrtc.TransceiverDirection.sendrecv
    assert transceiver.current_direction is None

    transceiver.direction = webrtc.TransceiverDirection.recvonly
    assert transceiver.direction == webrtc.TransceiverDirection.recvonly
    assert transceiver.current_direction is None, 'Expect transceiver.currentDirection to not change'


def test_2(pc):
    """setting direction with same direction should have no effect"""
    init = webrtc.RtpTransceiverInit(direction=webrtc.TransceiverDirection.sendonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.direction == webrtc.TransceiverDirection.sendonly
    transceiver.direction = webrtc.TransceiverDirection.sendonly
    assert transceiver.direction == webrtc.TransceiverDirection.sendonly


@pytest.mark.asyncio
async def test_3(pc):
    """setting direction should change transceiver.direction independent of transceiver.currentDirection"""
    init = webrtc.RtpTransceiverInit(direction=webrtc.TransceiverDirection.recvonly)
    transceiver = pc.add_transceiver(webrtc.MediaType.audio, init)

    assert transceiver.direction == webrtc.TransceiverDirection.recvonly
    assert transceiver.current_direction is None

    offer = await pc.create_offer()
    await pc.set_local_description(offer)
    await pc.set_remote_description(await generate_answer(offer))

    assert transceiver.current_direction == webrtc.TransceiverDirection.inactive

    transceiver.direction = webrtc.TransceiverDirection.sendrecv
    assert transceiver.direction == webrtc.TransceiverDirection.sendrecv

    assert transceiver.current_direction == webrtc.TransceiverDirection.inactive
