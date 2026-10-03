#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCIceTransport of WebRTC, standalone too, as in WebRTC Extensions."""

from __future__ import annotations

import re
import weakref
from typing import TYPE_CHECKING, Callable, Literal, TypeVar, cast, overload

from typing_extensions import override

from webrtc import (
    Event,
    InvalidStateError,
    InvalidSyntaxError,
    RTCIceCandidate,
    RTCIceCandidateInit,
    RTCIceCandidatePair,
    RTCIceGathererState,
    RTCIceGatherOptions,
    RTCIceParameters,
    RTCIceRole,
    RTCIceServer,
    RTCIceTransportState,
    RTCPeerConnectionIceEvent,
    RTCPeerConnectionIceEventInit,
    WebRTCObject,
    wrtc,
)
from webrtc.utils.events import AnyHandler, EventTarget, HandlerDecorator

if TYPE_CHECKING:
    import webrtc


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
    """The ICE transport a :obj:`webrtc.RTCDtlsTransport` of a connection runs over, or a standalone transport.

    A standalone one (``RTCIceTransport()``) connects after :meth:`gather`, :meth:`start` and
    :meth:`add_remote_candidate`.

    Events (see :meth:`on`):
        ``statechange`` (:obj:`webrtc.Event`): :attr:`state` changed.
        ``gatheringstatechange`` (:obj:`webrtc.Event`): :attr:`gathering_state` changed.
        ``selectedcandidatepairchange`` (:obj:`webrtc.Event`): :meth:`get_selected_candidate_pair` changed.
        ``icecandidate`` (:obj:`webrtc.RTCPeerConnectionIceEvent`): A standalone transport gathered a candidate,
        or :obj:`None` once it gathered them all.
        ``error`` (:obj:`webrtc.Event`): A standalone transport failed, which libwebrtc doesn't report.
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
        """See :meth:`webrtc.UniformEventTarget.on`."""
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
        """See :meth:`webrtc.UniformEventTarget.once`."""
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
        """Gathers the candidates of a standalone transport, sent in ``icecandidate`` events.

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
            raise InvalidStateError(msg)
        options = options if options is not None else RTCIceGatherOptions()
        servers = options.ice_servers if options.ice_servers is not None else ()
        self._native_obj.gather(options.gather_policy, RTCIceServer._to_native_list(servers))

    def start(
        self,
        remote_parameters: webrtc.RTCIceParameters | None = None,
        role: webrtc.RTCIceRole | str = 'controlled',
    ) -> None:
        """Starts connecting a standalone transport to the remote agent, with the candidates added, or later.

        Remote parameters that differ from the ones given before remove the remote candidates.

        Args:
            remote_parameters (:obj:`webrtc.RTCIceParameters`, optional): The username fragment and the password of
                the remote agent, which are required.
            role (:obj:`webrtc.RTCIceRole`, optional): Controlling or controlled (the default). When both agents take
                the same role, one of them switches.

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
            raise InvalidSyntaxError(msg)
        if password is None or _PASSWORD.fullmatch(password) is None:
            msg = 'the ICE password is not valid'
            raise InvalidSyntaxError(msg)
        if role not in {RTCIceRole.controlling, RTCIceRole.controlled}:
            msg = 'role must be controlling or controlled'
            raise ValueError(msg)
        self._native_obj.start(ufrag, password, role)

    def add_remote_candidate(
        self, remote_candidate: webrtc.RTCIceCandidate | webrtc.RTCIceCandidateInit | None = None
    ) -> None:
        """Adds a candidate of the remote agent to a standalone transport.

        Args:
            remote_candidate (:obj:`webrtc.RTCIceCandidate` or :obj:`webrtc.RTCIceCandidateInit`, optional): The
                candidate, which needs ``sdp_mid`` or ``sdp_m_line_index``.

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
        """Stops a standalone transport: it's closed, without a ``statechange`` event.

        Raises:
            webrtc.InvalidStateError: If it belongs to a connection.
        """
        self._check_standalone('stop')
        self._native_obj.stop()

    def get_selected_candidate_pair(self) -> webrtc.RTCIceCandidatePair | None:
        """Returns the local and the remote candidate the transport sends and receives with.

        Returns:
            :obj:`webrtc.RTCIceCandidatePair`, optional: The pair, :obj:`None` until one is selected.
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
        """Returns the candidates gathered for the transport, sent in ``icecandidate`` events of the connection.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate_of(c) for c in self._native_obj.getLocalCandidates()]

    def get_remote_candidates(self) -> list[webrtc.RTCIceCandidate]:
        """Returns the candidates the remote peer signaled for the transport, but not peer-reflexive ones.

        They're signaled in its description or with :meth:`webrtc.RTCPeerConnection.add_ice_candidate`.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate_of(c) for c in self._native_obj.getRemoteCandidates()]

    def get_local_parameters(self) -> webrtc.RTCIceParameters | None:
        """Returns the ICE parameters of the transport in the local description.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, :obj:`None` without a local description.
        """
        parameters = self._native_obj.getLocalParameters()
        return RTCIceParameters(*parameters, ice_lite=False) if parameters is not None else None

    def get_remote_parameters(self) -> webrtc.RTCIceParameters | None:
        """Returns the ICE parameters of the transport in the remote description.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, :obj:`None` without a remote description.
        """
        parameters = self._native_obj.getRemoteParameters()
        return RTCIceParameters(*parameters) if parameters is not None else None

    @property
    def component(self) -> webrtc.RTCIceComponent:
        """:obj:`webrtc.RTCIceComponent`: The ICE component being used by the transport, ``rtp`` or ``rtcp``."""
        return self._native_obj.component

    @property
    def gathering_state(self) -> webrtc.RTCIceGathererState:
        """:obj:`webrtc.RTCIceGathererState`: The gathering state of the ICE agent."""
        return self._native_obj.gatheringState

    @property
    def role(self) -> webrtc.RTCIceRole | None:
        """:obj:`webrtc.RTCIceRole`, optional: Whether the ICE agent decides the candidate pair to use.

        :obj:`None` for a standalone transport that isn't started.
        """
        role = self._native_obj.role
        if role == RTCIceRole.unknown and self._native_obj._standalone:
            return None
        return role

    @property
    def state(self) -> webrtc.RTCIceTransportState:
        """:obj:`webrtc.RTCIceTransportState`: The current state of the ICE agent.

        Note:
            For more details of values: https://developer.mozilla.org/en-US/docs/Web/API/RTCIceTransportState
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
