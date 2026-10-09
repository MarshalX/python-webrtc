#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCSessionDescription, created as in the specification: a type is required, the SDP is optional."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

import webrtc
from tests.helpers import mistyped

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.helpers import CreatePC


def test_type_is_required() -> None:
    """The init of a description needs its type, as its WebIDL dictionary does."""
    no_arguments: Callable[[], object] = mistyped(webrtc.RTCSessionDescription)
    with pytest.raises(TypeError):
        no_arguments()
    with pytest.raises(TypeError):
        webrtc.RTCSessionDescriptionInit.from_json({'sdp': ''})
    with pytest.raises(TypeError):
        webrtc.RTCSessionDescription('offer', mistyped(None))
    with pytest.raises(ValueError, match='not a valid RTCSdpType'):
        webrtc.RTCSessionDescription(mistyped({'type': 'offer'}))


@pytest.mark.parametrize(
    'init',
    [
        webrtc.RTCSessionDescriptionInit.from_json({'type': 'rollback'}),
        webrtc.RTCSessionDescriptionInit('rollback'),
        webrtc.RTCSdpType.rollback,
    ],
)
def test_sdp_is_empty_by_default(init: webrtc.RTCSessionDescriptionInit | webrtc.RTCSdpType) -> None:
    """A description from the JSON form, an init or a type has an empty SDP."""
    description = webrtc.RTCSessionDescription(init)
    assert description.type == webrtc.RTCSdpType.rollback
    assert description.sdp == ''
    assert description.to_json() == {'type': 'rollback', 'sdp': ''}


def test_type_and_sdp_can_be_changed() -> None:
    """The type and the SDP of a description can be set, and are validated."""
    description = webrtc.RTCSessionDescription('offer', 'v=0\r\n')
    description.type = 'answer'
    description.sdp += 'a=x\r\n'
    assert description.type == webrtc.RTCSdpType.answer
    assert description.to_json() == {'type': 'answer', 'sdp': 'v=0\r\na=x\r\n'}
    with pytest.raises(ValueError, match='not a valid RTCSdpType'):
        description.type = mistyped('bogus')
    with pytest.raises(TypeError):
        description.sdp = mistyped(None)


@pytest.mark.asyncio
async def test_changed_description_is_set(create_pc: CreatePC) -> None:
    """A changed description is set with its new values; the connection's own doesn't change."""
    caller, callee = create_pc(), create_pc()
    caller.add_transceiver(webrtc.MediaType.audio)
    await caller.set_local_description()
    offer = caller.local_description
    assert offer is not None
    ufrag = re.search(r'a=ice-ufrag:(\S+)', offer.sdp)
    assert ufrag is not None
    offer.sdp = offer.sdp.replace(f'a=ice-ufrag:{ufrag[1]}', 'a=ice-ufrag:munged')
    local = caller.local_description
    assert local is not None
    assert 'a=ice-ufrag:munged' not in local.sdp
    await callee.set_remote_description(offer)
    remote = callee.remote_description
    assert remote is not None
    assert 'a=ice-ufrag:munged' in remote.sdp

    answer = webrtc.RTCSessionDescription(await callee.create_answer())
    answer.type = webrtc.RTCSdpType.pranswer
    await callee.set_local_description(answer)
    assert callee.signaling_state == webrtc.RTCSignalingState.have_local_pranswer
