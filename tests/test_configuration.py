#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Configurations, certificates, descriptions, ICE candidates and errors: the models of a connection."""

import asyncio
import dataclasses
import time

import pytest

import webrtc
from tests.helpers import exchange_offer


def configuration():
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


def test_configuration_round_trip(create_pc):
    """A connection reports the configuration it was created with"""
    got = create_pc(configuration()).get_configuration()

    assert [server.urls for server in got.ice_servers] == [
        ['stun:stun.example.org'],
        ['turn:turn.example.org:3478?transport=tcp'],
    ]
    assert got.ice_servers[1].username == 'user' and got.ice_servers[1].credential == 'pass'
    assert got.ice_transport_policy == webrtc.RTCIceTransportPolicy.relay
    assert got.bundle_policy == webrtc.RTCBundlePolicy.max_bundle
    assert got.ice_candidate_pool_size == 2
    assert got.port_range == (40000, 40100)


def test_set_configuration_defaults(create_pc):
    """Members set_configuration isn't given get their defaults, which may not change what can't be changed"""
    pc = create_pc(configuration())
    with pytest.raises(webrtc.InvalidModificationError):
        # the default bundle policy isn't the one of the connection
        pc.set_configuration()
    pc.set_configuration(webrtc.RTCConfiguration(bundle_policy=webrtc.RTCBundlePolicy.max_bundle))
    assert pc.get_configuration().ice_servers == []


def test_set_configuration_of_closed_connection(pc):
    """A closed connection can't be configured"""
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
def test_invalid_ice_server_urls(url):
    """Malformed ICE server URLs are an InvalidSyntaxError"""
    with pytest.raises(webrtc.InvalidSyntaxError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer(url, 'u', 'p')]))


def test_ice_server_needs_credentials():
    """A TURN server needs a username and a credential"""
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer('turn:example.org')]))


def test_ice_server_needs_urls():
    """An ICE server needs at least one URL"""
    with pytest.raises(webrtc.InvalidSyntaxError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer([])]))


def test_ice_candidate_pool_size_range():
    """The candidate pool has at most 255 candidates"""
    with pytest.raises(ValueError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_candidate_pool_size=256))


def test_ice_server_of_ipv6_address(create_pc):
    """An IPv6 address of an ICE server is in brackets"""
    create_pc(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer('stun:[2001:db8::1]:3478')]))


def test_oauth_ice_server():
    """An OAuth credential is an RTCOAuthCredential, which libwebrtc doesn't support"""
    server = {'urls': 'turns:turn.example.org', 'username': 'user', 'credential': 'cred', 'credential_type': 'oauth'}
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[server]))
    server['credential'] = webrtc.RTCOAuthCredential(mac_key='a2V5', access_token='dG9rZW4=')
    with pytest.raises(webrtc.NotSupportedError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[server]))


@pytest.mark.asyncio
async def test_always_negotiate_data_channels_and_header_encryption(create_pc):
    """As configured, an offer always has a data section and encrypts header extensions; neither can change"""
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
    for changed in ({'always_negotiate_data_channels': False}, {'rtp_header_encryption_policy': 'negotiate'}):
        with pytest.raises(webrtc.InvalidModificationError):
            pc.set_configuration(dataclasses.replace(configuration, **changed))


@pytest.mark.asyncio
async def test_generate_ecdsa_certificate():
    """An ECDSA certificate expires in the future and has a SHA-256 fingerprint"""
    certificate = await webrtc.RTCPeerConnection.generate_certificate('ECDSA')
    assert certificate.expires > time.time() * 1000 and not certificate.expired
    (fingerprint,) = certificate.get_fingerprints()
    assert fingerprint.algorithm == 'sha-256' and len(fingerprint.value.split(':')) == 32


@pytest.mark.asyncio
async def test_generate_rsa_certificate():
    """An RSA certificate is generated from WebCrypto parameters"""
    rsa = await webrtc.RTCCertificate.generate(
        {'name': 'RSASSA-PKCS1-v1_5', 'modulus_length': 1024, 'public_exponent': 65537, 'hash': 'SHA-256'}
    )
    assert not rsa.expired


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'algorithm',
    ['nonsense', {'name': 'RSASSA-PKCS1-v1_5', 'modulusLength': 2048, 'publicExponent': 3, 'hash': 'SHA-1'}],
)
async def test_generate_unsupported_certificate(algorithm):
    """Algorithms other than ECDSA and RSASSA-PKCS1-v1_5 with SHA-256 and the exponent 65537 aren't supported"""
    with pytest.raises(webrtc.NotSupportedError):
        await webrtc.RTCCertificate.generate(algorithm)


@pytest.mark.asyncio
async def test_configured_certificate(create_pc):
    """The certificate of a configuration is the one of the connection, whose offer has its fingerprint"""
    certificate = await webrtc.RTCCertificate.generate('ECDSA')
    (fingerprint,) = certificate.get_fingerprints()
    pc = create_pc(webrtc.RTCConfiguration(certificates=[certificate]))
    pc.add_transceiver(webrtc.MediaType.audio)
    offer = await pc.create_offer()
    assert fingerprint.value.upper() in offer.sdp
    assert pc.get_configuration().certificates[0].get_fingerprints() == [fingerprint]


@pytest.mark.asyncio
async def test_certificates_can_not_change(create_pc):
    """A configuration without certificates keeps the ones of the connection, other ones aren't allowed"""
    ecdsa, other = [await webrtc.RTCCertificate.generate('ECDSA') for _ in range(2)]
    pc = create_pc(webrtc.RTCConfiguration(certificates=[ecdsa]))
    pc.set_configuration(webrtc.RTCConfiguration())
    with pytest.raises(webrtc.InvalidModificationError):
        pc.set_configuration(webrtc.RTCConfiguration(certificates=[other]))


@pytest.mark.asyncio
async def test_expired_certificate():
    """A connection can't be created with an expired certificate"""
    expired = await webrtc.RTCCertificate.generate('ECDSA', expires=0)
    # it expires at the millisecond it's generated, which has passed 10 ms later
    await asyncio.sleep(0.01)
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(certificates=[expired]))


def test_ice_candidate_parsing():
    """The attributes of a candidate are parsed from its candidate string"""
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
    assert webrtc.RTCIceCandidate.from_json(candidate.to_json()).candidate == candidate.candidate


def test_invalid_ice_candidate():
    """An invalid candidate string isn't validated, nor parsed, but a candidate needs an m-line"""
    invalid = webrtc.RTCIceCandidate('a=candidate:1 1 udp 1 1.2.3.4 5 typ host', sdp_m_line_index=0)
    assert invalid.foundation is None and invalid.port is None
    with pytest.raises(TypeError):
        webrtc.RTCIceCandidate('candidate:1 1 udp 1 1.2.3.4 5 typ host')


def test_ice_candidate_ufrag_characters():
    """A ufrag may have "/" and "+" """
    host = webrtc.RTCIceCandidate('candidate:1 1 udp 2121940223 ::1 60645 typ host ufrag /h4t+', sdp_mid='0')
    assert host.type == webrtc.RTCIceCandidateType.host


def test_peer_reflexive_candidate_hides_its_address():
    """A remote peer-reflexive candidate, which the remote peer didn't signal, exposes no address"""
    # made from what libwebrtc reports of a selected pair (see RTCIceTransport), as connectivity checks with
    # a peer-reflexive candidate can't be produced on demand
    candidate = webrtc.RTCIceCandidate._peer_reflexive(
        {
            'candidate': 'candidate:1 1 udp 1853504767 redacted-ip.invalid 62341 typ prflx generation 0 ufrag a/b+',
            'sdp_mid': '0',
        }
    )
    assert candidate.candidate == ''
    assert candidate.type == webrtc.RTCIceCandidateType.prflx
    assert candidate.address is None
    assert candidate.port == 62341


def test_rtc_error():
    """An RTCError is an OperationError with the details of the error"""
    error = webrtc.RTCError('sctp-failure', 'failed', sctp_cause_code=12)
    assert isinstance(error, webrtc.OperationError) and isinstance(error, webrtc.RTCException)
    assert error.error_detail == webrtc.RTCErrorDetailType.sctp_failure
    assert error.sctp_cause_code == 12 and error.sdp_line_number is None
    with pytest.raises(ValueError):
        webrtc.RTCError('nonsense')


@pytest.mark.asyncio
async def test_description_errors(pc):
    """An answer without an offer is in the wrong state, and invalid SDP is an RTCError of its syntax"""
    with pytest.raises(webrtc.InvalidStateError):
        await pc.set_remote_description({'type': 'answer', 'sdp': 'invalid'})
    with pytest.raises(webrtc.RTCError) as info:
        await pc.set_remote_description(webrtc.RTCSessionDescription('offer', 'v=0\r\nnonsense'))
    assert info.value.error_detail == webrtc.RTCErrorDetailType.sdp_syntax_error


@pytest.mark.asyncio
async def test_created_descriptions(pc):
    """Only the descriptions the connection created can be set as local ones, unmodified"""
    pc.add_transceiver(webrtc.MediaType.audio)
    offer = await pc.create_offer()
    assert isinstance(offer, webrtc.RTCSessionDescriptionInit)
    assert offer.to_json() == {'type': 'offer', 'sdp': offer.sdp}
    with pytest.raises(webrtc.InvalidModificationError):
        await pc.set_local_description({'type': 'offer', 'sdp': offer.sdp.replace('a=mid:0', 'a=mid:1')})
    await pc.set_local_description(offer)
    # not compared by identity: gathered candidates change the description (and its object) between reads
    assert pc.pending_local_description.type == pc.local_description.type == offer.type
    assert pc.current_local_description is None


@pytest.mark.asyncio
async def test_provisional_answers_without_sdp(caller, callee):
    """A provisional answer, and the final answer after it, are set without SDP"""
    caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer(caller, callee)

    await callee.set_local_description({'type': 'pranswer'})
    assert callee.signaling_state == webrtc.RTCSignalingState.have_local_pranswer
    assert callee.pending_local_description.type == webrtc.RTCSdpType.pranswer
    # without a type, the final answer
    await callee.set_local_description()
    assert callee.signaling_state == webrtc.RTCSignalingState.stable
    assert callee.current_local_description.type == webrtc.RTCSdpType.answer


def test_closed_connection_keeps_its_transceivers(pc):
    """The transceivers of a closed connection are stopped, but still there"""
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.close()
    [transceiver] = pc.get_transceivers()
    assert pc.get_senders() == pc.get_receivers() == []
    with pytest.raises(webrtc.InvalidStateError):
        transceiver.stop()
