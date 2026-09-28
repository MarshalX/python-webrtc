#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Enums with the spec string values: ``RTCSignalingState.have_local_offer == 'have-local-offer'``."""

import enum


class _StrEnum(str, enum.Enum):
    def __str__(self) -> str:
        return self.value


class RTCPeerConnectionState(_StrEnum):
    """The state of a connection, from the states of its ICE and DTLS transports."""

    new = 'new'
    connecting = 'connecting'
    connected = 'connected'
    disconnected = 'disconnected'
    failed = 'failed'
    closed = 'closed'


class RTCSignalingState(_StrEnum):
    """The state of the offer/answer negotiation of a connection."""

    stable = 'stable'
    have_local_offer = 'have-local-offer'
    have_local_pranswer = 'have-local-pranswer'
    have_remote_offer = 'have-remote-offer'
    have_remote_pranswer = 'have-remote-pranswer'
    closed = 'closed'


class RTCIceConnectionState(_StrEnum):
    """The state of the ICE transports of a connection, together."""

    new = 'new'
    checking = 'checking'
    connected = 'connected'
    completed = 'completed'
    failed = 'failed'
    disconnected = 'disconnected'
    closed = 'closed'
    #: Not a state: the number of states in libwebrtc, never reported.
    max = 'max'


class RTCIceGatheringState(_StrEnum):
    """The candidate gathering state of the ICE transports of a connection, together."""

    new = 'new'
    gathering = 'gathering'
    complete = 'complete'


class RTCSdpType(_StrEnum):
    """The type of a session description."""

    offer = 'offer'
    pranswer = 'pranswer'
    answer = 'answer'
    rollback = 'rollback'


class MediaStreamTrackState(_StrEnum):
    """The state of a track."""

    live = 'live'
    ended = 'ended'


class MediaStreamSourceState(_StrEnum):
    """The state of the source of a track. Not in the specifications, it's the state of a libwebrtc source."""

    initializing = 'initializing'
    live = 'live'
    ended = 'ended'
    muted = 'muted'


class TransceiverDirection(_StrEnum):
    """The direction of a transceiver, ``RTCRtpTransceiverDirection`` in the specification."""

    sendrecv = 'sendrecv'
    sendonly = 'sendonly'
    recvonly = 'recvonly'
    inactive = 'inactive'
    stopped = 'stopped'


class MediaType(_StrEnum):
    """The kind of a track: audio or video. Data and unsupported media sections exist in libwebrtc only."""

    audio = 'audio'
    video = 'video'
    data = 'data'
    unsupported = 'unsupported'


class RTCIceComponent(_StrEnum):
    """The component of an ICE transport or candidate."""

    rtp = 'rtp'
    rtcp = 'rtcp'


class RTCIceRole(_StrEnum):
    """The role of an ICE agent."""

    controlling = 'controlling'
    controlled = 'controlled'
    unknown = 'unknown'


class RTCIceTransportState(_StrEnum):
    """The state of an ICE transport."""

    new = 'new'
    checking = 'checking'
    connected = 'connected'
    completed = 'completed'
    disconnected = 'disconnected'
    failed = 'failed'
    closed = 'closed'


class CricketIceGatheringState(_StrEnum):
    """The candidate gathering state of an ICE transport, ``RTCIceGathererState`` in the specification."""

    new = 'new'
    gathering = 'gathering'
    complete = 'complete'


class DtlsTransportState(_StrEnum):
    """The state of a DTLS transport, ``RTCDtlsTransportState`` in the specification."""

    new = 'new'
    connecting = 'connecting'
    connected = 'connected'
    closed = 'closed'
    failed = 'failed'


class SctpTransportState(_StrEnum):
    """The state of an SCTP transport, ``RTCSctpTransportState`` in the specification."""

    new = 'new'
    connecting = 'connecting'
    connected = 'connected'
    closed = 'closed'


class RTCDataChannelState(_StrEnum):
    """The state of a data channel."""

    connecting = 'connecting'
    open = 'open'
    closing = 'closing'
    closed = 'closed'


class RTCPriorityType(_StrEnum):
    """The priority of a data channel or an encoding, relative to the others."""

    very_low = 'very-low'
    low = 'low'
    medium = 'medium'
    high = 'high'


class RTCDegradationPreference(_StrEnum):
    """What a video sender degrades first when it can't keep up."""

    maintain_framerate = 'maintain-framerate'
    maintain_resolution = 'maintain-resolution'
    balanced = 'balanced'
    maintain_framerate_and_resolution = 'maintain-framerate-and-resolution'


class RTCIceTransportPolicy(_StrEnum):
    """Which ICE candidates may be used."""

    all = 'all'
    relay = 'relay'


class RTCBundlePolicy(_StrEnum):
    """How media is bundled when the remote peer doesn't support bundling."""

    balanced = 'balanced'
    max_compat = 'max-compat'
    max_bundle = 'max-bundle'


class RTCRtcpMuxPolicy(_StrEnum):
    """Whether RTCP is multiplexed with RTP, which is required."""

    require = 'require'


class RTCRtpHeaderEncryptionPolicy(_StrEnum):
    """Whether RTP header extensions are encrypted with cryptex (RFC 9335)."""

    negotiate = 'negotiate'
    require = 'require'


class RTCIceCandidateType(_StrEnum):
    """The type of an ICE candidate."""

    host = 'host'
    srflx = 'srflx'
    prflx = 'prflx'
    relay = 'relay'


class RTCIceProtocol(_StrEnum):
    """The transport protocol of an ICE candidate."""

    udp = 'udp'
    tcp = 'tcp'


class RTCIceTcpCandidateType(_StrEnum):
    """The type of a TCP ICE candidate."""

    active = 'active'
    passive = 'passive'
    so = 'so'


class RTCIceServerTransportProtocol(_StrEnum):
    """The protocol used between the client and a TURN server."""

    udp = 'udp'
    tcp = 'tcp'
    tls = 'tls'


class RTCErrorDetailType(_StrEnum):
    """The WebRTC-specific cause of an :obj:`webrtc.RTCError`."""

    data_channel_failure = 'data-channel-failure'
    dtls_failure = 'dtls-failure'
    fingerprint_failure = 'fingerprint-failure'
    sctp_failure = 'sctp-failure'
    sdp_syntax_error = 'sdp-syntax-error'
    hardware_encoder_not_available = 'hardware-encoder-not-available'
    hardware_encoder_error = 'hardware-encoder-error'
