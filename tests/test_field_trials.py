#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Field trials, and the SNAP and SPED trials of WARP. Trials are fixed per process, so each test runs in its own."""

from __future__ import annotations

import asyncio
import multiprocessing
import multiprocessing.context
import os
import subprocess
import sys
from typing import TYPE_CHECKING, cast

import pytest

import webrtc
from tests.helpers import ROOT, UdpRelay, connect, isolated, wait_for_event, wait_until

if TYPE_CHECKING:
    from multiprocessing.connection import Connection, PipeConnection

    from typing_extensions import TypeAlias

    # what Pipe() returns, by platform
    Pipe: TypeAlias = Connection | PipeConnection

SNAP = {'WebRTC-Sctp-Snap': 'Enabled'}
SPED = {'WebRTC-IceHandshakeDtls': 'Enabled'}
WARP = SNAP | SPED


@isolated
def test_set_and_get() -> None:
    webrtc.field_trials['WebRTC-Sctp-Snap'] = 'Enabled'
    webrtc.field_trials.update([('WebRTC-IceHandshakeDtls', 'Enabled')], **{'WebRTC-Foo': 'Group1'})

    assert webrtc.field_trials['WebRTC-Sctp-Snap'] == 'Enabled'
    assert list(webrtc.field_trials) == ['WebRTC-Sctp-Snap', 'WebRTC-IceHandshakeDtls', 'WebRTC-Foo']
    assert webrtc.fieldTrials is webrtc.field_trials


@isolated
def test_delete() -> None:
    webrtc.field_trials.update(WARP)

    del webrtc.field_trials['WebRTC-Sctp-Snap']
    assert dict(webrtc.field_trials) == SPED
    assert webrtc.field_trials.pop('WebRTC-IceHandshakeDtls') == 'Enabled'
    assert len(webrtc.field_trials) == 0
    with pytest.raises(KeyError):
        del webrtc.field_trials['WebRTC-Sctp-Snap']


@isolated
def test_clear() -> None:
    webrtc.field_trials.update(WARP)
    webrtc.field_trials.clear()

    assert dict(webrtc.field_trials) == {}


@isolated
def test_str_and_repr() -> None:
    webrtc.field_trials.update(WARP)

    assert str(webrtc.field_trials) == 'WebRTC-Sctp-Snap/Enabled/WebRTC-IceHandshakeDtls/Enabled/'
    assert repr(webrtc.field_trials) == f'FieldTrials({WARP!r})'


@isolated
@pytest.mark.parametrize(
    ('name', 'group', 'error'),
    [
        (1, 'Enabled', TypeError),
        ('WebRTC-Foo', None, TypeError),
        ('', 'Enabled', ValueError),
        ('WebRTC-Foo', '', ValueError),
        ('WebRTC/Foo', 'Enabled', ValueError),
        ('WebRTC-Foo', 'Enabled/', ValueError),
    ],
)
def test_invalid_trial(name: str, group: str, error: type[Exception]) -> None:
    webrtc.field_trials.update(SNAP)

    with pytest.raises(error):
        webrtc.field_trials[name] = group
    with pytest.raises(error):
        webrtc.field_trials.update({'WebRTC-Bar': 'Enabled', name: group})
    assert dict(webrtc.field_trials) == SNAP


@isolated
def test_fixed_once_a_connection_is_created() -> None:
    webrtc.field_trials.update(SNAP)
    webrtc.RTCPeerConnection().close()

    with pytest.raises(webrtc.InvalidStateError):
        webrtc.field_trials.update(SPED)
    with pytest.raises(webrtc.InvalidStateError):
        webrtc.field_trials.clear()
    assert dict(webrtc.field_trials) == SNAP


@isolated
def test_fixed_once_an_ice_transport_is_created() -> None:
    webrtc.RTCIceTransport().stop()

    with pytest.raises(webrtc.InvalidStateError):
        webrtc.field_trials.update(SNAP)


@isolated
def _trials_at_start() -> dict[str, str]:
    return dict(webrtc.field_trials)


def test_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('WRTC_FIELD_TRIALS', 'WebRTC-Sctp-Snap/Enabled/WebRTC-Foo/Group1/')

    assert _trials_at_start() == {'WebRTC-Sctp-Snap': 'Enabled', 'WebRTC-Foo': 'Group1'}


@pytest.mark.parametrize(
    'value',
    ['WebRTC-Foo', 'WebRTC-Foo/Enabled', 'WebRTC-Foo/', '/Enabled/', 'WebRTC-Foo//', 'WebRTC-Foo/A/WebRTC-Foo/B/'],
)
def test_malformed_environment_variable(value: str) -> None:
    result = subprocess.run(
        [sys.executable, '-c', 'import webrtc'],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        env={**os.environ, 'WRTC_FIELD_TRIALS': value},
        check=False,
    )

    assert result.returncode != 0
    assert 'ValueError: Invalid WRTC_FIELD_TRIALS' in result.stderr


async def _tls_version() -> str | None:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    caller.create_data_channel('channel')
    await connect(caller, callee)
    stats = await caller.get_stats()
    caller.close()
    callee.close()
    return next(s.tls_version for s in stats.values() if isinstance(s, webrtc.RTCTransportStats))


@isolated
def test_dtls_13_by_default() -> None:
    # the version number of DTLS 1.3 (RFC 9147)
    assert asyncio.run(_tls_version()) == 'FEFC'


async def _offer() -> str:
    pc = webrtc.RTCPeerConnection()
    pc.create_data_channel('channel')
    await pc.set_local_description()
    assert pc.local_description is not None
    sdp = pc.local_description.sdp
    pc.close()
    return sdp


@isolated
def _offer_with(trials: dict[str, str]) -> str:
    webrtc.field_trials.update(trials)
    return asyncio.run(_offer())


@pytest.mark.parametrize(('trials', 'offered'), [({}, False), (SNAP, True)])
def test_snap_offers_the_sctp_init(trials: dict[str, str], *, offered: bool) -> None:
    assert ('a=sctp-init:' in _offer_with(trials)) is offered


async def _gathered(pc: webrtc.RTCPeerConnection) -> str:
    await wait_until(lambda: pc.ice_gathering_state == webrtc.RTCIceGatheringState.complete, 'ICE gathering')
    assert pc.local_description is not None
    return pc.local_description.sdp


async def _talk(pipe: Pipe, *, offerer: bool) -> None:
    """Negotiates through the pipe, then sends whether both channels opened and whether SNAP was negotiated."""
    pc = webrtc.RTCPeerConnection()
    channels = [pc.create_data_channel('negotiated', webrtc.RTCDataChannelInit(negotiated=True, id=4))]
    if offerer:
        channels.append(pc.create_data_channel('announced'))
        await pc.set_local_description()
        pipe.send(await _gathered(pc))
        answer: str = await asyncio.to_thread(pipe.recv)
        await pc.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', answer))
    else:
        announced = wait_for_event(pc, 'datachannel')
        offer: str = await asyncio.to_thread(pipe.recv)
        await pc.set_remote_description(webrtc.RTCSessionDescriptionInit('offer', offer))
        await pc.set_local_description()
        pipe.send(await _gathered(pc))
        channels.append(cast('webrtc.RTCDataChannelEvent', await announced).channel)

    for channel in channels:
        if channel.ready_state != webrtc.RTCDataChannelState.open:
            await wait_for_event(channel, 'open')
    assert pc.remote_description is not None
    pipe.send(('a=sctp-init:' in pc.remote_description.sdp, [c.ready_state for c in channels]))
    # stays connected until the other peer is done
    await asyncio.to_thread(pipe.recv)
    pc.close()


def _peer(pipe: Pipe, trials: dict[str, str], *, offerer: bool) -> None:
    webrtc.field_trials.update(trials)
    asyncio.run(_talk(pipe, offerer=offerer))


def _receive(pipe: Pipe) -> object:
    assert pipe.poll(30), 'the peer stopped answering'
    return pipe.recv()


def _interop(offerer_trials: dict[str, str], answerer_trials: dict[str, str]) -> list[object]:
    """Connects two peers with their own trials, each in a process of its own; returns what :func:`_talk` sent."""
    pipes: list[Pipe] = []
    peers: list[multiprocessing.context.SpawnProcess] = []
    for trials, offerer in ((offerer_trials, True), (answerer_trials, False)):
        ours, theirs = multiprocessing.Pipe()
        peer = multiprocessing.context.SpawnProcess(target=_peer, args=(theirs, trials), kwargs={'offerer': offerer})
        peer.start()
        pipes.append(ours)
        peers.append(peer)
    offerer_pipe, answerer_pipe = pipes
    try:
        answerer_pipe.send(_receive(offerer_pipe))
        offerer_pipe.send(_receive(answerer_pipe))
        results = [_receive(pipe) for pipe in pipes]
        for pipe in pipes:
            pipe.send('done')
        for peer in peers:
            peer.join(30)
            assert peer.exitcode == 0
    finally:
        for peer in peers:
            peer.kill()
    return results


@pytest.mark.parametrize('trials', [SNAP, SPED, WARP], ids=['snap', 'sped', 'warp'])
@pytest.mark.parametrize('side', ['both', 'offerer', 'answerer'])
def test_interop(trials: dict[str, str], side: str) -> None:
    offerer, answerer = _interop(trials if side != 'answerer' else {}, trials if side != 'offerer' else {})

    # a peer without a trial does the usual handshake instead, and the channels open either way
    snap = 'WebRTC-Sctp-Snap' in trials
    assert offerer == (snap and side == 'both', ['open', 'open'])
    assert answerer == (snap and side != 'answerer', ['open', 'open'])


async def _relayed_handshakes() -> set[int]:
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    channel = caller.create_data_channel('channel')
    relay = UdpRelay()
    opened = wait_for_event(channel, 'open')
    await relay.connect(caller, callee)
    await opened
    caller.close()
    callee.close()
    relay.close()
    return relay.handshakes


@isolated
def _handshakes_with(trials: dict[str, str]) -> set[int]:
    webrtc.field_trials.update(trials)
    return asyncio.run(_relayed_handshakes())


def test_sped_carries_the_handshake_in_stun() -> None:
    without = _handshakes_with({})

    assert without != set()
    # a handshake message rides in a STUN message instead of a packet of its own
    assert _handshakes_with(SPED) < without
