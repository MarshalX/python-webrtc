#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The HTTP signalling of clients: offers by POST, candidates by PATCH.

See https://wrtc.marshal.dev/guides/pipecat/.
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException
from loguru import logger
from pydantic import TypeAdapter
from typing_extensions import TypeGuard

import webrtc
from webrtc.pipecat.connection import IceServer, SmallWebRTCConnection

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@dataclass
class SmallWebRTCRequest:
    """The body of ``POST /api/offer``.

    Attributes:
        sdp: The offer's SDP.
        type: ``'offer'``.
        pc_id: From an earlier answer, for a later offer.
        restart_pc: Whether the client started over with a new connection.
        request_data: The application's data, for the bot.
    """

    sdp: str
    type: str
    pc_id: str | None = None
    restart_pc: bool | None = None
    request_data: object | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SmallWebRTCRequest:
        """Creates a request from its JSON body, with ``request_data`` or ``requestData``.

        Args:
            data: The body.

        Returns:
            The request.

        Raises:
            pydantic.ValidationError: If a field is missing or mistyped.
        """
        fields = dict(data)
        if 'requestData' in fields and 'request_data' not in fields:
            fields['request_data'] = fields.pop('requestData')
        request: SmallWebRTCRequest = TypeAdapter(cls).validate_python(fields)
        return request


@dataclass
class IceCandidate:
    """A candidate of the client.

    Attributes:
        candidate: Like ``'candidate:1 1 udp ...'``; an empty one ends its media section's candidates.
        sdp_mid: The media section's ``mid``.
        sdp_mline_index: The media section's index.
    """

    candidate: str
    sdp_mid: str
    sdp_mline_index: int


@dataclass
class SmallWebRTCPatchRequest:
    """The body of ``PATCH /api/offer``.

    Attributes:
        pc_id: From the answer.
        candidates: The candidates.
    """

    pc_id: str
    candidates: list[IceCandidate]


class ConnectionMode(enum.Enum):
    """How many connections a handler holds."""

    #: An offer without the current connection's ``pc_id`` is refused
    SINGLE = 'single'
    MULTIPLE = 'multiple'


def _candidate_init(candidate: IceCandidate) -> webrtc.RTCIceCandidateInit:
    """The candidate to add; the attribute's ``candidate:`` prefix may be left out."""
    attribute = candidate.candidate
    if attribute != '' and not attribute.startswith('candidate:'):
        attribute = f'candidate:{attribute}'
    return webrtc.RTCIceCandidateInit(
        candidate=attribute, sdp_mid=candidate.sdp_mid, sdp_m_line_index=candidate.sdp_mline_index
    )


def _given(pc_id: str | None) -> TypeGuard[str]:
    return pc_id is not None and pc_id != ''


async def _add_candidate(connection: SmallWebRTCConnection, candidate: IceCandidate) -> None:
    try:
        await connection.add_ice_candidate(_candidate_init(candidate))
    except (webrtc.OperationError, webrtc.InvalidStateError) as error:
        logger.warning('Skipping candidate {} of {}: {}', candidate, connection.pc_id, error)


class SmallWebRTCRequestHandler:
    """Answers the offers of clients and adds their candidates, one :obj:`SmallWebRTCConnection` per client.

    Args:
        ice_servers: The STUN and TURN servers of new connections.
        esp32_mode: Whether answers are rewritten for ESP32 clients.
        host: The address an ESP32 client reaches the bot at.
        connection_mode: Whether one connection is allowed or any number.
        port_range: The local ports of new connections, as :attr:`webrtc.RTCConfiguration.port_range`.
        tcp_listen: Whether new connections accept clients without UDP over TCP.
    """

    def __init__(
        self,
        ice_servers: list[IceServer] | None = None,
        esp32_mode: bool = False,
        host: str | None = None,
        connection_mode: ConnectionMode = ConnectionMode.MULTIPLE,
        *,
        port_range: tuple[int, int] | None = None,
        tcp_listen: bool = False,
    ) -> None:
        self._ice_servers = ice_servers
        self._port_range = port_range
        self._tcp_listen = tcp_listen
        self._esp32_mode = esp32_mode
        self._host = host
        self._connection_mode = connection_mode
        self._connections: dict[str, SmallWebRTCConnection] = {}

    def update_ice_servers(self, ice_servers: list[IceServer] | None = None) -> None:
        """Sets the STUN and TURN servers of new connections.

        Args:
            ice_servers: The servers.
        """
        self._ice_servers = ice_servers

    async def handle_web_request(
        self,
        request: SmallWebRTCRequest,
        webrtc_connection_callback: Callable[[SmallWebRTCConnection], Awaitable[None]],
    ) -> dict[str, str]:
        """Answers an offer.

        Args:
            request: The offer.
            webrtc_connection_callback: Starts the bot on a new connection, before its answer is returned.

        Returns:
            The answer's ``sdp`` and ``type``, and the ``pc_id``.

        Raises:
            fastapi.HTTPException: 400 if one connection is allowed and the offer is for another one.
        """
        try:
            return await self._answer(request, webrtc_connection_callback)
        except Exception as error:
            logger.error('Failed to answer an offer: {}', error)
            logger.debug('The offer: {}', request)
            raise

    async def handle_patch_request(self, request: SmallWebRTCPatchRequest) -> None:
        """Adds candidates of a client; one that can't be added is logged and skipped.

        Args:
            request: The candidates.

        Raises:
            fastapi.HTTPException: 404 if there's no connection with the ``pc_id``.
        """
        connection = self._connections.get(request.pc_id)
        if connection is None:
            raise HTTPException(status_code=404, detail='Peer connection not found')

        for candidate in request.candidates:
            await _add_candidate(connection, candidate)

    async def close(self) -> None:
        """Disconnects every connection."""
        connections = list(self._connections.values())
        self._connections.clear()
        await asyncio.gather(*(connection.disconnect() for connection in connections))

    async def _answer(
        self,
        request: SmallWebRTCRequest,
        webrtc_connection_callback: Callable[[SmallWebRTCConnection], Awaitable[None]],
    ) -> dict[str, str]:
        pc_id = request.pc_id
        self._check_single_connection(pc_id)

        connection = self._connections.get(pc_id) if _given(pc_id) else None
        if connection is not None:
            connection = await self._renegotiate(connection, request, webrtc_connection_callback)
        else:
            connection = await self._new_connection(request, webrtc_connection_callback)

        answer = connection.get_answer()
        if answer is None:
            msg = 'the connection made no answer'
            raise RuntimeError(msg)

        if self._esp32_mode:
            from pipecat.runner.utils import smallwebrtc_sdp_munging  # ruff: ignore[import-outside-top-level]

            answer['sdp'] = smallwebrtc_sdp_munging(answer['sdp'], self._host)

        # a restart gives the connection a new id
        if pc_id is not None and pc_id != connection.pc_id:
            _ = self._connections.pop(pc_id, None)
        if connection.pc.connection_state != webrtc.RTCPeerConnectionState.closed:
            self._connections[connection.pc_id] = connection
        return answer

    async def _renegotiate(
        self,
        connection: SmallWebRTCConnection,
        request: SmallWebRTCRequest,
        webrtc_connection_callback: Callable[[SmallWebRTCConnection], Awaitable[None]],
    ) -> SmallWebRTCConnection:
        """Returns the connection that answered, a new one after a late restart."""
        logger.info('Renegotiating connection {}', connection.pc_id)
        restart_pc = bool(request.restart_pc)
        try:
            await connection.renegotiate(sdp=request.sdp, type=request.type, restart_pc=restart_pc)
        except webrtc.InvalidStateError:
            if not connection.closed:
                raise
            # it closed while an earlier offer was answered: a restart starts over, another offer has no connection
            if not restart_pc:
                raise HTTPException(status_code=404, detail='Peer connection not found') from None
            return await self._new_connection(request, webrtc_connection_callback)
        return connection

    async def _new_connection(
        self,
        request: SmallWebRTCRequest,
        webrtc_connection_callback: Callable[[SmallWebRTCConnection], Awaitable[None]],
    ) -> SmallWebRTCConnection:
        connection = SmallWebRTCConnection(
            ice_servers=self._ice_servers, port_range=self._port_range, tcp_listen=self._tcp_listen
        )
        await connection.initialize(sdp=request.sdp, type=request.type)

        def forget(closed: SmallWebRTCConnection) -> None:
            logger.info('Connection {} closed', closed.pc_id)
            _ = self._connections.pop(closed.pc_id, None)

        connection.add_event_handler('closed', forget)

        try:
            await webrtc_connection_callback(connection)
        except Exception as error:  # ruff: ignore[blind-except]
            logger.error('The connection callback failed for {}: {}', connection.pc_id, error)
        return connection

    def _check_single_connection(self, pc_id: str | None) -> None:
        if self._connection_mode != ConnectionMode.SINGLE or len(self._connections) == 0:
            return

        current = next(iter(self._connections.values()))
        if not _given(pc_id):
            logger.warning('A connection exists already, refusing an offer without a pc_id')
            raise HTTPException(status_code=400, detail='Cannot create new connection with existing connection active')
        if pc_id != current.pc_id:
            logger.warning('Refusing an offer for {}, the connection is {}', pc_id, current.pc_id)
            raise HTTPException(status_code=400, detail='PC ID mismatch with existing connection')
