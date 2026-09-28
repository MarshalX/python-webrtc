#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import re
import weakref
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Union

from webrtc import WebRTCObject, wrtc
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
    """The ICE transport a :obj:`webrtc.RTCDtlsTransport` of a connection runs over, or a transport of its own.

    Created with ``RTCIceTransport()``, it's a transport of its own (as in the WebRTC ICE extension): :meth:`gather`
    gathers its candidates, sent in ``icecandidate`` events, :meth:`start` gives it the parameters of the remote
    agent, :meth:`add_remote_candidate` its candidates, and it connects.

    Events (see :meth:`on`):
        ``statechange`` (:obj:`webrtc.Event`): :attr:`state` changed.
        ``gatheringstatechange`` (:obj:`webrtc.Event`): :attr:`gathering_state` changed.
        ``selectedcandidatepairchange`` (:obj:`webrtc.Event`): :meth:`get_selected_candidate_pair` changed.
        ``icecandidate`` (:obj:`webrtc.RTCPeerConnectionIceEvent`): A transport of its own gathered a candidate,
            or :obj:`None` once it gathered them all.
    """

    _class = wrtc.RTCIceTransport
    _events = ('statechange', 'gatheringstatechange', 'selectedcandidatepairchange', 'icecandidate')

    def __init__(self, native_obj=None):
        super().__init__(native_obj)
        if native_obj is None:
            # a transport of its own delivers its events to the loop it's created on
            self._attach()

    def _candidate(self, init, candidate: Optional['webrtc.RTCIceCandidate'] = None) -> 'webrtc.RTCIceCandidate':
        """The candidate object of a native candidate (or the one given), the same one each time"""
        from webrtc import RTCIceCandidate

        kwargs = init.kwargs() if init is not None else None
        key = kwargs['candidate'] if kwargs is not None else candidate.candidate
        known = _candidates.setdefault(self._native_obj, {})
        if key not in known:
            known[key] = candidate if candidate is not None else RTCIceCandidate(**kwargs)
        return known[key]

    def _create_event(self, name: str, *args):
        from webrtc import Event, RTCPeerConnectionIceEvent

        if name == 'icecandidate':
            candidate = self._candidate(args[0]) if args and args[0] is not None else None
            return RTCPeerConnectionIceEvent(name, candidate, None, target=self)
        return Event(name, self)

    def _check_open(self, operation: str) -> None:
        from webrtc import InvalidStateError

        if not self._native_obj._standalone:
            raise InvalidStateError(f'Can not {operation}: the transport belongs to an RTCPeerConnection')
        if self.state == wrtc.RTCIceTransportState.closed:
            raise InvalidStateError(f'Can not {operation}: the transport is stopped')

    def gather(
        self,
        gather_policy: Union['webrtc.RTCIceTransportPolicy', str] = 'all',
        ice_servers: Optional[Sequence['webrtc.RTCIceServer']] = None,
    ) -> None:
        """Gathers the candidates of a transport of its own, sent in ``icecandidate`` events.

        Args:
            gather_policy (:obj:`webrtc.RTCIceTransportPolicy`, optional): All candidates, or only relay ones.
            ice_servers (:obj:`list` of :obj:`webrtc.RTCIceServer`, optional): STUN and TURN servers to gather with.

        Raises:
            :obj:`webrtc.InvalidStateError`: If it's stopped, gathering already, or belongs to a connection.
            :obj:`webrtc.InvalidSyntaxError`: If an ICE server URL is invalid.
            :obj:`webrtc.InvalidAccessError`: If a TURN server has no credentials.
        """
        from webrtc import InvalidStateError, RTCIceServer
        from webrtc.models.rtc_configuration import RTCIceTransportPolicy, _enum

        self._check_open('gather')
        if self.gathering_state != wrtc.CricketIceGatheringState.new:
            raise InvalidStateError('The transport gathers its candidates already')
        policy = _enum(RTCIceTransportPolicy, gather_policy)
        servers = [
            (RTCIceServer(**server) if isinstance(server, dict) else server)._validate() for server in ice_servers or ()
        ]
        self._native_obj.gather(policy == RTCIceTransportPolicy.relay, servers)

    def start(
        self,
        remote_parameters: 'webrtc.RTCIceParameters',
        role: Union['webrtc.RTCIceRole', str] = 'controlled',
    ) -> None:
        """Starts connecting a transport of its own to the remote agent, with the candidates added, or later.
        Remote parameters that differ from the ones given before remove the remote candidates.

        Args:
            remote_parameters (:obj:`webrtc.RTCIceParameters`): The username fragment and the password of the
                remote agent.
            role (:obj:`webrtc.RTCIceRole`, optional): Controlling or controlled (the default). When both agents take
                the same role, one of them switches.

        Raises:
            :obj:`webrtc.InvalidStateError`: If it's stopped, started with another role, or belongs to a connection.
            :obj:`webrtc.InvalidSyntaxError`: If the username fragment or the password is invalid.
        """
        from webrtc import InvalidSyntaxError, RTCIceParameters

        self._check_open('start')
        if isinstance(remote_parameters, dict):
            remote_parameters = RTCIceParameters(**remote_parameters)
        if not _UFRAG.fullmatch(remote_parameters.username_fragment):
            raise InvalidSyntaxError(f'{remote_parameters.username_fragment!r} is not a valid ICE username fragment')
        if not _PASSWORD.fullmatch(remote_parameters.password):
            raise InvalidSyntaxError('the ICE password is not valid')
        role = role if isinstance(role, wrtc.RTCIceRole) else getattr(wrtc.RTCIceRole, str(role), None)
        if role not in (wrtc.RTCIceRole.controlling, wrtc.RTCIceRole.controlled):
            raise ValueError('role must be controlling or controlled')
        self._native_obj.start(remote_parameters.username_fragment, remote_parameters.password, role)

    def add_remote_candidate(self, candidate: Union['webrtc.RTCIceCandidate', dict]) -> None:
        """Adds a candidate of the remote agent to a transport of its own.

        Args:
            candidate (:obj:`webrtc.RTCIceCandidate`): The candidate, or its JSON form.

        Raises:
            :obj:`webrtc.InvalidStateError`: If it's stopped, or belongs to a connection.
            :obj:`webrtc.OperationError`: If the candidate can't be parsed.
        """
        from webrtc import RTCIceCandidate

        self._check_open('add a remote candidate')
        if isinstance(candidate, dict):
            candidate = RTCIceCandidate.from_json(candidate)
        self._native_obj.addRemoteCandidate(
            candidate.candidate, candidate.sdp_mid or '', candidate.sdp_m_line_index or 0, candidate.username_fragment
        )
        self._candidate(None, candidate)

    def stop(self) -> None:
        """Stops a transport of its own: it's closed, without a ``statechange`` event.

        Raises:
            :obj:`webrtc.InvalidStateError`: If it belongs to a connection.
        """
        from webrtc import InvalidStateError

        if not self._native_obj._standalone:
            raise InvalidStateError('Can not stop the transport of an RTCPeerConnection')
        self._native_obj.stop()

    def get_selected_candidate_pair(self) -> Optional['webrtc.RTCIceCandidatePair']:
        """Returns the local and the remote candidate the transport sends and receives with.

        Returns:
            :obj:`webrtc.RTCIceCandidatePair`, optional: The pair, :obj:`None` until one is selected.
        """
        from webrtc import RTCIceCandidate, RTCIceCandidatePair

        pair = self._native_obj.getSelectedCandidatePair()
        if pair is None:
            return None
        local, remote = pair
        remote = remote.kwargs()
        if ' typ prflx' in remote.get('candidate', ''):
            remote_candidate = RTCIceCandidate._peer_reflexive(remote)
        else:
            remote_candidate = RTCIceCandidate(**remote)
        return RTCIceCandidatePair(RTCIceCandidate(**local.kwargs()), remote_candidate)

    def get_local_candidates(self) -> List['webrtc.RTCIceCandidate']:
        """Returns the candidates gathered for the transport, sent in ``icecandidate`` events of the connection.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate(c) for c in self._native_obj.getLocalCandidates()]

    def get_remote_candidates(self) -> List['webrtc.RTCIceCandidate']:
        """Returns the candidates the remote peer signaled for the transport, in its description or with
        :meth:`webrtc.RTCPeerConnection.add_ice_candidate`. Peer-reflexive ones aren't.

        Returns:
            :obj:`list` of :obj:`webrtc.RTCIceCandidate`: The candidates.
        """
        return [self._candidate(c) for c in self._native_obj.getRemoteCandidates()]

    def get_local_parameters(self) -> Optional['webrtc.RTCIceParameters']:
        """Returns the ICE parameters of the transport in the local description.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, :obj:`None` without a local description.
        """
        from webrtc import RTCIceParameters

        parameters = self._native_obj.getLocalParameters()
        return RTCIceParameters(*parameters) if parameters is not None else None

    def get_remote_parameters(self) -> Optional['webrtc.RTCIceParameters']:
        """Returns the ICE parameters of the transport in the remote description.

        Returns:
            :obj:`webrtc.RTCIceParameters`, optional: The parameters, :obj:`None` without a remote description.
        """
        from webrtc import RTCIceParameters

        parameters = self._native_obj.getRemoteParameters()
        return RTCIceParameters(*parameters) if parameters is not None else None

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

    def _on_event(self, name: str, *args):
        # the states change along with their events
        if name in ('statechange', 'gatheringstatechange'):
            self._native_obj._surface(name, args[0])
        elif name == 'icecandidate' and args and args[0] is not None:
            self._native_obj._surfaceCandidate()

    @property
    def component(self) -> 'webrtc.RTCIceComponent':
        """The ICE component being used by the transport. The value is one of the strings from
        the :obj:`webrtc.RTCIceComponent` enumerated type: ``rtp`` or ``rtcp``."""
        return self._native_obj.component

    @property
    def gathering_state(self) -> 'webrtc.CricketIceGatheringState':
        """A member of :obj:`webrtc.CricketIceGatheringState` enum, indicating which current
        gathering state of the ICE agent"""
        return self._native_obj.gatheringState

    @property
    def role(self) -> Optional['webrtc.RTCIceRole']:
        """A member of :obj:`webrtc.RTCIceRole`; this indicates whether the ICE agent is the one that makes the
        final decision as to the candidate pair to use or not. :obj:`None` for a transport of its own that isn't
        started."""
        role = self._native_obj.role
        if role == wrtc.RTCIceRole.unknown and self._native_obj._standalone:
            return None
        return role

    @property
    def state(self) -> 'webrtc.RTCIceTransportState':
        """A member of :obj:`webrtc.RTCIceTransportState` indicating what the current state of the ICE agent is.

        Note:
            For more details of values: https://developer.mozilla.org/en-US/docs/Web/API/RTCIceTransportState
        """
        return self._native_obj.state

    #: Alias for :attr:`gathering_state`
    gatheringState = gathering_state
