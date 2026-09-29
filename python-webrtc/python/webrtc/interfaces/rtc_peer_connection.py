#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio
import dataclasses
import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Union

from webrtc import (
    Event,
    InvalidAccessError,
    InvalidStateError,
    MediaType,
    OperationError,
    RTCCertificate,
    RTCConfiguration,
    RTCDataChannelEvent,
    RTCIceCandidate,
    RTCPeerConnectionIceErrorEvent,
    RTCPeerConnectionIceEvent,
    RTCRtpCodec,
    RTCRtpEncodingParameters,
    RTCSdpType,
    RTCSessionDescription,
    RTCSessionDescriptionInit,
    RTCSignalingState,
    RTCStatsReport,
    RTCTrackEvent,
    RtpTransceiverInit,
    TransceiverDirection,
    WebRTCObject,
    wrtc,
)
from webrtc.utils.callbacks_to_async import to_async
from webrtc.utils.events import EventTarget
from webrtc.utils.names import snake_case
from webrtc.utils.operations import OperationsChain, later
from webrtc.utils.task_queue import TaskQueue

if TYPE_CHECKING:
    import webrtc

#: A description, as the methods that set one take it
_Description = Union[RTCSessionDescription, RTCSessionDescriptionInit, Dict[str, Any]]

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


class RTCPeerConnection(WebRTCObject, EventTarget):
    """The RTCPeerConnection interface represents a WebRTC connection between the local computer and a remote peer.
    It provides methods to connect to a remote peer, maintain and monitor the connection, and close the connection
    once it's no longer needed.

    Events (see :meth:`on`):
        ``negotiationneeded`` (:obj:`webrtc.Event`): Negotiation (an offer/answer exchange) is needed.
        ``icecandidate`` (:obj:`webrtc.RTCPeerConnectionIceEvent`): A local ICE candidate was gathered, to be sent
        to the remote peer. Its ``candidate`` is :obj:`None` once gathering is complete.
        ``icecandidateerror`` (:obj:`webrtc.RTCPeerConnectionIceErrorEvent`): A STUN or TURN server failed.
        ``signalingstatechange``, ``iceconnectionstatechange``, ``icegatheringstatechange``,
        ``connectionstatechange`` (:obj:`webrtc.Event`): :attr:`signaling_state`, :attr:`ice_connection_state`,
        :attr:`ice_gathering_state` or :attr:`connection_state` changed.
        ``track`` (:obj:`webrtc.RTCTrackEvent`): A remote track was negotiated.
        ``datachannel`` (:obj:`webrtc.RTCDataChannelEvent`): The remote peer created a data channel.

    A closed connection emits no events.

    Args:
        configuration (:obj:`webrtc.RTCConfiguration`, optional): The configuration of the connection.

    Raises:
        :obj:`webrtc.InvalidSyntaxError`: If an ICE server URL is invalid.
        :obj:`webrtc.InvalidAccessError`: If a TURN server has no credentials.
        :obj:`ValueError`: If a member of the configuration is out of range.
        :obj:`TypeError`: If a member of the configuration has a wrong type, or a value its enum doesn't have.
    """

    _class = wrtc.RTCPeerConnection
    _events = (
        'negotiationneeded',
        'icecandidate',
        'icecandidateerror',
        'signalingstatechange',
        'iceconnectionstatechange',
        'icegatheringstatechange',
        'connectionstatechange',
        'track',
        'datachannel',
    )

    # the native method that surfaces the state of each state event
    _STATE_EVENTS = {
        'signalingstatechange': '_surfaceSignalingState',
        'iceconnectionstatechange': '_surfaceIceConnectionState',
        'icegatheringstatechange': '_surfaceIceGatheringState',
        'connectionstatechange': '_surfaceConnectionState',
    }

    #: The operations chain, created on first use (a wrapper of a native connection doesn't run __init__)
    _chain: Optional[OperationsChain] = None
    #: The id of a negotiationneeded event that waits for the operations chain to empty
    _deferred_negotiation_id: Optional[int] = None

    def __init__(self, configuration: Optional['webrtc.RTCConfiguration'] = None):
        super().__init__(self._class(configuration._to_native() if configuration is not None else None))
        self._attach()

    @classmethod
    def _wrap(cls, item) -> 'RTCPeerConnection':
        # the wrapper that owns the listeners (and so the operations chain), when there is one
        listeners = item._listeners
        if listeners is not None and isinstance(listeners.target, cls):
            return listeners.target
        # not attached, so the connection object of the application gets the listeners once it registers a handler
        connection = cls.__new__(cls)
        WebRTCObject.__init__(connection, item)
        return connection

    def _operation(self):
        """Chains an operation (like setting a description) after the ones that are running
        (see :obj:`webrtc.utils.operations.OperationsChain`)."""
        if self._chain is None:
            self._chain = OperationsChain(self._chain_emptied)
        return self._chain.operation()

    def _chain_emptied(self) -> None:
        # negotiationneeded fires now, if it's still needed
        if self._deferred_negotiation_id is not None:
            event_id, self._deferred_negotiation_id = self._deferred_negotiation_id, None
            asyncio.get_running_loop().call_soon(self._dispatch, 'negotiationneeded', event_id)

    def _check_state(self, operation: str, *allowed: RTCSignalingState) -> None:
        """Raises :obj:`webrtc.InvalidStateError` if the connection is closed, or not in one of the allowed states
        when they're given."""
        state = self.signaling_state
        if state == RTCSignalingState.closed:
            raise InvalidStateError(f"Can not {operation}: the RTCPeerConnection's signalingState is 'closed'")
        if allowed and state not in allowed:
            raise InvalidStateError(f'Can not {operation} in the {state} signaling state')

    def _on_event(self, name: str, *args):
        from webrtc import RTCDataChannel

        if name == '_gatheringcomplete':
            transports, state = args
            self._complete_gathering(transports, state)
            return
        # the state attributes change along with their events
        surface = self._STATE_EVENTS.get(name)
        if surface is not None:
            state = args[0]
            getattr(self._native_obj, surface)(state)
        if name == 'signalingstatechange':
            _, descriptions = args
            # the descriptions as the change left them
            self._native_obj._applyDescriptions(descriptions)
        elif name in ('icecandidate', 'icegatheringstatechange'):
            # the local description gains candidates (and loses pending ones) along with these events
            self._native_obj._refreshDescriptions()
        elif name == 'datachannel':
            (channel,) = args
            RTCDataChannel._wrap(channel)
            # the events of the channel follow the handlers of this one
            TaskQueue.post_to_running(channel._release)

    def _complete_gathering(
        self, transports: List['wrtc.RTCIceTransport'], state: 'webrtc.RTCIceGatheringState'
    ) -> None:
        """The ICE transports and the connection complete gathering, and the candidates end, in a single task:
        every handler sees all of them complete."""
        from webrtc import RTCIceTransport

        ice_transports = RTCIceTransport._wrap_many(transports)
        for ice_transport in ice_transports:
            ice_transport._native_obj._surfaceGatheringState(state)
        self._native_obj._surfaceIceGatheringState(state)
        self._native_obj._refreshDescriptions()
        for ice_transport in ice_transports:
            ice_transport._dispatch('gatheringstatechange', state)
        self._dispatch('icegatheringstatechange', state)
        # the end of candidates is an icecandidate event without a candidate
        self._dispatch('icecandidate')

    def _create_event(self, name: str, *args):
        from webrtc import RTCDataChannel

        # events queued before close() aren't delivered after it
        if self._native_obj.signalingState == RTCSignalingState.closed:
            return None

        if name == 'negotiationneeded':
            (event_id,) = args
            return self._negotiation_needed_event(event_id)
        if name == 'icecandidate':
            return self._ice_candidate_event(*args)
        if name == 'icecandidateerror':
            address, port, url, error_code, error_text = args
            return RTCPeerConnectionIceErrorEvent(
                name, address or None, port or None, url, error_code, error_text, target=self
            )
        if name == 'datachannel':
            (channel,) = args
            return RTCDataChannelEvent(name, RTCDataChannel._wrap(channel), target=self)
        if name == 'track':
            transceiver, receiver, streams = args
            return self._track_event(transceiver, receiver, streams)
        return super()._create_event(name, *args)

    def _negotiation_needed_event(self, event_id: int) -> Optional['webrtc.Event']:
        # not while operations are chained, but once they're done, if it's still needed
        if self._chain is not None and self._chain.busy:
            self._deferred_negotiation_id = event_id
            return None
        if not self._native_obj._shouldFireNegotiationNeededEvent(event_id):
            return None
        return Event('negotiationneeded', self)

    def _ice_candidate_event(self, candidate: Optional['wrtc.IceCandidateInit'] = None) -> 'webrtc.Event':
        if candidate is None:
            return RTCPeerConnectionIceEvent('icecandidate', None, None, target=self)
        kwargs = candidate.kwargs()
        return RTCPeerConnectionIceEvent('icecandidate', RTCIceCandidate(**kwargs), kwargs['url'], target=self)

    def _track_event(
        self, transceiver: 'wrtc.RTCRtpTransceiver', receiver: 'wrtc.RTCRtpReceiver', streams: List['wrtc.MediaStream']
    ) -> 'webrtc.Event':
        from webrtc import MediaStream, RTCRtpReceiver, RTCRtpTransceiver

        receiver = RTCRtpReceiver._wrap(receiver)
        return RTCTrackEvent(
            'track',
            receiver,
            receiver.track,
            MediaStream._wrap_many(streams),
            RTCRtpTransceiver._wrap(transceiver),
            target=self,
        )

    def _apply_legacy_offer_option(self, kind: 'webrtc.MediaType', receive: Optional[bool]) -> None:
        """``offer_to_receive_audio`` or ``offer_to_receive_video`` of :meth:`create_offer`, as the specification
        defines them in terms of transceivers."""
        if receive is None:
            return
        directions = TransceiverDirection
        transceivers = [t for t in self.get_transceivers() if not t.stopped and t.receiver.track.kind == kind]
        if not receive:
            for transceiver in transceivers:
                if transceiver.direction == directions.sendrecv:
                    transceiver.direction = directions.sendonly
                elif transceiver.direction == directions.recvonly:
                    transceiver.direction = directions.inactive
        elif not any(t.direction in (directions.sendrecv, directions.recvonly) for t in transceivers):
            self.add_transceiver(kind, RtpTransceiverInit(direction=directions.recvonly))

    def _completed_description(self) -> None:
        """The success task of setting a description."""
        # the descriptions as the operation left them, candidates gathered since come with their events
        self._native_obj._applyDescriptions()
        # parameters returned before can't be set anymore
        for sender in self._native_obj.getSenders():
            sender._expireParameters()

    async def create_offer(
        self,
        *,
        ice_restart: bool = False,
        offer_to_receive_audio: Optional[bool] = None,
        offer_to_receive_video: Optional[bool] = None,
        voice_activity_detection: bool = True,
    ) -> 'webrtc.RTCSessionDescriptionInit':
        """Initiates the creation of an SDP offer for the purpose of starting a new WebRTC connection to a remote peer.
        The SDP offer includes information about any MediaStreamTrack objects already attached to the WebRTC session,
        codec, and options supported by the machine, as well as any candidates already gathered by the ICE agent, for
        the purpose of being sent over the signaling channel to a potential peer to request a connection or to update
        the configuration of an existing connection.

        Args:
            ice_restart (:obj:`bool`, optional): Whether to restart ICE, gathering new credentials and candidates.
                :meth:`restart_ice` is the preferred way.
            offer_to_receive_audio (:obj:`bool`, optional): Legacy: :obj:`True` adds a receiving audio transceiver
                if there's none, :obj:`False` stops receiving audio on the existing ones.
                :meth:`add_transceiver` is the preferred way.
            offer_to_receive_video (:obj:`bool`, optional): The same for video.
            voice_activity_detection (:obj:`bool`, optional): Whether audio codecs may use voice activity detection.

        Returns:
            :obj:`webrtc.RTCSessionDescriptionInit`: The offer, to set with :meth:`set_local_description`.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the signaling state is neither stable nor have-local-offer.
        """
        async with self._operation():
            self._check_state('create an offer', RTCSignalingState.stable, RTCSignalingState.have_local_offer)
            self._apply_legacy_offer_option(MediaType.audio, offer_to_receive_audio)
            self._apply_legacy_offer_option(MediaType.video, offer_to_receive_video)
            await later()
            return _init_of(await to_async(self._native_obj.createOffer)(ice_restart, voice_activity_detection))

    async def create_answer(self, *, voice_activity_detection: bool = True) -> 'webrtc.RTCSessionDescriptionInit':
        """Initiates the creation an SDP answer to an offer received from a remote peer during the offer/answer
        negotiation of a WebRTC connection. The answer contains information about any media already attached to the
        session, codecs and options supported by the machine, and any ICE candidates already gathered.

        Args:
            voice_activity_detection (:obj:`bool`, optional): Whether audio codecs may use voice activity detection.

        Returns:
            :obj:`webrtc.RTCSessionDescriptionInit`: The answer, to set with :meth:`set_local_description`.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the connection is closed or has no remote offer.
        """
        async with self._operation():
            self._check_state(
                'create an answer', RTCSignalingState.have_remote_offer, RTCSignalingState.have_local_pranswer
            )
            await later()
            return _init_of(await to_async(self._native_obj.createAnswer)(voice_activity_detection))

    async def set_local_description(self, description: Optional[_Description] = None) -> None:
        """Changes the local description associated with the connection. This description specifies the properties
        of the local end of the connection, including the media format.

        Args:
            description (:obj:`webrtc.RTCSessionDescription`, optional): The description, as returned by
                :meth:`create_offer` or :meth:`create_answer`, or a ``rollback`` one. An
                :obj:`webrtc.RTCSessionDescriptionInit` or a :obj:`dict` with ``type`` and ``sdp`` keys is accepted
                too. Without it, or with an empty ``sdp``, the offer or the answer the signaling state calls for
                is created and set.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the type doesn't match the signaling state, or the connection is closed.
            :obj:`webrtc.InvalidModificationError`: If the SDP isn't the one :meth:`create_offer`
                or :meth:`create_answer` returned last.
            :obj:`webrtc.RTCError`: If the SDP can't be parsed (``sdp_syntax_error``).
        """
        init = _description_init(description, allow_implicit=True)
        async with self._operation():
            allowed = _LOCAL_DESCRIPTION_STATES[init.type] if init is not None else ()
            self._check_state('set the local description', *allowed)
            await later()
            await to_async(self._native_obj.setLocalDescription)(init)
            self._completed_description()

    async def set_remote_description(self, description: _Description) -> None:
        """Sets the specified session description as the remote peer's current offer or answer. The description
        specifies the properties of the remote end of the connection, including the media format.

        An offer set while there's a local offer rolls the local one back first.

        Args:
            description (:obj:`webrtc.RTCSessionDescription`): The description received from the remote peer.
                An :obj:`webrtc.RTCSessionDescriptionInit` or a :obj:`dict` with ``type`` and ``sdp`` keys
                is accepted too.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the type doesn't match the signaling state, or the connection is closed.
            :obj:`webrtc.RTCError`: If the SDP can't be parsed (``sdp_syntax_error``).
            :obj:`webrtc.InvalidAccessError`: If the description can't be applied.
        """
        init = _description_init(description, allow_implicit=False)
        async with self._operation():
            self._check_state('set the remote description', *_REMOTE_DESCRIPTION_STATES.get(init.type, ()))
            await later()
            await to_async(self._native_obj.setRemoteDescription)(init)
            self._completed_description()

    def add_track(
        self,
        track: 'webrtc.MediaStreamTrack',
        stream: Optional[Union['webrtc.MediaStream', List['webrtc.MediaStream']]] = None,
    ) -> 'webrtc.RTCRtpSender':
        """Adds a new :obj:`webrtc.MediaStreamTrack` to the set of tracks which will be transmitted to the other peer.

        Args:
            track (:obj:`webrtc.MediaStreamTrack`): A :obj:`webrtc.MediaStreamTrack` object representing the media track
                to add to the peer connection.
            stream (:obj:`webrtc.MediaStream` or :obj:`list` of :obj:`webrtc.MediaStream`, optional): One or more
                local :obj:`webrtc.MediaStream` objects to which the track should be added.

        Returns:
            :obj:`webrtc.RTCRtpSender`: The :obj:`webrtc.RTCRtpSender` object which will be used to
            transmit the media data.
        """
        from webrtc import RTCRtpSender

        if not stream:
            sender = self._native_obj.addTrack(track._native_obj, None)
        elif isinstance(stream, list):
            native_objects = [s._native_obj for s in stream]
            sender = self._native_obj.addTrack(track._native_obj, native_objects)
        else:
            sender = self._native_obj.addTrack(track._native_obj, stream._native_obj)

        return RTCRtpSender._wrap(sender)

    def add_transceiver(
        self,
        track_or_kind: Union['webrtc.MediaStreamTrack', 'webrtc.MediaType'],
        init: Optional[Union['webrtc.RtpTransceiverInit', Dict[str, Any]]] = None,
    ) -> 'webrtc.RTCRtpTransceiver':
        """Creates a new :obj:`webrtc.RTCRtpTransceiver` and adds it to the set of transceivers associated with the
        connection. Each transceiver represents a bidirectional stream, with both an :obj:`webrtc.RTCRtpSender` and
        an :obj:`webrtc.RTCRtpReceiver` associated with it.

        Args:
            track_or_kind (:obj:`webrtc.MediaStreamTrack` or :obj:`webrtc.MediaType`): A
                :obj:`webrtc.MediaStreamTrack` to associate with the transceiver, or :attr:`webrtc.MediaType.audio`
                or :attr:`webrtc.MediaType.video` (or its value), which is used as the kind of the receiver's track,
                and by extension of the :obj:`webrtc.RTCRtpReceiver` itself.
            init (:obj:`webrtc.RtpTransceiverInit` or :obj:`dict`, optional): An object for specifying any options
                when creating the new transceiver, or a dictionary of its members (the encodings may be dictionaries
                too). It isn't changed.

        Returns:
            :obj:`webrtc.RTCRtpTransceiver`: The new transceiver.

        Raises:
            :obj:`TypeError`: If the kind is neither audio nor video.
            :obj:`ValueError`: If a ``rid`` of the send encodings is invalid, or missing or repeated with several
                encodings.
            :obj:`webrtc.OperationError`: If the codec of a send encoding can't be sent.
        """
        from webrtc import MediaStreamTrack, RTCRtpTransceiver

        kind = track_or_kind.kind if isinstance(track_or_kind, MediaStreamTrack) else track_or_kind
        if kind not in (MediaType.audio, MediaType.video):
            raise TypeError(f'{kind!r} is not a kind of track')
        native_init = None
        if isinstance(init, dict):
            init = _transceiver_init(init)
        if init is not None:
            _check_send_encodings(init.send_encodings, kind)
            # a copy, with the encodings for the kind
            encodings = [encoding._for_kind(kind) for encoding in init.send_encodings]
            native_init = RtpTransceiverInit(init.direction, encodings, init.streams)._native_obj

        if isinstance(track_or_kind, MediaStreamTrack):
            transceiver = self._native_obj.addTransceiver(track_or_kind._native_obj, native_init)
        else:
            transceiver = self._native_obj.addTransceiver(track_or_kind, native_init)

        return RTCRtpTransceiver._wrap(transceiver)

    def get_transceivers(self) -> List['webrtc.RTCRtpTransceiver']:
        """Returns a :obj:`list` of the :obj:`webrtc.RTCRtpTransceiver` objects being used to send and
        receive data on the connection.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpTransceiver`: An array of the :obj:`webrtc.RTCRtpTransceiver` objects
            representing the transceivers handling sending and receiving all media
            on the :obj:`webrtc.RTCPeerConnection`. The list is in the order in which the transceivers were
            added to the connection.
        """
        from webrtc import RTCRtpTransceiver

        return RTCRtpTransceiver._wrap_many(self._native_obj.getTransceivers())

    def get_senders(self) -> List['webrtc.RTCRtpSender']:
        """Returns an array of :obj:`webrtc.RTCRtpSender` objects, each of which represents the RTP sender responsible
        for transmitting one track's data. A sender object provides methods and properties for examining
        and controlling the encoding and transmission of the track's data.

        Note:
            The order of the returned :obj:`webrtc.RTCRtpSender` objects is not defined by the specification,
            and may change from one call to :meth:`get_senders` to the next.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpSender`: An array of :obj:`webrtc.RTCRtpSender` objects, one for each
            track on the connection. The array is empty if there are no RTP senders on the connection.
        """
        from webrtc import RTCRtpSender

        return RTCRtpSender._wrap_many(self._native_obj.getSenders())

    def get_receivers(self) -> List['webrtc.RTCRtpReceiver']:
        """Returns an array of :obj:`webrtc.RTCRtpReceiver` objects, each of which represents one RTP receiver. Each RTP
        receiver manages the reception and decoding of data for a :obj:`webrtc.MediaStreamTrack`
        on an :obj:`webrtc.RTCPeerConnection`.

        Note:
            The order of the returned :obj:`webrtc.RTCRtpReceiver` objects is not defined by the specification,
            and may change from one call to :meth:`get_receivers` to the next.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCRtpReceiver`: An array of :obj:`webrtc.RTCRtpReceiver` objects, one for each
            track on the connection. The array is empty if there are no RTP receivers on the connection.
        """
        from webrtc import RTCRtpReceiver

        return RTCRtpReceiver._wrap_many(self._native_obj.getReceivers())

    def remove_track(self, sender: 'webrtc.RTCRtpSender') -> None:
        """Stops sending the track of a sender, which stays in :meth:`get_senders`. Does nothing if the sender
        has no track.

        Args:
            sender (:obj:`webrtc.RTCRtpSender`): A sender of this connection.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the connection is closed.
            :obj:`webrtc.InvalidAccessError`: If the sender belongs to another connection.
        """
        return self._native_obj.removeTrack(sender._native_obj)

    async def add_ice_candidate(
        self, candidate: Optional[Union['webrtc.RTCIceCandidate', Dict[str, Any]]] = None
    ) -> None:
        """Adds a candidate received from the remote peer to the remote description.

        Args:
            candidate (:obj:`webrtc.RTCIceCandidate` or :obj:`dict`, optional): The candidate, or its JSON form
                (see :meth:`webrtc.RTCIceCandidate.to_json`). A candidate with an empty
                :attr:`webrtc.RTCIceCandidate.candidate`, or :obj:`None`, means the end of candidates.

        Raises:
            :obj:`TypeError`: If a non-empty candidate has neither ``sdp_mid`` nor ``sdp_m_line_index``.
            :obj:`webrtc.InvalidStateError`: If there's no remote description, or the connection is closed.
            :obj:`webrtc.OperationError`: If the candidate can't be parsed or doesn't match a media section.
        """
        if candidate is None:
            candidate_str, sdp_mid, sdp_m_line_index, ufrag = '', None, None, None
        else:
            candidate_str, sdp_mid, sdp_m_line_index, ufrag = RTCIceCandidate._members_of(candidate)
        if candidate_str and sdp_mid is None and sdp_m_line_index is None:
            raise TypeError('sdp_mid and sdp_m_line_index are both None')

        async with self._operation():
            self._check_state('add an ICE candidate')
            if self.remote_description is None:
                raise InvalidStateError('A candidate can only be added once there is a remote description')
            await later()
            await to_async(self._native_obj.addIceCandidate)(candidate_str, sdp_mid, sdp_m_line_index, ufrag)

    def create_data_channel(
        self,
        label: str,
        *,
        ordered: bool = True,
        max_packet_life_time: Optional[int] = None,
        max_retransmits: Optional[int] = None,
        protocol: str = '',
        negotiated: bool = False,
        id: Optional[int] = None,
        priority: 'webrtc.RTCPriorityType' = 'low',
    ) -> 'webrtc.RTCDataChannel':
        """Creates a channel to send messages to the remote peer, negotiated with the next offer
        (unless ``negotiated`` is set).

        Args:
            label (:obj:`str`): The name of the channel, up to 65535 bytes in UTF-8.
            ordered (:obj:`bool`, optional): Whether messages are delivered in order.
            max_packet_life_time (:obj:`int`, optional): Makes the channel unreliable: how long in milliseconds
                a message is retransmitted.
            max_retransmits (:obj:`int`, optional): Makes the channel unreliable: how many times a message is
                retransmitted. Can't be set along with ``max_packet_life_time``.
            protocol (:obj:`str`, optional): The subprotocol name, up to 65535 bytes in UTF-8.
            negotiated (:obj:`bool`, optional): Whether the application creates the channel on both ends
                with the same ``id``, instead of announcing it to the remote peer.
            id (:obj:`int`, optional): The SCTP stream id (0 to 65534) of a ``negotiated`` channel, which requires it.
                Ignored otherwise, as the connection picks the id.
            priority (:obj:`webrtc.RTCPriorityType`, optional): The priority of the channel.

        Returns:
            :obj:`webrtc.RTCDataChannel`: The channel.

        Raises:
            :obj:`ValueError`: If an argument is out of range, or both ``max_packet_life_time`` and
                ``max_retransmits`` are set, or ``negotiated`` is set without ``id``.
            :obj:`webrtc.InvalidStateError`: If the connection is closed.
            :obj:`webrtc.OperationError`: If the ``id`` is in use, or no id is left.
        """
        from webrtc import RTCDataChannel

        _check_data_channel_init(label, protocol, max_packet_life_time, max_retransmits, negotiated, id)
        native = self._native_obj.createDataChannel(
            label,
            ordered,
            max_packet_life_time,
            max_retransmits,
            protocol,
            negotiated,
            id if negotiated else None,
            priority,
        )
        channel = RTCDataChannel._wrap(native)
        # handlers registered in this iteration of the loop get the first events
        if not TaskQueue.post_to_running(native._release):
            native._release()
        return channel

    async def get_stats(self, selector: Optional['webrtc.MediaStreamTrack'] = None) -> 'webrtc.RTCStatsReport':
        """Collects the stats of the connection, or of the sender or the receiver of a track.

        Args:
            selector (:obj:`webrtc.MediaStreamTrack`, optional): A track of exactly one sender or receiver
                of the connection, to only get the stats of it.

        Returns:
            :obj:`webrtc.RTCStatsReport`: The stats.

        Raises:
            :obj:`webrtc.InvalidAccessError`: If no sender or receiver, or more than one, has the track.
            :obj:`webrtc.InvalidStateError`: If the connection is closed.
        """
        if selector is not None:
            matches = [s for s in self.get_senders() if s.track == selector]
            matches += [r for r in self.get_receivers() if r.track == selector]
            if len(matches) != 1:
                raise InvalidAccessError(f'{len(matches)} senders and receivers have the track, not exactly one')
            return await matches[0].get_stats()
        return RTCStatsReport._from_native(await to_async(self._native_obj.getStats)(), self.get_receivers())

    @staticmethod
    async def generate_certificate(
        algorithm: 'webrtc.models.rtc_certificate.Algorithm' = 'ECDSA', expires: Optional[float] = None
    ) -> 'webrtc.RTCCertificate':
        """Generates a certificate for :attr:`webrtc.RTCConfiguration.certificates`, the same as
        :meth:`webrtc.RTCCertificate.generate`.

        Args:
            algorithm (:obj:`str` or :obj:`dict`, optional): The WebCrypto algorithm of the key.
            expires (:obj:`float`, optional): In how many milliseconds the certificate expires.

        Returns:
            :obj:`webrtc.RTCCertificate`: The certificate.

        Raises:
            :obj:`webrtc.NotSupportedError`: If the algorithm isn't supported.
            :obj:`ValueError`: If ``expires`` is negative.
        """
        return await RTCCertificate.generate(algorithm, expires)

    def get_configuration(self) -> 'webrtc.RTCConfiguration':
        """Returns the configuration of the connection, as it was last set.

        Returns:
            :obj:`webrtc.RTCConfiguration`: A copy of the configuration.
        """
        return RTCConfiguration._from_native(self._native_obj.getConfiguration())

    def set_configuration(self, configuration: Optional['webrtc.RTCConfiguration'] = None) -> None:
        """Changes the configuration of the connection. Members that aren't set get their default values.

        Changed ICE servers or ICE transport policy are used for the candidates gathered next,
        like after :meth:`restart_ice`.

        Args:
            configuration (:obj:`webrtc.RTCConfiguration`, optional): The new configuration.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the connection is closed.
            :obj:`webrtc.InvalidModificationError`: If a member that can't be changed differs, like
                :attr:`webrtc.RTCConfiguration.bundle_policy` or
                :attr:`webrtc.RTCConfiguration.always_negotiate_data_channels`.
            :obj:`webrtc.InvalidSyntaxError`: If an ICE server URL is invalid.
            :obj:`webrtc.InvalidAccessError`: If a TURN server has no credentials.
            :obj:`ValueError`: If a member of the configuration is out of range.
            :obj:`TypeError`: If a member of the configuration has a wrong type, or a value its enum doesn't have.
        """
        self._native_obj.setConfiguration((configuration or RTCConfiguration())._to_native())

    def restart_ice(self) -> None:
        """Allows to easily request that ICE candidate gathering be redone on both ends of the connection.
        This simplifies the process by allowing the same method to be used by either the caller or the receiver
        to trigger an ICE restart."""
        return self._native_obj.restartIce()

    def close(self):
        """Closes the current peer connection."""
        return self._native_obj.close()

    @property
    def sctp(self) -> Optional['webrtc.RTCSctpTransport']:
        """:obj:`webrtc.RTCSctpTransport`, optional: An object describing the SCTP transport layer over which SCTP
        data is being sent and received. If SCTP hasn't been negotiated, this value is :obj:`None`."""
        from webrtc import RTCSctpTransport

        return RTCSctpTransport._wrap_optional(self._native_obj.sctp)

    @property
    def local_description(self) -> Optional['webrtc.RTCSessionDescription']:
        """:obj:`webrtc.RTCSessionDescription`, optional: The local end of the connection, including ICE candidates
        gathered so far. :obj:`None` if the local description hasn't been set yet."""
        return RTCSessionDescription._wrap_optional(self._native_obj.localDescription)

    @property
    def remote_description(self) -> Optional['webrtc.RTCSessionDescription']:
        """:obj:`webrtc.RTCSessionDescription`, optional: The remote end of the connection.
        :obj:`None` if the remote description hasn't been set yet."""
        return RTCSessionDescription._wrap_optional(self._native_obj.remoteDescription)

    @property
    def current_local_description(self) -> Optional['webrtc.RTCSessionDescription']:
        """:obj:`webrtc.RTCSessionDescription`, optional: The local description negotiated the last time
        the connection was in the stable state."""
        return RTCSessionDescription._wrap_optional(self._native_obj.currentLocalDescription)

    @property
    def current_remote_description(self) -> Optional['webrtc.RTCSessionDescription']:
        """:obj:`webrtc.RTCSessionDescription`, optional: The remote description negotiated the last time
        the connection was in the stable state."""
        return RTCSessionDescription._wrap_optional(self._native_obj.currentRemoteDescription)

    @property
    def pending_local_description(self) -> Optional['webrtc.RTCSessionDescription']:
        """:obj:`webrtc.RTCSessionDescription`, optional: The local description being negotiated, :obj:`None`
        in the stable state."""
        return RTCSessionDescription._wrap_optional(self._native_obj.pendingLocalDescription)

    @property
    def pending_remote_description(self) -> Optional['webrtc.RTCSessionDescription']:
        """:obj:`webrtc.RTCSessionDescription`, optional: The remote description being negotiated, :obj:`None`
        in the stable state."""
        return RTCSessionDescription._wrap_optional(self._native_obj.pendingRemoteDescription)

    @property
    def can_trickle_ice_candidates(self) -> Optional[bool]:
        """:obj:`bool`, optional: Whether the remote peer takes candidates one by one (trickle ICE),
        :obj:`None` until there's a remote description."""
        return self._native_obj.canTrickleIceCandidates

    @property
    def connection_state(self) -> 'webrtc.RTCPeerConnectionState':
        """:obj:`webrtc.RTCPeerConnectionState`: The current state of the connection."""
        return self._native_obj.connectionState

    @property
    def signaling_state(self) -> 'webrtc.RTCSignalingState':
        """:obj:`webrtc.RTCSignalingState`: The state of the signaling process."""
        return self._native_obj.signalingState

    @property
    def ice_connection_state(self) -> 'webrtc.RTCIceConnectionState':
        """:obj:`webrtc.RTCIceConnectionState`: The state of the ICE agent."""
        return self._native_obj.iceConnectionState

    @property
    def ice_gathering_state(self) -> 'webrtc.RTCIceGatheringState':
        """:obj:`webrtc.RTCIceGatheringState`: The ICE candidate gathering state."""
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


def _description_init(
    description: Optional[_Description], allow_implicit: bool
) -> Optional['wrtc.RTCSessionDescriptionInit']:
    """The native RTCSessionDescriptionInit of a description, or :obj:`None` for an implicit one."""
    if description is None and allow_implicit:
        return None
    if isinstance(description, dict):
        if description.get('type') is None:
            if allow_implicit and not description.get('sdp'):
                return None
            raise TypeError('the type of a description is required')
        description = RTCSessionDescription(description)
    if isinstance(description, RTCSessionDescription):
        return description._native_obj.init
    if isinstance(description, RTCSessionDescriptionInit):
        return description._native_obj
    raise TypeError(f'expected an RTCSessionDescription, not {type(description).__name__}')


def _init_of(description: 'wrtc.RTCSessionDescription') -> 'webrtc.RTCSessionDescriptionInit':
    return RTCSessionDescriptionInit(description.type, description.sdp)


def _members(value: Dict[str, Any], names: Iterable[str]) -> Dict[str, Any]:
    """The members of a dictionary, with snake_case or camelCase names: unknown ones are ignored, as in WebIDL"""
    members = {snake_case(name): member for name, member in value.items()}
    return {name: member for name, member in members.items() if name in names}


def _transceiver_init(init: Dict[str, Any]) -> RtpTransceiverInit:
    """An init from a dictionary, as in browsers, with its encodings dictionaries too"""
    members = _members(init, ('direction', 'send_encodings', 'streams'))
    encodings = members.get('send_encodings')
    if encodings is not None:
        names = [field.name for field in dataclasses.fields(RTCRtpEncodingParameters)]
        members['send_encodings'] = [
            RTCRtpEncodingParameters(**_members(e, names)) if isinstance(e, dict) else e for e in encodings
        ]
    return RtpTransceiverInit(**members)


def _check_send_encodings(encodings: List['webrtc.RTCRtpEncodingParameters'], kind: 'webrtc.MediaType') -> None:
    """Validates the send encodings of a new transceiver, as the specification requires."""
    from webrtc import RTCRtpSender

    rids = [e.rid for e in encodings]
    for rid in rids:
        if rid is not None and not _RID.fullmatch(rid):
            raise ValueError(f'{rid!r} is not a valid rid: 1 to 16 letters and digits')
    if len(encodings) > 1 and (None in rids or len(set(rids)) != len(rids)):
        raise ValueError('every encoding needs a distinct rid when there are several')

    codecs = [e.codec for e in encodings if e.codec is not None]
    if codecs:
        capabilities = RTCRtpSender.get_capabilities(kind)
        supported = capabilities.codecs if capabilities is not None else []
        for codec in codecs:
            if not any(RTCRtpCodec._matches(c, codec) for c in supported):
                raise OperationError(f'{codec.mime_type} can not be sent')


def _check_data_channel_init(
    label: str,
    protocol: str,
    max_packet_life_time: Optional[int],
    max_retransmits: Optional[int],
    negotiated: bool,
    id: Optional[int],
) -> None:
    """Validates the arguments of :meth:`RTCPeerConnection.create_data_channel`, as the specification requires."""
    for name, value in (('label', label), ('protocol', protocol)):
        if len(value.encode()) > 65535:
            raise ValueError(f'{name} is longer than 65535 bytes')
    for name, value in (('max_packet_life_time', max_packet_life_time), ('max_retransmits', max_retransmits)):
        if value is not None and not 0 <= value <= 65535:
            raise ValueError(f'{name} must be from 0 to 65535, not {value}')
    if max_packet_life_time is not None and max_retransmits is not None:
        raise ValueError('max_packet_life_time and max_retransmits can not both be set')
    if not negotiated:
        return
    if id is None:
        raise ValueError('a negotiated channel needs an id')
    if not 0 <= id <= 65534:
        raise ValueError(f'id must be from 0 to 65534, not {id}')
