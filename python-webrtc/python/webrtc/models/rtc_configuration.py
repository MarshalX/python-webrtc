#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The configuration of a connection and the STUN and TURN servers it gathers candidates with."""

from __future__ import annotations

import ipaddress
import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import webrtc
import wrtc
from webrtc.enums import RTCBundlePolicy, RTCIceTransportPolicy, RTCRtcpMuxPolicy, RTCRtpHeaderEncryptionPolicy
from webrtc.exceptions import InvalidAccessError, InvalidSyntaxError
from webrtc.models.dictionary import Dictionary
from webrtc.models.rtc_certificate import RTCCertificate
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from collections.abc import Iterable

    from webrtc.enums import (
        RTCBundlePolicyValue,
        RTCIceTransportPolicyValue,
        RTCRtcpMuxPolicyValue,
        RTCRtpHeaderEncryptionPolicyValue,
    )

# the longest TURN username, as browsers limit it
_MAX_USERNAME_LENGTH = 509
_MAX_PORT = 65535
_MAX_CANDIDATE_POOL_SIZE = 255

# RFC 7064 and RFC 7065: scheme ":" host [ ":" port ] [ "?transport=" transport ], with udp and tcp transports only
_URL = re.compile(
    r'(?P<scheme>[^:]*):(?P<host>\[[^\]]*\]|[^:?]*)(?::(?P<port>[0-9]*))?(?:\?transport=(?P<transport>[^&]*))?'
)
# RFC 3986 reg-name, without percent-encoding
_REG_NAME = re.compile(r"[A-Za-z0-9\-._~!$&'()*+,;=]+")


def _check_url(url: str) -> str:
    """Returns the scheme of a STUN or TURN server URL.

    Raises:
        webrtc.InvalidSyntaxError: If the URL doesn't match RFC 7064 or RFC 7065.
    """
    match = _URL.fullmatch(url)
    if match is None or match['scheme'] not in {'stun', 'stuns', 'turn', 'turns'}:
        msg = f'{url!r} is not a valid STUN or TURN URL'
        raise webrtc.InvalidSyntaxError(msg)

    host: str = match['host']
    port: str | None = match['port']
    transport: str | None = match['transport']
    if host.startswith('['):
        try:
            _ = ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            msg = f'{url!r} has an invalid IPv6 address'
            raise webrtc.InvalidSyntaxError(msg) from None
    elif _REG_NAME.fullmatch(host) is None:
        msg = f'{url!r} has an invalid host'
        raise webrtc.InvalidSyntaxError(msg)

    if port is not None and (port == '' or int(port) > _MAX_PORT):
        msg = f'{url!r} has an invalid port'
        raise webrtc.InvalidSyntaxError(msg)
    if transport is not None and (match['scheme'].startswith('stun') or transport not in {'udp', 'tcp'}):
        msg = f'{url!r} has an invalid transport'
        raise webrtc.InvalidSyntaxError(msg)
    return match['scheme']


@dataclass
class RTCIceServer(Dictionary):
    """A STUN or TURN server to gather ICE candidates with.

    It isn't checked on creation, only when the configuration is applied. The URLs must be valid ``stun``,
    ``stuns``, ``turn`` or ``turns`` URLs (RFC 7064, RFC 7065), and a TURN server needs a username of at most
    509 characters and a non-empty password. See :mdn:`RTCPeerConnection/RTCPeerConnection`.

    Args:
        urls (:obj:`str` or :obj:`list` of :obj:`str`): One URL or several, like ``'stun:stun.example.org'``
            or ``'turn:turn.example.org:3478?transport=tcp'``. At least one is required.
        username (:obj:`str`, optional): The username of a TURN server.
        credential (:obj:`str`, optional): The password of a TURN server.
    """

    urls: str | list[str]
    username: str | None = None
    credential: str | None = None

    @classmethod
    def _to_native_list(cls, servers: Iterable[RTCIceServer]) -> list[wrtc.IceServerInit]:
        """The native servers of a list of servers."""
        return [server._to_native() for server in servers]

    def _to_native(self) -> wrtc.IceServerInit:
        urls = [self.urls] if isinstance(self.urls, str) else list(self.urls)
        if len(urls) == 0:
            msg = 'urls of an ICE server must not be empty'
            raise InvalidSyntaxError(msg)

        # every URL is parsed before the credentials are checked
        schemes = [_check_url(url) for url in urls]
        if any(scheme in {'turn', 'turns'} for scheme in schemes):
            if self.username is None or self.credential is None or self.credential == '':
                msg = 'a TURN server needs a username and a credential'
                raise InvalidAccessError(msg)
            if len(self.username) > _MAX_USERNAME_LENGTH:
                msg = f'the username of a TURN server is longer than {_MAX_USERNAME_LENGTH}'
                raise InvalidAccessError(msg)

        native = wrtc.IceServerInit()
        native.urls = urls
        native.username = self.username
        native.credential = self.credential
        return native


@dataclass
class RTCIceGatherOptions(Dictionary):
    """How a standalone :obj:`webrtc.RTCIceTransport` gathers candidates, for :meth:`webrtc.RTCIceTransport.gather`.

    Args:
        gather_policy (:obj:`webrtc.RTCIceTransportPolicy`, optional): Whether to gather every type of candidate
            (``all``, the default) or only relay ones.
        ice_servers (:obj:`list` of :obj:`webrtc.RTCIceServer`, optional): The STUN and TURN servers to gather with.
    """

    gather_policy: RTCIceTransportPolicy | RTCIceTransportPolicyValue = RTCIceTransportPolicy.all
    ice_servers: list[RTCIceServer] | None = None

    _dictionaries: ClassVar = {'ice_servers': RTCIceServer}

    #: Alias for :attr:`gather_policy`
    gatherPolicy: ClassVar[Alias[RTCIceTransportPolicy | RTCIceTransportPolicyValue]] = alias('gather_policy')
    #: Alias for :attr:`ice_servers`
    iceServers: ClassVar[Alias[list[RTCIceServer] | None]] = alias('ice_servers')


@dataclass
class RTCConfiguration(Dictionary):
    """The configuration of a :obj:`webrtc.RTCPeerConnection`.

    A connection takes it on creation and in :meth:`webrtc.RTCPeerConnection.set_configuration`, and checks the
    members there. This class doesn't check them. Enum members accept their values too.
    See :mdn:`RTCPeerConnection/RTCPeerConnection`.

    Args:
        ice_servers (:obj:`list` of :obj:`webrtc.RTCIceServer`, optional): The STUN and TURN servers to gather
            ICE candidates with. There are none by default.
        ice_transport_policy (:obj:`webrtc.RTCIceTransportPolicy`, optional): Whether every type of candidate may
            be used (``all``, the default) or only relay ones.
        bundle_policy (:obj:`webrtc.RTCBundlePolicy`, optional): How media is grouped into transports when the
            remote peer doesn't support bundling. It's ``balanced`` by default and can't be changed.
        rtcp_mux_policy (:obj:`webrtc.RTCRtcpMuxPolicy`, optional): Whether RTCP multiplexing is required (the
            default). It can't be changed.
        ice_candidate_pool_size (:obj:`int`, optional): How many candidates (0 to 255) to gather ahead of
            setting the local description. It's 0 by default and can't be changed once the local description
            is set.
        port_range (:obj:`tuple` of two :obj:`int`, optional): The lowest and the highest local UDP and TCP port
            to use, for firewalls that only allow a range. This option is specific to this library.
        certificates (:obj:`list` of :obj:`webrtc.RTCCertificate`, optional): The certificates to authenticate
            with. They're generated if omitted. They can't be changed, and leaving them out of
            :meth:`webrtc.RTCPeerConnection.set_configuration` keeps the current ones.
        always_negotiate_data_channels (:obj:`bool`, optional): Whether every offer has a media section for data
            channels even before a channel is created. The section comes first among the new sections. It can't
            be changed.
        rtp_header_encryption_policy (:obj:`webrtc.RTCRtpHeaderEncryptionPolicy`, optional): ``negotiate`` (the
            default) encrypts RTP header extensions with cryptex (RFC 9335) when the remote peer supports it,
            ``require`` fails a remote description without it, and ``disable`` never encrypts. It can't be changed.
    """

    ice_servers: list[RTCIceServer] = field(default_factory=list)
    ice_transport_policy: RTCIceTransportPolicy | RTCIceTransportPolicyValue = RTCIceTransportPolicy.all
    bundle_policy: RTCBundlePolicy | RTCBundlePolicyValue = RTCBundlePolicy.balanced
    rtcp_mux_policy: RTCRtcpMuxPolicy | RTCRtcpMuxPolicyValue = RTCRtcpMuxPolicy.require
    ice_candidate_pool_size: int = 0
    port_range: tuple[int, int] | None = None
    certificates: list[RTCCertificate] | None = None
    always_negotiate_data_channels: bool = False
    rtp_header_encryption_policy: RTCRtpHeaderEncryptionPolicy | RTCRtpHeaderEncryptionPolicyValue = (
        RTCRtpHeaderEncryptionPolicy.negotiate
    )

    _dictionaries: ClassVar = {'ice_servers': RTCIceServer}

    def _to_native(self) -> wrtc.ConfigurationInit:
        """Validates the configuration and creates the native one.

        Returns:
            :obj:`wrtc.ConfigurationInit`: The native configuration.

        Raises:
            ValueError: If ``ice_candidate_pool_size`` or ``port_range`` is out of range.
            webrtc.InvalidAccessError: If a certificate has expired.
        """
        native = wrtc.ConfigurationInit()
        native.iceServers = RTCIceServer._to_native_list(self.ice_servers)
        native.iceTransportPolicy = self.ice_transport_policy
        native.bundlePolicy = self.bundle_policy
        native.rtcpMuxPolicy = self.rtcp_mux_policy
        if self.rtcp_mux_policy == RTCRtcpMuxPolicy.negotiate:
            warnings.warn("rtcp_mux_policy 'negotiate' is deprecated", DeprecationWarning, stacklevel=3)

        pool_size = self.ice_candidate_pool_size
        if not isinstance(pool_size, int) or not 0 <= pool_size <= _MAX_CANDIDATE_POOL_SIZE:
            msg = f'ice_candidate_pool_size must be from 0 to {_MAX_CANDIDATE_POOL_SIZE}, not {pool_size}'
            raise ValueError(msg)
        native.iceCandidatePoolSize = pool_size
        native.alwaysNegotiateDataChannels = bool(self.always_negotiate_data_channels)
        native.rtpHeaderEncryptionPolicy = self.rtp_header_encryption_policy

        if self.certificates is not None:
            for certificate in self.certificates:
                if certificate._expired():
                    msg = 'the certificate has expired'
                    raise webrtc.InvalidAccessError(msg)
            native.certificates = [certificate._native_obj for certificate in self.certificates]

        if self.port_range is not None:
            low, high = self.port_range
            if not 0 <= low <= high <= _MAX_PORT:
                msg = f'port_range must be two ports from low to high, not {self.port_range}'
                raise ValueError(msg)
            native.portRange = (low, high)
        return native

    @classmethod
    def _from_native(cls, native: wrtc.ConfigurationInit) -> RTCConfiguration:
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
            port_range=tuple(native.portRange) if native.portRange is not None else None,
            certificates=RTCCertificate._wrap_many(native.certificates) if native.certificates is not None else [],
            always_negotiate_data_channels=native.alwaysNegotiateDataChannels,
            rtp_header_encryption_policy=native.rtpHeaderEncryptionPolicy,
        )

    #: Alias for :attr:`ice_servers`
    iceServers: ClassVar[Alias[list[RTCIceServer]]] = alias('ice_servers')
    #: Alias for :attr:`ice_transport_policy`
    iceTransportPolicy: ClassVar[Alias[RTCIceTransportPolicy | RTCIceTransportPolicyValue]] = alias(
        'ice_transport_policy'
    )
    #: Alias for :attr:`bundle_policy`
    bundlePolicy: ClassVar[Alias[RTCBundlePolicy | RTCBundlePolicyValue]] = alias('bundle_policy')
    #: Alias for :attr:`rtcp_mux_policy`
    rtcpMuxPolicy: ClassVar[Alias[RTCRtcpMuxPolicy | RTCRtcpMuxPolicyValue]] = alias('rtcp_mux_policy')
    #: Alias for :attr:`ice_candidate_pool_size`
    iceCandidatePoolSize: ClassVar[Alias[int]] = alias('ice_candidate_pool_size')
    #: Alias for :attr:`port_range`
    portRange: ClassVar[Alias[tuple[int, int] | None]] = alias('port_range')
    #: Alias for :attr:`always_negotiate_data_channels`
    alwaysNegotiateDataChannels: ClassVar[Alias[bool]] = alias('always_negotiate_data_channels')
    #: Alias for :attr:`rtp_header_encryption_policy`
    rtpHeaderEncryptionPolicy: ClassVar[Alias[RTCRtpHeaderEncryptionPolicy | RTCRtpHeaderEncryptionPolicyValue]] = (
        alias('rtp_header_encryption_policy')
    )
