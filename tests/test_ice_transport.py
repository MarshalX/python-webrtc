#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""ICE transports: the ones of a connection, and ones of their own.

The ones of their own (the WebRTC ICE extension) gather, start and connect without a connection.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from typing import cast

import pytest

import webrtc
import wrtc
from tests.helpers import (
    connect,
    exchange_answer,
    exchange_offer,
    wait_for_event,
    wait_for_ice_gathering_complete,
    wait_until,
)
from tests.timing import seconds
from webrtc.utils.loops import LoopState

#: the shortest valid ICE password
PASSWORD = 'p' * 22
CANDIDATE = 'candidate:1 1 udp 2122260223 192.0.2.1 50000 typ host'
#: the fields of a candidate before its address
CANDIDATE_ADDRESS = re.compile(r'^((?:\S+ ){4})\S+')
MDNS_NAME = '4f1e9d2c-8a7b-4c5d-9e3f-0f3c1d7e6b5a.local'


def local_parameters(transport: webrtc.RTCIceTransport) -> webrtc.RTCIceParameters:
    parameters = transport.get_local_parameters()
    assert parameters is not None
    return parameters


async def data_channel_ice_transport(pc: webrtc.RTCPeerConnection, label: str) -> webrtc.RTCIceTransport:
    """The ICE transport of a new data channel, once the offer is set locally."""
    pc.create_data_channel(label)
    await pc.set_local_description()
    assert pc.sctp is not None
    return pc.sctp.transport.ice_transport


def forward_candidates(source: webrtc.RTCIceTransport, destination: webrtc.RTCIceTransport) -> None:
    """Signals the candidates the source gathers to the destination."""

    def on_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
        if event.candidate is not None:
            destination.add_remote_candidate(event.candidate)

    source.on('icecandidate', on_candidate)


async def connect_transports(local: webrtc.RTCIceTransport, remote: webrtc.RTCIceTransport) -> None:
    """Gathers, starts the local transport controlling and the remote one controlled, and waits for both."""
    local.gather()
    remote.gather()
    local.start(local_parameters(remote), 'controlling')
    remote.start(local_parameters(local), 'controlled')

    def connected() -> bool:
        return local.state == remote.state == webrtc.RTCIceTransportState.connected

    await wait_until(connected, 'both transports to connect')


@pytest.mark.asyncio
async def test_candidates_parameters_and_role(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A connection's transport learns its role from the answer, and has the signaled parameters and candidates."""
    ice = await data_channel_ice_transport(caller, 'ice')
    assert ice.role == webrtc.RTCIceRole.unknown
    assert ice.get_remote_parameters() is None

    await connect(caller, callee)
    await wait_until(lambda: ice.role == webrtc.RTCIceRole.controlling, 'the controlling role')

    assert callee.sctp is not None
    remote_ice = callee.sctp.transport.ice_transport
    local = ice.get_local_parameters()
    remote = ice.get_remote_parameters()
    assert isinstance(local, webrtc.RTCIceParameters)
    assert local.username_fragment != ''
    assert local.password != ''
    assert remote is not None
    assert remote.username_fragment == local_parameters(remote_ice).username_fragment
    assert len(ice.get_local_candidates()) > 0
    assert all(c.candidate for c in ice.get_local_candidates())
    assert {c.candidate for c in ice.get_remote_candidates()} <= {
        c.candidate for c in remote_ice.get_local_candidates()
    }


@pytest.mark.asyncio
async def test_once_handles_the_first_state_change_only(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    ice = await data_channel_ice_transport(caller, 'once')
    first: list[webrtc.RTCIceTransportState] = []
    every: list[webrtc.RTCIceTransportState] = []
    ice.once('statechange', lambda _event: first.append(ice.state))
    ice.on('statechange', lambda _event: every.append(ice.state))

    await connect(caller, callee)
    await wait_until(lambda: webrtc.RTCIceTransportState.connected in every, 'the connected ICE transport')

    assert len(every) > 1
    assert first == every[:1]


@pytest.mark.asyncio
async def test_component(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """RTP and RTCP are multiplexed on the transport of the RTP component."""
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)

    await connect(caller, callee)

    assert transceiver.sender.transport is not None
    assert transceiver.sender.transport.ice_transport.component == webrtc.RTCIceComponent.rtp


@pytest.mark.asyncio
async def test_close_keeps_gathering_state(pc: webrtc.RTCPeerConnection) -> None:
    """Closing a connection closes its transports, it doesn't complete their gathering."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    await pc.set_local_description()
    assert transceiver.sender.transport is not None
    ice = transceiver.sender.transport.ice_transport
    state = ice.gathering_state

    pc.close()

    assert ice.state == webrtc.RTCIceTransportState.closed
    assert ice.gathering_state == state


@pytest.mark.asyncio
async def test_two_transports_connect() -> None:
    """Two transports gather, start with each other's parameters and connect, one switching to the controlled role."""
    local, remote = webrtc.RTCIceTransport(), webrtc.RTCIceTransport()
    assert local.role is None
    assert local.state == webrtc.RTCIceTransportState.new
    assert local.get_local_parameters() is not None
    assert local.get_remote_parameters() is None
    assert local.get_selected_candidate_pair() is None

    forward_candidates(local, remote)
    forward_candidates(remote, local)
    connected = [wait_for_event(t, 'statechange') for t in (local, remote)]

    local.gather()
    remote.gather()
    # read live: host candidates may all be gathered already
    assert local.gathering_state != webrtc.RTCIceGathererState.new
    # both take the controlling role: one of them switches
    local.start(local_parameters(remote), 'controlling')
    remote.start(local_parameters(local), 'controlling')
    await asyncio.gather(*connected)

    assert local.state == remote.state == webrtc.RTCIceTransportState.connected
    assert {local.role, remote.role} == {webrtc.RTCIceRole.controlling, webrtc.RTCIceRole.controlled}
    pair = local.get_selected_candidate_pair()
    assert pair is not None
    assert pair.local.candidate in [c.candidate for c in local.get_local_candidates()]
    assert pair.remote.candidate in [c.candidate for c in local.get_remote_candidates()]

    local.stop()
    assert local.state == webrtc.RTCIceTransportState.closed
    assert local.get_selected_candidate_pair() is None
    with pytest.raises(webrtc.InvalidStateError):
        local.gather()
    remote.stop()


def test_start_validation() -> None:
    """Start checks the remote parameters and the role, and other remote parameters restart the checks."""
    transport = webrtc.RTCIceTransport()
    with pytest.raises(webrtc.InvalidSyntaxError):
        transport.start(webrtc.RTCIceParameters('ab', PASSWORD))
    with pytest.raises(webrtc.InvalidSyntaxError):
        transport.start(webrtc.RTCIceParameters('abcd', 'short'))

    transport.start(webrtc.RTCIceParameters('abcd', PASSWORD))
    assert transport.role == webrtc.RTCIceRole.controlled
    with pytest.raises(webrtc.InvalidStateError):
        transport.start(webrtc.RTCIceParameters('abcd', PASSWORD), 'controlling')
    with pytest.raises(webrtc.OperationError):
        transport.add_remote_candidate(webrtc.RTCIceCandidate('invalid', sdp_mid=''))

    candidate = webrtc.RTCIceCandidate('candidate:1 1 udp 2113929471 203.0.113.100 10100 typ host', sdp_mid='')
    transport.add_remote_candidate(candidate)
    assert transport.state == webrtc.RTCIceTransportState.checking
    assert transport.get_remote_candidates() == [candidate]

    # other remote parameters are another remote agent
    transport.start(webrtc.RTCIceParameters('efgh', 'q' * 22))
    assert transport.state == webrtc.RTCIceTransportState.new
    assert transport.get_remote_candidates() == []

    transport.stop()


@pytest.mark.asyncio
async def test_selected_pair_changes_with_its_event(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A transport's selected pair changes once Python sees its selectedcandidatepairchange event."""
    caller.create_data_channel('pair')
    # the candidates go in the descriptions: none to trickle while the signaling thread is parked
    await caller.set_local_description()
    await wait_for_ice_gathering_complete(caller)
    await callee.set_remote_description(cast('webrtc.RTCSessionDescription', caller.local_description))
    await callee.set_local_description()
    await wait_for_ice_gathering_complete(callee)

    assert caller.sctp is not None
    assert callee.sctp is not None
    transports = (caller.sctp.transport.ice_transport, callee.sctp.transport.ice_transport)
    # the pair each transport showed last along with its event
    shown = [transport.get_selected_candidate_pair() for transport in transports]

    def show_on_change(index: int, transport: webrtc.RTCIceTransport) -> None:
        def on_change(_event: webrtc.Event) -> None:
            shown[index] = transport.get_selected_candidate_pair()

        transport.on('selectedcandidatepairchange', on_change)

    for index, transport in enumerate(transports):
        show_on_change(index, transport)

    wrtc._testing.park('ice.pairchanged')
    try:
        answering = asyncio.ensure_future(
            caller.set_remote_description(cast('webrtc.RTCSessionDescription', callee.local_description))
        )
        # a transport selected another pair, before its event
        assert await asyncio.to_thread(wrtc._testing.parked, 'ice.pairchanged', seconds(5))
        assert [transport.get_selected_candidate_pair() for transport in transports] == shown
    finally:
        wrtc._testing.release('ice.pairchanged')
    await answering
    await wait_until(lambda: shown[0] is not None, 'the selected pair')
    ice = transports[0]

    caller.close()

    assert ice.get_selected_candidate_pair() is None


@pytest.mark.asyncio
async def test_transport_bundled_away_shows_its_state_until_its_close_event(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    caller.add_transceiver('audio')
    video = caller.add_transceiver('video')
    await caller.set_local_description()
    transport = video.sender.transport
    assert transport is not None
    ice = transport.ice_transport
    closed = wait_for_event(ice, 'statechange')

    await callee.set_remote_description(cast('webrtc.RTCSessionDescription', caller.local_description))
    await callee.set_local_description()

    wrtc._testing.park('ice.closed')
    try:
        answering = asyncio.ensure_future(
            caller.set_remote_description(cast('webrtc.RTCSessionDescription', callee.local_description))
        )
        # closed natively, before its event
        assert await asyncio.to_thread(wrtc._testing.parked, 'ice.closed', seconds(5))
        assert ice.state == webrtc.RTCIceTransportState.new

        # as any event of the connection does
        LoopState.of(asyncio.get_running_loop()).update(caller)
    finally:
        wrtc._testing.release('ice.closed')
    await answering

    await closed
    assert ice.state == webrtc.RTCIceTransportState.closed


@pytest.mark.asyncio
async def test_gathering_shows_new_until_gather_surfaces_it() -> None:
    ice = webrtc.RTCIceTransport()
    completed = wait_for_event(ice, 'gatheringstatechange')

    wrtc._testing.park('ice.gatheringstatechange')
    try:
        gathering = asyncio.ensure_future(asyncio.to_thread(ice.gather))
        assert await asyncio.to_thread(wrtc._testing.parked, 'ice.gatheringstatechange', seconds(5))
        assert ice.gathering_state == webrtc.RTCIceGathererState.new
    finally:
        wrtc._testing.release('ice.gatheringstatechange')
    await gathering
    assert ice.gathering_state != webrtc.RTCIceGathererState.new

    await completed
    assert ice.gathering_state == webrtc.RTCIceGathererState.complete
    ice.stop()


async def offered_audio(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> webrtc.RTCIceTransport:
    """The callee's ICE transport of an offered audio section."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await callee.set_remote_description(await caller.create_offer())
    await callee.set_local_description()

    transport = callee.get_transceivers()[0].receiver.transport
    assert transport is not None
    return transport.ice_transport


@pytest.mark.asyncio
async def test_candidate_signaled_by_the_index_of_its_media_section(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A candidate with only sdp_m_line_index goes to that section."""
    ice = await offered_audio(caller, callee)

    await callee.add_ice_candidate(webrtc.RTCIceCandidateInit(CANDIDATE, sdp_m_line_index=0))

    remote = callee.remote_description
    assert remote is not None
    assert f'a={CANDIDATE}' in remote.sdp
    assert [(c.address, c.port) for c in ice.get_remote_candidates()] == [('192.0.2.1', 50000)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('candidate', 'message'),
    [
        (webrtc.RTCIceCandidateInit(CANDIDATE, sdp_mid='unknown'), 'media section of the candidate was not found'),
        (webrtc.RTCIceCandidateInit(CANDIDATE, sdp_m_line_index=1), 'media section of the candidate was not found'),
        (
            webrtc.RTCIceCandidateInit(CANDIDATE, sdp_mid='0', username_fragment='unknown'),
            "usernameFragment doesn't match the remote description",
        ),
        (webrtc.RTCIceCandidateInit('candidate:1 1 udp', sdp_mid='0'), 'Failed to parse the ICE candidate'),
    ],
)
async def test_candidate_rejected_with_operation_error(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    candidate: webrtc.RTCIceCandidateInit,
    message: str,
) -> None:
    """A candidate for no media section, or that doesn't parse."""
    ice = await offered_audio(caller, callee)

    with pytest.raises(webrtc.OperationError, match=message):
        await callee.add_ice_candidate(candidate)

    assert ice.get_remote_candidates() == []


@pytest.mark.asyncio
async def test_end_of_candidates_is_for_one_remote_description(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Remote descriptions after an ICE restart don't show the end of candidates of an earlier one."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer(caller, callee)
    await callee.add_ice_candidate()
    await exchange_answer(caller, callee)

    # the answer makes the offer current, which keeps it
    current = callee.current_remote_description
    assert current is not None
    assert 'a=end-of-candidates' in current.sdp

    # later descriptions may take the address of a freed one
    for _ in range(20):
        caller.restart_ice()
        await exchange_offer(caller, callee)
        pending = callee.pending_remote_description
        assert pending is not None
        assert 'a=end-of-candidates' not in pending.sdp

        await exchange_answer(caller, callee)
        current = callee.current_remote_description
        assert current is not None
        assert 'a=end-of-candidates' not in current.sdp


@pytest.mark.asyncio
async def test_candidate_without_media_section_is_a_type_error(pc: webrtc.RTCPeerConnection) -> None:
    """Checked before the state."""
    with pytest.raises(TypeError, match='sdp_mid and sdp_m_line_index are both None'):
        await pc.add_ice_candidate(webrtc.RTCIceCandidateInit(CANDIDATE))


async def offer_with_candidates(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, *candidates: str
) -> None:
    """Signals an audio offer with the candidates in its media section."""
    caller.add_transceiver(webrtc.MediaType.audio)
    offer = await caller.create_offer()
    lines = ''.join(f'a={candidate}\r\n' for candidate in candidates)
    offer.sdp = offer.sdp.replace('a=mid:0\r\n', f'a=mid:0\r\n{lines}')
    await callee.set_remote_description(offer)


@pytest.mark.asyncio
async def test_candidates_of_blocked_ports_are_ignored(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """TCP candidates for blocked ports are dropped."""
    blocked = 'candidate:2 1 tcp 1518280447 192.0.2.2 22 typ host tcptype passive'
    await offer_with_candidates(caller, callee, blocked, CANDIDATE)

    await callee.add_ice_candidate(webrtc.RTCIceCandidateInit(blocked.replace('192.0.2.2', '192.0.2.3'), sdp_mid='0'))

    remote = callee.remote_description
    assert remote is not None
    assert f'a={CANDIDATE}' in remote.sdp
    assert ' 22 typ host' not in remote.sdp


@pytest.mark.asyncio
async def test_active_tcp_candidates_on_the_discard_port_are_kept(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """An active candidate is never connected to, so its port 9 (RFC 6544) isn't blocked."""
    active = 'candidate:2 1 tcp 1518280447 192.0.2.2 9 typ host tcptype active'
    await offer_with_candidates(caller, callee, active)

    await callee.add_ice_candidate(webrtc.RTCIceCandidateInit(active.replace('192.0.2.2', '192.0.2.3'), sdp_mid='0'))

    remote = callee.remote_description
    assert remote is not None
    assert f'a={active}' in remote.sdp
    assert ' 192.0.2.3 9 typ host tcptype active' in remote.sdp


@pytest.mark.asyncio
async def test_standalone_methods_reject_a_transport_of_a_connection(pc: webrtc.RTCPeerConnection) -> None:
    """Gather, start, stop and remote candidates are standalone-only."""
    ice = await data_channel_ice_transport(pc, 'ice')
    calls = [
        ice.gather,
        lambda: ice.start(webrtc.RTCIceParameters('abcd', PASSWORD)),
        lambda: ice.add_remote_candidate(webrtc.RTCIceCandidateInit(CANDIDATE, sdp_mid='')),
        ice.stop,
    ]

    for call in calls:
        with pytest.raises(webrtc.InvalidStateError, match='belongs to an RTCPeerConnection'):
            call()


def test_gather_once_and_with_a_known_role() -> None:
    transport = webrtc.RTCIceTransport()
    transport.gather()

    with pytest.raises(webrtc.InvalidStateError, match='gathers its candidates already'):
        transport.gather()
    with pytest.raises(ValueError, match='controlling or controlled'):
        transport.start(webrtc.RTCIceParameters('abcd', PASSWORD), webrtc.RTCIceRole.unknown)

    transport.stop()


def has_usable_ipv6() -> bool:
    """A route to the global IPv6 internet from an address libwebrtc gathers on (not link-local nor MAC-based)."""
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as probe:
            # a documentation address: picks the source of the default route, sends nothing
            probe.connect(('2001:db8::1', 9))
            host: str = probe.getsockname()[0]
        address = ipaddress.IPv6Address(host.split('%', maxsplit=1)[0])
    except (OSError, ValueError):
        return False
    # RFC 4291 appendix A: an interface ID from a MAC has ff:fe in its middle
    mac_based = address.packed[11:13] == b'\xff\xfe'
    return not (address.is_link_local or address.is_loopback or address.is_unspecified or mac_based)


@pytest.mark.asyncio
async def test_gathers_like_a_connection() -> None:
    """Without the 1 s waits between phases or passive TCP candidates, with IPv6 where the host has it."""
    transport = webrtc.RTCIceTransport()

    def complete(_: webrtc.Event) -> bool:
        return transport.gathering_state == webrtc.RTCIceGathererState.complete

    gathered = wait_for_event(transport, 'gatheringstatechange', predicate=complete)

    start = time.monotonic()
    transport.gather()
    await gathered
    elapsed = time.monotonic() - start
    candidates = transport.get_local_candidates()
    transport.stop()

    assert elapsed < seconds(1), elapsed
    assert any(c.protocol == webrtc.RTCIceProtocol.udp for c in candidates), candidates
    assert all(c.tcp_type in {None, webrtc.RTCIceTcpCandidateType.active} for c in candidates), candidates
    if has_usable_ipv6():
        assert any(c.address is not None and ':' in c.address for c in candidates), candidates


def test_remote_candidate_from_a_dictionary() -> None:
    transport = webrtc.RTCIceTransport()

    transport.add_remote_candidate(webrtc.RTCIceCandidateInit(CANDIDATE, sdp_mid='', username_fragment='abcd'))

    (candidate,) = transport.get_remote_candidates()
    assert isinstance(candidate, webrtc.RTCIceCandidate)
    assert (candidate.candidate, candidate.address, candidate.username_fragment) == (CANDIDATE, '192.0.2.1', 'abcd')
    transport.stop()


@pytest.mark.asyncio
async def test_unsignaled_remote_is_peer_reflexive() -> None:
    """It connects to the address the checks come from."""
    local, remote = webrtc.RTCIceTransport(), webrtc.RTCIceTransport()
    # only the remote's candidates are signaled
    forward_candidates(remote, local)

    await connect_transports(local, remote)

    pair = remote.get_selected_candidate_pair()
    assert pair is not None
    assert pair.remote.candidate == ''
    assert pair.remote.type == webrtc.RTCIceCandidateType.prflx
    assert pair.remote.address is None

    # signaled later, the remote candidate is the signaled one
    for candidate in local.get_local_candidates():
        remote.add_remote_candidate(candidate)

    pair = remote.get_selected_candidate_pair()
    assert pair is not None
    assert pair.remote.type == webrtc.RTCIceCandidateType.host
    assert pair.remote.candidate in [c.candidate for c in local.get_local_candidates()]
    local.stop()
    remote.stop()


@pytest.mark.asyncio
async def test_remote_signaled_by_hostname_pairs_as_the_signaled_candidate() -> None:
    """An mDNS candidate connects from its address."""
    local, remote = webrtc.RTCIceTransport(), webrtc.RTCIceTransport()
    signaled: list[str] = []

    def on_local_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
        if event.candidate is not None and event.candidate.protocol == webrtc.RTCIceProtocol.udp:
            # an mDNS name the remote can't resolve
            hidden = CANDIDATE_ADDRESS.sub(rf'\g<1>{MDNS_NAME}', event.candidate.candidate)
            signaled.append(hidden)
            remote.add_remote_candidate(webrtc.RTCIceCandidateInit(hidden, sdp_mid=''))

    local.on('icecandidate', on_local_candidate)
    forward_candidates(remote, local)

    await connect_transports(local, remote)

    pair = remote.get_selected_candidate_pair()
    assert pair is not None
    assert pair.remote.candidate in signaled
    assert pair.remote.type == webrtc.RTCIceCandidateType.host
    local.stop()
    remote.stop()


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason='a transport bundled away forgets its parameters, webrtc-pc keeps them')
async def test_transport_bundled_away_keeps_its_parameters(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    audio = caller.add_transceiver('audio')
    video = caller.add_transceiver('video')
    await caller.set_local_description()

    transport = video.sender.transport
    assert transport is not None
    assert transport is not audio.sender.transport
    parameters = transport.ice_transport.get_local_parameters()
    assert parameters is not None

    assert caller.local_description is not None
    await callee.set_remote_description(caller.local_description)
    await callee.set_local_description()
    assert callee.local_description is not None
    await caller.set_remote_description(callee.local_description)

    assert video.sender.transport is audio.sender.transport
    assert transport.ice_transport.get_local_parameters() == parameters
