#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The connection between the local peer and a remote one."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Callable, ClassVar, Literal, TypeVar, Union, cast, overload

from typing_extensions import override

import webrtc
from webrtc import (
    Event,
    InvalidAccessError,
    InvalidStateError,
    MediaType,
    OperationError,
    RTCAnswerOptions,
    RTCCertificate,
    RTCConfiguration,
    RTCDataChannelEvent,
    RTCDataChannelEventInit,
    RTCIceCandidate,
    RTCIceGathererState,
    RTCLocalSessionDescriptionInit,
    RTCOfferOptions,
    RTCPeerConnectionIceErrorEvent,
    RTCPeerConnectionIceErrorEventInit,
    RTCPeerConnectionIceEvent,
    RTCPeerConnectionIceEventInit,
    RTCRtpCodec,
    RTCRtpTransceiverDirection,
    RTCRtpTransceiverInit,
    RTCSdpType,
    RTCSessionDescription,
    RTCSessionDescriptionInit,
    RTCSignalingState,
    RTCStatsReport,
    RTCTrackEvent,
    RTCTrackEventInit,
    WebRTCObject,
    wrtc,
)
from webrtc.interfaces.rtc_data_channel import RTCDataChannelInit, check_utf8_length
from webrtc.utils.events import AnyHandler, EventTarget, HandlerDecorator
from webrtc.utils.native_calls import call_native
from webrtc.utils.operations import OperationsChain, later
from webrtc.utils.task_queue import TaskQueue

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from typing_extensions import Self

    from webrtc.models.rtc_certificate import AlgorithmIdentifier

#: A description in the form the methods that set one accept
_Description = Union[RTCSessionDescription, RTCSessionDescriptionInit]

# the signaling states a local description of a type can be set in
_LOCAL_DESCRIPTION_STATES = {
    RTCSdpType.offer: (RTCSignalingState.stable, RTCSignalingState.have_local_offer),
    RTCSdpType.answer: (RTCSignalingState.have_remote_offer, RTCSignalingState.have_local_pranswer),
    RTCSdpType.pranswer: (RTCSignalingState.have_remote_offer, RTCSignalingState.have_local_pranswer),
    RTCSdpType.rollback: (RTCSignalingState.have_local_offer, RTCSignalingState.have_local_pranswer),
}
# the same for a remote description, but an offer, which can be set in any state (a local one is rolled back)
_REMOTE_DESCRIPTION_STATES = {
    RTCSdpType.answer: (RTCSignalingState.have_local_offer, RTCSignalingState.have_remote_pranswer),
    RTCSdpType.pranswer: (RTCSignalingState.have_local_offer, RTCSignalingState.have_remote_pranswer),
    RTCSdpType.rollback: (RTCSignalingState.have_remote_offer, RTCSignalingState.have_remote_pranswer),
}

_RID = re.compile(r'[A-Za-z0-9]{1,16}')


_PeerConnectionStateEvent = Literal[
    'negotiationneeded',
    'signalingstatechange',
    'iceconnectionstatechange',
    'icegatheringstatechange',
    'connectionstatechange',
]
_PeerConnectionEvent = Literal[_PeerConnectionStateEvent, 'icecandidate', 'icecandidateerror', 'track', 'datachannel']
_R = TypeVar('_R')


class RTCPeerConnection(WebRTCObject[wrtc.RTCPeerConnection], EventTarget[_PeerConnectionEvent]):
    """A connection to a remote peer, which negotiates and carries media tracks and data channels.

    The application exchanges descriptions (:meth:`create_offer`, :meth:`create_answer`) and ICE candidates
    with the remote peer over its own signaling channel. Operations that change the negotiation run one after
    another, in the order they're called. See :mdn:`RTCPeerConnection`.

    Events:
        negotiationneeded (:obj:`webrtc.Event`): Negotiation (an offer/answer exchange) is needed.
        icecandidate (:obj:`webrtc.RTCPeerConnectionIceEvent`): A local ICE candidate was gathered and should be
            sent to the remote peer. Its ``candidate`` is :obj:`None` once gathering is complete.
        icecandidateerror (:obj:`webrtc.RTCPeerConnectionIceErrorEvent`): A STUN or TURN server failed.
        signalingstatechange (:obj:`webrtc.Event`): :attr:`signaling_state` changed.
        iceconnectionstatechange (:obj:`webrtc.Event`): :attr:`ice_connection_state` changed.
        icegatheringstatechange (:obj:`webrtc.Event`): :attr:`ice_gathering_state` changed.
        connectionstatechange (:obj:`webrtc.Event`): :attr:`connection_state` changed.
        track (:obj:`webrtc.RTCTrackEvent`): A remote track was negotiated.
        datachannel (:obj:`webrtc.RTCDataChannelEvent`): The remote peer created a data channel.

    A closed connection emits no events, including the ones queued before :meth:`close`.

    Args:
        configuration (:obj:`webrtc.RTCConfiguration`, optional): The configuration of the connection.
            The defaults of :obj:`webrtc.RTCConfiguration` are used if it's omitted.

    Raises:
        webrtc.InvalidSyntaxError: If an ICE server URL is invalid.
        webrtc.InvalidAccessError: If a TURN server has no credentials, or a certificate has expired.
        webrtc.NotSupportedError: If a TURN server has an OAuth credential.
        ValueError: If a member of the configuration is out of range.
        TypeError: If a member of the configuration has a wrong type, or a value its enum doesn't have.
    """

    _class = wrtc.RTCPeerConnection

    # the native method that surfaces the state of each state event
    _STATE_EVENTS: ClassVar[dict[str, str]] = {
        'signalingstatechange': '_surfaceSignalingState',
        'iceconnectionstatechange': '_surfaceIceConnectionState',
        'icegatheringstatechange': '_surfaceIceGatheringState',
        'connectionstatechange': '_surfaceConnectionState',
    }
    # the method that creates the event object of each event, from its native arguments
    _EVENT_CREATORS: ClassVar[dict[str, str]] = {
        'negotiationneeded': '_negotiation_needed_event',
        'icecandidate': '_ice_candidate_event',
        'icecandidateerror': '_ice_candidate_error_event',
        'datachannel': '_data_channel_event',
        'track': '_track_event',
    }

    #: The operations chain, created on first use (a wrapper of a native connection doesn't run __init__)
    _chain: OperationsChain | None = None
    #: The id of a negotiationneeded event that waits for the operations chain to empty
    _deferred_negotiation_id: int | None = None

    @overload
    def on(self, name: _PeerConnectionStateEvent, handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def on(self, name: _PeerConnectionStateEvent, handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def on(
        self, name: Literal['icecandidate'], handler: None = None
    ) -> HandlerDecorator[RTCPeerConnectionIceEvent]: ...

    @overload
    def on(
        self, name: Literal['icecandidate'], handler: Callable[[RTCPeerConnectionIceEvent], _R]
    ) -> Callable[[RTCPeerConnectionIceEvent], _R]: ...

    @overload
    def on(
        self, name: Literal['icecandidateerror'], handler: None = None
    ) -> HandlerDecorator[RTCPeerConnectionIceErrorEvent]: ...

    @overload
    def on(
        self, name: Literal['icecandidateerror'], handler: Callable[[RTCPeerConnectionIceErrorEvent], _R]
    ) -> Callable[[RTCPeerConnectionIceErrorEvent], _R]: ...

    @overload
    def on(self, name: Literal['track'], handler: None = None) -> HandlerDecorator[RTCTrackEvent]: ...

    @overload
    def on(self, name: Literal['track'], handler: Callable[[RTCTrackEvent], _R]) -> Callable[[RTCTrackEvent], _R]: ...

    @overload
    def on(self, name: Literal['datachannel'], handler: None = None) -> HandlerDecorator[RTCDataChannelEvent]: ...

    @overload
    def on(
        self, name: Literal['datachannel'], handler: Callable[[RTCDataChannelEvent], _R]
    ) -> Callable[[RTCDataChannelEvent], _R]: ...

    def on(self, name: _PeerConnectionEvent, handler: AnyHandler | None = None) -> object:
        """Registers a handler of an event of the connection, listed above. Can be used as a decorator.

        Args:
            name (:obj:`str`): The name of the event, like ``'icecandidate'``.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.
                If omitted, a decorator is returned.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            ValueError: If the connection has no such event.
            RuntimeError: If called outside of a running event loop.
        """
        return self._add(name, handler, once=False)

    @overload
    def once(self, name: _PeerConnectionStateEvent, handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def once(self, name: _PeerConnectionStateEvent, handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def once(
        self, name: Literal['icecandidate'], handler: None = None
    ) -> HandlerDecorator[RTCPeerConnectionIceEvent]: ...

    @overload
    def once(
        self, name: Literal['icecandidate'], handler: Callable[[RTCPeerConnectionIceEvent], _R]
    ) -> Callable[[RTCPeerConnectionIceEvent], _R]: ...

    @overload
    def once(
        self, name: Literal['icecandidateerror'], handler: None = None
    ) -> HandlerDecorator[RTCPeerConnectionIceErrorEvent]: ...

    @overload
    def once(
        self, name: Literal['icecandidateerror'], handler: Callable[[RTCPeerConnectionIceErrorEvent], _R]
    ) -> Callable[[RTCPeerConnectionIceErrorEvent], _R]: ...

    @overload
    def once(self, name: Literal['track'], handler: None = None) -> HandlerDecorator[RTCTrackEvent]: ...

    @overload
    def once(self, name: Literal['track'], handler: Callable[[RTCTrackEvent], _R]) -> Callable[[RTCTrackEvent], _R]: ...

    @overload
    def once(self, name: Literal['datachannel'], handler: None = None) -> HandlerDecorator[RTCDataChannelEvent]: ...

    @overload
    def once(
        self, name: Literal['datachannel'], handler: Callable[[RTCDataChannelEvent], _R]
    ) -> Callable[[RTCDataChannelEvent], _R]: ...

    def once(self, name: _PeerConnectionEvent, handler: AnyHandler | None = None) -> object:
        """Registers a handler that is removed after its first call. Can be used as a decorator.

        Args:
            name (:obj:`str`): The name of the event, like ``'track'``.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.
                If omitted, a decorator is returned.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            ValueError: If the connection has no such event.
            RuntimeError: If called outside of a running event loop.
        """
        return self._add(name, handler, once=True)

    def __init__(self, configuration: webrtc.RTCConfiguration | None = None) -> None:
        super().__init__(wrtc.RTCPeerConnection(configuration._to_native() if configuration is not None else None))
        self._attach()

    @classmethod
    @override
    def _wrap(cls, item: wrtc.RTCPeerConnection) -> Self:
        # the wrapper that owns the listeners (and so the operations chain), when there is one
        listeners = item._listeners
        if listeners is not None and isinstance(listeners.target, cls):
            return listeners.target
        # not attached, so the connection object of the application gets the listeners once it registers a handler
        connection = cls.__new__(cls)
        connection._init_native(item)
        return connection

    def _operation(self) -> AbstractAsyncContextManager[None]:
        """Chains an operation, like setting a description, after the running ones (see :obj:`OperationsChain`)."""
        if self._chain is None:
            self._chain = OperationsChain(self._chain_emptied)
        return self._chain.operation()

    def _chain_emptied(self) -> None:
        # negotiationneeded fires now, if it's still needed
        if self._deferred_negotiation_id is not None:
            event_id, self._deferred_negotiation_id = self._deferred_negotiation_id, None
            _ = asyncio.get_running_loop().call_soon(self._dispatch, 'negotiationneeded', event_id)

    def _check_state(self, operation: str, *allowed: RTCSignalingState) -> None:
        """Checks the connection isn't closed, and is in one of the allowed states if they're given.

        Raises:
            webrtc.InvalidStateError: If it isn't.
        """
        state = self.signaling_state
        if state == RTCSignalingState.closed:
            msg = f"Can not {operation}: the RTCPeerConnection's signalingState is 'closed'"
            raise InvalidStateError(msg)
        if len(allowed) > 0 and state not in allowed:
            msg = f'Can not {operation} in the {state} signaling state'
            raise InvalidStateError(msg)

    @override
    def _on_event(self, name: str, *args: object) -> None:
        if name == '_gatheringcomplete':
            transports, state = cast('tuple[list[wrtc.RTCIceTransport], webrtc.RTCIceGatheringState]', args)
            self._complete_gathering(transports, state)
            return
        # the state attributes change along with their events
        surface = self._STATE_EVENTS.get(name)
        if surface is not None:
            state = args[0]
            getattr(self._native_obj, surface)(state)
        if name == 'signalingstatechange':
            _, descriptions = cast('tuple[RTCSignalingState, int]', args)
            # the descriptions as the change left them
            self._native_obj._applyDescriptions(descriptions)
        elif name in {'icecandidate', 'icegatheringstatechange'}:
            # the local description gains candidates (and loses pending ones) along with these events
            self._native_obj._refreshDescriptions()
        elif name == 'datachannel':
            (channel,) = cast('tuple[wrtc.RTCDataChannel]', args)
            _ = webrtc.RTCDataChannel._wrap(channel)
            # the events of the channel follow the handlers of this one
            _ = TaskQueue.post_to_running(channel._release)

    def _complete_gathering(self, transports: list[wrtc.RTCIceTransport], state: webrtc.RTCIceGatheringState) -> None:
        """Completes gathering on the ICE transports and the connection, and ends the candidates, in one task.

        This way every handler sees all of them complete.
        """
        ice_transports = webrtc.RTCIceTransport._wrap_many(transports)
        for ice_transport in ice_transports:
            ice_transport._native_obj._surfaceGatheringState(RTCIceGathererState(state))
        self._native_obj._surfaceIceGatheringState(state)
        self._native_obj._refreshDescriptions()
        for ice_transport in ice_transports:
            ice_transport._dispatch('gatheringstatechange', state)
        self._dispatch('icegatheringstatechange', state)
        # the end of candidates is an icecandidate event without a candidate
        self._dispatch('icecandidate')

    @override
    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        # events queued before close() aren't delivered after it
        if self._native_obj.signalingState == RTCSignalingState.closed:
            return None
        creator_name = self._EVENT_CREATORS.get(name)
        if creator_name is None:
            return super()._create_event(name, *args)
        creator: Callable[..., webrtc.Event | None] = getattr(self, creator_name)
        return creator(*args)

    def _negotiation_needed_event(self, event_id: int) -> webrtc.Event | None:
        # not while operations are chained, but once they're done, if it's still needed
        if self._chain is not None and self._chain.busy:
            self._deferred_negotiation_id = event_id
            return None
        if not self._native_obj._shouldFireNegotiationNeededEvent(event_id):
            return None
        return Event('negotiationneeded')

    @staticmethod
    def _ice_candidate_event(candidate: wrtc.IceCandidateInit | None = None) -> webrtc.Event:
        if candidate is None:
            return RTCPeerConnectionIceEvent('icecandidate')
        kwargs = candidate.kwargs()
        return RTCPeerConnectionIceEvent(
            'icecandidate', RTCPeerConnectionIceEventInit(RTCIceCandidate(**kwargs), kwargs['url'])
        )

    @staticmethod
    def _ice_candidate_error_event(*native: object) -> webrtc.Event:
        address, port, url, error_code, error_text = cast('tuple[str, int, str, int, str]', native)
        return RTCPeerConnectionIceErrorEvent(
            'icecandidateerror',
            RTCPeerConnectionIceErrorEventInit(
                error_code, address if address != '' else None, port if port != 0 else None, url, error_text
            ),
        )

    @staticmethod
    def _data_channel_event(channel: wrtc.RTCDataChannel) -> webrtc.Event:
        return RTCDataChannelEvent('datachannel', RTCDataChannelEventInit(webrtc.RTCDataChannel._wrap(channel)))

    @staticmethod
    def _track_event(
        transceiver: wrtc.RTCRtpTransceiver, receiver: wrtc.RTCRtpReceiver, streams: list[wrtc.MediaStream]
    ) -> webrtc.Event:
        wrapped_receiver = webrtc.RTCRtpReceiver._wrap(receiver)
        return RTCTrackEvent(
            'track',
            RTCTrackEventInit(
                wrapped_receiver,
                wrapped_receiver.track,
                webrtc.RTCRtpTransceiver._wrap(transceiver),
                webrtc.MediaStream._wrap_many(streams),
            ),
        )

    def _apply_legacy_offer_option(self, kind: webrtc.MediaType, *, receive: bool | None) -> None:
        """Applies ``offer_to_receive_audio`` or ``offer_to_receive_video`` of :meth:`create_offer`.

        It follows the specification, which defines them in terms of transceivers.
        """
        if receive is None:
            return
        directions = RTCRtpTransceiverDirection
        transceivers = [t for t in self.get_transceivers() if not t.stopped and t.receiver.track.kind == kind]
        if not receive:
            for transceiver in transceivers:
                if transceiver.direction == directions.sendrecv:
                    transceiver.direction = directions.sendonly
                elif transceiver.direction == directions.recvonly:
                    transceiver.direction = directions.inactive
        elif not any(t.direction in {directions.sendrecv, directions.recvonly} for t in transceivers):
            _ = self.add_transceiver(kind, RTCRtpTransceiverInit(direction=directions.recvonly))

    def _completed_description(self) -> None:
        """The success task of setting a description."""
        # the descriptions as the operation left them, candidates gathered since come with their events
        self._native_obj._applyDescriptions()
        # parameters returned before can't be set anymore
        for sender in self._native_obj.getSenders():
            sender._expireParameters()

    async def create_offer(self, options: webrtc.RTCOfferOptions | None = None) -> webrtc.RTCSessionDescriptionInit:
        """Creates an offer that starts a negotiation or renegotiates one.

        The offer describes the transceivers and data channels of the connection, with the codecs it supports and
        the ICE candidates gathered so far. It isn't applied until it's passed to :meth:`set_local_description`.
        See :mdn:`RTCPeerConnection/createOffer`.

        Args:
            options (:obj:`webrtc.RTCOfferOptions`, optional): How to create the offer.

        Returns:
            :obj:`webrtc.RTCSessionDescriptionInit`: The offer, to set with :meth:`set_local_description`.

        Raises:
            webrtc.InvalidStateError: If the signaling state isn't ``stable`` or ``have-local-offer``,
                or the connection is closed.
        """
        async with self._operation():
            self._check_state('create an offer', RTCSignalingState.stable, RTCSignalingState.have_local_offer)
            options = options if options is not None else RTCOfferOptions()
            self._apply_legacy_offer_option(MediaType.audio, receive=options.offer_to_receive_audio)
            self._apply_legacy_offer_option(MediaType.video, receive=options.offer_to_receive_video)
            await later()
            return _init_of(await call_native(self._native_obj.createOffer, options.ice_restart))

    async def create_answer(self, options: webrtc.RTCAnswerOptions | None = None) -> webrtc.RTCSessionDescriptionInit:
        """Creates an answer to the offer set as the remote description.

        It isn't applied until it's passed to :meth:`set_local_description`.
        See :mdn:`RTCPeerConnection/createAnswer`.

        Args:
            options (:obj:`webrtc.RTCAnswerOptions`, optional): How to create the answer.

        Returns:
            :obj:`webrtc.RTCSessionDescriptionInit`: The answer, to set with :meth:`set_local_description`.

        Raises:
            TypeError: If the options aren't an :obj:`webrtc.RTCAnswerOptions`.
            webrtc.InvalidStateError: If the connection is closed or has no remote offer.
        """
        # the options have no members yet, only their type is checked
        if options is not None and not isinstance(options, RTCAnswerOptions):
            msg = f'options must be an RTCAnswerOptions, not {type(options).__name__}'
            raise TypeError(msg)
        async with self._operation():
            self._check_state(
                'create an answer', RTCSignalingState.have_remote_offer, RTCSignalingState.have_local_pranswer
            )
            await later()
            return _init_of(await call_native(self._native_obj.createAnswer))

    async def set_local_description(
        self, description: _Description | RTCLocalSessionDescriptionInit | None = None
    ) -> None:
        """Applies a local session description, which starts ICE gathering.

        See :mdn:`RTCPeerConnection/setLocalDescription`.

        Args:
            description (:obj:`webrtc.RTCSessionDescription`, optional): The description, as returned by
                :meth:`create_offer` or :meth:`create_answer`, or a ``rollback`` one. An
                :obj:`webrtc.RTCSessionDescriptionInit` or :obj:`webrtc.RTCLocalSessionDescriptionInit` is accepted
                too. Without it, or without a type and an SDP, the offer or the answer the signaling state calls for
                is created and set.

        Raises:
            webrtc.InvalidStateError: If the type doesn't match the signaling state, or the connection is closed.
            webrtc.InvalidModificationError: If the SDP isn't the one :meth:`create_offer`
                or :meth:`create_answer` returned last.
            webrtc.RTCError: If the SDP can't be parsed (``sdp_syntax_error``).
            TypeError: If the description has an SDP but no type, or is neither of the accepted types.
        """
        init = _description_init(description, allow_implicit=True)
        async with self._operation():
            allowed = _LOCAL_DESCRIPTION_STATES[init.type] if init is not None else ()
            self._check_state('set the local description', *allowed)
            await later()
            await call_native(self._native_obj.setLocalDescription, init)
            self._completed_description()

    async def set_remote_description(
        self, description: webrtc.RTCSessionDescriptionInit | webrtc.RTCSessionDescription
    ) -> None:
        """Applies an offer, an answer or a rollback received from the remote peer.

        An offer set while there's a local offer rolls the local one back first. Remote tracks the description
        adds are announced with ``track`` events. See :mdn:`RTCPeerConnection/setRemoteDescription`.

        Args:
            description (:obj:`webrtc.RTCSessionDescriptionInit`): The description received from the remote peer,
                like one from :meth:`webrtc.RTCSessionDescriptionInit.from_json`. An
                :obj:`webrtc.RTCSessionDescription` is accepted too.

        Raises:
            webrtc.InvalidStateError: If the type doesn't match the signaling state, or the connection is closed.
            webrtc.RTCError: If the SDP can't be parsed (``sdp_syntax_error``).
            webrtc.InvalidAccessError: If the description can't be applied.
            TypeError: If the description is neither of the accepted types.
        """
        init = _description_init(description, allow_implicit=False)
        async with self._operation():
            self._check_state('set the remote description', *_REMOTE_DESCRIPTION_STATES.get(init.type, ()))
            await later()
            await call_native(self._native_obj.setRemoteDescription, init)
            self._completed_description()

    def add_track(self, track: webrtc.MediaStreamTrack, *streams: webrtc.MediaStream) -> webrtc.RTCRtpSender:
        """Starts sending a track to the remote peer, from the next negotiation.

        If there's an unused transceiver of the same kind, it's reused. Otherwise a new one is added.
        See :mdn:`RTCPeerConnection/addTrack`.

        Args:
            track (:obj:`webrtc.MediaStreamTrack`): The track to send.
            *streams (:obj:`webrtc.MediaStream`): The local streams the remote peer receives the track in.

        Returns:
            :obj:`webrtc.RTCRtpSender`: The sender of the track.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
            webrtc.InvalidAccessError: If a sender of the connection already has the track.
        """
        native_streams = [stream._native_obj for stream in streams] if len(streams) > 0 else None
        sender = self._native_obj.addTrack(track._native_obj, native_streams)

        return webrtc.RTCRtpSender._wrap(sender)

    def add_transceiver(
        self,
        track_or_kind: webrtc.MediaStreamTrack | webrtc.MediaType | webrtc.MediaTypeValue,
        init: webrtc.RTCRtpTransceiverInit | None = None,
    ) -> webrtc.RTCRtpTransceiver:
        """Adds a new transceiver, negotiated with the next offer.

        See :mdn:`RTCPeerConnection/addTransceiver`.

        Args:
            track_or_kind (:obj:`webrtc.MediaStreamTrack` or :obj:`webrtc.MediaType`): The track the sender of the
                transceiver sends, or the kind of media (``'audio'`` or ``'video'``) for a transceiver without one.
            init (:obj:`webrtc.RTCRtpTransceiverInit`, optional): The options of the new transceiver.

        Returns:
            :obj:`webrtc.RTCRtpTransceiver`: The new transceiver.

        Raises:
            TypeError: If the kind is neither audio nor video.
            ValueError: If a ``rid`` of the send encodings is invalid, or missing or repeated with several
                encodings.
            webrtc.OperationError: If the codec of a send encoding can't be sent.
            webrtc.InvalidStateError: If the connection is closed.
        """
        kind = track_or_kind.kind if isinstance(track_or_kind, webrtc.MediaStreamTrack) else track_or_kind
        if kind not in {MediaType.audio, MediaType.video}:
            msg = f'{kind!r} is not a kind of track'
            raise TypeError(msg)
        native_init = None
        if init is not None:
            _check_send_encodings(init.send_encodings, kind)
            native_init = init._to_native([encoding._for_kind(kind) for encoding in init.send_encodings])

        if isinstance(track_or_kind, webrtc.MediaStreamTrack):
            transceiver = self._native_obj.addTransceiver(track_or_kind._native_obj, native_init)
        else:
            transceiver = self._native_obj.addTransceiver(track_or_kind, native_init)

        return webrtc.RTCRtpTransceiver._wrap(transceiver)

    def get_transceivers(self) -> list[webrtc.RTCRtpTransceiver]:
        """Returns the transceivers of the connection, in the order they were added.

        See :mdn:`RTCPeerConnection/getTransceivers`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpTransceiver`: The transceivers.
        """
        return webrtc.RTCRtpTransceiver._wrap_many(self._native_obj.getTransceivers())

    def get_senders(self) -> list[webrtc.RTCRtpSender]:
        """Returns the senders of the transceivers of the connection, one per transceiver.

        See :mdn:`RTCPeerConnection/getSenders`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpSender`: The senders, including the ones without a track.
        """
        return webrtc.RTCRtpSender._wrap_many(self._native_obj.getSenders())

    def get_receivers(self) -> list[webrtc.RTCRtpReceiver]:
        """Returns the receivers of the transceivers of the connection, one per transceiver.

        See :mdn:`RTCPeerConnection/getReceivers`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpReceiver`: The receivers.
        """
        return webrtc.RTCRtpReceiver._wrap_many(self._native_obj.getReceivers())

    def remove_track(self, sender: webrtc.RTCRtpSender) -> None:
        """Stops sending the track of a sender, from the next negotiation. The sender stays in :meth:`get_senders`.

        Does nothing if the sender has no track. See :mdn:`RTCPeerConnection/removeTrack`.

        Args:
            sender (:obj:`webrtc.RTCRtpSender`): A sender of this connection.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
            webrtc.InvalidAccessError: If the sender belongs to another connection.
        """
        self._native_obj.removeTrack(sender._native_obj)

    async def add_ice_candidate(
        self, candidate: webrtc.RTCIceCandidateInit | webrtc.RTCIceCandidate | None = None
    ) -> None:
        """Adds a candidate received from the remote peer to the remote description.

        See :mdn:`RTCPeerConnection/addIceCandidate`.

        Args:
            candidate (:obj:`webrtc.RTCIceCandidateInit` or :obj:`webrtc.RTCIceCandidate`, optional): The
                candidate, like one from :meth:`webrtc.RTCIceCandidateInit.from_json`. An empty ``candidate``,
                or :obj:`None`, means the end of candidates.

        Raises:
            TypeError: If a non-empty candidate has neither ``sdp_mid`` nor ``sdp_m_line_index``.
            webrtc.InvalidStateError: If there's no remote description, or the connection is closed.
            webrtc.OperationError: If the candidate can't be parsed or doesn't match a media section.
        """
        if candidate is None:
            candidate_str, sdp_mid, sdp_m_line_index, ufrag = '', None, None, None
        else:
            candidate_str, sdp_mid, sdp_m_line_index, ufrag = RTCIceCandidate._members_of(candidate)
        if candidate_str != '' and sdp_mid is None and sdp_m_line_index is None:
            msg = 'sdp_mid and sdp_m_line_index are both None'
            raise TypeError(msg)

        async with self._operation():
            self._check_state('add an ICE candidate')
            if self.remote_description is None:
                msg = 'A candidate can only be added once there is a remote description'
                raise InvalidStateError(msg)
            await later()
            await call_native(self._native_obj.addIceCandidate, candidate_str, sdp_mid, sdp_m_line_index, ufrag)

    def create_data_channel(
        self, label: str, data_channel_dict: webrtc.RTCDataChannelInit | None = None
    ) -> webrtc.RTCDataChannel:
        """Creates a channel to exchange messages with the remote peer.

        The first channel needs a negotiation, which adds the SCTP transport. A ``negotiated`` channel isn't
        announced to the remote peer, so both peers create it with the same ``id``.
        See :mdn:`RTCPeerConnection/createDataChannel`.

        Args:
            label (:obj:`str`): The name of the channel, up to 65535 bytes in UTF-8.
            data_channel_dict (:obj:`webrtc.RTCDataChannelInit`, optional): How to create the channel.

        Returns:
            :obj:`webrtc.RTCDataChannel`: The channel.

        Raises:
            ValueError: If the label or an option is out of range, or both ``max_packet_life_time`` and
                ``max_retransmits`` are set, or ``negotiated`` is set without ``id``.
            webrtc.InvalidStateError: If the connection is closed.
            webrtc.OperationError: If the ``id`` is in use, or no id is left.
        """
        init = data_channel_dict if data_channel_dict is not None else RTCDataChannelInit()
        check_utf8_length('label', label)
        init._check()
        native = self._native_obj.createDataChannel(
            label,
            init.ordered,
            init.max_packet_life_time,
            init.max_retransmits,
            init.protocol,
            init.negotiated,
            init.id if init.negotiated else None,
            init.priority,
        )
        channel = webrtc.RTCDataChannel._wrap(native)
        # handlers registered in this iteration of the loop get the first events
        if not TaskQueue.post_to_running(native._release):
            native._release()
        return channel

    async def get_stats(self, selector: webrtc.MediaStreamTrack | None = None) -> webrtc.RTCStatsReport:
        """Collects the stats of the connection, or of the sender or the receiver of a track.

        See :mdn:`RTCPeerConnection/getStats`.

        Args:
            selector (:obj:`webrtc.MediaStreamTrack`, optional): A track of exactly one sender or receiver
                of the connection. Only the stats of that sender or receiver are collected.

        Returns:
            :obj:`webrtc.RTCStatsReport`: The stats.

        Raises:
            webrtc.InvalidAccessError: If no sender or receiver, or more than one, has the track.
            webrtc.InvalidStateError: If the connection is closed.
        """
        if selector is not None:
            matches = [s for s in self.get_senders() if s.track == selector]
            matches += [r for r in self.get_receivers() if r.track == selector]
            if len(matches) != 1:
                msg = f'{len(matches)} senders and receivers have the track, not exactly one'
                raise InvalidAccessError(msg)
            return await matches[0].get_stats()
        return RTCStatsReport._from_native(await call_native(self._native_obj.getStats), self.get_receivers())

    @staticmethod
    async def generate_certificate(keygen_algorithm: AlgorithmIdentifier) -> webrtc.RTCCertificate:
        """Generates a key and a self-signed certificate on a worker thread, for :attr:`RTCConfiguration.certificates`.

        See :mdn:`RTCPeerConnection/generateCertificate_static`.

        Args:
            keygen_algorithm (:obj:`str` or :obj:`webrtc.Algorithm`): A WebCrypto algorithm: ``'ECDSA'``
                (with the P-256 curve), an :obj:`webrtc.EcKeyGenParams`, or an :obj:`webrtc.RsaHashedKeyGenParams`
                like ``RsaHashedKeyGenParams('RSASSA-PKCS1-v1_5', modulus_length=2048,
                public_exponent=bytes([1, 0, 1]), hash='SHA-256')``. Its ``expires`` sets for how many milliseconds
                the certificate is valid, up to a year (30 days by default).

        Returns:
            :obj:`webrtc.RTCCertificate`: The certificate.

        Raises:
            webrtc.NotSupportedError: If the algorithm isn't supported.
            TypeError: If ``expires`` isn't an unsigned 64-bit integer.
        """
        return await RTCCertificate._generate(keygen_algorithm)

    def get_configuration(self) -> webrtc.RTCConfiguration:
        """Returns the configuration of the connection, as it was last set.

        The certificates are the ones in use, generated or given. See :mdn:`RTCPeerConnection/getConfiguration`.

        Returns:
            :obj:`webrtc.RTCConfiguration`: A copy of the configuration. Changing it doesn't affect the
            connection.
        """
        return RTCConfiguration._from_native(self._native_obj.getConfiguration())

    def set_configuration(self, configuration: webrtc.RTCConfiguration | None = None) -> None:
        """Replaces the configuration of the connection. Members that aren't set get their default values.

        Changed ICE servers or ICE transport policy apply to the candidates gathered next, like after
        :meth:`restart_ice`. See :mdn:`RTCPeerConnection/setConfiguration`.

        Args:
            configuration (:obj:`webrtc.RTCConfiguration`, optional): The new configuration.

        Raises:
            webrtc.InvalidStateError: If the connection is closed.
            webrtc.InvalidModificationError: If a member that can't be changed differs, like
                :attr:`webrtc.RTCConfiguration.bundle_policy` or
                :attr:`webrtc.RTCConfiguration.always_negotiate_data_channels`.
            webrtc.InvalidSyntaxError: If an ICE server URL is invalid.
            webrtc.InvalidAccessError: If a TURN server has no credentials, or a certificate has expired.
            webrtc.NotSupportedError: If a TURN server has an OAuth credential.
            ValueError: If a member of the configuration is out of range.
            TypeError: If a member of the configuration has a wrong type, or a value its enum doesn't have.
        """
        if configuration is None:
            configuration = RTCConfiguration()
        self._native_obj.setConfiguration(configuration._to_native())

    def restart_ice(self) -> None:
        """Requests an ICE restart, with new credentials and candidates, from the next negotiation on either side.

        It leads to a ``negotiationneeded`` event. It does nothing before the first local description, since that one
        already has new credentials, or once the connection is closed. See :mdn:`RTCPeerConnection/restartIce`.
        """
        self._native_obj.restartIce()

    def close(self) -> None:
        """Closes the connection for good, stopping its transceivers and data channels.

        Remote tracks end, the states become ``closed`` without events, and no event is emitted afterwards.
        Does nothing if it's already closed. See :mdn:`RTCPeerConnection/close`.
        """
        self._native_obj.close()

    @property
    def sctp(self) -> webrtc.RTCSctpTransport | None:
        """:obj:`webrtc.RTCSctpTransport`, optional: The transport of the data channels.

        It's :obj:`None` until the data channels are negotiated.
        See :mdn:`RTCPeerConnection/sctp`.
        """
        return webrtc.RTCSctpTransport._wrap_optional(self._native_obj.sctp)

    @property
    def local_description(self) -> webrtc.RTCSessionDescription | None:
        """:obj:`webrtc.RTCSessionDescription`, optional: The pending local description, or else the current one.

        :obj:`None` until one is set. It includes the ICE candidates gathered so far.
        See :mdn:`RTCPeerConnection/localDescription`.
        """
        return RTCSessionDescription._wrap_optional(self._native_obj.localDescription)

    @property
    def remote_description(self) -> webrtc.RTCSessionDescription | None:
        """:obj:`webrtc.RTCSessionDescription`, optional: The pending remote description, or else the current one.

        :obj:`None` until one is set. It includes the candidates added with :meth:`add_ice_candidate`.
        See :mdn:`RTCPeerConnection/remoteDescription`.
        """
        return RTCSessionDescription._wrap_optional(self._native_obj.remoteDescription)

    @property
    def current_local_description(self) -> webrtc.RTCSessionDescription | None:
        """:obj:`webrtc.RTCSessionDescription`, optional: The local description of the last completed negotiation.

        See :mdn:`RTCPeerConnection/currentLocalDescription`.
        """
        return RTCSessionDescription._wrap_optional(self._native_obj.currentLocalDescription)

    @property
    def current_remote_description(self) -> webrtc.RTCSessionDescription | None:
        """:obj:`webrtc.RTCSessionDescription`, optional: The remote description of the last completed negotiation.

        See :mdn:`RTCPeerConnection/currentRemoteDescription`.
        """
        return RTCSessionDescription._wrap_optional(self._native_obj.currentRemoteDescription)

    @property
    def pending_local_description(self) -> webrtc.RTCSessionDescription | None:
        """:obj:`webrtc.RTCSessionDescription`, optional: The local description of a negotiation in progress.

        See :mdn:`RTCPeerConnection/pendingLocalDescription`.
        """
        return RTCSessionDescription._wrap_optional(self._native_obj.pendingLocalDescription)

    @property
    def pending_remote_description(self) -> webrtc.RTCSessionDescription | None:
        """:obj:`webrtc.RTCSessionDescription`, optional: The remote description of a negotiation in progress.

        See :mdn:`RTCPeerConnection/pendingRemoteDescription`.
        """
        return RTCSessionDescription._wrap_optional(self._native_obj.pendingRemoteDescription)

    @property
    def can_trickle_ice_candidates(self) -> bool | None:
        """:obj:`bool`, optional: Whether the remote peer takes candidates one by one (trickle ICE).

        :obj:`None` until there's a remote description. See :mdn:`RTCPeerConnection/canTrickleIceCandidates`.
        """
        return self._native_obj.canTrickleIceCandidates

    @property
    def connection_state(self) -> webrtc.RTCPeerConnectionState:
        """:obj:`webrtc.RTCPeerConnectionState`: The overall state of the ICE and DTLS transports of the connection.

        See :mdn:`RTCPeerConnection/connectionState`.
        """
        return self._native_obj.connectionState

    @property
    def signaling_state(self) -> webrtc.RTCSignalingState:
        """:obj:`webrtc.RTCSignalingState`: Where the connection is in the offer/answer exchange.

        See :mdn:`RTCPeerConnection/signalingState`.
        """
        return self._native_obj.signalingState

    @property
    def ice_connection_state(self) -> webrtc.RTCIceConnectionState:
        """:obj:`webrtc.RTCIceConnectionState`: The overall state of the ICE transports of the connection.

        See :mdn:`RTCPeerConnection/iceConnectionState`.
        """
        return self._native_obj.iceConnectionState

    @property
    def ice_gathering_state(self) -> webrtc.RTCIceGatheringState:
        """:obj:`webrtc.RTCIceGatheringState`: The overall candidate gathering state of the ICE transports.

        See :mdn:`RTCPeerConnection/iceGatheringState`.
        """
        return self._native_obj.iceGatheringState

    #: Alias for :attr:`local_description`
    localDescription = local_description
    #: Alias for :attr:`remote_description`
    remoteDescription = remote_description
    #: Alias for :attr:`current_local_description`
    currentLocalDescription = current_local_description
    #: Alias for :attr:`current_remote_description`
    currentRemoteDescription = current_remote_description
    #: Alias for :attr:`pending_local_description`
    pendingLocalDescription = pending_local_description
    #: Alias for :attr:`pending_remote_description`
    pendingRemoteDescription = pending_remote_description
    #: Alias for :attr:`can_trickle_ice_candidates`
    canTrickleIceCandidates = can_trickle_ice_candidates
    #: Alias for :attr:`connection_state`
    connectionState = connection_state
    #: Alias for :attr:`signaling_state`
    signalingState = signaling_state
    #: Alias for :attr:`ice_connection_state`
    iceConnectionState = ice_connection_state
    #: Alias for :attr:`ice_gathering_state`
    iceGatheringState = ice_gathering_state
    #: Alias for :attr:`create_offer`
    createOffer = create_offer
    #: Alias for :attr:`create_answer`
    createAnswer = create_answer
    #: Alias for :attr:`set_local_description`
    setLocalDescription = set_local_description
    #: Alias for :attr:`set_remote_description`
    setRemoteDescription = set_remote_description
    #: Alias for :attr:`add_track`
    addTrack = add_track
    #: Alias for :attr:`add_transceiver`
    addTransceiver = add_transceiver
    #: Alias for :attr:`get_transceivers`
    getTransceivers = get_transceivers
    #: Alias for :attr:`get_senders`
    getSenders = get_senders
    #: Alias for :attr:`get_receivers`
    getReceivers = get_receivers
    #: Alias for :attr:`remove_track`
    removeTrack = remove_track
    #: Alias for :attr:`restart_ice`
    restartIce = restart_ice
    #: Alias for :attr:`add_ice_candidate`
    addIceCandidate = add_ice_candidate
    #: Alias for :attr:`create_data_channel`
    createDataChannel = create_data_channel
    #: Alias for :attr:`get_stats`
    getStats = get_stats
    #: Alias for :attr:`generate_certificate`
    generateCertificate = generate_certificate
    #: Alias for :attr:`get_configuration`
    getConfiguration = get_configuration
    #: Alias for :attr:`set_configuration`
    setConfiguration = set_configuration


@overload
def _description_init(
    description: _Description, *, allow_implicit: Literal[False]
) -> wrtc.RTCSessionDescriptionInit: ...


@overload
def _description_init(
    description: _Description | RTCLocalSessionDescriptionInit | None, *, allow_implicit: Literal[True]
) -> wrtc.RTCSessionDescriptionInit | None: ...


def _description_init(
    description: _Description | RTCLocalSessionDescriptionInit | None, *, allow_implicit: bool
) -> wrtc.RTCSessionDescriptionInit | None:
    """The native RTCSessionDescriptionInit of a description, or :obj:`None` for an implicit one."""
    if isinstance(description, RTCSessionDescription):
        return description._native_obj.init
    if allow_implicit and isinstance(description, RTCLocalSessionDescriptionInit):
        if description.type is None and description.sdp != '':
            msg = 'the type of a description is required'
            raise TypeError(msg)
        description = None if description.type is None else RTCSessionDescriptionInit(description.type, description.sdp)
    if isinstance(description, RTCSessionDescriptionInit):
        return description._to_native()
    if allow_implicit and description is None:
        return None
    msg = f'expected an RTCSessionDescription, not {type(description).__name__}'
    raise TypeError(msg)


def _init_of(description: wrtc.RTCSessionDescription) -> webrtc.RTCSessionDescriptionInit:
    return RTCSessionDescriptionInit(description.type, description.sdp)


def _check_send_encodings(encodings: list[webrtc.RTCRtpEncodingParameters], kind: webrtc.MediaType) -> None:
    """Validates the send encodings of a new transceiver, as the specification requires.

    Raises:
        ValueError: If a ``rid`` is invalid, or missing or repeated with several encodings.
        webrtc.OperationError: If the codec of an encoding can't be sent.
    """
    rids = [e.rid for e in encodings]
    for rid in rids:
        if rid is not None and _RID.fullmatch(rid) is None:
            msg = f'{rid!r} is not a valid rid: 1 to 16 letters and digits'
            raise ValueError(msg)
    if len(encodings) > 1 and (None in rids or len(set(rids)) != len(rids)):
        msg = 'every encoding needs a distinct rid when there are several'
        raise ValueError(msg)

    codecs = [e.codec for e in encodings if e.codec is not None]
    if len(codecs) > 0:
        capabilities = webrtc.RTCRtpSender.get_capabilities(kind)
        supported: list[RTCRtpCodec] = capabilities.codecs if capabilities is not None else []
        for codec in codecs:
            if not any(RTCRtpCodec._matches(c, codec) for c in supported):
                msg = f'{codec.mime_type} can not be sent'
                raise OperationError(msg)
