#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The ICE transport of a connection, which can also be used on its own."""

from __future__ import annotations

import re
import weakref
from typing import Callable, Literal, TypeVar, cast, overload

from typing_extensions import override

import webrtc
import wrtc
from webrtc.base import WebRTCObject
from webrtc.enums import RTCIceGathererState, RTCIceRole, RTCIceTransportState
from webrtc.exceptions import InvalidStateError
from webrtc.models.events import Event, RTCPeerConnectionIceEvent, RTCPeerConnectionIceEventInit
from webrtc.models.rtc_configuration import RTCIceGatherOptions, RTCIceServer
from webrtc.models.rtc_ice_candidate import RTCIceCandidate, RTCIceCandidateInit, RTCIceCandidatePair, RTCIceParameters
from webrtc.utils.events import AnyHandler, EventTarget, HandlerDecorator

# RFC 8839: ice-char is ALPHA / DIGIT / "+" / "/", the username fragment is 4 to 256 of them, the password 22 to 256
_UFRAG = re.compile(r'[A-Za-z0-9+/]{4,256}')
_PASSWORD = re.compile(r'[A-Za-z0-9+/]{22,256}')

# the candidates of every transport, by their candidate-attribute: a candidate is the same object each time
_candidates: weakref.WeakKeyDictionary[wrtc.RTCIceTransport, dict[str, webrtc.RTCIceCandidate]] = (
    weakref.WeakKeyDictionary()
)


_IceTransportStateEvent = Literal['statechange', 'gatheringstatechange', 'selectedcandidatepairchange', 'error']
_IceTransportEvent = Literal[_IceTransportStateEvent, 'icecandidate']
_R = TypeVar('_R')


class RTCIceTransport(WebRTCObject[wrtc.RTCIceTransport], EventTarget[_IceTransportEvent]):
    """The ICE transport a :obj:`webrtc.RTCDtlsTransport` of a connection runs over, or a standalone one.

    A standalone transport (``RTCIceTransport()``, from WebRTC Extensions) is driven by hand. Call :meth:`gather`,
    :meth:`start` and :meth:`add_remote_candidate`, then :meth:`stop` when done. Those methods raise for a
    transport of a connection. Its events go to the event loop it was created on.

    See :mdn:`RTCIceTransport`.

    Events:
        statechange (:obj:`webrtc.Event`): :attr:`state` changed.
        gatheringstatechange (:obj:`webrtc.Event`): :attr:`gathering_state` changed.
        selectedcandidatepairchange (:obj:`webrtc.Event`): :meth:`get_selected_candidate_pair` changed.
        icecandidate (:obj:`webrtc.RTCPeerConnectionIceEvent`): A standalone transport gathered a candidate,
            or :obj:`None` once it gathered them all.
        error (:obj:`webrtc.Event`): A standalone transport failed. It never fires, because the native ICE
            agent doesn't report it.
    """

    _class = wrtc.RTCIceTransport

    @overload
    def on(self, name: _IceTransportStateEvent, handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def on(self, name: _IceTransportStateEvent, handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def on(
        self, name: Literal['icecandidate'], handler: None = None
    ) -> HandlerDecorator[RTCPeerConnectionIceEvent]: ...

    @overload
    def on(
        self, name: Literal['icecandidate'], handler: Callable[[RTCPeerConnectionIceEvent], _R]
    ) -> Callable[[RTCPeerConnectionIceEvent], _R]: ...

    def on(self, name: _IceTransportEvent, handler: AnyHandler | None = None) -> object:
        """Adds a handler of an event, called each time. See :meth:`webrtc.UniformEventTarget.on`."""
        return self._add(name, handler, once=False)

    @overload
    def once(self, name: _IceTransportStateEvent, handler: None = None) -> HandlerDecorator[Event]: ...

    @overload
    def once(self, name: _IceTransportStateEvent, handler: Callable[[Event], _R]) -> Callable[[Event], _R]: ...

    @overload
    def once(
        self, name: Literal['icecandidate'], handler: None = None
    ) -> HandlerDecorator[RTCPeerConnectionIceEvent]: ...

    @overload
    def once(
        self, name: Literal['icecandidate'], handler: Callable[[RTCPeerConnectionIceEvent], _R]
    ) -> Callable[[RTCPeerConnectionIceEvent], _R]: ...

    def once(self, name: _IceTransportEvent, handler: AnyHandler | None = None) -> object:
        """Adds a handler of an event, called once. See :meth:`webrtc.UniformEventTarget.once`."""
        return self._add(name, handler, once=True)

    def __init__(self) -> None:
        super().__init__()
        # a standalone transport delivers its events to the loop it's created on
        self._attach()

    def _candidate_of(self, native: wrtc.IceCandidateInit) -> webrtc.RTCIceCandidate:
        """The candidate object of a native candidate, the same one each time."""
        kwargs = native.kwargs()
        known = _candidates.setdefault(self._native_obj, {})
        if kwargs['candidate'] not in known:
            known[kwargs['candidate']] = RTCIceCandidate(**kwargs)
        return known[kwargs['candidate']]

    def _remember(self, candidate: webrtc.RTCIceCandidate) -> None:
        """Makes a candidate the object of its native candidate, unless there's one already."""
        _ = _candidates.setdefault(self._native_obj, {}).setdefault(candidate.candidate, candidate)

    @override
    def _on_event(self, name: str, *args: object) -> None:
        # the states change along with their events
        if name == 'statechange':
            (state,) = cast('tuple[RTCIceTransportState]', args)
            self._native_obj._surfaceState(state)
        elif name == 'gatheringstatechange':
            (gathering_state,) = cast('tuple[RTCIceGathererState]', args)
            self._native_obj._surfaceGatheringState(gathering_state)
        elif name == 'icecandidate' and len(args) > 0 and args[0] is not None:
            self._native_obj._surfaceCandidate()

    @override
    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        if name == 'icecandidate':
            # the end of candidates has none
            native = cast('wrtc.IceCandidateInit | None', args[0]) if len(args) > 0 else None
            candidate = self._candidate_of(native) if native is not None else None
            return RTCPeerConnectionIceEvent(name, RTCPeerConnectionIceEventInit(candidate))
        return super()._create_event(name, *args)

    def _check_standalone(self, operation: str) -> None:
        if not self._native_obj._standalone:
            msg = f'Can not {operation}: the transport belongs to an RTCPeerConnection'
            raise InvalidStateError(msg)

    def _check_open(self, operation: str) -> None:
        self._check_standalone(operation)
        if self.state == RTCIceTransportState.closed:
            msg = f'Can not {operation}: the transport is stopped'
            raise InvalidStateError(msg)

    def gather(self, options: webrtc.RTCIceGatherOptions | None = None) -> None:
        """Starts gathering the local candidates of a standalone transport, each sent in an ``icecandidate`` event.

        Args:
            options (:obj:`webrtc.RTCIceGatherOptions`, optional): The policy and the ICE servers to gather with.

        Raises:
            webrtc.InvalidStateError: If it's stopped, gathering already, or belongs to a connection.
            webrtc.InvalidSyntaxError: If an ICE server URL is invalid.
            webrtc.InvalidAccessError: If a TURN server has no credentials.
            TypeError: If the policy isn't a value of :obj:`webrtc.RTCIceTransportPolicy`.
        """
        self._check_open('gather')
        if self.gathering_state != RTCIceGathererState.new:
            msg = 'The transport gathers its candidates already'
            raise webrtc.InvalidStateError(msg)
        options = options if options is not None else RTCIceGatherOptions()
        servers = options.ice_servers if options.ice_servers is not None else ()
        self._native_obj.gather(options.gather_policy, RTCIceServer._to_native_list(servers))

    def start(
        self,
        remote_parameters: webrtc.RTCIceParameters | None = None,
        role: webrtc.RTCIceRole | str = 'controlled',
    ) -> None:
        """Starts connectivity checks of a standalone transport with the remote agent.

        Checks use the remote candidates added so far and any added later. Calling it again with other remote
        parameters (an ICE restart of the remote agent) drops the remote candidates added before.

        Args:
            remote_parameters (:obj:`webrtc.RTCIceParameters`, optional): The username fragment and the password of
                the remote agent. Both are required, even though the argument has a default.
            role (:obj:`webrtc.RTCIceRole`, optional): Controlling or controlled (the default). If both agents pick
                the same role, the conflict is resolved and one of them switches.

        Raises:
            webrtc.InvalidStateError: If it's stopped, started with another role, or belongs to a connection.
            webrtc.InvalidSyntaxError: If the username fragment or the password is invalid.
            ValueError: If the role is neither controlling nor controlled.
        """
        self._check_open('start')
        parameters = remote_parameters if remote_parameters is not None else RTCIceParameters()
        ufrag, password = parameters.username_fragment, parameters.password
        if ufrag is None or _UFRAG.fullmatch(ufrag) is None:
            msg = f'{ufrag!r} is not a valid ICE username fragment'
            raise webrtc.InvalidSyntaxError(msg)
        if password is None or _PASSWORD.fullmatch(password) is None:
            msg = 'the ICE password is not valid'
            raise webrtc.InvalidSyntaxError(msg)
        if role not in {RTCIceRole.controlling, RTCIceRole.controlled}:
            msg = 'role must be controlling or controlled'
            raise ValueError(msg)
        self._native_obj.start(ufrag, password, role)

    def add_remote_candidate(
        self, remote_candidate: webrtc.RTCIceCandidate | webrtc.RTCIceCandidateInit | None = None
    ) -> None:
        """Adds a candidate of the remote agent to a standalone transport.

        The object passed is the one :meth:`get_remote_candidates` returns for it.

        Args:
            remote_candidate (:obj:`webrtc.RTCIceCandidate` or :obj:`webrtc.RTCIceCandidateInit`, optional): The
                candidate, which needs ``sdp_mid`` or ``sdp_m_line_index`` to be set.

        Raises:
            TypeError: If the candidate has neither ``sdp_mid`` nor ``sdp_m_line_index``.
            webrtc.InvalidStateError: If it's stopped, or belongs to a connection.
            webrtc.OperationError: If the candidate can't be parsed.
        """
        self._check_open('add a remote candidate')
        candidate = remote_candidate if remote_candidate is not None else RTCIceCandidateInit()
        if not isinstance(candidate, RTCIceCandidate):
            candidate = RTCIceCandidate(*RTCIceCandidate._members_of(candidate))
        self._native_obj.addRemoteCandidate(
            candidate.candidate,
            candidate.sdp_mid if candidate.sdp_mid is not None else '',
            candidate.sdp_m_line_index if candidate.sdp_m_line_index is not None else 0,
            candidate.username_fragment,
        )
        self._remember(candidate)

    def stop(self) -> None:
        """Stops a standalone transport for good.

        Its :attr:`state` becomes ``closed`` without a ``statechange`` event.

        Raises:
            webrtc.InvalidStateError: If it belongs to a connection.
        """
        self._check_standalone('stop')
        self._native_obj.stop()

    def get_selected_candidate_pair(self) -> webrtc.RTCIceCandidatePair | None:
        """Returns the local and the remote candidate the transport sends and receives with.

        A remote peer-reflexive candidate comes from connectivity checks. It has an empty ``candidate`` and no
        address.

        See :mdn:`RTCIceTransport/getSelectedCandidatePair`.

        Returns:
            :obj:`webrtc.RTCIceCandidatePair`, optional: The pair, or :obj:`None` until one is selected.
        """
        pair = self._native_obj.getSelectedCandidatePair()
        if pair is None:
            return None
        local, remote, remote_peer_reflexive = pair
        if remote_peer_reflexive:
            remote_candidate = RTCIceCandidate._peer_reflexive(remote.kwargs())
        else:
            remote_candidate = RTCIceCandidate(**remote.kwargs())
        return RTCIceCandidatePair(RTCIceCandidate(**local.kwargs()), remote_candidate)

    def get_local_candidates(self) -> list[webrtc.RTCIceCandidate]:
        """Returns the local candidates gathered for the transport so far.

        Each call returns the same objects. For a standalone transport, they're the ones of its ``icecandidate``
        events.

        See :mdn:`RTCIceTransport/getLocalCandidates`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate_of(c) for c in self._native_obj.getLocalCandidates()]

    def get_remote_candidates(self) -> list[webrtc.RTCIceCandidate]:
        """Returns the candidates the remote peer signaled for the transport, without peer-reflexive ones.

        They come from its description, :meth:`webrtc.RTCPeerConnection.add_ice_candidate` or
        :meth:`add_remote_candidate`.

        See :mdn:`RTCIceTransport/getRemoteCandidates`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate_of(c) for c in self._native_obj.getRemoteCandidates()]

    def get_local_parameters(self) -> webrtc.RTCIceParameters | None:
        """Returns the local username fragment and password of the transport, with ``ice_lite`` :obj:`False`.

        See :mdn:`RTCIceTransport/getLocalParameters`.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, or :obj:`None` without a local description.
        """
        parameters = self._native_obj.getLocalParameters()
        return RTCIceParameters(*parameters, ice_lite=False) if parameters is not None else None

    def get_remote_parameters(self) -> webrtc.RTCIceParameters | None:
        """Returns the remote username fragment and password of the transport, with ``ice_lite`` unknown.

        See :mdn:`RTCIceTransport/getRemoteParameters`.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, or :obj:`None` without a remote description.
        """
        parameters = self._native_obj.getRemoteParameters()
        return RTCIceParameters(*parameters) if parameters is not None else None

    @property
    def component(self) -> webrtc.RTCIceComponent:
        """:obj:`webrtc.RTCIceComponent`: Whether the transport carries RTP or RTCP. It's ``rtp`` when they're muxed.

        See :mdn:`RTCIceTransport/component`.
        """
        return self._native_obj.component

    @property
    def gathering_state(self) -> webrtc.RTCIceGathererState:
        """:obj:`webrtc.RTCIceGathererState`: Whether local candidates are being gathered, or all were.

        See :mdn:`RTCIceTransport/gatheringState`.
        """
        return self._native_obj.gatheringState

    @property
    def role(self) -> webrtc.RTCIceRole | None:
        """:obj:`webrtc.RTCIceRole`, optional: Whether this agent is the controlling one, which picks the pair.

        :obj:`None` for a standalone transport not started yet.

        See :mdn:`RTCIceTransport/role`.
        """
        role = self._native_obj.role
        if role == RTCIceRole.unknown and self._native_obj._standalone:
            return None
        return role

    @property
    def state(self) -> webrtc.RTCIceTransportState:
        """:obj:`webrtc.RTCIceTransportState`: Whether the transport is checking, connected, failed or closed.

        See :mdn:`RTCIceTransport/state`.
        """
        return self._native_obj.state

    #: Alias for :attr:`get_selected_candidate_pair`
    getSelectedCandidatePair = get_selected_candidate_pair
    #: Alias for :attr:`get_local_candidates`
    getLocalCandidates = get_local_candidates
    #: Alias for :attr:`add_remote_candidate`
    addRemoteCandidate = add_remote_candidate
    #: Alias for :attr:`get_remote_candidates`
    getRemoteCandidates = get_remote_candidates
    #: Alias for :attr:`get_local_parameters`
    getLocalParameters = get_local_parameters
    #: Alias for :attr:`get_remote_parameters`
    getRemoteParameters = get_remote_parameters
    #: Alias for :attr:`gathering_state`
    gatheringState = gathering_state
