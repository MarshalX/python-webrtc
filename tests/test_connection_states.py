#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The ICE connection state and the connection state, derived from the transports."""

from __future__ import annotations

import asyncio

import pytest

import webrtc
from tests.helpers import (
    QUIET_PERIOD,
    connect,
    exchange_offer_answer,
    wait_for_event,
    wait_for_ice_gathering_complete,
    wait_until,
)


def sctp_transport(pc: webrtc.RTCPeerConnection) -> webrtc.RTCDtlsTransport:
    assert pc.sctp is not None
    return pc.sctp.transport


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
    assert all(state == transport_state for kind, state, transport_state in seen if kind == 'ice'), seen


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
    await asyncio.sleep(QUIET_PERIOD)

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
    ice_closed = wait_for_event(
        dtls.ice_transport, 'statechange', predicate=lambda _event: dtls.ice_transport.state == 'closed'
    )

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
