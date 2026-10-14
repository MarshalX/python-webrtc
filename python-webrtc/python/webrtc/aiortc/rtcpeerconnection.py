#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import re
from typing import TYPE_CHECKING, Callable, TypeVar

from pyee.asyncio import AsyncIOEventEmitter
from typing_extensions import Never, override

import webrtc
from webrtc.aiortc._utils import (
    _DEFAULT_SAMPLE_RATE,
    _KINDS,
    _MSID,
    _datetime,
    _emitter,
    _found,
    _ice_state,
    _log_failure,
    _media_formats,
    _media_lines,
    _media_section,
    _ReadOnly,
    _sdp_of,
    _split,
    logger,
)
from webrtc.aiortc.codecs import h264, vpx
from webrtc.aiortc.exceptions import InternalError, InvalidAccessError, InvalidStateError, OperationError
from webrtc.aiortc.mediastreams import VIDEO_CLOCK_RATE, MediaStreamTrack
from webrtc.aiortc.rtcconfiguration import RTCConfiguration
from webrtc.aiortc.rtcdatachannel import RTCDataChannel, RTCDataChannelParameters
from webrtc.aiortc.rtcdtlstransport import RTCDtlsTransport
from webrtc.aiortc.rtcicetransport import RTCIceGatherer
from webrtc.aiortc.rtcrtpreceiver import RemoteStreamTrack, RTCRtpReceiver, _parameters
from webrtc.aiortc.rtcrtpsender import _source
from webrtc.aiortc.rtcrtptransceiver import RTCRtpTransceiver
from webrtc.aiortc.rtcsctptransport import RTCSctpTransport
from webrtc.aiortc.rtcsessiondescription import RTCSessionDescription
from webrtc.aiortc.sdp import candidate_to_sdp, parameters_to_sdp
from webrtc.aiortc.stats import (
    RTCInboundRtpStreamStats,
    RTCOutboundRtpStreamStats,
    RTCRemoteInboundRtpStreamStats,
    RTCRemoteOutboundRtpStreamStats,
    RTCStatsReport,
    RTCTransportStats,
)

if TYPE_CHECKING:
    import datetime as dt

    from webrtc.aiortc.rtcicetransport import RTCIceCandidate
    from webrtc.aiortc.rtcrtpparameters import ParametersDict
    from webrtc.aiortc.rtcrtpsender import RTCRtpSender
    from webrtc.aiortc.stats import RTCStats

# STUN and TURN servers get 5 seconds to answer
_GATHERING_TIMEOUT = 5
# attributes are never on the first line, and a newline before them is much faster to find than a line start
_END_OF_CANDIDATES = 'a=end-of-candidates\r\n'
_RTPMAP = re.compile(r'\na=rtpmap:(\d+) ([^/\s]+)/(\d+)')
_FMTP = re.compile(r'\na=fmtp:(\d+) ([^\r\n]*)')
_VIDEO_ORIENTATION = 'urn:3gpp:video-orientation'
_ICE_UFRAG = re.compile(r'\na=ice-ufrag:\S')
_ICE_PWD = re.compile(r'\na=ice-pwd:\S')
_SETUP = re.compile(r'\na=setup:(\w+)')
_RTCP_MUX = re.compile(r'\na=rtcp-mux[ \t\r]*(?:\n|$)')
_SETUP_LINE = re.compile(r'\na=setup:[^\r\n]*\r?\n')
_ENCODER_SETTINGS = {'vp8': vpx, 'h264': h264}
_BITRATE_PARAMETERS = {
    'DEFAULT_BITRATE': 'x-google-start-bitrate',
    'MIN_BITRATE': 'x-google-min-bitrate',
    'MAX_BITRATE': 'x-google-max-bitrate',
}
_UNCHANGED_BITRATES = {
    codec: {name: getattr(module, name) for name in _BITRATE_PARAMETERS} for codec, module in _ENCODER_SETTINGS.items()
}
_DIRECTIONS = ('sendrecv', 'sendonly', 'recvonly', 'inactive')
# the signaling states that take a local (True) or remote description of a type
_DESCRIPTION_STATES = {
    (True, 'offer'): ('stable', 'have-local-offer'),
    (True, 'answer'): ('have-remote-offer', 'have-local-pranswer'),
    (False, 'offer'): ('stable', 'have-remote-offer'),
    (False, 'answer'): ('have-local-offer', 'have-remote-pranswer'),
}
# bound to the core once heard: an unheard core event costs nothing
_CONNECTION_EVENTS = ('signalingstatechange', 'iceconnectionstatechange')
_T = TypeVar('_T')


def _track_kind(kind: str) -> webrtc.MediaType:
    if kind not in _KINDS:
        msg = f'Invalid track kind "{kind}"'
        raise InternalError(msg)
    return webrtc.MediaType(kind)


def _or(value: _T | None, default: _T) -> _T:
    return value if value is not None else default


def _stream(stats: webrtc.RTCRtpStreamStats) -> tuple[dt.datetime, str, str, int, str, str]:
    return _datetime(stats.timestamp), str(stats.type), stats.id, stats.ssrc, stats.kind, _or(stats.transport_id, '')


def _received(stats: webrtc.RTCReceivedRtpStreamStats, report: webrtc.RTCStatsReport) -> tuple[int, int, int]:
    codec = report.get(stats.codec_id) if stats.codec_id is not None else None
    if isinstance(codec, webrtc.RTCCodecStats) and codec.clock_rate is not None:
        clock_rate = codec.clock_rate
    else:
        clock_rate = VIDEO_CLOCK_RATE if stats.kind == 'video' else _DEFAULT_SAMPLE_RATE
    # jitter is in RTP timestamp units, not seconds
    return _or(stats.packets_received, 0), _or(stats.packets_lost, 0), round(_or(stats.jitter, 0.0) * clock_rate)


def _sent(stats: webrtc.RTCSentRtpStreamStats) -> tuple[int, int]:
    return _or(stats.packets_sent, 0), _or(stats.bytes_sent, 0)


def _converted_stats(  # ruff: ignore[too-many-return-statements]
    stats: webrtc.RTCStats, report: webrtc.RTCStatsReport, track_ids: dict[str | None, str]
) -> RTCStats | None:
    if isinstance(stats, webrtc.RTCInboundRtpStreamStats):
        return RTCInboundRtpStreamStats(*_stream(stats), *_received(stats, report))
    if isinstance(stats, webrtc.RTCRemoteInboundRtpStreamStats):
        # fractionLost is RTCP's 8-bit fixed point
        fraction_lost = min(255, round(_or(stats.fraction_lost, 0.0) * 256))
        return RTCRemoteInboundRtpStreamStats(
            *_stream(stats), *_received(stats, report), _or(stats.round_trip_time, 0.0), fraction_lost
        )
    if isinstance(stats, webrtc.RTCOutboundRtpStreamStats):
        return RTCOutboundRtpStreamStats(*_stream(stats), *_sent(stats), track_ids.get(stats.mid, ''))
    if isinstance(stats, webrtc.RTCRemoteOutboundRtpStreamStats):
        remote = stats.remote_timestamp
        return RTCRemoteOutboundRtpStreamStats(
            *_stream(stats), *_sent(stats), _datetime(remote) if remote is not None else None
        )
    if isinstance(stats, webrtc.RTCTransportStats):
        return RTCTransportStats(
            _datetime(stats.timestamp),
            str(stats.type),
            stats.id,
            _or(stats.packets_sent, 0),
            _or(stats.packets_received, 0),
            _or(stats.bytes_sent, 0),
            _or(stats.bytes_received, 0),
            str(stats.ice_role) if stats.ice_role is not None else '',
            str(stats.dtls_state),
        )
    return None


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _attribute(pattern: re.Pattern[str], head: str, section: str) -> re.Match[str] | None:
    found = pattern.search(section)
    return found if found is not None else pattern.search(head)


def _invalid_media(sdp: str, *, answer: bool) -> str | None:
    head, sections = _split(sdp)
    for section in sections:
        if _attribute(_ICE_UFRAG, head, section) is None or _attribute(_ICE_PWD, head, section) is None:
            return 'ICE username fragment or password is missing'
        setup = _attribute(_SETUP, head, section)
        if answer and (setup is None or setup.group(1) not in {'active', 'passive'}):
            return "DTLS setup attribute must be 'active' or 'passive' for an answer"
        if section.startswith(('m=audio', 'm=video')) and _RTCP_MUX.search(section) is None:
            return 'RTCP mux is not enabled'
    return None


def _kind_without_common_codec(sdp: str) -> str | None:
    for section in _split(sdp)[1]:
        kind = section[2:].split(' ', 1)[0]
        codecs = {pt: (name.lower(), int(clock)) for pt, name, clock in _RTPMAP.findall(section)}
        # a format with no rtpmap is a static payload type, which the engine resolves itself
        if kind not in _KINDS or any(f not in codecs for f in _media_formats(section)):
            continue
        supported = {(c.name.lower(), c.clockRate) for c in RTCRtpReceiver.getCapabilities(kind).codecs}
        if not any(codec in supported for codec in codecs.values() if codec[0] != 'rtx'):
            return kind
    return None


def _with_defaults(parameters: ParametersDict, defaults: ParametersDict) -> ParametersDict:
    return {**parameters, **{k: v for k, v in defaults.items() if k not in parameters}}


def _remote_parameters(codec: str, parameters: ParametersDict) -> ParametersDict:
    # what the remote description allows shapes what we send
    if codec in _ENCODER_SETTINGS:
        # unchanged constants keep the adaptive bandwidth estimation's range
        module, unchanged = _ENCODER_SETTINGS[codec], _UNCHANGED_BITRATES[codec]
        bitrates = {name: getattr(module, name) for name in _BITRATE_PARAMETERS}
        changed = {_BITRATE_PARAMETERS[k]: v // 1000 for k, v in bitrates.items() if v != unchanged[k]}
        return _with_defaults(parameters, changed)
    return parameters


def _with_parameters(
    sdp: str, rewrite: Callable[[str, ParametersDict], ParametersDict]
) -> tuple[str, dict[str, set[str]]]:
    added: dict[str, set[str]] = {}
    head, sections = _split(sdp)
    for index, section in enumerate(sections):
        lines: dict[str, str] = dict(_FMTP.findall(section))
        codecs: list[tuple[str, str, str]] = _RTPMAP.findall(section)
        for payload_type, name, _ in codecs:
            parameters = _parameters(lines.get(payload_type))
            rewritten = rewrite(name.lower(), parameters)
            if rewritten != parameters:
                added.setdefault(name.lower(), set()).update(rewritten.keys() - parameters.keys())
                new = parameters_to_sdp(rewritten)
                sections[index] = _with_fmtp(sections[index], payload_type, lines.get(payload_type), new)
    return head + ''.join(sections), added


def _with_fmtp(section: str, payload_type: str, old: str | None, new: str) -> str:
    if old is not None and new == '':
        return re.sub(rf'\na=fmtp:{payload_type} [^\r\n]*\r?\n', '\n', section, count=1)
    if old is not None:
        return section.replace(f'\na=fmtp:{payload_type} {old}', f'\na=fmtp:{payload_type} {new}', 1)
    rtpmap = re.search(rf'\na=rtpmap:{payload_type} [^\r\n]*(\r?\n)', section)
    if rtpmap is None:
        return section
    return f'{section[: rtpmap.end()]}a=fmtp:{payload_type} {new}{rtpmap.group(1)}{section[rtpmap.end() :]}'


def _description(
    description: webrtc.RTCSessionDescriptionInit | webrtc.RTCSessionDescription, *, ended: bool = False
) -> RTCSessionDescription:
    head, sections = _split(description.sdp)
    for index, section in enumerate(sections):
        text = section + _END_OF_CANDIDATES if ended and _END_OF_CANDIDATES not in section else section
        # each media section ends with its DTLS role, for code that reads it from the last line
        setup = _SETUP_LINE.search(text)
        if setup is not None and setup.end() != len(text):
            text = text[: setup.start() + 1] + text[setup.end() :] + setup.group(0)[1:]
        sections[index] = text
    return RTCSessionDescription(sdp=head + ''.join(sections), type=str(description.type))


def _native_description(description: RTCSessionDescription) -> webrtc.RTCSessionDescriptionInit:
    return webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType(description.type), description.sdp)


class RTCPeerConnection(AsyncIOEventEmitter):  # ruff: ignore[too-many-public-methods]
    signalingState: _ReadOnly[str] = _ReadOnly('_native.signaling_state.value')

    def __init__(self, configuration: RTCConfiguration | None = None) -> None:
        super().__init__()
        configuration = configuration if configuration is not None else RTCConfiguration()
        servers = configuration.iceServers
        if servers is None:
            servers = RTCIceGatherer.getDefaultIceServers()
        self._native = webrtc.RTCPeerConnection(
            webrtc.RTCConfiguration(
                ice_servers=[webrtc.RTCIceServer(s.urls, s.username, s.credential) for s in servers],
                bundle_policy=webrtc.RTCBundlePolicy(configuration.bundlePolicy.value),
                always_negotiate_data_channels=configuration.alwaysNegotiateDataChannels,
            )
        )
        self._pending: list[RTCDataChannel] = []
        self._channels: list[RTCDataChannel] = []
        self._dtls: dict[webrtc.RTCDtlsTransport, RTCDtlsTransport] = {}
        self._sctp: RTCSctpTransport | None = None
        self._transceivers: dict[webrtc.RTCRtpTransceiver, RTCRtpTransceiver] = {}
        self._stream: webrtc.MediaStream | None = None
        self._candidates: list[RTCIceCandidate | None] = []
        self._gathered: list[asyncio.Future[None]] = []
        self._emitted = dict.fromkeys(
            ('icegatheringstatechange', 'iceconnectionstatechange', 'connectionstatechange'), 'new'
        )
        self._gathering_timed_out = False
        self._remote_candidates_ended = False
        self._added_parameters: dict[str, set[str]] = {}
        self._closing: asyncio.Future[None] | None = None
        self._watching = False
        self._heard = {'icegatheringstatechange', 'connectionstatechange', 'datachannel', 'track'}
        self._bound: set[str] = set()
        self._attach()

    @override
    def _add_event_handler(self, event: str, k: Callable[..., object], v: Callable[..., object]) -> None:
        super()._add_event_handler(event, k, v)
        if event in _CONNECTION_EVENTS and event not in self._heard:
            self._heard.add(event)
            self._attach()

    def _attach(self) -> None:
        # the core takes handlers only on a running loop, which isn't needed to create a connection
        if _running_loop() is None or self._closed:
            return
        handlers: dict[str, Callable[[Never], object]] = {
            'signalingstatechange': lambda _event: self.emit('signalingstatechange'),
            'icegatheringstatechange': self._ice_gathering_state_changed,
            'iceconnectionstatechange': lambda _event: self._emit_ice_state(),
            'connectionstatechange': self._connection_state_changed,
            'datachannel': self._datachannel,
            'track': self._track_added,
        }
        for event in self._heard - self._bound:
            if event == 'iceconnectionstatechange':
                # only changes from now on are emitted
                self._emitted[event] = self.iceConnectionState
            self._native.on(event, handlers[event])  # pyrefly: ignore[no-matching-overload]
        self._bound |= self._heard
        pending = self._pending.copy()
        self._pending.clear()
        for channel in pending:
            channel._attach()

    def _adopt(self, channel: RTCDataChannel) -> None:
        self._pending.append(channel)
        self._attach()

    def _ice_gathering_state_changed(self, _event: webrtc.Event) -> None:
        state = self._native.ice_gathering_state
        if state == webrtc.RTCIceGatheringState.complete:
            self._end_gathering_waits()
        elif state == webrtc.RTCIceGatheringState.gathering:
            self._gathering_timed_out = False
        self._emit_changed('icegatheringstatechange', self.iceGatheringState)

    def _connection_state_changed(self, _event: webrtc.Event) -> None:
        self._start_senders()
        if self._native.connection_state == webrtc.RTCPeerConnectionState.connected and not self._watching:
            self._watching = True
            # off the path to the first messages and media
            asyncio.get_running_loop().call_soon(self._watch_transports)
        self._emit_changed('connectionstatechange', self.connectionState)

    def _emit_changed(self, name: str, state: str) -> None:
        if self._emitted[name] != state:
            self._emitted[name] = state
            self.emit(name)

    def _datachannel(self, event: webrtc.RTCDataChannelEvent) -> None:
        channel = _emitter(RTCDataChannel)
        channel._init(event.channel, self, local=False)
        if self._sctp is not None:
            self._sctp.emit('datachannel', channel)
        self.emit('datachannel', channel)

    def _track_added(self, event: webrtc.RTCTrackEvent) -> None:
        receiver = self._transceiver(event.transceiver).receiver
        if receiver._track is None:
            track_id = _found(_MSID, _media_section(_sdp_of(self._native.remote_description), event.transceiver.mid))
            receiver._track = RemoteStreamTrack._of(event.track, receiver, track_id)
            self.emit('track', receiver._track)

    def _transceiver(self, native: webrtc.RTCRtpTransceiver) -> RTCRtpTransceiver:
        transceiver = self._transceivers.get(native)
        if transceiver is None:
            transceiver = self._transceivers[native] = RTCRtpTransceiver._of(native, self)
        return transceiver

    def _local_stream(self) -> webrtc.MediaStream:
        # one stream for every track, so a browser gets streams[0]
        if self._stream is None:
            self._stream = webrtc.MediaStream()
        return self._stream

    def _check_no_sender(self, track: MediaStreamTrack) -> None:
        if any(sender.track is track for sender in self.getSenders()):
            msg = 'Track already has a sender'
            raise InvalidAccessError(msg)

    def _stop_orientation(self) -> None:
        # without the extension, senders rotate frames before encoding them
        for transceiver in self._native.get_transceivers():
            if transceiver.receiver.track.kind != 'video' or transceiver.direction == 'stopped':
                continue
            extensions = transceiver.get_header_extensions_to_negotiate()
            if any(e.uri == _VIDEO_ORIENTATION and e.direction != 'stopped' for e in extensions):
                transceiver.set_header_extensions_to_negotiate([
                    dataclasses.replace(e, direction='stopped') if e.uri == _VIDEO_ORIENTATION else e
                    for e in extensions
                ])

    def _local_description(self, native: webrtc.RTCSessionDescriptionInit) -> RTCSessionDescription:
        description = _description(native)
        # the remote peer sees the ids of the tracks the application added
        for transceiver in self._transceivers.values():
            track, announced = transceiver.sender._track, transceiver._announced_track_id(description.sdp)
            if track is not None and announced is not None:
                description.sdp = description.sdp.replace(announced, track.id)
        return description

    def _without_added_parameters(self, codec: str, parameters: ParametersDict) -> ParametersDict:
        # the remote description reads as the peer sent it
        added = self._added_parameters.get(codec, set())
        return {k: v for k, v in parameters.items() if k not in added}

    def _start_senders(self) -> None:
        for transceiver in self._transceivers.values():
            transceiver.sender._start()

    def _stats(self, report: webrtc.RTCStatsReport) -> RTCStatsReport:
        track_ids = {t.mid: str(id(t.sender.track)) for t in self._transceivers.values()}
        converted = RTCStatsReport()
        for stats in report.values():
            item = _converted_stats(stats, report, track_ids)
            if item is not None:
                converted.add(item)
        return converted

    def _end_gathering_waits(self) -> None:
        waits = self._gathered.copy()
        self._gathered.clear()
        for wait in waits:
            if not wait.done():
                wait.set_result(None)

    async def _gathering_complete(self) -> None:
        native = self._native
        has_media = '\nm=' in _sdp_of(native.local_description)
        if native.ice_gathering_state == webrtc.RTCIceGatheringState.complete or not has_media:
            return
        wait = asyncio.get_running_loop().create_future()
        self._gathered.append(wait)
        try:
            await asyncio.wait_for(wait, _GATHERING_TIMEOUT)
        except asyncio.TimeoutError:
            self._gathering_timed_out = True
            self._emit_changed('icegatheringstatechange', self.iceGatheringState)
        finally:
            with contextlib.suppress(ValueError):
                self._gathered.remove(wait)

    def _dtls_transport(self, native: webrtc.RTCDtlsTransport) -> RTCDtlsTransport:
        transport = self._dtls.get(native)
        if transport is None:
            transport = self._dtls[native] = RTCDtlsTransport._of(native, self)
            if _running_loop() is not None:
                transport._watch()
        return transport

    def _watch_transports(self) -> None:
        if self._closed:
            return
        natives = [t.sender.transport for t in self._native.get_transceivers()]
        sctp = self._native.sctp
        natives.append(sctp.transport if sctp is not None else None)
        self._dtls = {native: self._dtls_transport(native) for native in natives if native is not None}
        for transport in self._dtls.values():
            transport._watch()

    def _dtls_state_changed(self) -> None:
        if self._closed or not self._watching:
            return
        # a remote close ends the connection now, not once ICE consent expires
        if all(t.state == 'closed' for t in self._dtls.values()):
            task = asyncio.ensure_future(self.close())
            task.add_done_callback(functools.partial(_log_failure, 'RTCPeerConnection.close'))

    def _description_applied(self) -> None:
        current = set(self._native.get_transceivers())
        self._transceivers = {native: t for native, t in self._transceivers.items() if native in current}
        if self._watching:
            self._watch_transports()
        self._start_senders()

    @property
    def _closed(self) -> bool:
        return self._closing is not None

    def _check_open(self) -> None:
        if self._closed:
            msg = 'RTCPeerConnection is closed'
            raise InvalidStateError(msg)

    def _check_description(self, description: RTCSessionDescription, *, local: bool) -> None:
        states = _DESCRIPTION_STATES.get((local, description.type))
        if states is not None and self.signalingState not in states:
            msg = f'Cannot handle {description.type} in signaling state "{self.signalingState}"'
            raise InvalidStateError(msg)
        answer = description.type in {'answer', 'pranswer'}
        error = _invalid_media(description.sdp, answer=answer)
        offer = self._native.remote_description if local else self._native.local_description
        if error is None and answer and _media_lines(description.sdp) != _media_lines(_sdp_of(offer)):
            error = 'Media sections in answer do not match offer'
        if error is not None:
            raise ValueError(error)
        kind = _kind_without_common_codec(description.sdp) if not local else None
        if kind is not None:
            msg = f'Failed to set remote {kind} description send parameters'
            raise OperationError(msg)

    async def _add_candidate(self, candidate: RTCIceCandidate | None) -> None:
        native = None
        if candidate is None:
            self._remote_candidates_ended = True
        else:
            sdp = 'candidate:' + candidate_to_sdp(candidate)
            native = webrtc.RTCIceCandidateInit(sdp, candidate.sdpMid, candidate.sdpMLineIndex)
        try:
            await self._native.add_ice_candidate(native)
        except webrtc.OperationError:
            logger.warning('RTCPeerConnection addIceCandidate ignored a candidate of no media section: %s', candidate)

    def _ice_started(self) -> bool:
        # checks count as started once both descriptions are set, not once a remote candidate arrives
        native = self._native
        return native.remote_description is not None and '\nm=' in _sdp_of(native.local_description)

    def _emit_ice_state(self) -> None:
        self._emit_changed('iceconnectionstatechange', self.iceConnectionState)
        self._emit_changed('connectionstatechange', self.connectionState)

    @property
    def connectionState(self) -> str:
        state = self._native.connection_state
        if state == webrtc.RTCPeerConnectionState.new and self._ice_started():
            return 'connecting'
        if state == webrtc.RTCPeerConnectionState.disconnected:
            return 'connected'
        # failed ICE fails the connection, which the engine reports one event later
        if state == webrtc.RTCPeerConnectionState.connecting and self._native.ice_connection_state == 'failed':
            return 'failed'
        return state.value

    @property
    def iceConnectionState(self) -> str:
        state = self._native.ice_connection_state
        if state == webrtc.RTCIceConnectionState.new and self._ice_started():
            return 'checking'
        return _ice_state(state)

    @property
    def iceGatheringState(self) -> str:
        state = self._native.ice_gathering_state
        if self._gathering_timed_out and state == webrtc.RTCIceGatheringState.gathering:
            return 'complete'
        return state.value

    @property
    def localDescription(self) -> RTCSessionDescription | None:
        native = self._native.local_description
        # the candidates end once STUN and TURN servers are no longer waited for
        return _description(native, ended=self._gathering_timed_out) if native is not None else None

    @property
    def remoteDescription(self) -> RTCSessionDescription | None:
        native = self._native.remote_description
        if native is None:
            return None
        # the core drops the attribute from the descriptions it parses
        description = _description(native, ended=self._remote_candidates_ended)
        description.sdp, _ = _with_parameters(description.sdp, self._without_added_parameters)
        return description

    @property
    def sctp(self) -> RTCSctpTransport | None:
        if self._sctp is None and self._native.sctp is not None:
            self._sctp = RTCSctpTransport._of(self)
        return self._sctp

    async def addIceCandidate(self, candidate: RTCIceCandidate | None) -> None:
        if candidate is not None and candidate.sdpMid is None and candidate.sdpMLineIndex is None:
            msg = 'Candidate must have either sdpMid or sdpMLineIndex'
            raise ValueError(msg)
        self._attach()
        if self._native.remote_description is None:
            logger.warning('RTCPeerConnection addIceCandidate called without remote description')
            self._candidates.append(candidate)
            return
        await self._add_candidate(candidate)

    def addTrack(self, track: MediaStreamTrack) -> RTCRtpSender:
        self._check_open()
        _ = _track_kind(track.kind)
        self._check_no_sender(track)
        sent, generator = _source(track, None)
        native = self._native.add_track(sent, self._local_stream())
        sender = self._transceiver(next(t for t in self._native.get_transceivers() if t.sender == native)).sender
        sender._use(track, sent, generator if generator is not None else sender._generator)
        return sender

    def addTransceiver(self, trackOrKind: str | MediaStreamTrack, direction: str = 'sendrecv') -> RTCRtpTransceiver:
        self._check_open()
        track = trackOrKind if isinstance(trackOrKind, MediaStreamTrack) else None
        kind = _track_kind(track.kind if track is not None else str(trackOrKind))
        if direction not in _DIRECTIONS:
            msg = f'Invalid direction "{direction}"'
            raise InternalError(msg)
        init = webrtc.RTCRtpTransceiverInit(webrtc.RTCRtpTransceiverDirection(direction), [self._local_stream()])
        if track is None:
            return self._transceiver(self._native.add_transceiver(kind, init))
        self._check_no_sender(track)
        sent, generator = _source(track, None)
        transceiver = self._transceiver(self._native.add_transceiver(sent, init))
        transceiver.sender._use(track, sent, generator)
        return transceiver

    def getReceivers(self) -> list[RTCRtpReceiver]:
        return [t.receiver for t in self.getTransceivers()]

    def getSenders(self) -> list[RTCRtpSender]:
        return [t.sender for t in self.getTransceivers()]

    def getTransceivers(self) -> list[RTCRtpTransceiver]:
        return [self._transceiver(t) for t in self._native.get_transceivers()]

    def removeTrack(self, sender: RTCRtpSender) -> None:
        self._check_open()
        self._native.remove_track(sender._native)
        sender._stop_pump()
        sender._use(None, None, sender._generator)

    async def getStats(self) -> RTCStatsReport:
        return self._stats(await self._native.get_stats())

    async def close(self) -> None:
        if self._closing is not None:
            await asyncio.shield(self._closing)
            return
        self._closing = asyncio.get_running_loop().create_future()
        try:
            self._native.close()
            self.emit('signalingstatechange')
            self._end_gathering_waits()
            for transceiver in list(self._transceivers.values()):
                await transceiver.stop()
            for channel in list(self._channels):
                channel._emit_close()
            self._emit_changed('iceconnectionstatechange', 'closed')
            self._emit_changed('connectionstatechange', 'closed')
            self.remove_all_listeners()
        finally:
            self._closing.set_result(None)

    async def createAnswer(self) -> RTCSessionDescription:
        self._check_open()
        if self.signalingState not in {'have-remote-offer', 'have-local-pranswer'}:
            msg = f'Cannot create answer in signaling state "{self.signalingState}"'
            raise InvalidStateError(msg)
        self._attach()
        self._stop_orientation()
        return self._local_description(await self._native.create_answer())

    def createDataChannel(
        self,
        label: str,
        maxPacketLifeTime: int | None = None,
        maxRetransmits: int | None = None,
        ordered: bool = True,
        protocol: str = '',
        negotiated: bool = False,
        id: int | None = None,
    ) -> RTCDataChannel:
        if maxPacketLifeTime is not None and maxRetransmits is not None:
            msg = 'Cannot specify both maxPacketLifeTime and maxRetransmits'
            raise ValueError(msg)
        if self._sctp is None:
            self._sctp = RTCSctpTransport._of(self)
        parameters = RTCDataChannelParameters(
            label, maxPacketLifeTime, maxRetransmits, ordered, protocol, negotiated, id
        )
        return RTCDataChannel(self._sctp, parameters)

    async def createOffer(self) -> RTCSessionDescription:
        self._check_open()
        self._attach()
        self._stop_orientation()
        return self._local_description(await self._native.create_offer())

    async def setLocalDescription(self, sessionDescription: RTCSessionDescription | None = None) -> None:
        self._check_open()
        description = sessionDescription
        if description is None:
            implicit = self.createAnswer if self.signalingState == 'have-remote-offer' else self.createOffer
            description = await implicit()
        self._check_description(description, local=True)
        self._attach()
        await self._native.set_local_description(_native_description(description))
        if description.type in {'answer', 'pranswer'}:
            for transceiver in list(self._transceivers.values()):
                if transceiver._preferred and transceiver.direction in {'sendrecv', 'sendonly'}:
                    await transceiver._send_first_answered_codec(description.sdp)
        self._description_applied()
        await self._gathering_complete()
        self._emit_ice_state()

    async def setRemoteDescription(self, sessionDescription: RTCSessionDescription) -> None:
        self._check_description(sessionDescription, local=False)
        self._attach()
        sdp, added = _with_parameters(sessionDescription.sdp, _remote_parameters)
        await self._native.set_remote_description(_native_description(dataclasses.replace(sessionDescription, sdp=sdp)))
        self._added_parameters = added
        self._remote_candidates_ended = _END_OF_CANDIDATES in sessionDescription.sdp
        self._description_applied()
        candidates = self._candidates.copy()
        self._candidates.clear()
        for candidate in candidates:
            await self._add_candidate(candidate)
        self._emit_ice_state()


__all__ = ['RTCPeerConnection']
