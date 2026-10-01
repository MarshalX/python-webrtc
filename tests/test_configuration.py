#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Configurations, certificates, descriptions, ICE candidates and errors: the models of a connection."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import time
from typing import TYPE_CHECKING

import pytest

import webrtc
from tests.helpers import exchange_offer, mistyped

if TYPE_CHECKING:
    from tests.helpers import CreatePC


def configuration() -> webrtc.RTCConfiguration:
    return webrtc.RTCConfiguration(
        ice_servers=[
            webrtc.RTCIceServer('stun:stun.example.org'),
            webrtc.RTCIceServer(['turn:turn.example.org:3478?transport=tcp'], username='user', credential='pass'),
        ],
        ice_transport_policy=webrtc.RTCIceTransportPolicy.relay,
        bundle_policy='max-bundle',
        ice_candidate_pool_size=2,
        port_range=(40000, 40100),
    )


def test_configuration_round_trip(create_pc: CreatePC) -> None:
    """A connection reports the configuration it was created with."""
    got = create_pc(configuration()).get_configuration()

    assert [server.urls for server in got.ice_servers] == [
        ['stun:stun.example.org'],
        ['turn:turn.example.org:3478?transport=tcp'],
    ]
    assert got.ice_servers[1].username == 'user'
    assert got.ice_servers[1].credential == 'pass'
    assert got.ice_transport_policy == webrtc.RTCIceTransportPolicy.relay
    assert got.bundle_policy == webrtc.RTCBundlePolicy.max_bundle
    assert got.ice_candidate_pool_size == 2
    assert got.port_range == (40000, 40100)


def test_set_configuration_defaults(create_pc: CreatePC) -> None:
    """Members set_configuration isn't given get their defaults, which may not change what can't be changed."""
    pc = create_pc(configuration())
    with pytest.raises(webrtc.InvalidModificationError):
        # the default bundle policy isn't the one of the connection
        pc.set_configuration()
    pc.set_configuration(webrtc.RTCConfiguration(bundle_policy=webrtc.RTCBundlePolicy.max_bundle))
    assert pc.get_configuration().ice_servers == []


def test_set_configuration_of_closed_connection(pc: webrtc.RTCPeerConnection) -> None:
    """A closed connection can't be configured."""
    pc.close()
    with pytest.raises(webrtc.InvalidStateError):
        pc.set_configuration()


@pytest.mark.parametrize(
    'url',
    [
        '',
        'relative',
        'http://example.org',
        'stun:',
        'stun:example.org/path',
        'stun:user@example.org',
        'stun:example.org?transport=udp',
        'turn:example.org?transport=sctp',
        'stun:example.org:70000',
        'stun:2001:db8::1',
    ],
)
def test_invalid_ice_server_urls(url: str) -> None:
    """Malformed ICE server URLs are an InvalidSyntaxError."""
    with pytest.raises(webrtc.InvalidSyntaxError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer(url, 'u', 'p')]))


def test_ice_server_needs_credentials() -> None:
    """A TURN server needs a username and a credential."""
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer('turn:example.org')]))


def test_ice_server_needs_urls() -> None:
    """An ICE server needs at least one URL."""
    with pytest.raises(webrtc.InvalidSyntaxError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer([])]))


def test_ice_candidate_pool_size_range() -> None:
    """The candidate pool has at most 255 candidates."""
    with pytest.raises(ValueError, match='from 0 to 255'):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_candidate_pool_size=256))


def test_ice_server_of_ipv6_address(create_pc: CreatePC) -> None:
    """An IPv6 address of an ICE server is in brackets."""
    create_pc(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer('stun:[2001:db8::1]:3478')]))


def test_oauth_ice_server() -> None:
    """An OAuth credential is an RTCOAuthCredential, which libwebrtc doesn't support."""
    server = webrtc.RTCIceServer('turns:turn.example.org', 'user', 'cred', credential_type='oauth')
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[server]))
    server.credential = webrtc.RTCOAuthCredential(
        mac_key=base64.b64encode(b'key').decode(), access_token=base64.b64encode(b'token').decode()
    )
    with pytest.raises(webrtc.NotSupportedError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[server]))


def test_configuration_from_json() -> None:
    """Nested dictionaries are converted, with camelCase names."""
    configuration = webrtc.RTCConfiguration.from_json({
        'iceServers': [
            {'urls': 'stun:stun.example.org'},
            {'urls': 'turns:turn.example.org', 'credential': {'macKey': 'a2V5', 'accessToken': 'dG9rZW4='}},
        ],
        'iceTransportPolicy': 'relay',
    })
    stun, turn = configuration.ice_servers
    assert stun == webrtc.RTCIceServer('stun:stun.example.org')
    assert turn.credential == webrtc.RTCOAuthCredential('a2V5', 'dG9rZW4=')
    assert configuration.ice_transport_policy == 'relay'


@pytest.mark.asyncio
async def test_always_negotiate_data_channels_and_header_encryption(create_pc: CreatePC) -> None:
    """As configured, an offer always has a data section and encrypts header extensions; neither can change."""
    pc = create_pc(
        webrtc.RTCConfiguration(
            always_negotiate_data_channels=True,
            rtp_header_encryption_policy=webrtc.RTCRtpHeaderEncryptionPolicy.require,
        )
    )
    configuration = pc.get_configuration()
    assert configuration.always_negotiate_data_channels
    assert configuration.rtp_header_encryption_policy == webrtc.RTCRtpHeaderEncryptionPolicy.require

    offer = await pc.create_offer()
    assert offer.sdp.count('m=application') == 1
    assert 'a=cryptex' in offer.sdp

    pc.set_configuration(configuration)
    for changed in (
        dataclasses.replace(configuration, always_negotiate_data_channels=False),
        dataclasses.replace(configuration, rtp_header_encryption_policy='negotiate'),
    ):
        with pytest.raises(webrtc.InvalidModificationError):
            pc.set_configuration(changed)


@pytest.mark.asyncio
async def test_generate_ecdsa_certificate() -> None:
    """An ECDSA certificate expires in the future and has a SHA-256 fingerprint."""
    certificate = await webrtc.RTCPeerConnection.generate_certificate('ECDSA')
    assert certificate.expires > time.time() * 1000
    assert not certificate.expired
    (fingerprint,) = certificate.get_fingerprints()
    assert fingerprint.algorithm == 'sha-256'
    assert fingerprint.value is not None
    assert len(fingerprint.value.split(':')) == 32


@pytest.mark.asyncio
async def test_generate_rsa_certificate() -> None:
    """An RSA certificate is generated from WebCrypto parameters."""
    rsa = await webrtc.RTCCertificate.generate(
        webrtc.RsaHashedKeyGenParams(
            'RSASSA-PKCS1-v1_5', modulus_length=1024, public_exponent=b'\x01\x00\x01', hash='SHA-256'
        )
    )
    assert not rsa.expired


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'algorithm',
    [
        'nonsense',
        webrtc.Algorithm('RSASSA-PKCS1-v1_5'),
        webrtc.EcKeyGenParams('ECDSA', named_curve='P-384'),
        webrtc.RsaHashedKeyGenParams.from_json({
            'name': 'RSASSA-PKCS1-v1_5',
            'modulusLength': 2048,
            'publicExponent': bytes([3]),
            'hash': {'name': 'SHA-1'},
        }),
    ],
)
async def test_generate_unsupported_certificate(algorithm: str | webrtc.Algorithm) -> None:
    """Algorithms other than ECDSA and RSASSA-PKCS1-v1_5 with SHA-256 and the exponent 65537 aren't supported."""
    with pytest.raises(webrtc.NotSupportedError):
        await webrtc.RTCCertificate.generate(algorithm)


@pytest.mark.asyncio
async def test_configured_certificate(create_pc: CreatePC) -> None:
    """The certificate of a configuration is the one of the connection, whose offer has its fingerprint."""
    certificate = await webrtc.RTCCertificate.generate('ECDSA')
    (fingerprint,) = certificate.get_fingerprints()
    pc = create_pc(webrtc.RTCConfiguration(certificates=[certificate]))
    pc.add_transceiver(webrtc.MediaType.audio)
    offer = await pc.create_offer()
    assert fingerprint.value is not None
    assert fingerprint.value.upper() in offer.sdp
    certificates = pc.get_configuration().certificates
    assert certificates is not None
    assert certificates[0].get_fingerprints() == [fingerprint]


@pytest.mark.asyncio
async def test_certificates_can_not_change(create_pc: CreatePC) -> None:
    """A configuration without certificates keeps the ones of the connection, other ones aren't allowed."""
    ecdsa, other = [await webrtc.RTCCertificate.generate('ECDSA') for _ in range(2)]
    pc = create_pc(webrtc.RTCConfiguration(certificates=[ecdsa]))
    pc.set_configuration(webrtc.RTCConfiguration())
    with pytest.raises(webrtc.InvalidModificationError):
        pc.set_configuration(webrtc.RTCConfiguration(certificates=[other]))


@pytest.mark.asyncio
async def test_expired_certificate() -> None:
    """A connection can't be created with an expired certificate."""
    expired = await webrtc.RTCCertificate.generate('ECDSA', expires=0)
    # it expires at the millisecond it's generated, which has passed 10 ms later
    await asyncio.sleep(0.01)
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(certificates=[expired]))


def test_ice_candidate_parsing() -> None:
    """The attributes of a candidate are parsed from its candidate string."""
    candidate = webrtc.RTCIceCandidate(
        'candidate:1 2 TCP 1845501695 192.168.0.1 4444 typ srflx raddr 10.0.0.1 rport 5555 tcptype active',
        sdp_mid='0',
    )
    assert candidate.foundation == '1'
    assert candidate.component == webrtc.RTCIceComponent.rtcp
    assert candidate.protocol == webrtc.RTCIceProtocol.tcp
    assert candidate.type == webrtc.RTCIceCandidateType.srflx
    assert candidate.tcp_type == webrtc.RTCIceTcpCandidateType.active
    assert (candidate.related_address, candidate.related_port) == ('10.0.0.1', 5555)
    assert candidate.to_json() == {
        'candidate': candidate.candidate,
        'sdpMid': '0',
        'sdpMLineIndex': None,
        'usernameFragment': None,
    }
    assert (
        webrtc.RTCIceCandidate(**vars(webrtc.RTCIceCandidateInit.from_json(candidate.to_json()))).candidate
        == candidate.candidate
    )


def test_invalid_ice_candidate() -> None:
    """An invalid candidate string isn't validated, nor parsed, but a candidate needs an m-line."""
    invalid = webrtc.RTCIceCandidate('a=candidate:1 1 udp 1 1.2.3.4 5 typ host', sdp_m_line_index=0)
    assert invalid.foundation is None
    assert invalid.port is None
    with pytest.raises(TypeError):
        webrtc.RTCIceCandidate('candidate:1 1 udp 1 1.2.3.4 5 typ host')


def test_ice_candidate_ufrag_characters() -> None:
    """A ufrag may have "/" and "+"."""
    host = webrtc.RTCIceCandidate('candidate:1 1 udp 2121940223 ::1 60645 typ host ufrag /h4t+', sdp_mid='0')
    assert host.type == webrtc.RTCIceCandidateType.host


def test_peer_reflexive_candidate_hides_its_address() -> None:
    """A remote peer-reflexive candidate, which the remote peer didn't signal, exposes no address."""
    # made from what libwebrtc reports of a selected pair (see RTCIceTransport), as connectivity checks with
    # a peer-reflexive candidate can't be produced on demand
    candidate = webrtc.RTCIceCandidate._peer_reflexive({
        'candidate': 'candidate:1 1 udp 1853504767 redacted-ip.invalid 62341 typ prflx generation 0 ufrag a/b+',
        'sdp_mid': '0',
        'sdp_m_line_index': 0,
        'username_fragment': None,
        'url': None,
        'relay_protocol': None,
    })
    assert candidate.candidate == ''
    assert candidate.type == webrtc.RTCIceCandidateType.prflx
    assert candidate.address is None
    assert candidate.port == 62341


def test_rtc_error() -> None:
    """An RTCError is an OperationError with the details of the error."""
    error = webrtc.RTCError(webrtc.RTCErrorInit('sctp-failure', sctp_cause_code=12), 'failed')
    assert isinstance(error, webrtc.OperationError)
    assert isinstance(error, webrtc.RTCException)
    assert error.error_detail == webrtc.RTCErrorDetailType.sctp_failure
    assert error.sctp_cause_code == 12
    assert error.sdp_line_number is None
    with pytest.raises(ValueError, match='not a valid RTCErrorDetailType'):
        webrtc.RTCErrorInit(mistyped('nonsense'))


def test_rtc_error_init_from_json() -> None:
    """The init can come from its JSON form, with camelCase names and unknown ones ignored."""
    init = webrtc.RTCErrorInit.from_json({'errorDetail': 'sdp-syntax-error', 'sdpLineNumber': 3, 'unknown': 1})
    error = webrtc.RTCError(init, 'bad')
    assert error.error_detail == webrtc.RTCErrorDetailType.sdp_syntax_error
    assert error.sdp_line_number == 3
    assert str(error) == 'bad'
    with pytest.raises(TypeError, match='error_detail'):
        webrtc.RTCErrorInit.from_json({})


@pytest.mark.asyncio
async def test_description_errors(pc: webrtc.RTCPeerConnection) -> None:
    """An answer without an offer is in the wrong state, and invalid SDP is an RTCError of its syntax."""
    with pytest.raises(webrtc.InvalidStateError):
        await pc.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', 'invalid'))
    with pytest.raises(webrtc.RTCError) as info:
        await pc.set_remote_description(webrtc.RTCSessionDescription('offer', 'v=0\r\nnonsense'))
    assert info.value.error_detail == webrtc.RTCErrorDetailType.sdp_syntax_error


@pytest.mark.asyncio
async def test_created_descriptions(pc: webrtc.RTCPeerConnection) -> None:
    """Only the descriptions the connection created can be set as local ones, unmodified."""
    pc.add_transceiver(webrtc.MediaType.audio)
    offer = await pc.create_offer()
    assert isinstance(offer, webrtc.RTCSessionDescriptionInit)
    assert offer.to_json() == {'type': 'offer', 'sdp': offer.sdp}
    with pytest.raises(webrtc.InvalidModificationError):
        await pc.set_local_description(
            webrtc.RTCSessionDescriptionInit('offer', offer.sdp.replace('a=mid:0', 'a=mid:1'))
        )
    await pc.set_local_description(offer)
    # not compared by identity: gathered candidates change the description (and its object) between reads
    assert pc.pending_local_description is not None
    assert pc.local_description is not None
    assert pc.pending_local_description.type == pc.local_description.type == offer.type
    assert pc.current_local_description is None


@pytest.mark.asyncio
async def test_provisional_answers_without_sdp(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A provisional answer, and the final answer after it, are set without SDP."""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer(caller, callee)

    await callee.set_local_description(webrtc.RTCSessionDescriptionInit('pranswer'))
    assert callee.signaling_state == webrtc.RTCSignalingState.have_local_pranswer
    assert callee.pending_local_description is not None
    assert callee.pending_local_description.type == webrtc.RTCSdpType.pranswer
    # without a type, the final answer
    await callee.set_local_description()
    assert callee.signaling_state == webrtc.RTCSignalingState.stable
    assert callee.current_local_description is not None
    assert callee.current_local_description.type == webrtc.RTCSdpType.answer


def test_closed_connection_keeps_its_transceivers(pc: webrtc.RTCPeerConnection) -> None:
    """The transceivers of a closed connection are stopped, but still there."""
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.close()
    [transceiver] = pc.get_transceivers()
    assert pc.get_senders() == pc.get_receivers() == []
    with pytest.raises(webrtc.InvalidStateError):
        transceiver.stop()
