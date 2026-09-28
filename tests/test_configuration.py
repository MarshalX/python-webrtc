#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio
import dataclasses
import time

import pytest

import webrtc


def test_configuration_round_trip():
    configuration = webrtc.RTCConfiguration(
        ice_servers=[
            webrtc.RTCIceServer('stun:stun.example.org'),
            webrtc.RTCIceServer(['turn:turn.example.org:3478?transport=tcp'], username='user', credential='pass'),
        ],
        ice_transport_policy=webrtc.RTCIceTransportPolicy.relay,
        bundle_policy='max-bundle',
        ice_candidate_pool_size=2,
        port_range=(40000, 40100),
    )
    pc = webrtc.RTCPeerConnection(configuration)
    got = pc.get_configuration()

    assert [server.urls for server in got.ice_servers] == [
        ['stun:stun.example.org'],
        ['turn:turn.example.org:3478?transport=tcp'],
    ]
    assert got.ice_servers[1].username == 'user' and got.ice_servers[1].credential == 'pass'
    assert got.ice_transport_policy == webrtc.RTCIceTransportPolicy.relay
    assert got.bundle_policy == webrtc.RTCBundlePolicy.max_bundle
    assert got.ice_candidate_pool_size == 2
    assert got.port_range == (40000, 40100)

    # members that aren't set get their defaults
    with pytest.raises(webrtc.InvalidModificationError):
        pc.set_configuration()
    pc.set_configuration(webrtc.RTCConfiguration(bundle_policy=webrtc.RTCBundlePolicy.max_bundle))
    assert pc.get_configuration().ice_servers == []
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
    with pytest.raises(webrtc.InvalidSyntaxError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer(url, 'u', 'p')]))


def test_ice_server_credentials_and_ranges():
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer('turn:example.org')]))
    with pytest.raises(webrtc.InvalidSyntaxError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer([])]))
    with pytest.raises(ValueError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_candidate_pool_size=256))
    webrtc.RTCPeerConnection(
        webrtc.RTCConfiguration(ice_servers=[webrtc.RTCIceServer('stun:[2001:db8::1]:3478')])
    ).close()


def test_ice_candidate_parsing():
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

    # not validated, but not parsed either
    invalid = webrtc.RTCIceCandidate('a=candidate:1 1 udp 1 1.2.3.4 5 typ host', sdp_m_line_index=0)
    assert invalid.foundation is None and invalid.port is None
    with pytest.raises(TypeError):
        webrtc.RTCIceCandidate('candidate:1 1 udp 1 1.2.3.4 5 typ host')


def test_rtc_error():
    error = webrtc.RTCError('sctp-failure', 'failed', sctp_cause_code=12)
    assert isinstance(error, webrtc.OperationError) and isinstance(error, webrtc.RTCException)
    assert error.error_detail == webrtc.RTCErrorDetailType.sctp_failure
    assert error.sctp_cause_code == 12 and error.sdp_line_number is None
    with pytest.raises(ValueError):
        webrtc.RTCError('nonsense')


@pytest.mark.asyncio
async def test_description_errors_and_models(pc):
    with pytest.raises(webrtc.InvalidStateError):
        await pc.set_remote_description({'type': 'answer', 'sdp': 'invalid'})
    with pytest.raises(webrtc.RTCError) as info:
        await pc.set_remote_description(webrtc.RTCSessionDescription('offer', 'v=0\r\nnonsense'))
    assert info.value.error_detail == webrtc.RTCErrorDetailType.sdp_syntax_error

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
async def test_certificates():
    ecdsa = await webrtc.RTCPeerConnection.generate_certificate('ECDSA')
    assert ecdsa.expires > time.time() * 1000 and not ecdsa.expired
    (fingerprint,) = ecdsa.get_fingerprints()
    assert fingerprint.algorithm == 'sha-256' and len(fingerprint.value.split(':')) == 32

    rsa = await webrtc.RTCCertificate.generate(
        {'name': 'RSASSA-PKCS1-v1_5', 'modulus_length': 1024, 'public_exponent': 65537, 'hash': 'SHA-256'}
    )
    for algorithm in (
        'nonsense',
        {'name': 'RSASSA-PKCS1-v1_5', 'modulusLength': 2048, 'publicExponent': 3, 'hash': 'SHA-1'},
    ):
        with pytest.raises(webrtc.NotSupportedError):
            await webrtc.RTCCertificate.generate(algorithm)

    pc = webrtc.RTCPeerConnection(webrtc.RTCConfiguration(certificates=[ecdsa]))
    pc.add_transceiver(webrtc.MediaType.audio)
    offer = await pc.create_offer()
    assert fingerprint.value.upper() in offer.sdp
    assert pc.get_configuration().certificates[0].get_fingerprints() == [fingerprint]
    # omitting certificates keeps them, changing them isn't allowed
    pc.set_configuration(webrtc.RTCConfiguration())
    with pytest.raises(webrtc.InvalidModificationError):
        pc.set_configuration(webrtc.RTCConfiguration(certificates=[rsa]))
    pc.close()

    expired = await webrtc.RTCCertificate.generate('ECDSA', expires=0)
    await asyncio.sleep(0.01)
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(certificates=[expired]))


@pytest.mark.asyncio
async def test_always_negotiate_data_channels_and_header_encryption():
    pc = webrtc.RTCPeerConnection(
        webrtc.RTCConfiguration(
            always_negotiate_data_channels=True,
            rtp_header_encryption_policy=webrtc.RTCRtpHeaderEncryptionPolicy.require,
        )
    )
    configuration = pc.get_configuration()
    assert configuration.always_negotiate_data_channels
    assert configuration.rtp_header_encryption_policy == webrtc.RTCRtpHeaderEncryptionPolicy.require

    # an offer has a media section for data channels, even without one
    offer = await pc.create_offer()
    assert offer.sdp.count('m=application') == 1
    assert 'a=cryptex' in offer.sdp

    pc.set_configuration(configuration)
    for changed in ({'always_negotiate_data_channels': False}, {'rtp_header_encryption_policy': 'negotiate'}):
        with pytest.raises(webrtc.InvalidModificationError):
            pc.set_configuration(dataclasses.replace(configuration, **changed))
    pc.close()


def test_oauth_ice_server():
    server = {'urls': 'turns:turn.example.org', 'username': 'user', 'credential': 'cred', 'credential_type': 'oauth'}
    with pytest.raises(webrtc.InvalidAccessError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[server]))
    server['credential'] = webrtc.RTCOAuthCredential(mac_key='a2V5', access_token='dG9rZW4=')
    with pytest.raises(webrtc.NotSupportedError):
        webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=[server]))


@pytest.mark.asyncio
async def test_provisional_answers_without_sdp():
    offerer, answerer = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    offerer.add_transceiver(webrtc.MediaType.audio)
    await offerer.set_local_description()
    await answerer.set_remote_description(offerer.local_description)

    await answerer.set_local_description({'type': 'pranswer'})
    assert answerer.signaling_state == webrtc.RTCSignalingState.have_local_pranswer
    assert answerer.pending_local_description.type == webrtc.RTCSdpType.pranswer
    # without a type, the final answer
    await answerer.set_local_description()
    assert answerer.signaling_state == webrtc.RTCSignalingState.stable
    assert answerer.current_local_description.type == webrtc.RTCSdpType.answer
    offerer.close()
    answerer.close()


@pytest.mark.asyncio
async def test_closed_connection_keeps_its_transceivers():
    pc = webrtc.RTCPeerConnection()
    pc.add_transceiver(webrtc.MediaType.audio)
    pc.close()
    [transceiver] = pc.get_transceivers()
    # stopped, as every transceiver of a closed connection
    assert pc.get_senders() == pc.get_receivers() == []
    with pytest.raises(webrtc.InvalidStateError):
        transceiver.stop()
