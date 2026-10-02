#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Enums: their members are their spec strings, in both directions of the native API."""

from __future__ import annotations

import enum
import typing

import pytest

import webrtc
import webrtc.enums
from tests.helpers import mistyped


def test_members_are_their_values() -> None:
    """Members equal their values, and print as them."""
    assert webrtc.RTCSignalingState.have_local_offer == 'have-local-offer'
    assert webrtc.RTCPriorityType('very-low') is webrtc.RTCPriorityType.very_low
    assert str(webrtc.MediaType.audio) == f'{webrtc.MediaType.audio}' == 'audio'


def test_enums_are_exported() -> None:
    """Every enum is exported from the package, and defined in one module."""
    enums = [
        (name, value)
        for name, value in vars(webrtc.enums).items()
        if isinstance(value, type) and issubclass(value, enum.Enum) and value.__module__ == 'webrtc.enums'
    ]
    assert len(enums) > 0
    for name, value in enums:
        if not name.startswith('_'):
            assert getattr(webrtc, name) is value
            assert name in webrtc.__all__


def test_value_aliases_match_enums() -> None:
    """Each Literal alias of the values a parameter takes has exactly the values of its enum."""
    aliases = [name for name in webrtc.__all__ if name.endswith('Value')]
    assert len(aliases) > 0
    for name in aliases:
        cls = getattr(webrtc, name.removesuffix('Value'))
        assert typing.get_args(getattr(webrtc, name)) == tuple(member.value for member in cls), name


def test_native_getters_return_members(pc: webrtc.RTCPeerConnection) -> None:
    """The native API returns members."""
    assert pc.signaling_state is webrtc.RTCSignalingState.stable
    transceiver = pc.add_transceiver('audio')
    assert transceiver.receiver.track.kind is webrtc.MediaType.audio
    assert transceiver.direction is webrtc.RTCRtpTransceiverDirection.sendrecv


def test_native_setters_take_members_and_values(pc: webrtc.RTCPeerConnection) -> None:
    """The native API takes members and their values."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    transceiver.direction = 'recvonly'
    assert transceiver.direction is webrtc.RTCRtpTransceiverDirection.recvonly
    transceiver.direction = webrtc.RTCRtpTransceiverDirection.inactive
    assert transceiver.direction == 'inactive'


def test_invalid_values_are_type_errors(pc: webrtc.RTCPeerConnection) -> None:
    """Like for a WebIDL enum, a value the enum doesn't have is a TypeError."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    with pytest.raises(TypeError):
        transceiver.direction = mistyped('nonsense')
    with pytest.raises(TypeError):
        transceiver.direction = mistyped(1)
    with pytest.raises(TypeError):
        pc.add_transceiver('data')
    with pytest.raises(TypeError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(bundle_policy=mistyped('nonsense')))


def test_data_channel_priority(pc: webrtc.RTCPeerConnection) -> None:
    """Every priority of a data channel round-trips through libwebrtc."""
    for priority in webrtc.RTCPriorityType:
        assert pc.create_data_channel('x', webrtc.RTCDataChannelInit(priority=priority.value)).priority is priority
