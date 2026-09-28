#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import ipaddress
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

import wrtc
from webrtc.exceptions import InvalidAccessError, InvalidSyntaxError, NotSupportedError
from webrtc.models.rtc_certificate import RTCCertificate

RTCIceTransportPolicy = wrtc.RTCIceTransportPolicy
RTCBundlePolicy = wrtc.RTCBundlePolicy
RTCRtcpMuxPolicy = wrtc.RTCRtcpMuxPolicy
RTCRtpHeaderEncryptionPolicy = wrtc.RTCRtpHeaderEncryptionPolicy

# the longest TURN username, as browsers limit it
_MAX_USERNAME_LENGTH = 509

# RFC 7064 and RFC 7065: scheme ":" host [ ":" port ] [ "?transport=" transport ], with udp and tcp transports only
_URL = re.compile(
    r'(?P<scheme>[^:]*):(?P<host>\[[^\]]*\]|[^:?]*)(?::(?P<port>[0-9]*))?(?:\?transport=(?P<transport>[^&]*))?'
)
# RFC 3986 reg-name, without percent-encoding
_REG_NAME = re.compile(r"[A-Za-z0-9\-._~!$&'()*+,;=]+")


def _check_url(url: str) -> str:
    """Returns the scheme of a STUN or TURN server URL.

    Raises:
        :obj:`webrtc.InvalidSyntaxError`: If the URL doesn't match RFC 7064 or RFC 7065.
    """
    match = _URL.fullmatch(url)
    if not match or match['scheme'] not in ('stun', 'stuns', 'turn', 'turns'):
        raise InvalidSyntaxError(f'{url!r} is not a valid STUN or TURN URL')

    host, port, transport = match['host'], match['port'], match['transport']
    if host.startswith('['):
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            raise InvalidSyntaxError(f'{url!r} has an invalid IPv6 address') from None
    elif not _REG_NAME.fullmatch(host):
        raise InvalidSyntaxError(f'{url!r} has an invalid host')

    if port is not None and (not port or int(port) > 65535):
        raise InvalidSyntaxError(f'{url!r} has an invalid port')
    if transport is not None and (match['scheme'].startswith('stun') or transport not in ('udp', 'tcp')):
        raise InvalidSyntaxError(f'{url!r} has an invalid transport')
    return match['scheme']


@dataclass
class RTCOAuthCredential:
    """An OAuth credential of a TURN server (RFC 7635).

    Args:
        mac_key (:obj:`str`): The base64-encoded MAC key.
        access_token (:obj:`str`): The base64-encoded access token.
    """

    mac_key: str
    access_token: str


@dataclass
class RTCIceServer:
    """A STUN or TURN server used to gather ICE candidates.

    Args:
        urls (:obj:`str` or :obj:`list` of :obj:`str`): The URLs of the server, like ``'stun:stun.example.org'``
            or ``'turn:turn.example.org:3478?transport=tcp'``.
        username (:obj:`str`, optional): The username of a TURN server.
        credential (:obj:`str` or :obj:`webrtc.RTCOAuthCredential`, optional): The password of a TURN server,
            or its OAuth credential.
        credential_type (:obj:`str`, optional): ``'password'`` (the default) or ``'oauth'``, which libwebrtc
            doesn't support.
    """

    urls: Union[str, List[str]]
    username: Optional[str] = None
    credential: Optional[Union[str, RTCOAuthCredential]] = None
    credential_type: str = 'password'

    def _validate(self) -> 'wrtc.IceServerInit':
        urls = [self.urls] if isinstance(self.urls, str) else list(self.urls)
        if not urls:
            raise InvalidSyntaxError('urls of an ICE server must not be empty')

        # every URL is parsed before the credentials are checked
        schemes = [_check_url(url) for url in urls]
        if self.credential_type not in ('password', 'oauth'):
            raise ValueError(f"credential_type must be 'password' or 'oauth', not {self.credential_type!r}")
        if any(scheme in ('turn', 'turns') for scheme in schemes):
            if self.credential_type == 'oauth':
                if not isinstance(self.credential, RTCOAuthCredential):
                    raise InvalidAccessError('an OAuth TURN server needs an RTCOAuthCredential')
                raise NotSupportedError('libwebrtc does not support OAuth credentials of TURN servers')
            if self.username is None or not self.credential:
                raise InvalidAccessError('a TURN server needs a username and a credential')
            if len(self.username) > _MAX_USERNAME_LENGTH:
                raise InvalidAccessError(f'the username of a TURN server is longer than {_MAX_USERNAME_LENGTH}')

        native = wrtc.IceServerInit()
        native.urls = urls
        native.username = self.username
        native.credential = self.credential
        return native


@dataclass
class RTCConfiguration:
    """The configuration of a :obj:`webrtc.RTCPeerConnection`.

    Args:
        ice_servers (:obj:`list` of :obj:`webrtc.RTCIceServer`, optional): STUN and TURN servers to gather
            ICE candidates with.
        ice_transport_policy (:obj:`webrtc.RTCIceTransportPolicy`, optional): Which candidates may be used,
            all of them (the default) or only relay ones.
        bundle_policy (:obj:`webrtc.RTCBundlePolicy`, optional): How media is bundled when the remote peer
            doesn't support bundling. Can't be changed with :meth:`webrtc.RTCPeerConnection.set_configuration`.
        rtcp_mux_policy (:obj:`webrtc.RTCRtcpMuxPolicy`, optional): RTCP multiplexing, which is required.
        ice_candidate_pool_size (:obj:`int`, optional): The number of candidates (0 to 255) to gather before
            they are needed. Can't be changed once the local description is set.
        port_range (:obj:`tuple` of two :obj:`int`, optional): The lowest and the highest local UDP and TCP port
            to use, for firewalls that only allow a range. Not in the WebRTC specification.
        certificates (:obj:`list` of :obj:`webrtc.RTCCertificate`, optional): The certificates to authenticate
            with, generated if omitted. Can't be changed with :meth:`webrtc.RTCPeerConnection.set_configuration`,
            where omitting them keeps them.
        always_negotiate_data_channels (:obj:`bool`, optional): Whether offers always have a media section for
            data channels, first among the new ones, even before a data channel is created. Can't be changed.
        rtp_header_encryption_policy (:obj:`webrtc.RTCRtpHeaderEncryptionPolicy`, optional): Whether RTP header
            extensions are encrypted with cryptex (RFC 9335) when the remote peer supports it (``negotiate``), or
            a remote description without it fails (``require``). Can't be changed.
    """

    ice_servers: List[RTCIceServer] = field(default_factory=list)
    ice_transport_policy: RTCIceTransportPolicy = RTCIceTransportPolicy.all
    bundle_policy: RTCBundlePolicy = RTCBundlePolicy.balanced
    rtcp_mux_policy: RTCRtcpMuxPolicy = RTCRtcpMuxPolicy.require
    ice_candidate_pool_size: int = 0
    port_range: Optional[Tuple[int, int]] = None
    certificates: Optional[List[RTCCertificate]] = None
    always_negotiate_data_channels: bool = False
    rtp_header_encryption_policy: RTCRtpHeaderEncryptionPolicy = RTCRtpHeaderEncryptionPolicy.negotiate

    def _validate(self) -> 'wrtc.ConfigurationInit':
        """The native configuration.

        Raises:
            :obj:`TypeError`: If a member has a wrong type.
            :obj:`ValueError`: If ``ice_candidate_pool_size`` or ``port_range`` is out of range.
            :obj:`webrtc.InvalidSyntaxError`: If an ICE server URL is invalid.
            :obj:`webrtc.InvalidAccessError`: If a TURN server has no credentials.
        """
        native = wrtc.ConfigurationInit()
        native.iceServers = [
            (RTCIceServer(**server) if isinstance(server, dict) else server)._validate() for server in self.ice_servers
        ]
        native.iceTransportPolicy = _enum(RTCIceTransportPolicy, self.ice_transport_policy)
        native.bundlePolicy = _enum(RTCBundlePolicy, self.bundle_policy)
        native.rtcpMuxPolicy = _enum(RTCRtcpMuxPolicy, self.rtcp_mux_policy)

        if not isinstance(self.ice_candidate_pool_size, int) or not 0 <= self.ice_candidate_pool_size <= 255:
            raise ValueError(f'ice_candidate_pool_size must be from 0 to 255, not {self.ice_candidate_pool_size}')
        native.iceCandidatePoolSize = self.ice_candidate_pool_size
        native.alwaysNegotiateDataChannels = bool(self.always_negotiate_data_channels)
        native.rtpHeaderEncryptionPolicy = _enum(RTCRtpHeaderEncryptionPolicy, self.rtp_header_encryption_policy)

        if self.certificates is not None:
            for certificate in self.certificates:
                if certificate.expired:
                    raise InvalidAccessError('the certificate has expired')
            native.certificates = [certificate._native_obj for certificate in self.certificates]

        if self.port_range is not None:
            low, high = self.port_range
            if not 0 <= low <= high <= 65535:
                raise ValueError(f'port_range must be two ports from low to high, not {self.port_range}')
            native.portRange = (low, high)
        return native

    @classmethod
    def _from_native(cls, native: 'wrtc.ConfigurationInit') -> 'RTCConfiguration':
        return cls(
            ice_servers=[
                RTCIceServer(
                    urls=list(server.urls),
                    username=server.username,
                    credential=server.credential,
                )
                for server in native.iceServers
            ],
            ice_transport_policy=native.iceTransportPolicy,
            bundle_policy=native.bundlePolicy,
            rtcp_mux_policy=native.rtcpMuxPolicy,
            ice_candidate_pool_size=native.iceCandidatePoolSize,
            port_range=tuple(native.portRange) if native.portRange else None,
            certificates=[RTCCertificate(c) for c in native.certificates] if native.certificates else [],
            always_negotiate_data_channels=native.alwaysNegotiateDataChannels,
            rtp_header_encryption_policy=native.rtpHeaderEncryptionPolicy,
        )


def _enum(cls, value):
    """A member of a native enum, also accepted by its name with dashes (like ``'max-bundle'``)"""
    if isinstance(value, cls):
        return value
    if isinstance(value, str):
        member = getattr(cls, value.replace('-', '_'), None)
        if isinstance(member, cls):
            return member
        raise ValueError(f'{value!r} is not a valid {cls.__name__}')
    raise TypeError(f'expected {cls.__name__}, not {type(value).__name__}')
