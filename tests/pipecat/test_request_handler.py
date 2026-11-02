#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The HTTP signalling of clients, over the routes the framework's runner serves, against native peers."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI, Request

from tests.helpers import wait_until
from tests.pipecat._client import BrowserClient, wire_candidate
from webrtc.pipecat.request_handler import (
    ConnectionMode,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping, Sequence

    from webrtc.pipecat.connection import SmallWebRTCConnection

ROUTE = '/api/offer'


class Bot:
    """A handler behind the routes of the runner, and the connections it handed out."""

    def __init__(self, handler: SmallWebRTCRequestHandler) -> None:
        self.handler = handler
        self.connections: list[SmallWebRTCConnection] = []
        self.app = FastAPI()
        self.app.state.bot = self
        _ = self.app.post(ROUTE)(post_offer_route)
        _ = self.app.patch(ROUTE)(patch_candidates_route)

    async def started(self, connection: SmallWebRTCConnection) -> None:
        self.connections.append(connection)


# module functions: the framework caches what it learns of a route by the route, so a method would keep its bot
async def post_offer_route(body: SmallWebRTCRequest, request: Request) -> dict[str, str] | None:
    bot: Bot = request.app.state.bot
    return await bot.handler.handle_web_request(body, bot.started)


async def patch_candidates_route(body: SmallWebRTCPatchRequest, request: Request) -> dict[str, str]:
    bot: Bot = request.app.state.bot
    await bot.handler.handle_patch_request(body)
    return {'status': 'success'}


@contextlib.asynccontextmanager
async def serving(
    handler: SmallWebRTCRequestHandler | None = None, *clients: BrowserClient
) -> AsyncGenerator[tuple[Bot, httpx.AsyncClient], None]:
    """A bot and an HTTP client of it for the block; then the clients and every connection close."""
    bot = Bot(SmallWebRTCRequestHandler() if handler is None else handler)
    transport = httpx.ASGITransport(app=bot.app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url='http://bot') as http:
            yield bot, http
    finally:
        for client in clients:
            client.close()
        for connection in bot.connections:
            await connection.disconnect()


async def post_offer(http: httpx.AsyncClient, client: BrowserClient, **fields: object) -> httpx.Response:
    return await http.post(ROUTE, json={**await client.offer(), **fields})


async def patch_candidates(
    http: httpx.AsyncClient, pc_id: str, candidates: Sequence[Mapping[str, object]]
) -> httpx.Response:
    return await http.patch(ROUTE, json={'pc_id': pc_id, 'candidates': [dict(candidate) for candidate in candidates]})


async def connect(http: httpx.AsyncClient, client: BrowserClient) -> str:
    """Posts the client's offer, sends its candidates and end-of-candidates per mid; returns the ``pc_id``."""
    response = await post_offer(http, client)
    assert response.status_code == 200
    answer = response.json()
    await client.accept(answer)

    candidates = [wire_candidate(candidate) for candidate in await client.gathered_candidates()]
    mids = [transceiver.mid for transceiver in client.pc.get_transceivers()]
    ends = [{'candidate': '', 'sdp_mid': mid, 'sdp_mline_index': index} for index, mid in enumerate(mids)]
    response = await patch_candidates(http, answer['pc_id'], candidates + ends)
    assert response.status_code == 200
    assert response.json() == {'status': 'success'}

    await client.wait_connected()
    return answer['pc_id']


def remote_sdp(connection: SmallWebRTCConnection) -> str:
    description = connection.pc.remote_description
    assert description is not None
    return description.sdp


@pytest.mark.asyncio
async def test_an_offer_and_its_candidates_connect() -> None:
    client = BrowserClient()
    async with serving(None, client) as (bot, http):
        pc_id = await connect(http, client)

        [connection] = bot.connections
        assert connection.pc_id == pc_id
        await wait_until(lambda: connection.pc.connection_state == 'connected', 'the bot connecting')
        sdp = remote_sdp(connection)
        assert sdp.count('a=end-of-candidates') == len(client.pc.get_transceivers())
        assert re.search(r'^a=candidate:.* typ host', sdp, re.MULTILINE) is not None


@pytest.mark.asyncio
async def test_new_connections_take_the_port_range() -> None:
    client = BrowserClient()
    async with serving(SmallWebRTCRequestHandler(port_range=(40020, 40039), tcp_listen=True), client) as (bot, http):
        _ = await connect(http, client)

        [connection] = bot.connections
        assert connection.port_range == (40020, 40039)
        assert connection.tcp_listen
        answer = connection.get_answer()
        assert answer is not None
        ports = re.findall(r'^a=candidate:\S+ \d+ udp \d+ \S+ (\d+) typ', answer['sdp'], re.MULTILINE)
        assert len(ports) > 0
        assert all(40020 <= int(port) <= 40039 for port in ports)


@pytest.mark.asyncio
async def test_the_answer_has_the_wire_fields() -> None:
    client = BrowserClient()
    async with serving(None, client) as (bot, http):
        response = await post_offer(http, client, request_data={'user': 'one'})

        assert response.status_code == 200
        answer = response.json()
        assert set(answer) == {'sdp', 'type', 'pc_id'}
        assert answer['type'] == 'answer'
        assert answer['pc_id'] == bot.connections[0].pc_id
        fingerprints = set(re.findall(r'^a=fingerprint:(.*)$', answer['sdp'], re.MULTILINE))
        assert len(fingerprints) == 1
        assert next(iter(fingerprints)).startswith('sha-256 ')


def test_request_data_has_two_spellings() -> None:
    camel = SmallWebRTCRequest.from_dict({'sdp': 'v=0', 'type': 'offer', 'requestData': {'user': 'one'}})
    snake = SmallWebRTCRequest.from_dict({'sdp': 'v=0', 'type': 'offer', 'request_data': {'user': 'one'}})

    assert camel == snake == SmallWebRTCRequest(sdp='v=0', type='offer', request_data={'user': 'one'})


@pytest.mark.asyncio
async def test_candidates_of_an_unknown_connection_are_not_found() -> None:
    async with serving() as (_, http):
        response = await patch_candidates(http, 'unknown', [])

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_bad_candidates_are_skipped() -> None:
    client = BrowserClient()
    async with serving(None, client) as (bot, http):
        response = await post_offer(http, client)
        answer = response.json()
        await client.accept(answer)
        [candidate, *_] = await client.gathered_candidates()
        bad = [
            {'candidate': 'candidate:garbage', 'sdp_mid': '0', 'sdp_mline_index': 0},
            {**wire_candidate(candidate), 'sdp_mid': '9', 'sdp_mline_index': 9},
            {'candidate': '', 'sdp_mid': '9', 'sdp_mline_index': 9},
        ]
        without_prefix = {**wire_candidate(candidate), 'candidate': candidate.candidate.removeprefix('candidate:')}

        response = await patch_candidates(http, answer['pc_id'], [*bad, without_prefix])

        assert response.status_code == 200
        assert f' {candidate.port} typ ' in remote_sdp(bot.connections[0])


@pytest.mark.asyncio
async def test_an_offer_with_the_pc_id_renegotiates() -> None:
    client = BrowserClient()
    async with serving(None, client) as (bot, http):
        pc_id = await connect(http, client)

        response = await post_offer(http, client, pc_id=pc_id)

        assert response.status_code == 200
        assert response.json()['pc_id'] == pc_id
        assert len(bot.connections) == 1
        await client.accept(response.json())
        assert bot.connections[0].pc.connection_state == 'connected'


@pytest.mark.asyncio
async def test_a_restart_moves_the_connection_to_its_new_id() -> None:
    client = BrowserClient()
    restarted = BrowserClient()
    async with serving(None, client, restarted) as (bot, http):
        old_pc_id = await connect(http, client)

        response = await post_offer(http, restarted, pc_id=old_pc_id, restart_pc=True)
        assert response.status_code == 200
        new_pc_id = response.json()['pc_id']
        await restarted.accept(response.json())

        assert new_pc_id != old_pc_id
        assert len(bot.connections) == 1
        assert (await patch_candidates(http, old_pc_id, [])).status_code == 404
        assert (await patch_candidates(http, new_pc_id, [])).status_code == 200
        await restarted.wait_connected()


@pytest.mark.asyncio
async def test_one_connection_mode_refuses_other_offers() -> None:
    client = BrowserClient()
    other = BrowserClient()
    handler = SmallWebRTCRequestHandler(connection_mode=ConnectionMode.SINGLE)
    async with serving(handler, client, other) as (bot, http):
        pc_id = await connect(http, client)

        without_id = await post_offer(http, other)
        other_id = await post_offer(http, other, pc_id='another')
        own_id = await post_offer(http, client, pc_id=pc_id)

        assert without_id.status_code == 400
        assert other_id.status_code == 400
        assert own_id.status_code == 200
        assert len(bot.connections) == 1


@pytest.mark.asyncio
async def test_a_closed_connection_is_dropped() -> None:
    client = BrowserClient()
    async with serving(None, client) as (bot, http):
        pc_id = await connect(http, client)

        await bot.connections[0].disconnect()

        async def dropped() -> bool:
            return (await patch_candidates(http, pc_id, [])).status_code == 404

        await wait_until(dropped, 'the connection to be dropped')


@pytest.mark.asyncio
async def test_esp32_answers_have_only_the_host_candidates() -> None:
    client = BrowserClient()
    handler = SmallWebRTCRequestHandler(esp32_mode=True, host='127.0.0.1')
    async with serving(handler, client) as (_, http):
        response = await post_offer(http, client)

        candidates = re.findall(r'^a=candidate:.*$', response.json()['sdp'], re.MULTILINE)
        assert len(candidates) > 0
        assert all(' 127.0.0.1 ' in candidate for candidate in candidates)


@pytest.mark.asyncio
async def test_a_failing_callback_still_answers() -> None:
    client = BrowserClient()
    handler = SmallWebRTCRequestHandler()
    connections: list[SmallWebRTCConnection] = []

    async def fail(connection: SmallWebRTCConnection) -> None:  # ruff: ignore[unused-async]
        connections.append(connection)
        msg = 'the bot failed to start'
        raise RuntimeError(msg)

    try:
        offer = await client.offer()
        request = SmallWebRTCRequest(sdp=offer['sdp'], type=offer['type'])
        answer = await handler.handle_web_request(request, fail)

        assert answer is not None
        assert answer['pc_id'] == connections[0].pc_id
    finally:
        client.close()
        await handler.close()


@pytest.mark.asyncio
async def test_close_tells_every_client() -> None:
    clients = [BrowserClient(), BrowserClient()]
    handler = SmallWebRTCRequestHandler()
    async with serving(handler, *clients) as (bot, http):
        for client in clients:
            _ = await connect(http, client)
            await client.wait_channel_open()

        await handler.close()

        for client in clients:
            await wait_until(lambda client=client: len(client.messages) == 1, 'the bot leaving')
            assert client.messages == [{'type': 'signalling', 'message': {'type': 'peerLeft'}}]
        assert all(connection.pc.connection_state == 'closed' for connection in bot.connections)
