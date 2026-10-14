#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The aiortc-shaped connection and data channels over loopback."""

from __future__ import annotations

import asyncio
import functools

import pytest

from tests.helpers import mistyped
from webrtc.aiortc import (
    InvalidStateError,
    RTCConfiguration,
    RTCDataChannel,
    RTCDtlsTransport,
    RTCIceCandidate,
    RTCIceGatherer,
    RTCPeerConnection,
    RTCSctpTransport,
    RTCSessionDescription,
    VideoStreamTrack,
)
from webrtc.aiortc.sdp import candidate_from_sdp

TIMEOUT = 10
#: no STUN server, so gathering is local
CONFIGURATION = RTCConfiguration(iceServers=[])


def local_description(pc: RTCPeerConnection) -> RTCSessionDescription:
    description = pc.localDescription
    assert description is not None
    return description


async def negotiate(caller: RTCPeerConnection, callee: RTCPeerConnection) -> None:
    await caller.setLocalDescription(await caller.createOffer())
    await callee.setRemoteDescription(local_description(caller))
    await callee.setLocalDescription(await callee.createAnswer())
    await caller.setRemoteDescription(local_description(callee))


def connected(pc: RTCPeerConnection) -> asyncio.Event:
    """Set once the connection is connected."""
    event = asyncio.Event()

    def on_change() -> None:
        if pc.connectionState == 'connected':
            event.set()

    pc.on('connectionstatechange', on_change)
    return event


async def close(*pcs: RTCPeerConnection) -> None:
    for pc in pcs:
        await pc.close()


@pytest.mark.asyncio
async def test_offer_has_every_candidate() -> None:
    """The offer is complete once setLocalDescription returns."""
    pc = RTCPeerConnection(CONFIGURATION)
    try:
        pc.createDataChannel('chat')
        await pc.setLocalDescription(await pc.createOffer())

        assert pc.iceGatheringState == 'complete'
        assert 'a=candidate:' in local_description(pc).sdp
        assert 'a=end-of-candidates' in local_description(pc).sdp
    finally:
        await pc.close()


@pytest.mark.asyncio
async def test_messages_round_trip() -> None:
    """Text, binary and empty messages arrive as sent; a remote channel never emits open."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    try:
        channel = caller.createDataChannel('chat')
        opened = asyncio.Event()
        received: asyncio.Queue[str | bytes] = asyncio.Queue()
        remote_opens: list[RTCDataChannel] = []
        channel.on('open', opened.set)

        @channel.on('message')
        async def on_message(message: str | bytes) -> None:
            await received.put(message)

        @callee.on('datachannel')
        def echo(remote: RTCDataChannel) -> None:
            assert remote.readyState == 'open'
            remote.on('open', functools.partial(remote_opens.append, remote))
            remote.on('message', remote.send)

        await negotiate(caller, callee)
        await asyncio.wait_for(opened.wait(), TIMEOUT)
        for message in ['text', '', b'\x00binary', b'']:
            channel.send(message)
            echoed = await asyncio.wait_for(received.get(), TIMEOUT)
            assert type(echoed) is type(message)
            assert echoed == message
        assert remote_opens == []
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_handler_errors() -> None:
    """An exception of a message handler is emitted as 'error', and later handlers still run."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    errors: list[Exception] = []
    try:
        channel = caller.createDataChannel('chat')
        opened, received = asyncio.Event(), asyncio.Event()
        channel.on('open', opened.set)

        def fail(message: str | bytes) -> None:
            raise ValueError(message)

        def receive(_message: str | bytes) -> None:
            received.set()

        def send(remote: RTCDataChannel) -> None:
            remote.send('boom')

        channel.on('message', fail)
        channel.on('message', receive)
        channel.on('error', errors.append)
        callee.on('datachannel', send)

        await negotiate(caller, callee)
        await asyncio.wait_for(asyncio.gather(opened.wait(), received.wait()), TIMEOUT)

        assert [str(e) for e in errors] == ['boom']
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_state_events_and_transports() -> None:
    """State handlers take no arguments and see aiortc's states, and the transports follow."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    connection_states: list[str] = []
    ice_states: list[str] = []
    try:
        caller.on('connectionstatechange', lambda: connection_states.append(caller.connectionState))
        caller.on('iceconnectionstatechange', lambda: ice_states.append(caller.iceConnectionState))
        caller_connected, callee_connected = connected(caller), connected(callee)
        caller.createDataChannel('chat')
        sctp = caller.sctp
        assert sctp is not None
        assert sctp.state == 'new'
        assert sctp.transport is None

        await negotiate(caller, callee)
        await asyncio.wait_for(asyncio.gather(caller_connected.wait(), callee_connected.wait()), TIMEOUT)

        assert connection_states == ['connecting', 'connected']
        assert ice_states == ['checking', 'completed']
        dtls = sctp.transport
        assert dtls is not None
        assert dtls.state == 'connected'
        assert dtls.transport.state == 'completed'
        assert dtls.transport.iceGatherer.state == 'completed'
        assert len(dtls.getLocalParameters().fingerprints) == 1
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_close() -> None:
    """close() can be repeated and emits the closed states once, and the remote peer closes too."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    events: list[str] = []
    try:
        channel = caller.createDataChannel('chat')
        opened, closed, remote_closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
        channel.on('open', opened.set)
        channel.on('close', closed.set)
        await negotiate(caller, callee)
        await asyncio.wait_for(opened.wait(), TIMEOUT)

        def on_remote_change() -> None:
            if callee.connectionState == 'closed':
                remote_closed.set()

        callee.on('connectionstatechange', on_remote_change)
        for name in ('signalingstatechange', 'iceconnectionstatechange', 'connectionstatechange'):
            caller.on(name, functools.partial(events.append, name))

        await caller.close()
        await caller.close()

        assert events == ['signalingstatechange', 'iceconnectionstatechange', 'connectionstatechange']
        assert caller.signalingState == caller.iceConnectionState == caller.connectionState == 'closed'
        assert closed.is_set()
        await asyncio.wait_for(remote_closed.wait(), TIMEOUT)
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_overlapping_closes() -> None:
    """A second close() waits for the first, which ends signaling before stopping the tracks."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    try:
        track = VideoStreamTrack()
        caller.addTrack(track)
        ready = connected(caller)
        await negotiate(caller, callee)
        await asyncio.wait_for(ready.wait(), TIMEOUT)
        events: list[tuple[str, str]] = []
        caller.on('signalingstatechange', lambda: events.append((caller.signalingState, track.readyState)))
        caller.on('connectionstatechange', lambda: events.append((caller.connectionState, track.readyState)))

        first = asyncio.ensure_future(caller.close())
        await asyncio.sleep(0)
        await caller.close()

        assert first.done()
        assert events == [('closed', 'live'), ('closed', 'ended')]
    finally:
        await close(caller, callee)


def test_created_outside_a_loop() -> None:
    """A connection and its channel can be created, and handled, before a loop runs."""
    caller = RTCPeerConnection(CONFIGURATION)
    channel = caller.createDataChannel('chat')
    opens: list[str] = []
    channel.on('open', functools.partial(opens.append, 'open'))

    async def run() -> None:
        callee = RTCPeerConnection(CONFIGURATION)
        try:
            opened = asyncio.Event()
            channel.on('open', opened.set)
            await negotiate(caller, callee)
            await asyncio.wait_for(opened.wait(), TIMEOUT)
        finally:
            await close(caller, callee)

    asyncio.run(run())
    assert opens == ['open']


@pytest.mark.asyncio
async def test_lenient_candidates() -> None:
    """Candidates added before the remote description are kept, and unknown media sections are ignored."""
    caller, callee = RTCPeerConnection(CONFIGURATION), RTCPeerConnection(CONFIGURATION)
    try:
        callee_connected = connected(callee)
        caller.createDataChannel('chat')
        await caller.setLocalDescription(await caller.createOffer())
        lines = local_description(caller).sdp.splitlines(keepends=True)
        candidates = [line.strip()[len('a=candidate:') :] for line in lines if line.startswith('a=candidate:')]
        stripped = ''.join(line for line in lines if not line.startswith(('a=candidate:', 'a=end-of-candidates')))

        for sdp in candidates:
            candidate = candidate_from_sdp(sdp)
            candidate.sdpMLineIndex = 0
            await callee.addIceCandidate(candidate)
        await callee.addIceCandidate(None)
        await callee.setRemoteDescription(RTCSessionDescription(stripped, 'offer'))
        await callee.setLocalDescription(await callee.createAnswer())
        await caller.setRemoteDescription(local_description(callee))
        await asyncio.wait_for(callee_connected.wait(), TIMEOUT)

        unknown = candidate_from_sdp(candidates[0])
        unknown.sdpMid = 'unknown'
        await callee.addIceCandidate(unknown)
        unknown.sdpMid = None
        with pytest.raises(ValueError, match='sdpMid or sdpMLineIndex'):
            await callee.addIceCandidate(unknown)
    finally:
        await close(caller, callee)


@pytest.mark.asyncio
async def test_errors() -> None:
    """Bad options and calls raise aiortc's errors."""
    pc = RTCPeerConnection(CONFIGURATION)
    try:
        with pytest.raises(ValueError, match='both'):
            pc.createDataChannel('chat', maxPacketLifeTime=1, maxRetransmits=1)
        with pytest.raises(ValueError, match='negotiated'):
            pc.createDataChannel('chat', negotiated=True)
        with pytest.raises(ValueError, match='unsupported data type'):
            pc.createDataChannel('chat').send(mistyped(1))
        with pytest.raises(ValueError, match="got 'bogus'"):
            RTCSessionDescription('v=0\r\n', 'bogus')
        with pytest.raises(InvalidStateError, match='Cannot create answer in signaling state "stable"'):
            await pc.createAnswer()
        await pc.close()
        with pytest.raises(InvalidStateError, match='RTCPeerConnection is closed'):
            await pc.createOffer()
    finally:
        await pc.close()


def test_ortc_constructors_raise() -> None:
    """The transports and channels below ICE only come from a connection."""
    with pytest.raises(NotImplementedError):
        RTCIceGatherer()
    with pytest.raises(NotImplementedError):
        RTCDtlsTransport(mistyped(None), [])
    with pytest.raises(NotImplementedError):
        RTCSctpTransport(mistyped(None))
    with pytest.raises(NotImplementedError):
        RTCDataChannel(mistyped(None), mistyped(None))
    assert isinstance(candidate_from_sdp('1 1 udp 1 127.0.0.1 9 typ host'), RTCIceCandidate)
