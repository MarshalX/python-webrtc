#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The ICE connection state and the connection state, derived from the transports."""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import TYPE_CHECKING

import pytest

import webrtc
import wrtc
from tests.helpers import (
    connect,
    delivered,
    exchange_answer,
    exchange_ice_candidates,
    exchange_offer_answer,
    wait_for_event,
    wait_for_ice_gathering_complete,
    wait_until,
)
from tests.timing import seconds

if TYPE_CHECKING:
    from collections.abc import Awaitable


def sctp_transport(pc: webrtc.RTCPeerConnection) -> webrtc.RTCDtlsTransport:
    assert pc.sctp is not None
    return pc.sctp.transport


def collected_candidates(pc: webrtc.RTCPeerConnection) -> list[webrtc.RTCIceCandidate]:
    """Collects the candidates the connection gathers from now on."""
    candidates: list[webrtc.RTCIceCandidate] = []

    def collect(event: webrtc.RTCPeerConnectionIceEvent) -> None:
        if event.candidate is not None:
            candidates.append(event.candidate)

    pc.on('icecandidate', collect)
    return candidates


def colon_separated(digest: str) -> str:
    """A hex digest as an SDP fingerprint: byte by byte, separated by colons."""
    return ':'.join(digest[i : i + 2] for i in range(0, len(digest), 2))


@pytest.mark.asyncio
async def test_transports_change_with_the_connection(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The handlers of the connection's state events see its transports in the matching states."""
    seen: list[tuple[str, str, str]] = []

    def on_ice_connection_state(_event: webrtc.Event) -> None:
        # Python takes the transports here first
        seen.append(('ice', caller.ice_connection_state, sctp_transport(caller).ice_transport.state))

    def on_connection_state(_event: webrtc.Event) -> None:
        seen.append(('connection', caller.connection_state, sctp_transport(caller).state))

    caller.on('iceconnectionstatechange', on_ice_connection_state)
    caller.on('connectionstatechange', on_connection_state)
    caller.create_data_channel('states')

    await connect(caller, callee)
    await wait_until(lambda: ('ice', 'connected', 'connected') in seen, 'the connected ICE transport')

    assert ('ice', 'checking', 'checking') in seen
    assert ('connection', 'connected', 'connected') in seen
    ice_states = [(state, transport_state) for kind, state, transport_state in seen if kind == 'ice']
    assert all(state == transport_state for state, transport_state in ice_states), seen


@pytest.mark.asyncio
async def test_transport_event_comes_first(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """A transport's statechange comes before the connection's events, in one task."""
    caller.create_data_channel('order')
    await caller.set_local_description()
    ice = sctp_transport(caller).ice_transport
    events: list[tuple[str, str, str]] = []

    def on_transport_state(_event: webrtc.Event) -> None:
        events.append(('statechange', ice.state, caller.ice_connection_state))

    def on_ice_connection_state(_event: webrtc.Event) -> None:
        events.append(('iceconnectionstatechange', ice.state, caller.ice_connection_state))

    ice.on('statechange', on_transport_state)
    caller.on('iceconnectionstatechange', on_ice_connection_state)

    await connect(caller, callee)
    await wait_until(lambda: len(events) >= 4, 'the connected events')

    assert events[:4] == [
        ('statechange', 'checking', 'checking'),
        ('iceconnectionstatechange', 'checking', 'checking'),
        ('statechange', 'connected', 'connected'),
        ('iceconnectionstatechange', 'connected', 'connected'),
    ]


@pytest.mark.asyncio
async def test_ice_restart_keeps_the_connection_connected(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """An ICE restart over a working connection changes no state, and the connection is never completed."""
    caller.add_transceiver(webrtc.MediaType.audio, webrtc.RTCRtpTransceiverInit(direction='recvonly'))
    await connect(caller, callee)
    assert caller.ice_connection_state == webrtc.RTCIceConnectionState.connected
    events: list[str] = []
    caller.on('iceconnectionstatechange', lambda _event: events.append(caller.ice_connection_state))

    caller.restart_ice()
    await exchange_offer_answer(caller, callee)
    await delivered()

    assert events == []
    assert caller.ice_connection_state == webrtc.RTCIceConnectionState.connected


@pytest.mark.asyncio
async def test_remote_close_ends_dtls_only(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """The remote peer closing ends DTLS, while ICE goes on."""
    caller.create_data_channel('close')
    await connect(caller, callee)
    dtls = sctp_transport(caller)
    closed = wait_for_event(dtls, 'statechange', predicate=lambda _event: dtls.state == 'closed')

    callee.close()
    await closed

    assert dtls.ice_transport.state == webrtc.RTCIceTransportState.connected
    assert caller.ice_connection_state == webrtc.RTCIceConnectionState.connected
    assert caller.connection_state == webrtc.RTCPeerConnectionState.connected

    caller.close()

    assert dtls.ice_transport.state == webrtc.RTCIceTransportState.closed


@pytest.mark.asyncio
async def test_remote_certificates_match_the_signaled_fingerprint(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    caller.create_data_channel('certificates')
    await caller.set_local_description()
    dtls = sctp_transport(caller)
    assert dtls.get_remote_certificates() == []

    await connect(caller, callee)

    certificates = dtls.get_remote_certificates()
    assert len(certificates) > 0
    assert callee.local_description is not None
    lines = callee.local_description.sdp.split('\r\n')
    fingerprint = next(line for line in lines if line.startswith('a=fingerprint:sha-256 '))
    digest = hashlib.sha256(certificates[0]).hexdigest().upper()
    assert fingerprint.split(' ')[1] == colon_separated(digest)


@pytest.mark.asyncio
async def test_wrong_fingerprint_fails_dtls(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """A mismatched certificate fires a dtls-failure error first."""
    caller.create_data_channel('dtls')
    exchange_ice_candidates(caller, callee)
    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    zeros = ':'.join(['00'] * 32)
    wrong = re.sub(r'(a=fingerprint:sha-256 )\S+', rf'\g<1>{zeros}', offer.sdp)
    await callee.set_remote_description(webrtc.RTCSessionDescriptionInit('offer', wrong))
    dtls = sctp_transport(callee)
    events: list[webrtc.Event] = []
    dtls.on('error', events.append)
    failed = wait_for_event(dtls, 'statechange', predicate=lambda _event: dtls.state == 'failed')

    await exchange_answer(caller, callee)
    events.append(await failed)

    error_event, state_event = events
    assert isinstance(error_event, webrtc.RTCErrorEvent)
    # libwebrtc reports a fingerprint mismatch as any handshake failure
    assert error_event.error.error_detail == webrtc.RTCErrorDetailType.dtls_failure
    assert state_event.type == 'statechange'


@pytest.mark.asyncio
async def test_once_handles_the_first_dtls_state_change_only(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    caller.create_data_channel('once')
    await caller.set_local_description()
    dtls = sctp_transport(caller)
    first: list[webrtc.RTCDtlsTransportState] = []
    every: list[webrtc.RTCDtlsTransportState] = []
    dtls.once('statechange', lambda _event: first.append(dtls.state))
    dtls.on('statechange', lambda _event: every.append(dtls.state))

    await connect(caller, callee)
    await wait_until(lambda: webrtc.RTCDtlsTransportState.connected in every, 'the connected DTLS transport')

    assert len(every) > 1
    assert first == every[:1]


@pytest.mark.asyncio
async def test_dtls_transport_shows_its_state_until_its_statechange_event(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    caller_candidates = collected_candidates(caller)
    callee_candidates = collected_candidates(callee)
    caller.create_data_channel('pinned')
    # no candidates yet, so neither end connects before both transports are taken
    await exchange_offer_answer(caller, callee)
    await asyncio.gather(*(wait_for_ice_gathering_complete(pc) for pc in (caller, callee)))
    transports = [sctp_transport(pc) for pc in (caller, callee)]
    changed = [wait_for_event(dtls, 'statechange') for dtls in transports]

    wrtc._testing.park('dtls.statechange')
    try:
        adding = [asyncio.ensure_future(callee.add_ice_candidate(candidate)) for candidate in caller_candidates]
        adding += [asyncio.ensure_future(caller.add_ice_candidate(candidate)) for candidate in callee_candidates]
        assert await asyncio.to_thread(wrtc._testing.parked, 'dtls.statechange', seconds(10))
        assert [dtls.state for dtls in transports] == [webrtc.RTCDtlsTransportState.new] * 2
    finally:
        wrtc._testing.release('dtls.statechange')
    await asyncio.gather(*adding)

    await asyncio.gather(*changed)
    assert all(dtls.state != webrtc.RTCDtlsTransportState.new for dtls in transports)


@pytest.mark.asyncio
@pytest.mark.parametrize('remote_closed', [False, True], ids=['connected', 'remote closed'])
async def test_dropped_transport_closes(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, *, remote_closed: bool
) -> None:
    """A transport a negotiation drops closes with its ICE transport."""
    transceiver = caller.add_transceiver('audio')
    await connect(caller, callee)
    dtls = transceiver.sender.transport
    assert dtls is not None
    if remote_closed:
        dtls_closed = wait_for_event(dtls, 'statechange', predicate=lambda _event: dtls.state == 'closed')
        callee.close()
        await dtls_closed
    ice = dtls.ice_transport
    ice_closed = wait_for_event(ice, 'statechange', predicate=lambda _event: ice.state == 'closed')

    transceiver.stop()
    # another peer answers, rejecting the only m-line
    answerer = webrtc.RTCPeerConnection()
    await exchange_offer_answer(caller, answerer)
    await ice_closed

    assert dtls.state == webrtc.RTCDtlsTransportState.closed
    answerer.close()


@pytest.mark.asyncio
async def test_transport_taken_late_shows_its_state_and_gets_the_next_events(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Transport taken after connecting gets later events."""
    caller.create_data_channel('late')
    await connect(caller, callee)
    ice = sctp_transport(caller).ice_transport
    assert ice.state == webrtc.RTCIceTransportState.connected
    assert ice.gathering_state == webrtc.RTCIceGathererState.complete

    states: list[str] = []
    ice.on('gatheringstatechange', lambda _event: states.append(ice.gathering_state))

    caller.restart_ice()
    await exchange_offer_answer(caller, callee)
    await wait_until(lambda: 'complete' in states, 'the transport to gather again')

    assert states == ['gathering', 'complete']


async def connect_watching_ice(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> list[str]:
    """Connects without trickling, and returns the states of the caller's ICE transport until connected."""
    caller.create_data_channel('unwatched')
    await caller.set_local_description()
    ice = sctp_transport(caller).ice_transport
    states: list[str] = []
    ice.on('statechange', lambda _event: states.append(ice.state))

    await wait_for_ice_gathering_complete(caller)
    assert caller.local_description is not None
    await callee.set_remote_description(caller.local_description)
    await callee.set_local_description()
    await wait_for_ice_gathering_complete(callee)
    assert callee.local_description is not None
    await caller.set_remote_description(callee.local_description)

    await wait_until(lambda: 'connected' in states, 'the events of the transport')
    return states


def test_transport_events_without_connection_handlers() -> None:
    """A transport's handlers get its events while its connection, made outside a loop, has none."""
    caller = webrtc.RTCPeerConnection()
    callee = webrtc.RTCPeerConnection()
    try:
        states = asyncio.run(connect_watching_ice(caller, callee))
    finally:
        caller.close()
        callee.close()

    assert states == ['checking', 'connected']


@pytest.mark.asyncio
async def test_close_leaves_the_gathering_state(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """close() sets the ICE connection state to closed."""
    callee.close()

    assert callee.ice_connection_state == webrtc.RTCIceConnectionState.closed
    assert callee.ice_gathering_state == webrtc.RTCIceGatheringState.new

    caller.add_transceiver('audio')
    await caller.set_local_description()
    await wait_for_ice_gathering_complete(caller)

    caller.close()

    assert caller.ice_connection_state == webrtc.RTCIceConnectionState.closed
    assert caller.ice_gathering_state == webrtc.RTCIceGatheringState.complete


async def negotiated_without_candidates() -> tuple[
    webrtc.RTCPeerConnection, webrtc.RTCPeerConnection, webrtc.RTCIceTransport
]:
    caller = webrtc.RTCPeerConnection()
    callee = webrtc.RTCPeerConnection()
    caller.add_transceiver('audio')
    # made before gathering, so no candidates
    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    await caller.set_remote_description(answer)
    await wait_for_ice_gathering_complete(caller)

    transport = caller.get_transceivers()[0].sender.transport
    assert transport is not None
    return caller, callee, transport.ice_transport


async def watch_state(ice: webrtc.RTCIceTransport, state: webrtc.RTCIceTransportState) -> Awaitable[webrtc.Event]:  # ruff: ignore[unused-async]
    return wait_for_event(ice, 'statechange', predicate=lambda _event: ice.state == state)


def test_transport_events_reach_their_loop_once_the_connection_loop_is_gone() -> None:
    first = asyncio.new_event_loop()
    second = asyncio.new_event_loop()
    caller, callee, ice = first.run_until_complete(negotiated_without_candidates())
    try:
        connected = second.run_until_complete(watch_state(ice, webrtc.RTCIceTransportState.connected))
        # no handlers that would bind it to the second loop
        first.close()

        async def signal_caller() -> None:
            # the caller learns the callee from its checks
            for candidate in ice.get_local_candidates():
                await callee.add_ice_candidate(candidate)
            await connected

        second.run_until_complete(signal_caller())

        assert ice.state == webrtc.RTCIceTransportState.connected
    finally:
        caller.close()
        callee.close()
        first.close()
        second.close()
