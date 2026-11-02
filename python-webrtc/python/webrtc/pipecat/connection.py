#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The peer connection to one client and the signalling on its data channel.

See https://wrtc.marshal.dev/guides/pipecat/.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import re
import time
import uuid
from typing import TYPE_CHECKING, Literal, cast

from loguru import logger
from pipecat.utils.base_object import BaseObject
from pydantic import BaseModel, ValidationError
from typing_extensions import TypeGuard

import webrtc

if TYPE_CHECKING:
    from collections.abc import Coroutine

SIGNALLING_TYPE = 'signalling'
AUDIO_TRANSCEIVER_INDEX = 0
VIDEO_TRANSCEIVER_INDEX = 1
SCREEN_VIDEO_TRANSCEIVER_INDEX = 2

MAX_MESSAGE_QUEUE_SIZE = 50
DATA_CHANNEL_TIMEOUT_SECS = 10

_PING_TIMEOUT_SECS = 3
# Pipecat's JavaScript client reconnects 5 s after its own disconnect and may gather for 2 s first
_DISCONNECTED_CLIENT_SECS = 8
_RENEGOTIATION_SECS = 2
_CANDIDATE = re.compile(r'^a=candidate:\S+ \d+ (\S+) \d+ (\S+) \d+ typ (\w+)', re.MULTILINE)
_MID = re.compile(r'^a=mid:(\S+)', re.MULTILINE)

IceServer = webrtc.RTCIceServer


class TrackStatusMessage(BaseModel):
    """The client turned one of its sources on or off."""

    type: Literal['trackStatus']
    receiver_index: int
    enabled: bool


class RenegotiateMessage(BaseModel):
    """Asks the client for a new offer."""

    type: Literal['renegotiate'] = 'renegotiate'


class PeerLeftMessage(BaseModel):
    """Tells the client the bot left."""

    type: Literal['peerLeft'] = 'peerLeft'


def _ice_servers_of(ice_servers: list[str] | list[IceServer] | None) -> list[IceServer]:
    if ice_servers is None:
        return []
    if all(isinstance(server, IceServer) for server in ice_servers):
        return [server for server in ice_servers if isinstance(server, IceServer)]
    if all(isinstance(server, str) for server in ice_servers):
        return [IceServer(urls=server) for server in ice_servers if isinstance(server, str)]

    msg = 'ice_servers must be a list of URLs or a list of IceServer'
    raise TypeError(msg)


def _schemes_of(ice_servers: list[IceServer]) -> set[str]:
    schemes: set[str] = set()
    for server in ice_servers:
        urls = [server.urls] if isinstance(server.urls, str) else server.urls
        schemes.update(url.split(':', 1)[0].lower() for url in urls)
    return schemes


def _needed_candidate_types(ice_servers: list[IceServer]) -> set[str]:
    schemes = _schemes_of(ice_servers)
    needed = {'host'}
    if not schemes.isdisjoint({'stun', 'stuns'}):
        needed.add('srflx')
    if not schemes.isdisjoint({'turn', 'turns'}):
        needed.add('relay')
    return needed


def _covers(sdp: str, needed: set[str]) -> bool:
    gathered: set[str] = set()
    hosts_gathered = False
    candidates: list[tuple[str, str, str]] = _CANDIDATE.findall(sdp)
    for transport, address, candidate_type in candidates:
        gathered.add(candidate_type)
        is_udp = transport.lower() == 'udp'
        # the engine gathers UDP on every interface before TCP
        if candidate_type == 'host' and not is_udp:
            hosts_gathered = True
        # the engine drops a srflx candidate equal to a public host one
        if candidate_type == 'host' and is_udp and _is_public_ipv4(address):
            gathered.add('srflx')
    return hosts_gathered and needed <= gathered


def _is_public_ipv4(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return isinstance(ip, ipaddress.IPv4Address) and ip.is_global


def _media_mids(sdp: str) -> list[str | None]:
    # the data channel's section has no transceiver
    mids: list[str | None] = []
    for section in sdp.split('\nm=')[1:]:
        if section.startswith(('audio ', 'video ')):
            mid = _MID.search(section)
            mids.append(None if mid is None else mid.group(1))
    return mids


def _is_signalling(message: object) -> TypeGuard[dict[str, object]]:
    return isinstance(message, dict) and message.get('type') == SIGNALLING_TYPE


class SmallWebRTCConnection(BaseObject):
    """The peer connection to one client, which answers its offers and carries its signalling.

    The answer carries all of the bot's candidates, so it waits for the ones the configuration needs, at most
    ``ice_gathering_timeout_secs``.

    Events, added with ``event_handler(name)``: ``app-message``, ``track-started``, ``track-ended``,
    ``track-status`` and the states ``new``, ``connecting``, ``connected``, ``disconnected``, ``failed`` and
    ``closed``. ``connected`` waits for :meth:`connect`. Nothing fires after ``closed``.

    Args:
        ice_servers: STUN and TURN servers, as URLs or :obj:`IceServer`.
        connection_timeout_secs: How long after the answer to wait for connecting before closing.
        ice_gathering_timeout_secs: How long an answer waits for candidates at most.
        port_range: The local ports to gather on, as :attr:`webrtc.RTCConfiguration.port_range`.
        tcp_listen: Whether clients without UDP can connect over TCP, as :attr:`webrtc.RTCConfiguration.tcp_listen`.

    Raises:
        TypeError: If ``ice_servers`` mixes URLs and :obj:`IceServer`.
        ValueError: If ``port_range`` isn't two ports from low to high.
        RuntimeError: If no event loop is running.
    """

    # replaced on restart_pc
    _pc: webrtc.RTCPeerConnection
    _pc_id: str
    _answer: webrtc.RTCSessionDescription | None
    _closed: bool
    _gathering_progress: asyncio.Event
    _transports: list[webrtc.RTCDtlsTransport]
    _data_channel: webrtc.RTCDataChannel | None
    _data_channel_enabled: bool
    _outgoing_messages: list[str]
    _pending_app_messages: list[object]
    _last_ping: float | None
    _renegotiation_in_progress: bool
    _connecting_timeout: asyncio.Task[None] | None
    _data_channel_timeout: asyncio.Task[None] | None
    _renegotiation_end: asyncio.Task[None] | None
    _pings_stopped_timeout: asyncio.Task[None] | None

    def __init__(
        self,
        ice_servers: list[str] | list[IceServer] | None = None,
        connection_timeout_secs: int = 60,
        *,
        ice_gathering_timeout_secs: float = 5.0,
        port_range: tuple[int, int] | None = None,
        tcp_listen: bool = False,
    ) -> None:
        super().__init__()
        self.ice_servers = _ice_servers_of(ice_servers)
        self.connection_timeout_secs = connection_timeout_secs
        self.ice_gathering_timeout_secs = ice_gathering_timeout_secs
        self.port_range = port_range
        self.tcp_listen = tcp_listen

        self._needed_candidate_types = _needed_candidate_types(self.ice_servers)
        self._connect_invoked = False
        self._tasks: set[asyncio.Task[None]] = set()
        # a restart mustn't replace the connection under another answer
        self._negotiation = asyncio.Lock()
        self._initialize()

        for name in ('app-message', 'track-started', 'track-ended', 'track-status'):
            self._register_event_handler(name)
        for state in ('new', 'connecting', 'connected', 'disconnected', 'closed', 'failed'):
            self._register_event_handler(state)

    def _initialize(self) -> None:
        configuration = webrtc.RTCConfiguration(
            ice_servers=self.ice_servers,
            bundle_policy=webrtc.RTCBundlePolicy.max_bundle,
            port_range=self.port_range,
            tcp_listen=self.tcp_listen,
        )
        self._pc = webrtc.RTCPeerConnection(configuration)
        self._pc_id = f'{self.name}-{uuid.uuid4().hex}'
        self._answer = None
        self._closed = False

        self._gathering_progress = asyncio.Event()
        self._transports = []
        self._data_channel = None
        self._data_channel_enabled = True
        self._outgoing_messages = []
        self._pending_app_messages = []
        self._last_ping = None
        self._renegotiation_in_progress = False

        self._connecting_timeout = None
        self._data_channel_timeout = None
        self._renegotiation_end = None
        self._pings_stopped_timeout = None

        _ = self._pc.on('connectionstatechange', self._on_connection_state)
        _ = self._pc.on('icecandidate', self._on_gathering_progress)
        _ = self._pc.on('icegatheringstatechange', self._on_gathering_progress)
        _ = self._pc.on('track', self._on_track)
        _ = self._pc.on('datachannel', self._on_data_channel)

    @property
    def pc(self) -> webrtc.RTCPeerConnection:
        """The current peer connection, which ``restart_pc`` replaces."""
        return self._pc

    @property
    def pc_id(self) -> str:
        """The id of the current peer connection."""
        return self._pc_id

    @property
    def closed(self) -> bool:
        """Whether the connection is closed."""
        return self._closed

    async def initialize(self, sdp: str, type: str) -> None:
        """Answers the client's first offer.

        Args:
            sdp: The SDP of the offer.
            type: ``'offer'``.
        """
        async with self._negotiation:
            await self._create_answer(sdp, type)

    async def connect(self) -> None:
        """Marks the bot ready, so ``connected`` fires once the client is connected."""
        self._connect_invoked = True
        if self.is_connected():
            await self._announce_connected()

    async def renegotiate(self, sdp: str, type: str, restart_pc: bool = False) -> None:
        """Answers a later offer of the client.

        Args:
            sdp: The SDP of the offer.
            type: ``'offer'``.
            restart_pc: Whether to replace the peer connection with a new one, with a new :attr:`pc_id`.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
        """
        # an offer proves a disconnected client is alive
        self._cancel(self._pings_stopped_timeout)
        try:
            async with self._negotiation:
                if self._closed:
                    msg = 'The connection is closed'
                    raise webrtc.InvalidStateError(msg)
                logger.debug('Renegotiating {}', self._pc_id)
                if restart_pc:
                    await self._call_event_handler('disconnected')
                    self._close_peer_connection()
                    self._initialize()

                await self._create_answer(sdp, type)
                # after an ICE restart, the next ping may wait for an SCTP retransmit
                if self._last_ping is not None:
                    self._last_ping = time.monotonic()
                self._cancel(self._renegotiation_end)
                self._renegotiation_end = self._spawn(self._end_renegotiation())
        finally:
            self._watch_for_pings_stopped()

    async def disconnect(self) -> None:
        """Tells the client the bot left, and closes the connection."""
        self.send_app_message({'type': SIGNALLING_TYPE, 'message': PeerLeftMessage().model_dump()})
        await self._close()

    def get_answer(self) -> dict[str, str] | None:
        """The ``sdp``, ``type`` and ``pc_id`` of the last answer, or :obj:`None` before the first offer."""
        if self._answer is None:
            return None
        return {'sdp': self._answer.sdp, 'type': str(self._answer.type), 'pc_id': self._pc_id}

    async def add_ice_candidate(self, candidate: webrtc.RTCIceCandidateInit | None) -> None:
        """Adds a candidate of the client; an empty one or :obj:`None` ends its candidates.

        Raises:
            webrtc.OperationError: If the candidate can't be parsed or matches no media section.
            webrtc.InvalidStateError: If the connection is closed.
        """
        logger.debug('Adding remote candidate {}', candidate)
        await self._pc.add_ice_candidate(candidate)
        # a candidate proves a disconnected client is alive
        self._watch_for_pings_stopped()

    def send_app_message(self, message: object) -> None:
        """Sends a message as JSON over the data channel.

        Messages wait for the channel to open, and are dropped if it doesn't open within
        :data:`DATA_CHANNEL_TIMEOUT_SECS` of connecting, since the client may have none.
        """
        text = json.dumps(message)
        channel = self._data_channel
        if channel is not None and channel.ready_state == webrtc.RTCDataChannelState.open:
            channel.send(text)
        elif self._closed or not self._data_channel_enabled:
            logger.trace('No data channel, dropping a message')
        elif len(self._outgoing_messages) < MAX_MESSAGE_QUEUE_SIZE:
            self._outgoing_messages.append(text)
        else:
            logger.warning('{} messages wait for the data channel already, dropping one', MAX_MESSAGE_QUEUE_SIZE)

    def ask_to_renegotiate(self) -> None:
        """Asks the client for a new offer, unless a renegotiation is in progress."""
        if self._renegotiation_in_progress:
            return

        self._renegotiation_in_progress = True
        self.send_app_message({'type': SIGNALLING_TYPE, 'message': RenegotiateMessage().model_dump()})

    def is_connected(self) -> bool:
        """Whether the bot is ready and the client pinged or offered recently."""
        if not self._connect_invoked or self._closed:
            return False
        if self._last_ping is None:
            return self._pc.connection_state == webrtc.RTCPeerConnectionState.connected
        return self._pinged_recently()

    def _pinged_recently(self) -> bool:
        return self._last_ping is not None and time.monotonic() - self._last_ping < _PING_TIMEOUT_SECS

    def audio_input_track(self) -> webrtc.MediaStreamTrack | None:
        """The track of the client's microphone, or :obj:`None` if it offered none."""
        return self._input_track(AUDIO_TRANSCEIVER_INDEX, 'audio')

    def video_input_track(self) -> webrtc.MediaStreamTrack | None:
        """The track of the client's camera, or :obj:`None` if it offered none."""
        return self._input_track(VIDEO_TRANSCEIVER_INDEX, 'video')

    def screen_video_input_track(self) -> webrtc.MediaStreamTrack | None:
        """The track of the client's screen share, or :obj:`None` if it offered none."""
        return self._input_track(SCREEN_VIDEO_TRANSCEIVER_INDEX, 'video')

    async def replace_audio_track(self, track: webrtc.MediaStreamTrack | None) -> None:
        """Sends a track as the bot's audio, or nothing with :obj:`None`."""
        await self._replace_track(AUDIO_TRANSCEIVER_INDEX, track)

    async def replace_video_track(self, track: webrtc.MediaStreamTrack | None) -> None:
        """Sends a track as the bot's video, or nothing with :obj:`None`."""
        await self._replace_track(VIDEO_TRANSCEIVER_INDEX, track)

    async def replace_screen_video_track(self, track: webrtc.MediaStreamTrack | None) -> None:
        """Sets the track of the screen share's transceiver, which is receive-only."""
        await self._replace_track(SCREEN_VIDEO_TRANSCEIVER_INDEX, track)

    async def _create_answer(self, sdp: str, type: str) -> None:
        await self._pc.set_remote_description(webrtc.RTCSessionDescriptionInit(type=webrtc.RTCSdpType(type), sdp=sdp))
        self._set_directions()

        await self._pc.set_local_description()
        self._watch_transports()
        # from the answer: a client that never sends a candidate leaves the state new
        if self._pc.connection_state == webrtc.RTCPeerConnectionState.new:
            self._start_connecting_timeout()

        await self._wait_for_candidates()
        self._answer = self._pc.local_description

    def _set_directions(self) -> None:
        for index, transceiver in enumerate(self._transceivers()):
            if transceiver is None:
                continue
            if index <= VIDEO_TRANSCEIVER_INDEX:
                transceiver.direction = webrtc.RTCRtpTransceiverDirection.sendrecv
            else:
                transceiver.direction = webrtc.RTCRtpTransceiverDirection.recvonly

    def _watch_transports(self) -> None:
        # a closed DTLS transport tells the client left long before ICE does
        transports = [transceiver.receiver.transport for transceiver in self._pc.get_transceivers()]
        sctp = self._pc.sctp
        if sctp is not None:
            transports.append(sctp.transport)

        for transport in transports:
            if transport is not None and transport not in self._transports:
                _ = transport.on('statechange', self._on_transport_state)
                self._transports.append(transport)

    async def _wait_for_candidates(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.ice_gathering_timeout_secs
        while not self._answer_is_ready():
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.debug('Answering with the candidates gathered in {} s', self.ice_gathering_timeout_secs)
                return

            self._gathering_progress.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._gathering_progress.wait(), remaining)

    def _answer_is_ready(self) -> bool:
        if self._closed:
            return True
        description = self._pc.local_description
        if description is None:
            return False

        # after an ICE restart it still reads complete from the round before
        if self._pc.ice_gathering_state == webrtc.RTCIceGatheringState.complete:
            return _CANDIDATE.search(description.sdp) is not None
        return _covers(description.sdp, self._needed_candidate_types)

    def _transceivers(self) -> list[webrtc.RTCRtpTransceiver | None]:
        # by the offer's sections, since get_transceivers() drops stopped ones and shifts the indexes
        description = self._pc.remote_description
        if description is None:
            return []
        transceivers = self._pc.get_transceivers()
        by_mid = {transceiver.mid: transceiver for transceiver in transceivers if not transceiver.stopped}
        return [by_mid.get(mid) if mid is not None else None for mid in _media_mids(description.sdp)]

    def _transceiver_at(self, index: int) -> webrtc.RTCRtpTransceiver | None:
        transceivers = self._transceivers()
        return transceivers[index] if index < len(transceivers) else None

    def _input_track(self, index: int, kind: str) -> webrtc.MediaStreamTrack | None:
        transceiver = self._transceiver_at(index)
        if transceiver is None or transceiver.receiver.track.kind != kind:
            logger.warning('The client offered no {} transceiver at {}', kind, index)
            return None
        return transceiver.receiver.track

    async def _replace_track(self, index: int, track: webrtc.MediaStreamTrack | None) -> None:
        if self._closed:
            logger.debug('Connection {} is closed, not sending {}', self._pc_id, track)
            return
        transceiver = self._transceiver_at(index)
        if transceiver is None:
            logger.warning('The client offered no transceiver at {}, not sending {}', index, track)
            return

        pc = self._pc
        try:
            await transceiver.sender.replace_track(track)
        except webrtc.InvalidStateError:
            # closed or replaced while awaiting
            if pc is self._pc and not self._closed:
                raise

    async def _announce_connected(self) -> None:
        await self._call_event_handler('connected')

        pending = self._pending_app_messages
        self._pending_app_messages = []
        for message in pending:
            await self._call_event_handler('app-message', message)

    def _on_connection_state(self, _event: webrtc.Event) -> None:
        # read now: a later state may come before the task runs
        state = self._pc.connection_state
        _ = self._spawn(self._handle_connection_state(self._pc, state))

    async def _handle_connection_state(
        self, pc: webrtc.RTCPeerConnection, state: webrtc.RTCPeerConnectionState
    ) -> None:
        if pc is not self._pc or self._closed:
            return

        logger.debug('Connection {} is {}', self._pc_id, state)
        if state not in {webrtc.RTCPeerConnectionState.new, webrtc.RTCPeerConnectionState.connecting}:
            self._cancel(self._connecting_timeout)

        if state == webrtc.RTCPeerConnectionState.connected:
            if self._data_channel_timeout is None:
                self._data_channel_timeout = self._spawn(self._time_out_data_channel())
            if self._connect_invoked:
                await self._announce_connected()
            return

        await self._call_event_handler(str(state))
        if state == webrtc.RTCPeerConnectionState.failed:
            logger.warning('Connection {} failed, closing it', self._pc_id)
            await self._close()
        # pings tell a dead client long before the connection fails
        elif state == webrtc.RTCPeerConnectionState.disconnected:
            self._watch_for_pings_stopped()

    def _watch_for_pings_stopped(self) -> None:
        self._cancel(self._pings_stopped_timeout)
        disconnected = self._pc.connection_state == webrtc.RTCPeerConnectionState.disconnected
        if disconnected and self._last_ping is not None and not self._closed:
            self._pings_stopped_timeout = self._spawn(self._leave_if_pings_stopped(self._pc))

    def _start_connecting_timeout(self) -> None:
        self._cancel(self._connecting_timeout)
        self._connecting_timeout = self._spawn(self._time_out_connecting())

    async def _time_out_connecting(self) -> None:
        await asyncio.sleep(self.connection_timeout_secs)
        logger.warning('Connection {} not connected in {} s, closing it', self._pc_id, self.connection_timeout_secs)
        await self._close()

    async def _time_out_data_channel(self) -> None:
        await asyncio.sleep(DATA_CHANNEL_TIMEOUT_SECS)
        channel = self._data_channel
        if channel is None or channel.ready_state != webrtc.RTCDataChannelState.open:
            logger.warning(
                'No data channel {} s after connecting, dropping messages to send', DATA_CHANNEL_TIMEOUT_SECS
            )
            self._outgoing_messages.clear()
            self._data_channel_enabled = False

    async def _leave_if_pings_stopped(self, pc: webrtc.RTCPeerConnection) -> None:
        await asyncio.sleep(_DISCONNECTED_CLIENT_SECS)
        if pc.connection_state == webrtc.RTCPeerConnectionState.disconnected and not self._pinged_recently():
            await self._peer_left(pc, 'stopped pinging while disconnected')

    async def _end_renegotiation(self) -> None:
        await asyncio.sleep(_RENEGOTIATION_SECS)
        self._renegotiation_in_progress = False

    def _on_gathering_progress(self, _event: webrtc.Event) -> None:
        self._gathering_progress.set()

    def _on_track(self, event: webrtc.RTCTrackEvent) -> None:
        track = event.track
        logger.debug('Track {} received', track.kind)

        def on_ended(_event: webrtc.Event) -> None:
            logger.debug('Track {} ended', track.kind)
            self._emit('track-ended', track)

        _ = track.on('ended', on_ended)
        self._emit('track-started', track)

    def _on_transport_state(self, event: webrtc.Event) -> None:
        transport = event.target
        if not isinstance(transport, webrtc.RTCDtlsTransport) or transport not in self._transports:
            return
        if transport.state == webrtc.RTCDtlsTransportState.closed:
            _ = self._spawn(self._peer_left(self._pc, 'closed its connection'))

    def _on_data_channel(self, event: webrtc.RTCDataChannelEvent) -> None:
        channel = event.channel
        self._data_channel = channel
        _ = channel.on('open', self._on_channel_open)
        _ = channel.on('message', self._on_channel_message)
        _ = channel.on('close', self._on_channel_close)
        if channel.ready_state == webrtc.RTCDataChannelState.open:
            self._flush_messages()

    def _on_channel_open(self, _event: webrtc.Event) -> None:
        logger.debug('Data channel of {} is open', self._pc_id)
        self._flush_messages()

    def _on_channel_close(self, event: webrtc.Event) -> None:
        if event.target is self._data_channel:
            _ = self._spawn(self._peer_left(self._pc, 'closed its data channel'))

    def _on_channel_message(self, event: webrtc.MessageEvent) -> None:
        data = event.data
        if isinstance(data, str) and data.startswith('ping'):
            self._last_ping = time.monotonic()
            return

        if not isinstance(data, (str, bytes)):
            logger.error('Ignoring a blob message of the client')
            return
        try:
            message: object = json.loads(data)
        except ValueError:
            logger.error('A message of the client is not JSON: {!r}', data)
            return

        signalling = message.get('message') if _is_signalling(message) else None
        if signalling is not None:
            self._handle_signalling_message(signalling)
        elif self.is_connected():
            self._emit('app-message', message)
        else:
            logger.debug('The bot is not connected, holding an app message')
            self._pending_app_messages.append(message)

    def _handle_signalling_message(self, message: object) -> None:
        logger.debug('Signalling message {}', message)
        if not isinstance(message, dict) or message.get('type') != 'trackStatus':
            logger.debug('Ignoring a signalling message of an unknown type')
            return

        try:
            status: TrackStatusMessage = TrackStatusMessage.model_validate(message)
        except ValidationError as error:
            logger.warning('A malformed track status: {}', error)
            return
        self._emit('track-status', status.receiver_index, status.enabled)

    def _flush_messages(self) -> None:
        self._cancel(self._data_channel_timeout)
        channel = self._data_channel
        if channel is None:
            return

        messages = self._outgoing_messages
        self._outgoing_messages = []
        for message in messages:
            channel.send(message)

    async def _peer_left(self, pc: webrtc.RTCPeerConnection, how: str) -> None:
        if pc is not self._pc or self._closed:
            return
        logger.debug('The client of {} {}', self._pc_id, how)
        await self._close()

    async def _close(self) -> None:
        if self._closed:
            return
        self._close_peer_connection()
        await self._call_event_handler('closed')

    def _close_peer_connection(self) -> None:
        self._closed = True
        for task in (
            self._connecting_timeout,
            self._data_channel_timeout,
            self._renegotiation_end,
            self._pings_stopped_timeout,
        ):
            self._cancel(task)
        self._outgoing_messages.clear()
        self._pending_app_messages.clear()
        # wakes an answer waiting for candidates
        self._gathering_progress.set()

        self._pc.remove_all_listeners()
        for transport in self._transports:
            transport.off('statechange', self._on_transport_state)
        if self._data_channel is not None:
            self._data_channel.remove_all_listeners()
        self._pc.close()

    def _emit(self, name: str, *args: object) -> None:
        # native handlers can't await
        _ = self._spawn(cast('Coroutine[object, object, None]', self._call_event_handler(name, *args)))

    def _spawn(self, coroutine: Coroutine[object, object, None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.opt(exception=task.exception()).error('A task of connection {} failed', self._pc_id)

    @staticmethod
    def _cancel(task: asyncio.Task[None] | None) -> None:
        # a timeout that closes the connection mustn't cancel itself
        if task is not None and task is not asyncio.current_task():
            _ = task.cancel()
