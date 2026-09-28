#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import re
import weakref
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

from webrtc import (
    CricketIceGatheringState,
    InvalidStateError,
    InvalidSyntaxError,
    RTCIceCandidate,
    RTCIceCandidatePair,
    RTCIceParameters,
    RTCIceRole,
    RTCIceServer,
    RTCIceTransportState,
    RTCPeerConnectionIceEvent,
    WebRTCObject,
    wrtc,
)
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc


# RFC 8839: ice-char is ALPHA / DIGIT / "+" / "/", the username fragment is 4 to 256 of them, the password 22 to 256
_UFRAG = re.compile(r'[A-Za-z0-9+/]{4,256}')
_PASSWORD = re.compile(r'[A-Za-z0-9+/]{22,256}')

# the candidates of every transport, by their candidate-attribute: a candidate is the same object each time
_candidates: 'weakref.WeakKeyDictionary[wrtc.RTCIceTransport, Dict[str, webrtc.RTCIceCandidate]]' = (
    weakref.WeakKeyDictionary()
)


class RTCIceTransport(WebRTCObject, EventTarget):
    """The ICE transport a :obj:`webrtc.RTCDtlsTransport` of a connection runs over, or a standalone transport.

    A standalone one (``RTCIceTransport()``) connects after :meth:`gather`, :meth:`start` and
    :meth:`add_remote_candidate`.

    Events (see :meth:`on`):
        ``statechange`` (:obj:`webrtc.Event`): :attr:`state` changed.
        ``gatheringstatechange`` (:obj:`webrtc.Event`): :attr:`gathering_state` changed.
        ``selectedcandidatepairchange`` (:obj:`webrtc.Event`): :meth:`get_selected_candidate_pair` changed.
        ``icecandidate`` (:obj:`webrtc.RTCPeerConnectionIceEvent`): A standalone transport gathered a candidate,
        or :obj:`None` once it gathered them all.
    """

    _class = wrtc.RTCIceTransport
    _events = ('statechange', 'gatheringstatechange', 'selectedcandidatepairchange', 'icecandidate')

    def __init__(self):
        super().__init__()
        # a standalone transport delivers its events to the loop it's created on
        self._attach()

    def _candidate_of(self, native: 'wrtc.IceCandidateInit') -> 'webrtc.RTCIceCandidate':
        """The candidate object of a native candidate, the same one each time."""
        kwargs = native.kwargs()
        known = _candidates.setdefault(self._native_obj, {})
        if kwargs['candidate'] not in known:
            known[kwargs['candidate']] = RTCIceCandidate(**kwargs)
        return known[kwargs['candidate']]

    def _remember(self, candidate: 'webrtc.RTCIceCandidate') -> None:
        """Makes a candidate the object of its native candidate, unless there's one already."""
        _candidates.setdefault(self._native_obj, {}).setdefault(candidate.candidate, candidate)

    def _on_event(self, name: str, *args):
        # the states change along with their events
        if name == 'statechange':
            (state,) = args
            self._native_obj._surfaceState(state)
        elif name == 'gatheringstatechange':
            (state,) = args
            self._native_obj._surfaceGatheringState(state)
        elif name == 'icecandidate' and args and args[0] is not None:
            self._native_obj._surfaceCandidate()

    def _create_event(self, name: str, *args):
        if name == 'icecandidate':
            candidate = self._candidate_of(args[0]) if args and args[0] is not None else None
            return RTCPeerConnectionIceEvent(name, candidate, None, target=self)
        return super()._create_event(name, *args)

    def _check_standalone(self, operation: str) -> None:
        if not self._native_obj._standalone:
            raise InvalidStateError(f'Can not {operation}: the transport belongs to an RTCPeerConnection')

    def _check_open(self, operation: str) -> None:
        self._check_standalone(operation)
        if self.state == RTCIceTransportState.closed:
            raise InvalidStateError(f'Can not {operation}: the transport is stopped')

    def gather(
        self,
        gather_policy: Union['webrtc.RTCIceTransportPolicy', str] = 'all',
        ice_servers: Optional[Sequence[Union['webrtc.RTCIceServer', Dict[str, Any]]]] = None,
    ) -> None:
        """Gathers the candidates of a standalone transport, sent in ``icecandidate`` events.

        Args:
            gather_policy (:obj:`webrtc.RTCIceTransportPolicy`, optional): All candidates, or only relay ones.
            ice_servers (:obj:`list` of :obj:`webrtc.RTCIceServer`, optional): STUN and TURN servers to gather with.
                A :obj:`dict` of the arguments of :obj:`webrtc.RTCIceServer` is accepted too.

        Raises:
            :obj:`webrtc.InvalidStateError`: If it's stopped, gathering already, or belongs to a connection.
            :obj:`webrtc.InvalidSyntaxError`: If an ICE server URL is invalid.
            :obj:`webrtc.InvalidAccessError`: If a TURN server has no credentials.
            :obj:`TypeError`: If the policy isn't a value of :obj:`webrtc.RTCIceTransportPolicy`.
        """
        self._check_open('gather')
        if self.gathering_state != CricketIceGatheringState.new:
            raise InvalidStateError('The transport gathers its candidates already')
        self._native_obj.gather(gather_policy, RTCIceServer._to_native_list(ice_servers or ()))

    def start(
        self,
        remote_parameters: Union['webrtc.RTCIceParameters', Dict[str, str]],
        role: Union['webrtc.RTCIceRole', str] = 'controlled',
    ) -> None:
        """Starts connecting a standalone transport to the remote agent, with the candidates added, or later.
        Remote parameters that differ from the ones given before remove the remote candidates.

        Args:
            remote_parameters (:obj:`webrtc.RTCIceParameters`): The username fragment and the password of the
                remote agent. A :obj:`dict` of the arguments of :obj:`webrtc.RTCIceParameters` is accepted too.
            role (:obj:`webrtc.RTCIceRole`, optional): Controlling or controlled (the default). When both agents take
                the same role, one of them switches.

        Raises:
            :obj:`webrtc.InvalidStateError`: If it's stopped, started with another role, or belongs to a connection.
            :obj:`webrtc.InvalidSyntaxError`: If the username fragment or the password is invalid.
            :obj:`ValueError`: If the role is neither controlling nor controlled.
        """
        self._check_open('start')
        if isinstance(remote_parameters, dict):
            remote_parameters = RTCIceParameters(**remote_parameters)
        if not _UFRAG.fullmatch(remote_parameters.username_fragment):
            raise InvalidSyntaxError(f'{remote_parameters.username_fragment!r} is not a valid ICE username fragment')
        if not _PASSWORD.fullmatch(remote_parameters.password):
            raise InvalidSyntaxError('the ICE password is not valid')
        if role not in (RTCIceRole.controlling, RTCIceRole.controlled):
            raise ValueError('role must be controlling or controlled')
        self._native_obj.start(remote_parameters.username_fragment, remote_parameters.password, role)

    def add_remote_candidate(self, candidate: Union['webrtc.RTCIceCandidate', Dict[str, Any]]) -> None:
        """Adds a candidate of the remote agent to a standalone transport.

        Args:
            candidate (:obj:`webrtc.RTCIceCandidate`): The candidate, or its JSON form
                (see :meth:`webrtc.RTCIceCandidate.to_json`).

        Raises:
            :obj:`TypeError`: If the candidate has neither ``sdp_mid`` nor ``sdp_m_line_index``.
            :obj:`webrtc.InvalidStateError`: If it's stopped, or belongs to a connection.
            :obj:`webrtc.OperationError`: If the candidate can't be parsed.
        """
        self._check_open('add a remote candidate')
        if not isinstance(candidate, RTCIceCandidate):
            candidate = RTCIceCandidate.from_json(candidate)
        self._native_obj.addRemoteCandidate(
            candidate.candidate, candidate.sdp_mid or '', candidate.sdp_m_line_index or 0, candidate.username_fragment
        )
        self._remember(candidate)

    def stop(self) -> None:
        """Stops a standalone transport: it's closed, without a ``statechange`` event.

        Raises:
            :obj:`webrtc.InvalidStateError`: If it belongs to a connection.
        """
        self._check_standalone('stop')
        self._native_obj.stop()

    def get_selected_candidate_pair(self) -> Optional['webrtc.RTCIceCandidatePair']:
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

    def get_local_candidates(self) -> List['webrtc.RTCIceCandidate']:
        """Returns the candidates gathered for the transport, sent in ``icecandidate`` events of the connection.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate_of(c) for c in self._native_obj.getLocalCandidates()]

    def get_remote_candidates(self) -> List['webrtc.RTCIceCandidate']:
        """Returns the candidates the remote peer signaled for the transport, in its description or with
        :meth:`webrtc.RTCPeerConnection.add_ice_candidate`. Peer-reflexive ones aren't.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate_of(c) for c in self._native_obj.getRemoteCandidates()]

    def get_local_parameters(self) -> Optional['webrtc.RTCIceParameters']:
        """Returns the ICE parameters of the transport in the local description.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, :obj:`None` without a local description.
        """
        parameters = self._native_obj.getLocalParameters()
        return RTCIceParameters(*parameters) if parameters is not None else None

    def get_remote_parameters(self) -> Optional['webrtc.RTCIceParameters']:
        """Returns the ICE parameters of the transport in the remote description.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, :obj:`None` without a remote description.
        """
        parameters = self._native_obj.getRemoteParameters()
        return RTCIceParameters(*parameters) if parameters is not None else None

    @property
    def component(self) -> 'webrtc.RTCIceComponent':
        """:obj:`webrtc.RTCIceComponent`: The ICE component being used by the transport, ``rtp`` or ``rtcp``."""
        return self._native_obj.component

    @property
    def gathering_state(self) -> 'webrtc.CricketIceGatheringState':
        """:obj:`webrtc.CricketIceGatheringState`: The gathering state of the ICE agent."""
        return self._native_obj.gatheringState

    @property
    def role(self) -> Optional['webrtc.RTCIceRole']:
        """:obj:`webrtc.RTCIceRole`, optional: Whether the ICE agent is the one that makes the final decision as to
        the candidate pair to use or not. :obj:`None` for a standalone transport that isn't started."""
        role = self._native_obj.role
        if role == RTCIceRole.unknown and self._native_obj._standalone:
            return None
        return role

    @property
    def state(self) -> 'webrtc.RTCIceTransportState':
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
