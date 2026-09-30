#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""ICE candidates and parameters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, TypeVar, Union

from webrtc import (
    RTCIceCandidateType,
    RTCIceComponent,
    RTCIceProtocol,
    RTCIceServerTransportProtocol,
    RTCIceTcpCandidateType,
)
from webrtc.utils.names import Alias, alias

_FOUNDATION = re.compile(r'[A-Za-z0-9+/]{1,32}')
_DIGITS = re.compile(r'[0-9]+')
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`{|}~A-Za-z0-9]+")

_MIN_TOKENS = 8  # foundation, component, transport, priority, address, port, "typ" and the type
_RELATED_TOKENS = 4  # "raddr", the address, "rport" and the port
_TCP_TYPE_TOKENS = 2  # "tcptype" and the type
_PORTS = range(65536)
_COMPONENTS = {1: 'rtp', 2: 'rtcp'}
_PROTOCOLS = frozenset({'udp', 'tcp'})
_TYPES = frozenset({'host', 'srflx', 'prflx', 'relay'})
_TCP_TYPES = frozenset({'active', 'passive', 'so'})

_T = TypeVar('_T')
_EnumT = TypeVar('_EnumT', bound=Enum)
#: The fields parsed from a candidate-attribute, by the names of the properties of RTCIceCandidate
_CandidateFields = dict[str, Union[str, int, None]]


class _InvalidCandidateError(ValueError):
    """A candidate-attribute that doesn't parse."""


def _number(token: str, max_digits: int, valid: range) -> int | None:
    if len(token) > max_digits or not _DIGITS.fullmatch(token):
        return None
    value = int(token)
    return value if value in valid else None


def _required(value: _T | None) -> _T:
    if value is None:
        raise _InvalidCandidateError
    return value


def _one_of(value: str, allowed: frozenset[str]) -> str:
    if value not in allowed:
        raise _InvalidCandidateError
    return value


def _parse_related(fields: _CandidateFields, rest: list[str], *, strict: bool) -> list[str]:
    """Parses the related address and port into the fields, returns the tokens after them."""
    if rest[:1] == ['raddr']:
        if len(rest) < _RELATED_TOKENS or rest[2] != 'rport':
            raise _InvalidCandidateError
        fields['related_address'] = rest[1]
        fields['related_port'] = _required(_number(rest[3], 5, _PORTS))
        return rest[_RELATED_TOKENS:]
    if fields['type'] != 'host' and strict:
        raise _InvalidCandidateError
    return rest


def _parse_tcp_type(fields: _CandidateFields, rest: list[str]) -> list[str]:
    """Parses the tcptype into the fields, returns the tokens after it."""
    if rest[:1] == ['tcptype']:
        if len(rest) < _TCP_TYPE_TOKENS:
            raise _InvalidCandidateError
        fields['tcp_type'] = _one_of(rest[1].lower(), _TCP_TYPES)
        return rest[_TCP_TYPE_TOKENS:]
    if fields['protocol'] == 'tcp' and fields['type'] != 'relay':
        raise _InvalidCandidateError
    return rest


def _base_fields(tokens: list[str]) -> _CandidateFields:
    """The fields of the tokens up to the type."""
    foundation, component, transport, priority, address, port, _, cand_type = tokens
    component_id = _required(_number(component, 3, range(1, 257)))
    return {
        'foundation': _required(foundation if _FOUNDATION.fullmatch(foundation) else None),
        'component': _COMPONENTS.get(component_id),
        'priority': _required(_number(priority, 10, range(1, 2**31))),
        'address': address,
        'protocol': _one_of(transport.lower(), _PROTOCOLS),
        'port': _required(_number(port, 5, _PORTS)),
        'type': _one_of(cand_type.lower(), _TYPES),
        'tcp_type': None,
        'related_address': None,
        'related_port': None,
    }


def _parse_fields(value: str, *, strict: bool) -> _CandidateFields:
    if not value.startswith('candidate:'):
        raise _InvalidCandidateError
    tokens = value[len('candidate:') :].split(' ')
    if len(tokens) < _MIN_TOKENS or tokens[6] != 'typ' or not all(tokens):
        raise _InvalidCandidateError

    fields = _base_fields(tokens[:_MIN_TOKENS])
    rest = _parse_tcp_type(fields, _parse_related(fields, tokens[_MIN_TOKENS:], strict=strict))
    # extensions are pairs of a token and a value without spaces (like an ufrag, with "/" and "+")
    if len(rest) % 2 or not all(_TOKEN.fullmatch(t) for t in rest[::2]):
        raise _InvalidCandidateError
    return fields


def _parse_candidate(value: str, *, strict: bool = True) -> _CandidateFields | None:
    """Parses a candidate-attribute (RFC 8839, with the tcptype of RFC 6544).

    Not strict, a candidate other than a host one may have no related address, as libwebrtc describes
    peer-reflexive candidates.

    Returns:
        :obj:`dict`: The fields, or :obj:`None` if the candidate doesn't parse.
    """
    try:
        return _parse_fields(value, strict=strict)
    except _InvalidCandidateError:
        return None


def _member_or_none(cls: type[_EnumT], value: object) -> _EnumT | None:
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
    usernameFragment: ClassVar[Alias[str]] = alias('username_fragment')


@dataclass(frozen=True)
class RTCIceCandidatePair:
    """The local and the remote candidate an :obj:`webrtc.RTCIceTransport` sends and receives with.

    Args:
        local (:obj:`webrtc.RTCIceCandidate`): The local candidate.
        remote (:obj:`webrtc.RTCIceCandidate`): The remote candidate.
    """

    local: RTCIceCandidate
    remote: RTCIceCandidate


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
        TypeError: If both ``sdp_mid`` and ``sdp_m_line_index`` are :obj:`None`.
    """

    candidate: str = ''
    sdp_mid: str | None = None
    sdp_m_line_index: int | None = None
    username_fragment: str | None = None
    relay_protocol: RTCIceServerTransportProtocol | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if self.sdp_mid is None and self.sdp_m_line_index is None:
            msg = 'sdp_mid and sdp_m_line_index are both None'
            raise TypeError(msg)
        object.__setattr__(self, 'candidate', str(self.candidate))
        object.__setattr__(self, 'relay_protocol', _member_or_none(RTCIceServerTransportProtocol, self.relay_protocol))
        # the fields parsed from the candidate, not a field of the dataclass
        object.__setattr__(self, '_parsed', _parse_candidate(self.candidate) or {})

    @staticmethod
    def _members_of(
        candidate: RTCIceCandidate | dict[str, Any],
    ) -> tuple[str, str | None, int | None, str | None]:
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
        msg = f'candidate must be an RTCIceCandidate or a dict, not {type(candidate).__name__}'
        raise TypeError(msg)

    @classmethod
    def _peer_reflexive(cls, kwargs: dict[str, Any]) -> RTCIceCandidate:
        """A remote peer-reflexive candidate, only known from connectivity checks.

        Its candidate string and address aren't exposed, as the remote peer didn't signal them.

        Args:
            kwargs (:obj:`dict`): The arguments of the constructor, as the native candidate gives them.

        Returns:
            :obj:`webrtc.RTCIceCandidate`: The candidate.
        """
        fields = _parse_candidate(kwargs.get('candidate', ''), strict=False) or {}
        candidate = cls(**{**kwargs, 'candidate': ''})
        # libwebrtc knows no related address of it, which is port 0
        parsed = {**fields, 'address': None, 'related_address': None, 'related_port': 0}
        # past the frozen __setattr__, as __post_init__ parsed the empty candidate string
        vars(candidate)['_parsed'] = parsed
        return candidate

    @classmethod
    def from_json(cls, init: dict[str, Any]) -> RTCIceCandidate:
        """Creates a candidate from its JSON form, as :meth:`to_json` returns it.

        Args:
            init (:obj:`dict`): A dictionary with ``candidate``, ``sdpMid``, ``sdpMLineIndex``
                and ``usernameFragment`` keys, all optional.

        Returns:
            :obj:`webrtc.RTCIceCandidate`: The candidate.
        """
        return cls(*cls._members_of(init))

    @property
    def foundation(self) -> str | None:
        """:obj:`str`, optional: An identifier of candidates of the same type, base and server."""
        return self._parsed.get('foundation')

    @property
    def component(self) -> RTCIceComponent | None:
        """:obj:`webrtc.RTCIceComponent`, optional: Whether the candidate is for RTP or RTCP."""
        return _member_or_none(RTCIceComponent, self._parsed.get('component'))

    @property
    def priority(self) -> int | None:
        """:obj:`int`, optional: The priority of the candidate."""
        return self._parsed.get('priority')

    @property
    def address(self) -> str | None:
        """:obj:`str`, optional: The IP address or the host name of the candidate."""
        return self._parsed.get('address')

    @property
    def protocol(self) -> RTCIceProtocol | None:
        """:obj:`webrtc.RTCIceProtocol`, optional: The transport protocol of the candidate."""
        return _member_or_none(RTCIceProtocol, self._parsed.get('protocol'))

    @property
    def port(self) -> int | None:
        """:obj:`int`, optional: The port of the candidate."""
        return self._parsed.get('port')

    @property
    def type(self) -> RTCIceCandidateType | None:
        """:obj:`webrtc.RTCIceCandidateType`, optional: The type of the candidate."""
        return _member_or_none(RTCIceCandidateType, self._parsed.get('type'))

    @property
    def tcp_type(self) -> RTCIceTcpCandidateType | None:
        """:obj:`webrtc.RTCIceTcpCandidateType`, optional: The type of a TCP candidate."""
        return _member_or_none(RTCIceTcpCandidateType, self._parsed.get('tcp_type'))

    @property
    def related_address(self) -> str | None:
        """:obj:`str`, optional: For a candidate that isn't a host one, the address it's derived from."""
        return self._parsed.get('related_address')

    @property
    def related_port(self) -> int | None:
        """:obj:`int`, optional: For a candidate that isn't a host one, the port it's derived from."""
        return self._parsed.get('related_port')

    def to_json(self) -> dict[str, Any]:
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

    def __repr__(self) -> str:
        return (
            f'RTCIceCandidate({self.candidate!r}, sdp_mid={self.sdp_mid!r}, sdp_m_line_index={self.sdp_m_line_index!r})'
        )

    #: Alias for :attr:`sdp_mid`
    sdpMid: ClassVar[Alias[str | None]] = alias('sdp_mid')
    #: Alias for :attr:`sdp_m_line_index`
    sdpMLineIndex: ClassVar[Alias[int | None]] = alias('sdp_m_line_index')
    #: Alias for :attr:`username_fragment`
    usernameFragment: ClassVar[Alias[str | None]] = alias('username_fragment')
    #: Alias for :attr:`relay_protocol`
    relayProtocol: ClassVar[Alias[RTCIceServerTransportProtocol | None]] = alias('relay_protocol')
    #: Alias for :attr:`tcp_type`
    tcpType: ClassVar = tcp_type
    #: Alias for :attr:`related_address`
    relatedAddress: ClassVar = related_address
    #: Alias for :attr:`related_port`
    relatedPort: ClassVar = related_port
    #: Alias for :attr:`to_json`
    toJSON: ClassVar = to_json
    #: Alias for :attr:`from_json`
    fromJSON: ClassVar = from_json
