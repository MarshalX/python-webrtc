#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Enums with the spec string values: ``RTCSignalingState.have_local_offer == 'have-local-offer'``."""

from __future__ import annotations

import enum
from typing import Literal


class _StrEnum(str, enum.Enum):
    def __str__(self) -> str:
        value: str = self.value
        return value


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


#: The values of :obj:`RTCSdpType`, which parameters taking it take too
RTCSdpTypeValue = Literal['offer', 'pranswer', 'answer', 'rollback']


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


class RTCRtpTransceiverDirection(_StrEnum):
    """The direction of a transceiver."""

    sendrecv = 'sendrecv'
    sendonly = 'sendonly'
    recvonly = 'recvonly'
    inactive = 'inactive'
    stopped = 'stopped'


#: The values of :obj:`RTCRtpTransceiverDirection`, which parameters taking it take too
RTCRtpTransceiverDirectionValue = Literal['sendrecv', 'sendonly', 'recvonly', 'inactive', 'stopped']


class MediaType(_StrEnum):
    """The kind of a track: audio or video. Data and unsupported media sections exist in libwebrtc only."""

    audio = 'audio'
    video = 'video'
    data = 'data'
    unsupported = 'unsupported'


#: The values of :obj:`MediaType`, which parameters taking it take too
MediaTypeValue = Literal['audio', 'video', 'data', 'unsupported']


class MediaDeviceKind(_StrEnum):
    """The kind of a media device."""

    audioinput = 'audioinput'
    audiooutput = 'audiooutput'
    videoinput = 'videoinput'


class VideoFacingModeEnum(_StrEnum):
    """Where a camera faces."""

    user = 'user'
    environment = 'environment'
    left = 'left'
    right = 'right'


class VideoResizeModeEnum(_StrEnum):
    """How the video of a source is resized."""

    none = 'none'
    crop_and_scale = 'crop-and-scale'


class EchoCancellationModeEnum(_StrEnum):
    """Which echo is cancelled: of all the audio played, or of the remote audio only."""

    all = 'all'
    remote_only = 'remote-only'


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


class RTCIceGathererState(_StrEnum):
    """The candidate gathering state of an ICE transport."""

    new = 'new'
    gathering = 'gathering'
    complete = 'complete'


class RTCDtlsTransportState(_StrEnum):
    """The state of a DTLS transport."""

    new = 'new'
    connecting = 'connecting'
    connected = 'connected'
    closed = 'closed'
    failed = 'failed'


class RTCSctpTransportState(_StrEnum):
    """The state of an SCTP transport."""

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


#: The values of :obj:`RTCPriorityType`, which parameters taking it take too
RTCPriorityTypeValue = Literal['very-low', 'low', 'medium', 'high']


class RTCDegradationPreference(_StrEnum):
    """What a video sender degrades first when it can't keep up."""

    maintain_framerate = 'maintain-framerate'
    maintain_resolution = 'maintain-resolution'
    balanced = 'balanced'
    maintain_framerate_and_resolution = 'maintain-framerate-and-resolution'


#: The values of :obj:`RTCDegradationPreference`, which parameters taking it take too
RTCDegradationPreferenceValue = Literal[
    'maintain-framerate',
    'maintain-resolution',
    'balanced',
    'maintain-framerate-and-resolution',
]


class RTCIceTransportPolicy(_StrEnum):
    """Which ICE candidates may be used."""

    all = 'all'
    relay = 'relay'


#: The values of :obj:`RTCIceTransportPolicy`, which parameters taking it take too
RTCIceTransportPolicyValue = Literal['all', 'relay']


class RTCBundlePolicy(_StrEnum):
    """How media is bundled when the remote peer doesn't support bundling."""

    balanced = 'balanced'
    max_compat = 'max-compat'
    max_bundle = 'max-bundle'


#: The values of :obj:`RTCBundlePolicy`, which parameters taking it take too
RTCBundlePolicyValue = Literal['balanced', 'max-compat', 'max-bundle']


class RTCRtcpMuxPolicy(_StrEnum):
    """Whether RTCP is multiplexed with RTP, which is required."""

    require = 'require'


#: The values of :obj:`RTCRtcpMuxPolicy`, which parameters taking it take too
RTCRtcpMuxPolicyValue = Literal['require']


class RTCRtpHeaderEncryptionPolicy(_StrEnum):
    """Whether RTP header extensions are encrypted with cryptex (RFC 9335)."""

    negotiate = 'negotiate'
    require = 'require'


#: The values of :obj:`RTCRtpHeaderEncryptionPolicy`, which parameters taking it take too
RTCRtpHeaderEncryptionPolicyValue = Literal['negotiate', 'require']


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


#: The values of :obj:`RTCIceServerTransportProtocol`, which parameters taking it take too
RTCIceServerTransportProtocolValue = Literal['udp', 'tcp', 'tls']


class RTCStatsType(_StrEnum):
    """The type of stats, which tells the dictionary they are."""

    codec = 'codec'
    inbound_rtp = 'inbound-rtp'
    outbound_rtp = 'outbound-rtp'
    remote_inbound_rtp = 'remote-inbound-rtp'
    remote_outbound_rtp = 'remote-outbound-rtp'
    media_source = 'media-source'
    media_playout = 'media-playout'
    peer_connection = 'peer-connection'
    data_channel = 'data-channel'
    transport = 'transport'
    candidate_pair = 'candidate-pair'
    local_candidate = 'local-candidate'
    remote_candidate = 'remote-candidate'
    certificate = 'certificate'


class RTCQualityLimitationReason(_StrEnum):
    """What limits the resolution or frame rate of a video sender the most."""

    none = 'none'
    cpu = 'cpu'
    bandwidth = 'bandwidth'
    other = 'other'


class RTCDtlsRole(_StrEnum):
    """The role of a DTLS transport in the handshake."""

    client = 'client'
    server = 'server'
    unknown = 'unknown'


class RTCStatsIceCandidatePairState(_StrEnum):
    """The state of an ICE candidate pair in the checklist."""

    frozen = 'frozen'
    waiting = 'waiting'
    in_progress = 'in-progress'
    failed = 'failed'
    succeeded = 'succeeded'


class RTCErrorDetailType(_StrEnum):
    """The WebRTC-specific cause of an :obj:`webrtc.RTCError`."""

    data_channel_failure = 'data-channel-failure'
    dtls_failure = 'dtls-failure'
    fingerprint_failure = 'fingerprint-failure'
    sctp_failure = 'sctp-failure'
    sdp_syntax_error = 'sdp-syntax-error'
    hardware_encoder_not_available = 'hardware-encoder-not-available'
    hardware_encoder_error = 'hardware-encoder-error'


#: The values of :obj:`webrtc.RTCErrorDetailType`, which parameters taking it take too
RTCErrorDetailTypeValue = Literal[
    'data-channel-failure',
    'dtls-failure',
    'fingerprint-failure',
    'sctp-failure',
    'sdp-syntax-error',
    'hardware-encoder-not-available',
    'hardware-encoder-error',
]


class BinaryType(_StrEnum):
    """What the binary messages of a :obj:`webrtc.RTCDataChannel` are delivered as."""

    #: :obj:`bytes`
    arraybuffer = 'arraybuffer'
    #: :obj:`webrtc.Blob`
    blob = 'blob'


#: The values of :obj:`BinaryType`, which parameters taking it take too
BinaryTypeValue = Literal['arraybuffer', 'blob']


class EndingType(_StrEnum):
    """How a :obj:`webrtc.Blob` writes the line endings of its string parts."""

    #: As they are
    transparent = 'transparent'
    #: As the ones of the platform: ``\r\n`` on Windows, ``\n`` elsewhere
    native = 'native'


#: The values of :obj:`EndingType`, which parameters taking it take too
EndingTypeValue = Literal['transparent', 'native']


class VideoPixelFormat(_StrEnum):
    """The layout of the pixels of a :obj:`webrtc.VideoFrame`.

    Y, U, V (and alpha) planes of 8-bit samples, or of 10- and 12-bit samples stored in 16 bits (``P10``, ``P12``),
    NV12 with interleaved U and V, or 4 bytes per RGB pixel.
    """

    I420 = 'I420'
    I420P10 = 'I420P10'
    I420P12 = 'I420P12'
    I420A = 'I420A'
    I420AP10 = 'I420AP10'
    I420AP12 = 'I420AP12'
    I422 = 'I422'
    I422P10 = 'I422P10'
    I422P12 = 'I422P12'
    I422A = 'I422A'
    I422AP10 = 'I422AP10'
    I422AP12 = 'I422AP12'
    I444 = 'I444'
    I444P10 = 'I444P10'
    I444P12 = 'I444P12'
    I444A = 'I444A'
    I444AP10 = 'I444AP10'
    I444AP12 = 'I444AP12'
    NV12 = 'NV12'
    RGBA = 'RGBA'
    RGBX = 'RGBX'
    BGRA = 'BGRA'
    BGRX = 'BGRX'


#: The values of :obj:`VideoPixelFormat`, which parameters taking it take too
VideoPixelFormatValue = Literal[
    'I420',
    'I420P10',
    'I420P12',
    'I420A',
    'I420AP10',
    'I420AP12',
    'I422',
    'I422P10',
    'I422P12',
    'I422A',
    'I422AP10',
    'I422AP12',
    'I444',
    'I444P10',
    'I444P12',
    'I444A',
    'I444AP10',
    'I444AP12',
    'NV12',
    'RGBA',
    'RGBX',
    'BGRA',
    'BGRX',
]


class VideoColorPrimaries(_StrEnum):
    """The color primaries of a :obj:`webrtc.VideoColorSpace`."""

    bt709 = 'bt709'
    bt470bg = 'bt470bg'
    smpte170m = 'smpte170m'
    bt2020 = 'bt2020'
    smpte432 = 'smpte432'


#: The values of :obj:`VideoColorPrimaries`, which parameters taking it take too
VideoColorPrimariesValue = Literal['bt709', 'bt470bg', 'smpte170m', 'bt2020', 'smpte432']


class VideoTransferCharacteristics(_StrEnum):
    """The transfer characteristics of a :obj:`webrtc.VideoColorSpace`."""

    bt709 = 'bt709'
    smpte170m = 'smpte170m'
    iec61966_2_1 = 'iec61966-2-1'
    linear = 'linear'
    pq = 'pq'
    hlg = 'hlg'


#: The values of :obj:`VideoTransferCharacteristics`, which parameters taking it take too
VideoTransferCharacteristicsValue = Literal['bt709', 'smpte170m', 'iec61966-2-1', 'linear', 'pq', 'hlg']


class VideoMatrixCoefficients(_StrEnum):
    """The matrix coefficients of a :obj:`webrtc.VideoColorSpace`."""

    rgb = 'rgb'
    bt709 = 'bt709'
    bt470bg = 'bt470bg'
    smpte170m = 'smpte170m'
    bt2020_ncl = 'bt2020-ncl'


#: The values of :obj:`VideoMatrixCoefficients`, which parameters taking it take too
VideoMatrixCoefficientsValue = Literal['rgb', 'bt709', 'bt470bg', 'smpte170m', 'bt2020-ncl']


class AlphaOption(_StrEnum):
    """Whether a :obj:`webrtc.VideoFrame` created from another one keeps its alpha channel."""

    keep = 'keep'
    discard = 'discard'


#: The values of :obj:`AlphaOption`, which parameters taking it take too
AlphaOptionValue = Literal['keep', 'discard']


class PredefinedColorSpace(_StrEnum):
    """The color space :meth:`webrtc.VideoFrame.copy_to` converts RGB pixels to."""

    srgb = 'srgb'
    srgb_linear = 'srgb-linear'
    display_p3 = 'display-p3'
    display_p3_linear = 'display-p3-linear'


#: The values of :obj:`PredefinedColorSpace`, which parameters taking it take too
PredefinedColorSpaceValue = Literal['srgb', 'srgb-linear', 'display-p3', 'display-p3-linear']


class AudioSampleFormat(_StrEnum):
    """The type of the samples of an :obj:`webrtc.AudioData`, interleaved or in a plane per channel."""

    u8 = 'u8'
    s16 = 's16'
    s32 = 's32'
    f32 = 'f32'
    u8_planar = 'u8-planar'
    s16_planar = 's16-planar'
    s32_planar = 's32-planar'
    f32_planar = 'f32-planar'


#: The values of :obj:`AudioSampleFormat`, which parameters taking it take too
AudioSampleFormatValue = Literal['u8', 's16', 's32', 'f32', 'u8-planar', 's16-planar', 's32-planar', 'f32-planar']


class ReadableStreamReaderMode(_StrEnum):
    """The type of reader :meth:`webrtc.ReadableStream.get_reader` returns."""

    byob = 'byob'


#: The values of :obj:`ReadableStreamReaderMode`, which parameters taking it take too
ReadableStreamReaderModeValue = Literal['byob']


class EncodedVideoChunkType(_StrEnum):
    """Whether an encoded video frame is a key frame, which decodes on its own, or depends on earlier frames."""

    key = 'key'
    delta = 'delta'


class RTCRtpScriptTransformType(_StrEnum):
    """How an :obj:`webrtc.RTCRtpScriptTransform` packetizes the frames it outputs."""

    #: The frames are SFrame-encrypted, packetized as SFrame
    sframe = 'sframe'


#: The values of :obj:`RTCRtpScriptTransformType`, which parameters taking it take too
RTCRtpScriptTransformTypeValue = Literal['sframe']


class SFrameCipherSuite(_StrEnum):
    """The SFrame cipher suites of RFC 9605 and draft-barnes-sframe-iana-256: AES-CTR with HMAC tags, or AES-GCM."""

    AES_128_CTR_HMAC_SHA256_80 = 'AES_128_CTR_HMAC_SHA256_80'
    AES_128_CTR_HMAC_SHA256_64 = 'AES_128_CTR_HMAC_SHA256_64'
    AES_128_CTR_HMAC_SHA256_32 = 'AES_128_CTR_HMAC_SHA256_32'
    AES_128_GCM_SHA256_128 = 'AES_128_GCM_SHA256_128'
    AES_256_GCM_SHA512_128 = 'AES_256_GCM_SHA512_128'
    AES_256_CTR_HMAC_SHA512_80 = 'AES_256_CTR_HMAC_SHA512_80'
    AES_256_CTR_HMAC_SHA512_64 = 'AES_256_CTR_HMAC_SHA512_64'
    AES_256_CTR_HMAC_SHA512_32 = 'AES_256_CTR_HMAC_SHA512_32'


#: The values of :obj:`SFrameCipherSuite`, which parameters taking it take too
SFrameCipherSuiteValue = Literal[
    'AES_128_CTR_HMAC_SHA256_80',
    'AES_128_CTR_HMAC_SHA256_64',
    'AES_128_CTR_HMAC_SHA256_32',
    'AES_128_GCM_SHA256_128',
    'AES_256_GCM_SHA512_128',
    'AES_256_CTR_HMAC_SHA512_80',
    'AES_256_CTR_HMAC_SHA512_64',
    'AES_256_CTR_HMAC_SHA512_32',
]


class SFrameType(_StrEnum):
    """Whether an :obj:`webrtc.RTCRtpSFrameEncryptor` encrypts whole frames or each RTP packet."""

    per_frame = 'per-frame'
    per_packet = 'per-packet'


#: The values of :obj:`SFrameType`, which parameters taking it take too
SFrameTypeValue = Literal['per-frame', 'per-packet']


class SFrameTransformErrorEventType(_StrEnum):
    """Why a frame didn't decrypt: it didn't authenticate, its key id is unknown, or it isn't SFrame."""

    authentication = 'authentication'
    key_id = 'keyID'
    syntax = 'syntax'


#: The values of :obj:`SFrameTransformErrorEventType`, which parameters taking it take too
SFrameTransformErrorEventTypeValue = Literal['authentication', 'keyID', 'syntax']
