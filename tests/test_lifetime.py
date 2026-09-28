#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Ownership and lifetime of the native wrappers: no leaks, no use-after-free, stable identity and state."""

import gc
import threading
import time

import pytest

import webrtc
import wrtc
from tests.helpers import exchange_offer_answer


def collect():
    gc.collect()
    gc.collect()


def alive_factories():
    """Factories constructed and not destroyed yet. The last reference to one may be released
    on a helper thread (see CreateSessionDescriptionObserver), so wait for the count to settle"""
    collect()
    count = wrtc._alive_factories()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        time.sleep(0.05)
        current = wrtc._alive_factories()
        if current == count:
            break
        count = current
    return count


def peer_connection_cycle():
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.add_transceiver(webrtc.MediaType.video)
    pc.get_transceivers()
    pc.close()
    del pc
    collect()


@pytest.fixture
def isolated():
    """Nothing created by earlier tests may keep the default factory alive"""
    collect()
    yield
    collect()


pytestmark = pytest.mark.usefixtures('isolated')


def test_peer_connection_cycles_do_not_leak_factories():
    baseline = alive_factories()

    for _ in range(30):
        peer_connection_cycle()

    # previously every connection leaked its factory
    assert alive_factories() == baseline


def test_factories_return_to_baseline_when_everything_is_gone():
    baseline = alive_factories()

    pc = webrtc.RTCPeerConnection()
    stream = webrtc.get_user_media()
    source = webrtc.RTCAudioSource()
    track = source.create_track()
    pc.add_track(stream.get_tracks()[0])
    pc.add_track(track)

    # one factory for everything
    assert alive_factories() == (baseline or 1)

    pc.close()
    del pc, stream, source, track
    collect()

    assert alive_factories() == baseline


def test_everything_alive_shares_one_factory():
    stream = webrtc.get_user_media()
    source = webrtc.RTCAudioSource()
    source_track = source.create_track()
    before = alive_factories()

    connections = [webrtc.RTCPeerConnection() for _ in range(5)]
    assert alive_factories() == before

    for pc in connections:
        pc.add_track(stream.get_tracks()[0])
        pc.add_track(source_track)
        pc.close()


def test_closed_connection_keeps_its_factory_shared():
    pc = webrtc.RTCPeerConnection()
    receiver_track = pc.add_transceiver(webrtc.MediaType.audio).receiver.track
    pc.close()
    before = alive_factories()

    # the first factory is alive while the closed connection and its track are, so it must be reused
    pc2 = webrtc.RTCPeerConnection()
    assert alive_factories() == before
    pc2.close()

    assert receiver_track.ready_state == webrtc.MediaStreamTrackState.ended


def test_dropped_track_wrappers_are_not_notified():
    """Toggling a track notifies its observers, a dropped wrapper must not be one of them"""
    streams = [webrtc.get_user_media() for _ in range(50)]
    tracks = [stream.get_tracks()[0] for stream in streams]
    del tracks
    collect()

    for i in range(10):
        for stream in streams:
            stream.get_tracks()[0].enabled = bool(i % 2)


def test_destroyed_track_wrapper_is_not_notified():
    """A track wrapper dies while libwebrtc keeps the track alive in a sender"""
    pc = webrtc.RTCPeerConnection()
    stream = webrtc.get_user_media()
    pc.add_track(stream.get_tracks()[0])
    del stream
    collect()

    for i in range(10):
        pc.get_senders()[0].track.enabled = bool(i % 2)
        collect()

    pc.close()


def test_track_state_survives_gc():
    stream = webrtc.get_user_media()
    track = stream.get_tracks()[0]
    track.enabled = False
    track.stop()
    del track
    collect()

    track = stream.get_tracks()[0]
    assert track.ready_state == webrtc.MediaStreamTrackState.ended
    assert track.enabled is False


def test_track_state_survives_gc_of_all_python_references():
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.get_transceivers()[0].receiver.track.stop()
    collect()

    assert pc.get_transceivers()[0].receiver.track.ready_state == webrtc.MediaStreamTrackState.ended
    pc.close()


def test_transceiver_identity():
    pc = webrtc.RTCPeerConnection()
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    collect()

    assert pc.get_transceivers()[0] == transceiver
    assert pc.get_transceivers()[0]._native_obj is transceiver._native_obj
    assert pc.get_senders()[0]._native_obj is transceiver.sender._native_obj
    assert pc.get_receivers()[0]._native_obj is transceiver.receiver._native_obj
    assert transceiver.receiver.track._native_obj is transceiver.receiver.track._native_obj
    pc.close()


def test_sender_identity(audio_stream):
    pc = webrtc.RTCPeerConnection()
    track = audio_stream.get_tracks()[0]
    sender = pc.add_track(track)
    collect()

    assert pc.get_senders()[0] == sender
    assert sender.track._native_obj is track._native_obj
    pc.close()


def test_drop_and_refetch_before_negotiation():
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.add_transceiver(webrtc.MediaType.video)

    for _ in range(50):
        for transceiver in pc.get_transceivers():
            _ = transceiver.sender.track, transceiver.sender.transport
            _ = transceiver.receiver.track.ready_state, transceiver.receiver.transport
        for sender in pc.get_senders():
            _ = sender.track
        for receiver in pc.get_receivers():
            _ = receiver.track.enabled
        del transceiver, sender, receiver, _
        collect()

    pc.close()


@pytest.mark.asyncio
async def test_drop_and_refetch_transports(caller, callee, audio_stream):
    caller.add_track(audio_stream.get_tracks()[0])
    await exchange_offer_answer(caller, callee)

    transport = caller.get_senders()[0].transport
    assert transport is not None
    ice_transport = transport.ice_transport
    del transport, ice_transport

    for _ in range(50):
        for pc in (caller, callee):
            for transceiver in pc.get_transceivers():
                for transport in (transceiver.sender.transport, transceiver.receiver.transport):
                    if transport is not None:
                        _ = transport.state, transport.ice_transport.state, transport.ice_transport.gathering_state
        del pc, transceiver, transport
        collect()

    assert caller.get_senders()[0].transport == caller.get_transceivers()[0].receiver.transport
    assert caller.get_senders()[0].transport.ice_transport == caller.get_receivers()[0].transport.ice_transport


@pytest.mark.asyncio
async def test_transports_outlive_closed_connection(caller, callee, audio_stream):
    caller.add_track(audio_stream.get_tracks()[0])
    await exchange_offer_answer(caller, callee)

    transport = caller.get_senders()[0].transport
    ice_transport = transport.ice_transport
    caller.close()
    callee.close()
    collect()

    assert transport.state == webrtc.DtlsTransportState.closed
    assert ice_transport.state == webrtc.RTCIceTransportState.closed


def test_getters_while_connection_is_closed_and_dropped(audio_stream):
    track = audio_stream.get_tracks()[0]

    for _ in range(20):
        pc = webrtc.RTCPeerConnection()
        pc.add_track(track)
        pc.add_transceiver(webrtc.MediaType.video)
        stop = threading.Event()
        errors = []

        def read(pc=pc, stop=stop, errors=errors):
            try:
                while not stop.is_set():
                    for transceiver in pc.get_transceivers():
                        _ = transceiver.direction, transceiver.receiver.track.ready_state, transceiver.sender.track
                    for sender in pc.get_senders():
                        _ = sender.track, sender.transport
                    for receiver in pc.get_receivers():
                        _ = receiver.track.enabled, receiver.transport
                    _ = pc.connection_state, pc.signaling_state
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        readers = [threading.Thread(target=read) for _ in range(4)]
        for reader in readers:
            reader.start()

        pc.close()
        del pc
        collect()
        stop.set()

        for reader in readers:
            reader.join(timeout=10)
            assert not reader.is_alive(), 'reader thread is stuck'
        assert not errors, errors
        collect()
