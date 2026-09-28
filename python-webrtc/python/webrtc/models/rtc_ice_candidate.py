#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

from webrtc import (
    RTCIceCandidateType,
    RTCIceComponent,
    RTCIceProtocol,
    RTCIceServerTransportProtocol,
    RTCIceTcpCandidateType,
)
from webrtc.utils.names import alias

_FOUNDATION = re.compile(r'[A-Za-z0-9+/]{1,32}')
_DIGITS = re.compile(r'[0-9]+')
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`{|}~A-Za-z0-9]+")


def _number(token: str, max_digits: int, low: int, high: int) -> Optional[int]:
    if len(token) > max_digits or not _DIGITS.fullmatch(token):
        return None
    value = int(token)
    return value if low <= value <= high else None


def _parse_candidate(value: str, strict: bool = True) -> Optional[Dict[str, Any]]:
    """Parses a candidate-attribute (RFC 8839, with the tcptype of RFC 6544), or returns :obj:`None`.
    Not strict, a candidate other than a host one may have no related address, as libwebrtc describes
    peer-reflexive candidates."""
    if not value.startswith('candidate:'):
        return None
    tokens = value[len('candidate:') :].split(' ')
    if len(tokens) < 8 or tokens[6] != 'typ' or any(not t for t in tokens):
        return None

    foundation, component, transport, priority, address, port, _, cand_type, *rest = tokens
    component_id = _number(component, 3, 1, 256)
    fields = {
        'foundation': foundation if _FOUNDATION.fullmatch(foundation) else None,
        'component': {1: 'rtp', 2: 'rtcp'}.get(component_id),
        'priority': _number(priority, 10, 1, 2**31 - 1),
        'address': address,
        'protocol': transport.lower(),
        'port': _number(port, 5, 0, 65535),
        'type': cand_type.lower(),
        'tcp_type': None,
        'related_address': None,
        'related_port': None,
    }
    if (
        None in (fields['foundation'], fields['priority'], fields['port'])
        or component_id is None
        or fields['protocol'] not in ('udp', 'tcp')
        or fields['type'] not in ('host', 'srflx', 'prflx', 'relay')
    ):
        return None

    if rest[:1] == ['raddr']:
        if len(rest) < 4 or rest[2] != 'rport':
            return None
        fields['related_address'] = rest[1]
        fields['related_port'] = _number(rest[3], 5, 0, 65535)
        if fields['related_port'] is None:
            return None
        rest = rest[4:]
    elif fields['type'] != 'host' and strict:
        return None

    if rest[:1] == ['tcptype']:
        if len(rest) < 2 or rest[1].lower() not in ('active', 'passive', 'so'):
            return None
        fields['tcp_type'] = rest[1].lower()
        rest = rest[2:]
    elif fields['protocol'] == 'tcp' and fields['type'] != 'relay':
        return None

    # extensions are pairs of a token and a value without spaces (like an ufrag, with "/" and "+")
    if len(rest) % 2 or not all(_TOKEN.fullmatch(t) for t in rest[::2]):
        return None
    return fields


def _member_or_none(cls, value):
    # candidates with values the enum doesn't have are valid
    try:
        return cls(value) if value is not None else None
    except ValueError:
        return None


@dataclass(frozen=True)
class RTCIceParameters:
    """The ICE username fragment and password of one end of an :obj:`webrtc.RTCIceTransport`.

    Args:
        username_fragment (:obj:`str`): The username fragment (``a=ice-ufrag``).
        password (:obj:`str`): The password (``a=ice-pwd``).
    """

    username_fragment: str
    password: str

    #: Alias for :attr:`username_fragment`
    usernameFragment = alias('username_fragment')


@dataclass(frozen=True)
class RTCIceCandidatePair:
    """The local and the remote candidate an :obj:`webrtc.RTCIceTransport` sends and receives with.

    Args:
        local (:obj:`webrtc.RTCIceCandidate`): The local candidate.
        remote (:obj:`webrtc.RTCIceCandidate`): The remote candidate.
    """

    local: 'RTCIceCandidate'
    remote: 'RTCIceCandidate'


@dataclass(frozen=True, repr=False)
class RTCIceCandidate:
    """An ICE candidate: a way the remote peer may be reached.

    Candidates are gathered by :obj:`webrtc.RTCPeerConnection` (see its ``icecandidate`` event), sent to the remote
    peer, and added there with :meth:`webrtc.RTCPeerConnection.add_ice_candidate`. The fields parsed from
    :attr:`candidate` are :obj:`None` if it can't be parsed, the candidate string isn't validated here.

    Args:
        candidate (:obj:`str`, optional): The candidate-attribute from SDP, like ``'candidate:1 1 udp ...'``.
            An empty string means the end of candidates.
        sdp_mid (:obj:`str`, optional): The media stream identification tag of the media section of the candidate.
        sdp_m_line_index (:obj:`int`, optional): The index of the media section of the candidate.
        username_fragment (:obj:`str`, optional): The ICE username fragment the candidate belongs to.
        relay_protocol (:obj:`webrtc.RTCIceServerTransportProtocol`, optional): For a local relay candidate,
            the protocol used to reach the TURN server. Not signaled, so :obj:`None` for remote candidates.
        url (:obj:`str`, optional): For a local candidate, the STUN or TURN server that gathered it.

    Raises:
        :obj:`TypeError`: If both ``sdp_mid`` and ``sdp_m_line_index`` are :obj:`None`.
    """

    candidate: str = ''
    sdp_mid: Optional[str] = None
    sdp_m_line_index: Optional[int] = None
    username_fragment: Optional[str] = None
    relay_protocol: Optional[RTCIceServerTransportProtocol] = None
    url: Optional[str] = None

    def __post_init__(self):
        if self.sdp_mid is None and self.sdp_m_line_index is None:
            raise TypeError('sdp_mid and sdp_m_line_index are both None')
        object.__setattr__(self, 'candidate', str(self.candidate))
        object.__setattr__(self, 'relay_protocol', _member_or_none(RTCIceServerTransportProtocol, self.relay_protocol))
        # the fields parsed from the candidate, not a field of the dataclass
        object.__setattr__(self, '_parsed', _parse_candidate(self.candidate) or {})

    @staticmethod
    def _members_of(
        candidate: Union['RTCIceCandidate', Dict[str, Any]],
    ) -> Tuple[str, Optional[str], Optional[int], Optional[str]]:
        """The candidate, sdp_mid, sdp_m_line_index and username_fragment of a candidate or of its JSON form."""
        if isinstance(candidate, RTCIceCandidate):
            return candidate.candidate, candidate.sdp_mid, candidate.sdp_m_line_index, candidate.username_fragment
        if isinstance(candidate, dict):
            return (
                candidate.get('candidate') or '',
                candidate.get('sdpMid'),
                candidate.get('sdpMLineIndex'),
                candidate.get('usernameFragment'),
            )
        raise TypeError(f'candidate must be an RTCIceCandidate or a dict, not {type(candidate).__name__}')

    @classmethod
    def _peer_reflexive(cls, kwargs: Dict[str, Any]) -> 'RTCIceCandidate':
        """A remote peer-reflexive candidate, only known from connectivity checks: its candidate string and
        address aren't exposed, as the remote peer didn't signal them.

        Args:
            kwargs (:obj:`dict`): The arguments of the constructor, as the native candidate gives them."""
        fields = _parse_candidate(kwargs.get('candidate', ''), strict=False) or {}
        candidate = cls(**{**kwargs, 'candidate': ''})
        # libwebrtc knows no related address of it, which is port 0
        parsed = {**fields, 'address': None, 'related_address': None, 'related_port': 0}
        object.__setattr__(candidate, '_parsed', parsed)
        return candidate

    @classmethod
    def from_json(cls, init: Dict[str, Any]) -> 'RTCIceCandidate':
        """Creates a candidate from its JSON form, as :meth:`to_json` returns it.

        Args:
            init (:obj:`dict`): A dictionary with ``candidate``, ``sdpMid``, ``sdpMLineIndex``
                and ``usernameFragment`` keys, all optional.

        Returns:
            :obj:`webrtc.RTCIceCandidate`: The candidate.

        Raises:
            :obj:`TypeError`: If both ``sdpMid`` and ``sdpMLineIndex`` are missing or :obj:`None`.
        """
        return cls(*cls._members_of(init))

    @property
    def foundation(self) -> Optional[str]:
        """:obj:`str`, optional: An identifier of candidates of the same type, base and server."""
        return self._parsed.get('foundation')

    @property
    def component(self) -> Optional[RTCIceComponent]:
        """:obj:`webrtc.RTCIceComponent`, optional: Whether the candidate is for RTP or RTCP."""
        return _member_or_none(RTCIceComponent, self._parsed.get('component'))

    @property
    def priority(self) -> Optional[int]:
        """:obj:`int`, optional: The priority of the candidate."""
        return self._parsed.get('priority')

    @property
    def address(self) -> Optional[str]:
        """:obj:`str`, optional: The IP address or the host name of the candidate."""
        return self._parsed.get('address')

    @property
    def protocol(self) -> Optional[RTCIceProtocol]:
        """:obj:`webrtc.RTCIceProtocol`, optional: The transport protocol of the candidate."""
        return _member_or_none(RTCIceProtocol, self._parsed.get('protocol'))

    @property
    def port(self) -> Optional[int]:
        """:obj:`int`, optional: The port of the candidate."""
        return self._parsed.get('port')

    @property
    def type(self) -> Optional[RTCIceCandidateType]:
        """:obj:`webrtc.RTCIceCandidateType`, optional: The type of the candidate."""
        return _member_or_none(RTCIceCandidateType, self._parsed.get('type'))

    @property
    def tcp_type(self) -> Optional[RTCIceTcpCandidateType]:
        """:obj:`webrtc.RTCIceTcpCandidateType`, optional: The type of a TCP candidate."""
        return _member_or_none(RTCIceTcpCandidateType, self._parsed.get('tcp_type'))

    @property
    def related_address(self) -> Optional[str]:
        """:obj:`str`, optional: For a candidate that isn't a host one, the address it's derived from."""
        return self._parsed.get('related_address')

    @property
    def related_port(self) -> Optional[int]:
        """:obj:`int`, optional: For a candidate that isn't a host one, the port it's derived from."""
        return self._parsed.get('related_port')

    def to_json(self) -> Dict[str, Any]:
        """The candidate as a JSON-serializable dictionary, to send to the remote peer.

        Returns:
            :obj:`dict`: ``candidate``, ``sdpMid``, ``sdpMLineIndex`` and ``usernameFragment``.
        """
        return {
            'candidate': self.candidate,
            'sdpMid': self.sdp_mid,
            'sdpMLineIndex': self.sdp_m_line_index,
            'usernameFragment': self.username_fragment,
        }

    def __repr__(self):
        return (
            f'RTCIceCandidate({self.candidate!r}, sdp_mid={self.sdp_mid!r}, sdp_m_line_index={self.sdp_m_line_index!r})'
        )

    #: Alias for :attr:`sdp_mid`
    sdpMid = alias('sdp_mid')
    #: Alias for :attr:`sdp_m_line_index`
    sdpMLineIndex = alias('sdp_m_line_index')
    #: Alias for :attr:`username_fragment`
    usernameFragment = alias('username_fragment')
    #: Alias for :attr:`relay_protocol`
    relayProtocol = alias('relay_protocol')
    #: Alias for :attr:`tcp_type`
    tcpType = tcp_type
    #: Alias for :attr:`related_address`
    relatedAddress = related_address
    #: Alias for :attr:`related_port`
    relatedPort = related_port
    #: Alias for :attr:`to_json`
    toJSON = to_json
    #: Alias for :attr:`from_json`
    fromJSON = from_json
