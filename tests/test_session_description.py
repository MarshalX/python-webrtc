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
from tests.helpers import exchange_offer, exchange_offer_answer, mistyped

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
    caller = create_pc()
    callee = create_pc()
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


def test_init_repr_shows_the_sdp_length() -> None:
    """The repr of an init gives the length of its SDP, not the SDP."""
    assert repr(webrtc.RTCSessionDescriptionInit('offer', 'v=0\r\n')) == (
        "RTCSessionDescriptionInit(type='offer', sdp=5 characters)"
    )


def test_local_description_init() -> None:
    """A local description init may have no type."""
    assert webrtc.RTCLocalSessionDescriptionInit().type is None
    assert webrtc.RTCLocalSessionDescriptionInit('answer').type == webrtc.RTCSdpType.answer
    with pytest.raises(ValueError, match='not a valid RTCSdpType'):
        webrtc.RTCLocalSessionDescriptionInit(mistyped('bogus'))
    with pytest.raises(TypeError, match='may not be None'):
        webrtc.RTCLocalSessionDescriptionInit('offer', mistyped(None))


@pytest.mark.asyncio
async def test_set_local_description_of_a_local_init(pc: webrtc.RTCPeerConnection) -> None:
    """A local init without a type sets the implicit description."""
    pc.add_transceiver(webrtc.MediaType.audio)

    with pytest.raises(TypeError, match='type of a description is required'):
        await pc.set_local_description(webrtc.RTCLocalSessionDescriptionInit(sdp='v=0\r\n'))

    await pc.set_local_description(webrtc.RTCLocalSessionDescriptionInit())
    assert pc.signaling_state == webrtc.RTCSignalingState.have_local_offer

    await pc.set_local_description(webrtc.RTCLocalSessionDescriptionInit('rollback'))
    assert pc.signaling_state == webrtc.RTCSignalingState.stable


@pytest.mark.asyncio
async def test_descriptions_have_to_be_of_their_types(pc: webrtc.RTCPeerConnection) -> None:
    """A description of another type is a TypeError."""
    with pytest.raises(TypeError, match='expected an RTCSessionDescription, not object'):
        await pc.set_local_description(mistyped(object()))
    with pytest.raises(TypeError, match='must be an RTCAnswerOptions, not RTCOfferOptions'):
        await pc.create_answer(mistyped(webrtc.RTCOfferOptions()))


@pytest.mark.asyncio
@pytest.mark.parametrize(('sdp', 'line'), [('garbage', 1), ('v=0\r\n', None)])
async def test_unparseable_local_description(pc: webrtc.RTCPeerConnection, sdp: str, line: int | None) -> None:
    """Unparseable local SDP is an sdp-syntax-error."""
    with pytest.raises(webrtc.RTCError, match='Failed to parse the session description') as error:
        await pc.set_local_description(webrtc.RTCSessionDescriptionInit('offer', sdp))

    assert error.value.error_detail == webrtc.RTCErrorDetailType.sdp_syntax_error
    assert error.value.sdp_line_number == line
    assert pc.signaling_state == webrtc.RTCSignalingState.stable


@pytest.mark.asyncio
async def test_descriptions_stay_after_close(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """webrtc-pc: close keeps the descriptions."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer_answer(caller, callee)
    await exchange_offer(caller, callee)
    local = caller.local_description
    remote = caller.current_remote_description
    assert local is not None
    assert remote is not None

    caller.close()

    # compared by type and ufrag, as candidates gathered meanwhile may be added to the SDP
    def type_and_ufrag(description: webrtc.RTCSessionDescription | None) -> tuple[str, str] | None:
        if description is None:
            return None
        return description.type, re.findall(r'a=ice-ufrag:\S+', description.sdp)[0]

    assert type_and_ufrag(caller.local_description) == type_and_ufrag(caller.pending_local_description)
    assert type_and_ufrag(caller.pending_local_description) == type_and_ufrag(local)
    assert type_and_ufrag(caller.current_remote_description) == type_and_ufrag(remote)
    assert caller.pending_remote_description is None


@pytest.mark.asyncio
async def test_offer_to_receive_adds_a_receiving_transceiver(pc: webrtc.RTCPeerConnection) -> None:
    """offer_to_receive_audio adds one recvonly transceiver."""
    options = webrtc.RTCOfferOptions(offer_to_receive_audio=True)
    offer = await pc.create_offer(options)
    await pc.create_offer(options)

    assert [(t.receiver.track.kind, t.direction) for t in pc.get_transceivers()] == [
        (webrtc.MediaType.audio, webrtc.RTCRtpTransceiverDirection.recvonly)
    ]
    assert 'm=audio' in offer.sdp
    assert 'a=recvonly' in offer.sdp


@pytest.mark.asyncio
async def test_offer_not_to_receive_stops_receiving(pc: webrtc.RTCPeerConnection) -> None:
    """offer_to_receive_video=False stops video transceivers receiving."""
    directions = webrtc.RTCRtpTransceiverDirection
    audio = pc.add_transceiver(webrtc.MediaType.audio)
    sendrecv = pc.add_transceiver(webrtc.MediaType.video)
    recvonly = pc.add_transceiver(webrtc.MediaType.video, webrtc.RTCRtpTransceiverInit(direction=directions.recvonly))
    sendonly = pc.add_transceiver(webrtc.MediaType.video, webrtc.RTCRtpTransceiverInit(direction=directions.sendonly))

    await pc.create_offer(webrtc.RTCOfferOptions(offer_to_receive_video=False))

    assert (audio.direction, sendrecv.direction, recvonly.direction, sendonly.direction) == (
        directions.sendrecv,
        directions.sendonly,
        directions.inactive,
        directions.sendonly,
    )


@pytest.mark.asyncio
async def test_final_answer_after_a_provisional_one(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """webrtc-pc: a provisional answer can't be rolled back."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer(caller, callee)
    answer = await callee.create_answer()

    await callee.set_local_description(webrtc.RTCSessionDescriptionInit('pranswer', answer.sdp))
    await caller.set_remote_description(webrtc.RTCSessionDescriptionInit('pranswer', answer.sdp))
    assert callee.signaling_state == webrtc.RTCSignalingState.have_local_pranswer
    assert caller.signaling_state == webrtc.RTCSignalingState.have_remote_pranswer

    with pytest.raises(
        webrtc.InvalidStateError, match='Can not set the local description in the have-local-pranswer signaling state'
    ):
        await callee.set_local_description(webrtc.RTCSessionDescriptionInit('rollback'))
    with pytest.raises(
        webrtc.InvalidStateError, match='Can not set the remote description in the have-remote-pranswer signaling state'
    ):
        await caller.set_remote_description(webrtc.RTCSessionDescriptionInit('rollback'))
    assert callee.signaling_state == webrtc.RTCSignalingState.have_local_pranswer
    assert caller.signaling_state == webrtc.RTCSignalingState.have_remote_pranswer

    await callee.set_local_description(webrtc.RTCSessionDescriptionInit('answer', answer.sdp))
    await caller.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', answer.sdp))
    assert callee.signaling_state == caller.signaling_state == webrtc.RTCSignalingState.stable
    assert callee.current_local_description is not None
    assert callee.current_local_description.type == webrtc.RTCSdpType.answer
    assert caller.current_remote_description is not None
    assert caller.current_remote_description.type == webrtc.RTCSdpType.answer
