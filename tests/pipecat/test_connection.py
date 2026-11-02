#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The connection to one client: its answers, data channel, signalling and events, against native peers."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import re
from typing import TYPE_CHECKING

import pytest

import webrtc
from tests.helpers import QUIET_PERIOD, mistyped, wait_until, write_video, writing
from tests.pipecat._client import SENDRECV, BrowserClient, add_candidates, connect_client
from tests.pipecat._stun import MAPPED_ADDRESS, stun_server
from tests.timing import seconds
from webrtc.pipecat import connection as connection_module
from webrtc.pipecat.connection import IceServer, SmallWebRTCConnection, _covers  # ruff: ignore[import-private-name]

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

STATES = ('new', 'connecting', 'connected', 'disconnected', 'closed', 'failed')
EVENTS = ('app-message', 'track-started', 'track-ended', 'track-status', *STATES)
SHORT_GATHERING = 0.5
FRAME_SIZE = (320, 240)
FRAME = bytes(FRAME_SIZE[0] * FRAME_SIZE[1] * 3 // 2)


class Events:
    """The events a connection fires, in order, with their arguments."""

    def __init__(self, connection: SmallWebRTCConnection) -> None:
        self.fired: list[tuple[str, tuple[object, ...]]] = []
        for name in EVENTS:
            connection.add_event_handler(name, functools.partial(self._record, name))

    def _record(self, name: str, _connection: SmallWebRTCConnection, *args: object) -> None:
        self.fired.append((name, args))

    def count(self, name: str) -> int:
        return sum(fired == name for fired, _ in self.fired)

    def arguments(self, name: str) -> list[tuple[object, ...]]:
        return [args for fired, args in self.fired if fired == name]

    async def wait_for(self, name: str, count: int = 1) -> None:
        await wait_until(lambda: self.count(name) >= count, f'{count} {name} events')


@contextlib.asynccontextmanager
async def closing(connection: SmallWebRTCConnection, *clients: BrowserClient) -> AsyncGenerator[None, None]:
    """Closes the clients and the connection after the block."""
    try:
        yield
    finally:
        for client in clients:
            client.close()
        await connection.disconnect()


def candidate_types(sdp: str) -> list[str]:
    return re.findall(r'^a=candidate:.* typ (\w+)', sdp, re.MULTILINE)


def answer_sdp(connection: SmallWebRTCConnection) -> str:
    answer = connection.get_answer()
    assert answer is not None
    return answer['sdp']


async def answer_offer(connection: SmallWebRTCConnection, client: BrowserClient) -> float:
    """Answers the client's offer, and returns how long it took."""
    loop = asyncio.get_running_loop()
    offer = await client.offer()
    start = loop.time()
    await connection.initialize(sdp=offer['sdp'], type=offer['type'])
    return loop.time() - start


async def renegotiate(connection: SmallWebRTCConnection, client: BrowserClient, *, restart_pc: bool = False) -> None:
    offer = await client.offer()
    await connection.renegotiate(sdp=offer['sdp'], type=offer['type'], restart_pc=restart_pc)
    await client.accept(connection.get_answer())


@pytest.mark.asyncio
async def test_answers_without_servers_with_host_candidates() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await answer_offer(connection, client)

        answer = connection.get_answer()
        assert answer is not None
        assert answer['type'] == 'answer'
        assert answer['pc_id'] == connection.pc_id
        assert connection.pc_id.startswith('SmallWebRTCConnection#')
        assert 'host' in candidate_types(answer['sdp'])


@pytest.mark.asyncio
async def test_has_no_answer_before_an_offer() -> None:
    connection = SmallWebRTCConnection()
    async with closing(connection):
        assert connection.get_answer() is None


@pytest.mark.asyncio
async def test_answers_once_a_stun_server_maps_it() -> None:
    # the silent one keeps gathering from completing, whatever the interfaces
    async with stun_server() as server, stun_server(silent=True) as silent:
        connection = SmallWebRTCConnection([server.url, silent.url], ice_gathering_timeout_secs=seconds(10))
        client = BrowserClient()
        async with closing(connection, client):
            elapsed = await answer_offer(connection, client)

            sdp = answer_sdp(connection)
            assert {'host', 'srflx'} <= set(candidate_types(sdp))
            assert f' {MAPPED_ADDRESS} ' in sdp
            assert connection.pc.ice_gathering_state == 'gathering'
            assert elapsed < connection.ice_gathering_timeout_secs


@pytest.mark.asyncio
async def test_answers_after_the_cap_when_a_stun_server_is_silent() -> None:
    async with stun_server(silent=True) as server:
        connection = SmallWebRTCConnection([IceServer(urls=server.url)], ice_gathering_timeout_secs=SHORT_GATHERING)
        client = BrowserClient()
        async with closing(connection, client):
            elapsed = await answer_offer(connection, client)

            types = candidate_types(answer_sdp(connection))
            assert 'host' in types
            assert 'srflx' not in types
            assert server.requests > 0
            assert elapsed >= SHORT_GATHERING


#: candidate attributes, without the ``candidate:`` foundation
PRIVATE_HOST = '1 1 udp 2122260223 192.168.1.20 50000 typ host generation 0'
PUBLIC_HOST = '2 1 udp 2122260223 8.8.8.8 50001 typ host generation 0'
PUBLIC_IPV6_HOST = '3 1 udp 2122265343 2606:4700::1111 50002 typ host generation 0'
PUBLIC_TCP_HOST = '4 1 tcp 1518280447 8.8.8.8 9 typ host tcptype passive generation 0'
MDNS_HOST = '5 1 udp 2122260223 2d4bd8a3-84b4-4b9a-a1e8-2ac5c5a8a6e1.local 50003 typ host generation 0'
SRFLX = '6 1 udp 1686052607 8.8.4.4 50000 typ srflx raddr 192.168.1.20 rport 50000 generation 0'
#: the engine's TCP host candidates come after the UDP host ones of every interface
TCP_HOST = '7 1 tcp 1518280447 192.168.1.20 9 typ host tcptype passive generation 0'
IPV6_TCP_HOST = '8 1 tcp 1518285567 2606:4700::1111 9 typ host tcptype passive generation 0'


def sdp_with(*candidates: str) -> str:
    lines = ['v=0', 'm=audio 9 UDP/TLS/RTP/SAVPF 111', 'a=mid:0', *(f'a=candidate:{c}' for c in candidates)]
    return '\r\n'.join(lines) + '\r\n'


@pytest.mark.parametrize(
    'candidates',
    [[PRIVATE_HOST, TCP_HOST], [PUBLIC_TCP_HOST], [PUBLIC_IPV6_HOST, IPV6_TCP_HOST]],
    ids=['UDP and TCP', 'TCP only', 'IPv6 only'],
)
def test_host_candidates_are_all_there_once_tcp_ones_come(candidates: list[str]) -> None:
    assert _covers(sdp_with(*candidates), {'host'})


@pytest.mark.parametrize(
    'candidates', [[PRIVATE_HOST], [PRIVATE_HOST, PUBLIC_HOST], [PUBLIC_IPV6_HOST]], ids=['one', 'two', 'IPv6 only']
)
def test_udp_host_candidates_may_miss_an_interface(candidates: list[str]) -> None:
    assert not _covers(sdp_with(*candidates), {'host'})


@pytest.mark.parametrize(
    'candidates',
    [[PRIVATE_HOST, TCP_HOST, SRFLX], [PUBLIC_HOST, TCP_HOST]],
    ids=['private host and srflx', 'public host'],
)
def test_a_public_ipv4_host_stands_for_a_stun_candidate(candidates: list[str]) -> None:
    assert _covers(sdp_with(*candidates), {'host', 'srflx'})


@pytest.mark.parametrize(
    'candidates',
    [
        [PRIVATE_HOST, TCP_HOST],
        [PRIVATE_HOST, PUBLIC_IPV6_HOST, IPV6_TCP_HOST],
        [PUBLIC_TCP_HOST],
        [MDNS_HOST, TCP_HOST],
    ],
    ids=['private host', 'public IPv6 host', 'public TCP host', 'mDNS host'],
)
def test_other_hosts_stand_for_no_stun_candidate(candidates: list[str]) -> None:
    assert not _covers(sdp_with(*candidates), {'host', 'srflx'})


def test_a_public_ipv4_host_stands_for_no_relay_candidate() -> None:
    assert not _covers(sdp_with(PUBLIC_HOST, TCP_HOST), {'host', 'srflx', 'relay'})


@pytest.mark.asyncio
async def test_a_turn_server_needs_a_relay_candidate() -> None:
    async with stun_server() as stun, stun_server(silent=True) as turn:
        servers = [
            IceServer(urls=stun.url),
            IceServer(urls=f'turn:127.0.0.1:{turn.port}', username='user', credential='secret'),
        ]
        connection = SmallWebRTCConnection(servers, ice_gathering_timeout_secs=SHORT_GATHERING)
        client = BrowserClient()
        async with closing(connection, client):
            elapsed = await answer_offer(connection, client)

            types = candidate_types(answer_sdp(connection))
            assert 'srflx' in types
            assert 'relay' not in types
            assert elapsed >= SHORT_GATHERING


@pytest.mark.asyncio
async def test_ice_servers_are_urls_or_servers() -> None:
    connection = SmallWebRTCConnection(['stun:127.0.0.1:3478'])
    async with closing(connection):
        assert connection.ice_servers == [IceServer(urls='stun:127.0.0.1:3478')]

    with pytest.raises(TypeError, match='ice_servers'):
        _ = SmallWebRTCConnection(mistyped(['stun:127.0.0.1:3478', IceServer(urls='stun:127.0.0.1:3479')]))


@pytest.mark.asyncio
async def test_sends_on_the_microphone_and_the_camera_and_bundles() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)

        directions = [transceiver.current_direction for transceiver in client.pc.get_transceivers()]
        assert directions == ['sendrecv', 'sendrecv', 'sendonly']
        bot_directions = [transceiver.current_direction for transceiver in connection.pc.get_transceivers()]
        assert bot_directions == ['sendrecv', 'sendrecv', 'recvonly']
        transports = {transceiver.receiver.transport for transceiver in connection.pc.get_transceivers()}
        assert len(transports) == 1


@pytest.mark.asyncio
async def test_input_tracks_follow_the_transceivers() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)

        tracks = [connection.audio_input_track(), connection.video_input_track(), connection.screen_video_input_track()]
        receivers = [transceiver.receiver.track for transceiver in connection.pc.get_transceivers()]
        assert tracks == receivers
        assert [track.kind for track in receivers] == ['audio', 'video', 'video']


@pytest.mark.asyncio
async def test_an_audio_only_client_has_no_video_tracks() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient(video=False)
    async with closing(connection, client):
        await connect_client(connection, client)

        audio = connection.audio_input_track()
        assert audio is not None
        assert audio.kind == 'audio'
        assert connection.video_input_track() is None
        assert connection.screen_video_input_track() is None


@pytest.mark.asyncio
async def test_bot_tracks_reach_the_client() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)

        generator = webrtc.VideoTrackGenerator()
        await connection.replace_video_track(generator.track)
        camera = client.camera
        assert camera is not None
        reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(camera.receiver.track))
        async with writing(write_video, generator, FRAME, FRAME_SIZE):
            chunk = await asyncio.wait_for(reader.readable.get_reader().read(), seconds(10))

        assert isinstance(chunk.value, webrtc.VideoFrame)
        assert (chunk.value.display_width, chunk.value.display_height) == FRAME_SIZE
        chunk.value.close()
        generator.track.stop()


@pytest.mark.asyncio
async def test_a_screen_share_started_after_connecting_arrives() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)

        generator = webrtc.VideoTrackGenerator()
        assert client.screen is not None
        await client.screen.sender.replace_track(generator.track)
        screen = connection.screen_video_input_track()
        assert screen is not None
        reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(screen))
        async with writing(write_video, generator, FRAME, FRAME_SIZE):
            chunk = await asyncio.wait_for(reader.readable.get_reader().read(), seconds(10))

        assert isinstance(chunk.value, webrtc.VideoFrame)
        chunk.value.close()
        generator.track.stop()


@pytest.mark.asyncio
async def test_tracks_start_on_the_offer() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await answer_offer(connection, client)

        await events.wait_for('track-started', 3)
        tracks = [args[0] for args in events.arguments('track-started')]
        assert [track.kind for track in tracks if isinstance(track, webrtc.MediaStreamTrack)] == [
            'audio',
            'video',
            'video',
        ]


@pytest.mark.asyncio
async def test_connected_waits_for_connect() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await events.wait_for('connecting')
        await asyncio.sleep(QUIET_PERIOD)
        assert events.count('connected') == 0
        assert not connection.is_connected()

        await connection.connect()
        await events.wait_for('connected')
        assert connection.is_connected()

        await connection.connect()
        await events.wait_for('connected', 2)


@pytest.mark.asyncio
async def test_connected_fires_on_connecting_after_connect() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connection.connect()
        assert events.count('connected') == 0

        await connect_client(connection, client)
        await events.wait_for('connected')
        assert events.count('connected') == 1


@pytest.mark.asyncio
async def test_messages_wait_for_the_channel_in_order() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await answer_offer(connection, client)
        for index in range(3):
            connection.send_app_message({'type': 'early', 'index': index})

        await client.accept(connection.get_answer())
        await add_candidates(connection, client)
        await wait_until(lambda: len(client.messages) == 3, 'the early messages')
        connection.send_app_message({'type': 'late'})

        await wait_until(lambda: len(client.messages) == 4, 'the late message')
        assert client.messages == [
            {'type': 'early', 'index': 0},
            {'type': 'early', 'index': 1},
            {'type': 'early', 'index': 2},
            {'type': 'late'},
        ]


@pytest.mark.asyncio
async def test_messages_beyond_the_queue_are_dropped() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await answer_offer(connection, client)
        for index in range(connection_module.MAX_MESSAGE_QUEUE_SIZE + 10):
            connection.send_app_message(index)

        await client.accept(connection.get_answer())
        await add_candidates(connection, client)
        await wait_until(lambda: len(client.messages) == connection_module.MAX_MESSAGE_QUEUE_SIZE, 'the queue')
        await asyncio.sleep(QUIET_PERIOD)

        assert client.messages == list(range(connection_module.MAX_MESSAGE_QUEUE_SIZE))


@pytest.mark.asyncio
async def test_messages_are_dropped_once_no_channel_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection_module, 'DATA_CHANNEL_TIMEOUT_SECS', 0.2)
    connection = SmallWebRTCConnection()
    client = BrowserClient(channel=False)
    async with closing(connection, client):
        await connect_client(connection, client)
        connection.send_app_message('before the timeout')
        await asyncio.sleep(0.2 + QUIET_PERIOD)
        connection.send_app_message('after the timeout')

        client.open_channel()
        await renegotiate(connection, client)
        await client.wait_channel_open()
        await asyncio.sleep(QUIET_PERIOD)
        connection.send_app_message('once open')

        await wait_until(lambda: len(client.messages) >= 1, 'a message')
        assert client.messages == ['once open']


@pytest.mark.asyncio
async def test_app_messages_wait_for_connect() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await client.wait_channel_open()
        client.send({'label': 'rtvi-ai', 'type': 'client-ready'})
        await asyncio.sleep(QUIET_PERIOD)
        assert events.count('app-message') == 0

        await connection.connect()
        await events.wait_for('app-message')
        client.send({'label': 'rtvi-ai', 'type': 'action'})

        await events.wait_for('app-message', 2)
        assert events.arguments('app-message') == [
            ({'label': 'rtvi-ai', 'type': 'client-ready'},),
            ({'label': 'rtvi-ai', 'type': 'action'},),
        ]


@pytest.mark.asyncio
async def test_track_status_is_signalled() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await connection.connect()
        await client.wait_channel_open()

        client.send({'type': 'signalling', 'message': {'type': 'trackStatus', 'receiver_index': 1, 'enabled': False}})
        client.send({'type': 'signalling', 'message': {'type': 'trackStatus', 'receiver_index': 'one'}})
        client.send({'type': 'signalling', 'message': {'type': 'somethingNew'}})
        client.send_text('not JSON')
        client.send({'type': 'signalling', 'message': {'type': 'trackStatus', 'receiver_index': 1, 'enabled': True}})

        await events.wait_for('track-status', 2)
        await asyncio.sleep(QUIET_PERIOD)
        assert events.arguments('track-status') == [(1, False), (1, True)]
        assert events.count('app-message') == 0


@pytest.mark.asyncio
async def test_pings_keep_the_client_connected() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await connection.connect()
        await client.wait_channel_open()

        client.ping()
        await wait_until(connection.is_connected, 'the ping')
        await wait_until(lambda: not connection.is_connected(), 'the ping to expire', timeout=seconds(5))

        assert connection.pc.connection_state == 'connected'
        client.ping()
        await wait_until(connection.is_connected, 'the next ping')


@pytest.mark.asyncio
async def test_an_ice_restart_offer_counts_as_a_ping() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await connection.connect()
        await client.wait_channel_open()

        client.ping()
        await wait_until(connection.is_connected, 'the ping')
        await wait_until(lambda: not connection.is_connected(), 'the ping to expire', timeout=seconds(5))

        client.pc.restart_ice()
        await renegotiate(connection, client)

        assert connection.is_connected()


@pytest.mark.asyncio
async def test_disconnect_tells_the_client() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await client.wait_channel_open()

        await connection.disconnect()

        await wait_until(lambda: len(client.messages) == 1, 'the bot leaving')
        assert client.messages == [{'type': 'signalling', 'message': {'type': 'peerLeft'}}]
        await events.wait_for('closed')
        assert connection.pc.connection_state == 'closed'
        assert not connection.is_connected()

    await asyncio.sleep(QUIET_PERIOD)
    assert events.count('closed') == 1


@pytest.mark.asyncio
async def test_the_client_closing_closes_it() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await connection.connect()

        client.close()

        # long before the connection state notices
        await events.wait_for('closed')
        assert events.count('disconnected') == 0
        assert connection.pc.connection_state == 'closed'


@pytest.mark.asyncio
async def test_the_client_closing_its_channel_closes_it() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await client.wait_channel_open()

        client.close_channel()

        await events.wait_for('closed')
        assert connection.pc.connection_state == 'closed'


@pytest.mark.asyncio
async def test_asks_for_one_renegotiation_at_a_time() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await client.wait_channel_open()
        renegotiate_message = {'type': 'signalling', 'message': {'type': 'renegotiate'}}

        connection.ask_to_renegotiate()
        connection.ask_to_renegotiate()
        await wait_until(lambda: len(client.messages) >= 1, 'the request')
        await asyncio.sleep(QUIET_PERIOD)
        assert client.messages == [renegotiate_message]

        pc_id = connection.pc_id
        await renegotiate(connection, client)
        assert connection.pc_id == pc_id

        def asked_again() -> bool:
            connection.ask_to_renegotiate()
            return len(client.messages) == 2

        await wait_until(asked_again, 'the renegotiation to end')
        assert client.messages == [renegotiate_message, renegotiate_message]
        assert connection.pc.connection_state == 'connected'


@pytest.mark.asyncio
async def test_a_restart_replaces_the_peer_connection() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    restarted = BrowserClient()
    async with closing(connection, client, restarted):
        await connect_client(connection, client)
        await connection.connect()
        await events.wait_for('connected')
        old_pc, old_pc_id = connection.pc, connection.pc_id

        await renegotiate(connection, restarted, restart_pc=True)
        await add_candidates(connection, restarted)

        await events.wait_for('connected', 2)
        assert events.count('disconnected') == 1
        assert events.count('closed') == 0
        assert connection.pc_id != old_pc_id
        assert old_pc.connection_state == 'closed'
        assert connection.pc.connection_state == 'connected'


@pytest.mark.asyncio
async def test_closes_after_connecting_too_long() -> None:
    async with stun_server(silent=True) as silent:
        connection = SmallWebRTCConnection(connection_timeout_secs=1)
        events = Events(connection)
        client = BrowserClient()
        async with closing(connection, client):
            await answer_offer(connection, client)
            unreachable = f'candidate:1 1 udp 2122260223 127.0.0.1 {silent.port} typ host'
            await connection.add_ice_candidate(webrtc.RTCIceCandidateInit(candidate=unreachable, sdp_mid='0'))

            await events.wait_for('connecting')
            await events.wait_for('closed')
            assert connection.pc.connection_state == 'closed'
            assert events.count('connected') == 0


@pytest.mark.asyncio
async def test_closes_when_no_candidates_come() -> None:
    connection = SmallWebRTCConnection(connection_timeout_secs=1)
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        # the client never learns the answer, so neither side gets a candidate
        await answer_offer(connection, client)

        await events.wait_for('closed')
        assert connection.pc.connection_state == 'closed'
        assert events.count('connecting') == 0


@pytest.mark.asyncio
async def test_a_stun_server_mapping_to_the_own_address_adds_nothing() -> None:
    # the engine drops a server-reflexive candidate that's a host one; the silent server keeps gathering going
    async with stun_server(mirror=True) as mirror, stun_server(silent=True) as silent:
        connection = SmallWebRTCConnection([mirror.url, silent.url], ice_gathering_timeout_secs=SHORT_GATHERING)
        client = BrowserClient()
        async with closing(connection, client):
            elapsed = await answer_offer(connection, client)

            assert 'srflx' not in candidate_types(answer_sdp(connection))
            assert mirror.requests > 0
            assert elapsed >= SHORT_GATHERING


@pytest.mark.asyncio
async def test_closing_ends_the_wait_for_candidates() -> None:
    async with stun_server(silent=True) as silent:
        connection = SmallWebRTCConnection([silent.url], ice_gathering_timeout_secs=seconds(30))
        client = BrowserClient()
        async with closing(connection, client):
            answering = asyncio.ensure_future(answer_offer(connection, client))
            await wait_until(lambda: connection.pc.local_description is not None, 'the answer to wait')

            await connection.disconnect()

            _ = await asyncio.wait_for(answering, connection.ice_gathering_timeout_secs / 2)


@pytest.mark.asyncio
async def test_an_ice_restart_is_answered_with_candidates() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        first_ufrag = ice_ufrag(answer_sdp(connection))

        client.pc.restart_ice()
        await renegotiate(connection, client)

        sdp = answer_sdp(connection)
        assert ice_ufrag(sdp) != first_ufrag
        assert 'host' in candidate_types(sdp)


def ice_ufrag(sdp: str) -> str:
    match = re.search(r'^a=ice-ufrag:(\S+)', sdp, re.MULTILINE)
    assert match is not None
    return match.group(1)


@pytest.mark.asyncio
async def test_the_data_channel_takes_no_transceiver_index() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient(video=False)
    async with closing(connection, client):
        await connect_client(connection, client)

        # a camera added after the channel: its media section comes after the channel's
        camera = client.pc.add_transceiver('video', SENDRECV)
        await renegotiate(connection, client)

        [bot_camera] = [
            transceiver for transceiver in connection.pc.get_transceivers() if transceiver.mid == camera.mid
        ]
        assert connection.video_input_track() is bot_camera.receiver.track
        assert bot_camera.current_direction == 'sendrecv'


@pytest.mark.asyncio
async def test_no_state_fires_after_closed() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        await connection.connect()
        await events.wait_for('connected')

        # a state change the engine reported just before the close, which runs after it
        connection._on_connection_state(webrtc.Event('connectionstatechange'))
        await connection.disconnect()
        await asyncio.sleep(QUIET_PERIOD)

        names = [name for name, _ in events.fired]
        assert set(names[names.index('closed') + 1 :]).isdisjoint(STATES)
        assert events.count('connected') == 1


@pytest.mark.asyncio
async def test_an_offer_waiting_while_the_connection_closes_is_refused() -> None:
    connection = SmallWebRTCConnection()
    events = Events(connection)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)
        offer = await client.offer()

        # an earlier offer holds the lock while the connection closes
        async with connection._negotiation:
            waiting = asyncio.ensure_future(
                connection.renegotiate(sdp=offer['sdp'], type=offer['type'], restart_pc=True)
            )
            await asyncio.sleep(0)
            await connection.disconnect()

        with pytest.raises(webrtc.InvalidStateError):
            await waiting
        assert connection.closed
        assert events.count('closed') == 1
        assert events.count('disconnected') == 0


PORT_RANGE = (40000, 40019)


def udp_candidate_ports(sdp: str) -> list[int]:
    return [int(port) for port in re.findall(r'^a=candidate:\S+ \d+ udp \d+ \S+ (\d+) typ', sdp, re.MULTILINE)]


@pytest.mark.asyncio
async def test_candidates_come_from_the_port_range() -> None:
    connection = SmallWebRTCConnection(port_range=PORT_RANGE)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)

        ports = udp_candidate_ports(answer_sdp(connection))
        assert len(ports) > 0
        assert all(PORT_RANGE[0] <= port <= PORT_RANGE[1] for port in ports)
        assert connection.pc.connection_state == 'connected'


@pytest.mark.asyncio
async def test_a_listening_bot_answers_with_passive_tcp_candidates() -> None:
    connection = SmallWebRTCConnection(port_range=PORT_RANGE, tcp_listen=True)
    client = BrowserClient()
    async with closing(connection, client):
        await connect_client(connection, client)

        passive = re.findall(
            r'^a=candidate:\S+ \d+ tcp \d+ \S+ (\d+) typ host tcptype passive', answer_sdp(connection), re.MULTILINE
        )
        assert len(passive) > 0
        assert all(PORT_RANGE[0] <= int(port) <= PORT_RANGE[1] for port in passive)


@pytest.mark.asyncio
@pytest.mark.parametrize('port_range', [(5000, 4000), (-1, 10), (1, 70000)])
async def test_a_port_range_out_of_order_or_bounds_raises(  # ruff: ignore[unused-async]
    port_range: tuple[int, int],
) -> None:
    with pytest.raises(ValueError, match='port_range'):
        _ = SmallWebRTCConnection(port_range=port_range)


@pytest.mark.asyncio
async def test_overlapping_offers_are_answered_in_turn() -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    restarted = BrowserClient()
    async with closing(connection, client, restarted):
        await connect_client(connection, client)
        old_pc_id = connection.pc_id
        offer = await client.offer()
        restart_offer = await restarted.offer()

        async def answer_to(offer: dict[str, str], *, restart_pc: bool) -> dict[str, str] | None:
            await connection.renegotiate(sdp=offer['sdp'], type=offer['type'], restart_pc=restart_pc)
            return connection.get_answer()

        first, second = await asyncio.gather(
            answer_to(offer, restart_pc=False), answer_to(restart_offer, restart_pc=True)
        )

        assert first is not None
        assert second is not None
        assert first['pc_id'] == old_pc_id
        assert second['pc_id'] == connection.pc_id != old_pc_id
        await restarted.accept(second)
        await add_candidates(connection, restarted)
        await restarted.wait_connected()
