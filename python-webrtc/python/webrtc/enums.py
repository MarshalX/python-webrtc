#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""String enums of the specifications.

Members compare equal to their spec strings and print as them: ``RTCSignalingState.have_local_offer ==
'have-local-offer'``. Hyphens in the values become underscores in the member names. Parameters that take an enum take
its string value too, as typed by the ``...Value`` literal next to it.
"""

from __future__ import annotations

import enum
from typing import Literal


class _StrEnum(str, enum.Enum):
    def __str__(self) -> str:
        value: str = self.value
        return value


class RTCPeerConnectionState(_StrEnum):
    """The overall state of a connection, combined from its ICE and DTLS transports.

    See :mdn:`RTCPeerConnection/connectionState`.
    """

    #: No transport has started connecting yet
    new = 'new'
    #: A transport is connecting, and none has failed
    connecting = 'connecting'
    #: Every transport in use is connected
    connected = 'connected'
    #: A transport lost connectivity, and may recover
    disconnected = 'disconnected'
    #: A transport failed and needs an ICE restart
    failed = 'failed'
    #: The connection was closed
    closed = 'closed'


class RTCSignalingState(_StrEnum):
    """Where a connection is in the offer/answer exchange.

    See :mdn:`RTCPeerConnection/signalingState`.
    """

    #: No offer/answer exchange is in progress
    stable = 'stable'
    #: A local offer is set, waiting for an answer
    have_local_offer = 'have-local-offer'
    #: A remote offer and a local provisional answer are set
    have_local_pranswer = 'have-local-pranswer'
    #: A remote offer is set, waiting for a local answer
    have_remote_offer = 'have-remote-offer'
    #: A local offer and a remote provisional answer are set
    have_remote_pranswer = 'have-remote-pranswer'
    #: The connection was closed
    closed = 'closed'


class RTCIceConnectionState(_StrEnum):
    """The state of the ICE transports of a connection, taken together.

    See :mdn:`RTCPeerConnection/iceConnectionState`.
    """

    #: No transport is checking candidates yet
    new = 'new'
    #: A transport is checking candidate pairs, and none is connected
    checking = 'checking'
    #: Every transport has a usable pair
    connected = 'connected'
    #: Every transport finished checking and has a usable pair
    completed = 'completed'
    #: A transport found no usable pair
    failed = 'failed'
    #: A transport lost connectivity, and may recover
    disconnected = 'disconnected'
    #: The connection was closed
    closed = 'closed'


class RTCIceGatheringState(_StrEnum):
    """The candidate gathering state of the ICE transports of a connection, taken together.

    See :mdn:`RTCPeerConnection/iceGatheringState`.
    """

    #: No transport has started gathering
    new = 'new'
    #: A transport is gathering candidates
    gathering = 'gathering'
    #: Every transport finished gathering
    complete = 'complete'


class RTCSdpType(_StrEnum):
    """The type of a session description.

    See :mdn:`RTCSessionDescription/type`.
    """

    #: An offer, which starts an exchange
    offer = 'offer'
    #: A provisional answer, which can still be replaced
    pranswer = 'pranswer'
    #: The final answer, which ends an exchange
    answer = 'answer'
    #: Discards a pending offer and returns to the last stable state
    rollback = 'rollback'


#: The string values of :obj:`RTCSdpType`, which parameters accept in place of its members
RTCSdpTypeValue = Literal['offer', 'pranswer', 'answer', 'rollback']


class MediaStreamTrackState(_StrEnum):
    """Whether a track still delivers media.

    See :mdn:`MediaStreamTrack/readyState`.
    """

    #: The track delivers media, or will when it's unmuted
    live = 'live'
    #: The track was stopped or its source ended, and it won't deliver media again
    ended = 'ended'


class MediaStreamSourceState(_StrEnum):
    """The state of the native source of a track. This library adds it. The specifications have no such enum."""

    #: The source is starting
    initializing = 'initializing'
    #: The source produces media
    live = 'live'
    #: The source stopped permanently
    ended = 'ended'
    #: The source produces no media for now
    muted = 'muted'


class RTCRtpTransceiverDirection(_StrEnum):
    """Whether a transceiver sends media, receives it, both or neither.

    See :mdn:`RTCRtpTransceiver/direction`.
    """

    #: Sends and receives
    sendrecv = 'sendrecv'
    #: Sends only
    sendonly = 'sendonly'
    #: Receives only
    recvonly = 'recvonly'
    #: Neither sends nor receives
    inactive = 'inactive'
    #: Stopped, which isn't a direction that can be set
    stopped = 'stopped'


#: The string values of :obj:`RTCRtpTransceiverDirection`, which parameters accept in place of its members
RTCRtpTransceiverDirectionValue = Literal['sendrecv', 'sendonly', 'recvonly', 'inactive', 'stopped']


class MediaType(_StrEnum):
    """The kind of a track or a transceiver.

    Tracks are audio or video. The data and unsupported kinds come from the media sections of the native WebRTC engine.

    See :mdn:`MediaStreamTrack/kind`.
    """

    #: Audio
    audio = 'audio'
    #: Video
    video = 'video'
    #: The media section of data channels
    data = 'data'
    #: A media section of a kind the native WebRTC engine doesn't handle
    unsupported = 'unsupported'


#: The string values of :obj:`MediaType`, which parameters accept in place of its members
MediaTypeValue = Literal['audio', 'video', 'data', 'unsupported']


class MediaDeviceKind(_StrEnum):
    """The kind of a media device.

    See :mdn:`MediaDeviceInfo/kind`.
    """

    #: A microphone or another audio input
    audioinput = 'audioinput'
    #: Speakers, headphones or another audio output
    audiooutput = 'audiooutput'
    #: A camera or another video input
    videoinput = 'videoinput'


class VideoFacingModeEnum(_StrEnum):
    """The direction a camera faces, relative to the user.

    See :mdn:`MediaTrackConstraints/facingMode`.
    """

    #: Towards the user, like a front camera
    user = 'user'
    #: Away from the user, like a back camera
    environment = 'environment'
    #: Towards the left of the user
    left = 'left'
    #: Towards the right of the user
    right = 'right'


class VideoResizeModeEnum(_StrEnum):
    """Whether the video of a source may be cropped and scaled to meet the constraints of a track."""

    #: The video keeps the resolution and frame rate of the source
    none = 'none'
    #: The video may be cropped, scaled down and have frames dropped
    crop_and_scale = 'crop-and-scale'


class EchoCancellationModeEnum(_StrEnum):
    """Which audio played out is removed as echo from a microphone.

    See :mdn:`MediaTrackConstraints/echoCancellation`.
    """

    #: Any audio the system plays
    all = 'all'
    #: Only the audio received from remote peers
    remote_only = 'remote-only'


class RTCIceComponent(_StrEnum):
    """Whether an ICE transport or candidate carries RTP or RTCP.

    See :mdn:`RTCIceCandidate/component`.
    """

    #: RTP, or RTP and RTCP multiplexed together
    rtp = 'rtp'
    #: RTCP on its own transport
    rtcp = 'rtcp'


class RTCIceRole(_StrEnum):
    """The role of an ICE agent. The controlling agent picks the candidate pair.

    See :mdn:`RTCIceTransport/role`.
    """

    #: Nominates the candidate pair in use
    controlling = 'controlling'
    #: Accepts the pair the other agent nominates
    controlled = 'controlled'
    #: Not decided yet
    unknown = 'unknown'


class RTCIceTransportState(_StrEnum):
    """The state of an ICE transport.

    See :mdn:`RTCIceTransport/state`.
    """

    #: The transport is gathering candidates or waiting for remote ones, and hasn't started checks
    new = 'new'
    #: Candidate pairs are being checked, and none works yet
    checking = 'checking'
    #: A usable pair was found, and checks may go on
    connected = 'connected'
    #: Checks finished, and a usable pair was found
    completed = 'completed'
    #: Connectivity was lost, and may recover
    disconnected = 'disconnected'
    #: Checks finished without a usable pair
    failed = 'failed'
    #: The transport was closed
    closed = 'closed'


class RTCIceGathererState(_StrEnum):
    """The candidate gathering state of an ICE transport.

    See :mdn:`RTCIceTransport/gatheringState`.
    """

    #: Gathering hasn't started
    new = 'new'
    #: Candidates are being gathered
    gathering = 'gathering'
    #: Gathering finished
    complete = 'complete'


class RTCDtlsTransportState(_StrEnum):
    """The state of a DTLS transport.

    See :mdn:`RTCDtlsTransport/state`.
    """

    #: The handshake hasn't started
    new = 'new'
    #: The handshake is in progress
    connecting = 'connecting'
    #: The handshake succeeded
    connected = 'connected'
    #: Either side closed the transport
    closed = 'closed'
    #: The handshake or the fingerprint check failed
    failed = 'failed'


class RTCSctpTransportState(_StrEnum):
    """The state of an SCTP transport.

    See :mdn:`RTCSctpTransport/state`.
    """

    #: The association is being set up
    connecting = 'connecting'
    #: The association is up, and channels can open
    connected = 'connected'
    #: The association was closed
    closed = 'closed'


class RTCDataChannelState(_StrEnum):
    """The state of a data channel.

    See :mdn:`RTCDataChannel/readyState`.
    """

    #: The channel is being opened, and messages can't be sent yet
    connecting = 'connecting'
    #: Messages can be sent and received
    open = 'open'
    #: The channel will close once the messages already queued are sent
    closing = 'closing'
    #: The channel was closed, or couldn't be opened
    closed = 'closed'


class RTCPriorityType(_StrEnum):
    """The priority of a data channel or an encoding, relative to the others of the connection.

    Each level gets twice the bandwidth share of the one below it.

    See :mdn:`RTCRtpSender/setParameters`.
    """

    #: The lowest priority, with half the share of ``low``
    very_low = 'very-low'
    #: The default priority
    low = 'low'
    #: Twice the share of ``low``
    medium = 'medium'
    #: Four times the share of ``low``
    high = 'high'


#: The string values of :obj:`RTCPriorityType`, which parameters accept in place of its members
RTCPriorityTypeValue = Literal['very-low', 'low', 'medium', 'high']


class RTCDegradationPreference(_StrEnum):
    """What a video sender gives up first when bandwidth or CPU runs short.

    See :mdn:`RTCRtpSender/setParameters`.
    """

    #: Keeps the frame rate and lowers the resolution
    maintain_framerate = 'maintain-framerate'
    #: Keeps the resolution and lowers the frame rate
    maintain_resolution = 'maintain-resolution'
    #: Lowers both, as the native WebRTC engine sees fit
    balanced = 'balanced'
    #: Keeps both and lowers only the quality of the encoding
    maintain_framerate_and_resolution = 'maintain-framerate-and-resolution'


#: The string values of :obj:`RTCDegradationPreference`, which parameters accept in place of its members
RTCDegradationPreferenceValue = Literal[
    'maintain-framerate',
    'maintain-resolution',
    'balanced',
    'maintain-framerate-and-resolution',
]


class RTCIceTransportPolicy(_StrEnum):
    """Which ICE candidates a connection may use.

    See :mdn:`RTCPeerConnection/RTCPeerConnection`.
    """

    #: Any candidate
    all = 'all'
    #: Only candidates relayed through a TURN server, which hides the host's addresses
    relay = 'relay'


#: The string values of :obj:`RTCIceTransportPolicy`, which parameters accept in place of its members
RTCIceTransportPolicyValue = Literal['all', 'relay']


class RTCBundlePolicy(_StrEnum):
    """How media sections share transports when the remote peer may not support bundling.

    See :mdn:`RTCPeerConnection/RTCPeerConnection`.
    """

    #: A transport per media kind until the remote peer accepts bundling
    balanced = 'balanced'
    #: A transport per media section until the remote peer accepts bundling
    max_compat = 'max-compat'
    #: One transport for every media section, which needs a remote peer that supports bundling
    max_bundle = 'max-bundle'


#: The string values of :obj:`RTCBundlePolicy`, which parameters accept in place of its members
RTCBundlePolicyValue = Literal['balanced', 'max-compat', 'max-bundle']


class RTCRtcpMuxPolicy(_StrEnum):
    """Whether RTCP shares the transport of RTP.

    See :mdn:`RTCPeerConnection/RTCPeerConnection`.
    """

    #: RTCP may use its own transport; removed from the specification
    negotiate = 'negotiate'
    #: RTCP shares the transport of RTP, and a remote description without RTCP multiplexing fails
    require = 'require'


#: The string values of :obj:`RTCRtcpMuxPolicy`, which parameters accept in place of its members
RTCRtcpMuxPolicyValue = Literal['negotiate', 'require']


class RTCRtpHeaderEncryptionPolicy(_StrEnum):
    """Whether RTP header extensions are encrypted with cryptex (RFC 9335)."""

    #: Never encrypts them
    disable = 'disable'
    #: Encrypts them when the remote peer supports it
    negotiate = 'negotiate'
    #: Always encrypts them, so a remote description without cryptex fails
    require = 'require'


#: The string values of :obj:`RTCRtpHeaderEncryptionPolicy`, which parameters accept in place of its members
RTCRtpHeaderEncryptionPolicyValue = Literal['disable', 'negotiate', 'require']


class RTCIceCandidateType(_StrEnum):
    """Where the address of an ICE candidate comes from.

    See :mdn:`RTCIceCandidate/type`.
    """

    #: An address of a local network interface
    host = 'host'
    #: The public address a STUN server saw (server reflexive)
    srflx = 'srflx'
    #: An address learned from the checks of the remote peer (peer reflexive)
    prflx = 'prflx'
    #: An address allocated on a TURN server
    relay = 'relay'


class RTCIceProtocol(_StrEnum):
    """The transport protocol of an ICE candidate.

    See :mdn:`RTCIceCandidate/protocol`.
    """

    #: UDP
    udp = 'udp'
    #: TCP
    tcp = 'tcp'


class RTCIceTcpCandidateType(_StrEnum):
    """How a TCP ICE candidate opens its connections.

    See :mdn:`RTCIceCandidate/tcpType`.
    """

    #: Opens connections but doesn't accept them
    active = 'active'
    #: Accepts connections but doesn't open them
    passive = 'passive'
    #: Both sides try to open the connection at once (simultaneous open)
    so = 'so'


class RTCIceServerTransportProtocol(_StrEnum):
    """The protocol between the client and the TURN server of a relay candidate.

    See :mdn:`RTCIceCandidateStats/relayProtocol`.
    """

    #: UDP
    udp = 'udp'
    #: TCP
    tcp = 'tcp'
    #: TLS over TCP
    tls = 'tls'


#: The string values of :obj:`RTCIceServerTransportProtocol`, which parameters accept in place of its members
RTCIceServerTransportProtocolValue = Literal['udp', 'tcp', 'tls']


class RTCStatsType(_StrEnum):
    """The type of a stats object, which tells which stats class it is.

    See :mdn:`RTCStatsReport`.
    """

    #: :obj:`webrtc.RTCCodecStats`
    codec = 'codec'
    #: :obj:`webrtc.RTCInboundRtpStreamStats`
    inbound_rtp = 'inbound-rtp'
    #: :obj:`webrtc.RTCOutboundRtpStreamStats`
    outbound_rtp = 'outbound-rtp'
    #: :obj:`webrtc.RTCRemoteInboundRtpStreamStats`
    remote_inbound_rtp = 'remote-inbound-rtp'
    #: :obj:`webrtc.RTCRemoteOutboundRtpStreamStats`
    remote_outbound_rtp = 'remote-outbound-rtp'
    #: :obj:`webrtc.RTCAudioSourceStats` or :obj:`webrtc.RTCVideoSourceStats`
    media_source = 'media-source'
    #: :obj:`webrtc.RTCAudioPlayoutStats`
    media_playout = 'media-playout'
    #: :obj:`webrtc.RTCPeerConnectionStats`
    peer_connection = 'peer-connection'
    #: :obj:`webrtc.RTCDataChannelStats`
    data_channel = 'data-channel'
    #: :obj:`webrtc.RTCTransportStats`
    transport = 'transport'
    #: :obj:`webrtc.RTCIceCandidatePairStats`
    candidate_pair = 'candidate-pair'
    #: :obj:`webrtc.RTCIceCandidateStats` of a local candidate
    local_candidate = 'local-candidate'
    #: :obj:`webrtc.RTCIceCandidateStats` of a remote candidate
    remote_candidate = 'remote-candidate'
    #: :obj:`webrtc.RTCCertificateStats`
    certificate = 'certificate'


class RTCQualityLimitationReason(_StrEnum):
    """What limits the resolution or frame rate of a video sender the most.

    See :mdn:`RTCOutboundRtpStreamStats/qualityLimitationReason`.
    """

    #: Nothing
    none = 'none'
    #: The CPU, which can't encode fast enough
    cpu = 'cpu'
    #: The estimated bandwidth
    bandwidth = 'bandwidth'
    #: Something else
    other = 'other'


class RTCDtlsRole(_StrEnum):
    """The role of a DTLS transport in the handshake.

    See :mdn:`RTCTransportStats/dtlsRole`.
    """

    #: Starts the handshake
    client = 'client'
    #: Answers the handshake
    server = 'server'
    #: Not decided yet
    unknown = 'unknown'


class RTCStatsIceCandidatePairState(_StrEnum):
    """The state of an ICE candidate pair in the checklist.

    See :mdn:`RTCIceCandidatePairStats/state`.
    """

    #: Waits for a check of another pair of the same foundation
    frozen = 'frozen'
    #: Waits to be checked
    waiting = 'waiting'
    #: Being checked
    in_progress = 'in-progress'
    #: The check failed
    failed = 'failed'
    #: The check succeeded
    succeeded = 'succeeded'


class RTCErrorDetailType(_StrEnum):
    """The WebRTC-specific cause of an :obj:`webrtc.RTCError`.

    See :mdn:`RTCError/errorDetail`.
    """

    #: A data channel failed (see :attr:`webrtc.RTCError.sctp_cause_code`)
    data_channel_failure = 'data-channel-failure'
    #: The DTLS handshake failed or a DTLS alert was received
    dtls_failure = 'dtls-failure'
    #: The certificate of the remote peer doesn't match the fingerprint of its description
    fingerprint_failure = 'fingerprint-failure'
    #: The SCTP association failed (see :attr:`webrtc.RTCError.sctp_cause_code`)
    sctp_failure = 'sctp-failure'
    #: A description doesn't parse (see :attr:`webrtc.RTCError.sdp_line_number`)
    sdp_syntax_error = 'sdp-syntax-error'
    #: A hardware encoder was required and none is available
    hardware_encoder_not_available = 'hardware-encoder-not-available'
    #: The hardware encoder failed
    hardware_encoder_error = 'hardware-encoder-error'


#: The string values of :obj:`webrtc.RTCErrorDetailType`, which parameters accept in place of its members
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
    """What the binary messages of a :obj:`webrtc.RTCDataChannel` are delivered as.

    See :mdn:`RTCDataChannel/binaryType`.
    """

    #: :obj:`bytes`
    arraybuffer = 'arraybuffer'
    #: :obj:`webrtc.Blob`
    blob = 'blob'


#: The string values of :obj:`BinaryType`, which parameters accept in place of its members
BinaryTypeValue = Literal['arraybuffer', 'blob']


class EndingType(_StrEnum):
    """How a :obj:`webrtc.Blob` writes the line endings of its string parts.

    See :mdn:`Blob/Blob`.
    """

    #: As they are
    transparent = 'transparent'
    #: As the platform's, which are ``\r\n`` on Windows and ``\n`` elsewhere
    native = 'native'


#: The string values of :obj:`EndingType`, which parameters accept in place of its members
EndingTypeValue = Literal['transparent', 'native']


class VideoPixelFormat(_StrEnum):
    """The layout of the pixels of a :obj:`webrtc.VideoFrame`.

    ``I4xx`` formats are planar Y, U and V, plus alpha with ``A``. Chroma is subsampled ``4:2:0`` in ``I420`` and
    ``4:2:2`` in ``I422``, and has full resolution in ``I444``. Samples are 8-bit, or 10- and 12-bit stored in 16 bits
    with ``P10`` and ``P12``.

    See :mdn:`VideoFrame/format`.
    """

    #: 8-bit Y, U, V, ``4:2:0``
    I420 = 'I420'
    #: 10-bit Y, U, V, ``4:2:0``
    I420P10 = 'I420P10'
    #: 12-bit Y, U, V, ``4:2:0``
    I420P12 = 'I420P12'
    #: 8-bit Y, U, V, alpha, ``4:2:0``
    I420A = 'I420A'
    #: 10-bit Y, U, V, alpha, ``4:2:0``
    I420AP10 = 'I420AP10'
    #: 12-bit Y, U, V, alpha, ``4:2:0``
    I420AP12 = 'I420AP12'
    #: 8-bit Y, U, V, ``4:2:2``
    I422 = 'I422'
    #: 10-bit Y, U, V, ``4:2:2``
    I422P10 = 'I422P10'
    #: 12-bit Y, U, V, ``4:2:2``
    I422P12 = 'I422P12'
    #: 8-bit Y, U, V, alpha, ``4:2:2``
    I422A = 'I422A'
    #: 10-bit Y, U, V, alpha, ``4:2:2``
    I422AP10 = 'I422AP10'
    #: 12-bit Y, U, V, alpha, ``4:2:2``
    I422AP12 = 'I422AP12'
    #: 8-bit Y, U, V, ``4:4:4``
    I444 = 'I444'
    #: 10-bit Y, U, V, ``4:4:4``
    I444P10 = 'I444P10'
    #: 12-bit Y, U, V, ``4:4:4``
    I444P12 = 'I444P12'
    #: 8-bit Y, U, V, alpha, ``4:4:4``
    I444A = 'I444A'
    #: 10-bit Y, U, V, alpha, ``4:4:4``
    I444AP10 = 'I444AP10'
    #: 12-bit Y, U, V, alpha, ``4:4:4``
    I444AP12 = 'I444AP12'
    #: 8-bit Y plane and a plane of interleaved U and V, ``4:2:0``
    NV12 = 'NV12'
    #: 8-bit red, green, blue and alpha per pixel
    RGBA = 'RGBA'
    #: 8-bit red, green, blue and an unused byte per pixel
    RGBX = 'RGBX'
    #: 8-bit blue, green, red and alpha per pixel
    BGRA = 'BGRA'
    #: 8-bit blue, green, red and an unused byte per pixel
    BGRX = 'BGRX'


#: The string values of :obj:`VideoPixelFormat`, which parameters accept in place of its members
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
    """The color primaries of a :obj:`webrtc.VideoColorSpace`.

    See :mdn:`VideoColorSpace/primaries`.
    """

    #: BT.709, used by HD video and sRGB
    bt709 = 'bt709'
    #: BT.470 B/G, used by PAL video
    bt470bg = 'bt470bg'
    #: SMPTE 170M, used by NTSC video
    smpte170m = 'smpte170m'
    #: BT.2020, used by UHD video
    bt2020 = 'bt2020'
    #: SMPTE EG 432-1, used by Display P3
    smpte432 = 'smpte432'


#: The string values of :obj:`VideoColorPrimaries`, which parameters accept in place of its members
VideoColorPrimariesValue = Literal['bt709', 'bt470bg', 'smpte170m', 'bt2020', 'smpte432']


class VideoTransferCharacteristics(_StrEnum):
    """The transfer characteristics of a :obj:`webrtc.VideoColorSpace`.

    See :mdn:`VideoColorSpace/transfer`.
    """

    #: BT.709
    bt709 = 'bt709'
    #: SMPTE 170M
    smpte170m = 'smpte170m'
    #: IEC 61966-2-1, the sRGB curve
    iec61966_2_1 = 'iec61966-2-1'
    #: Linear light
    linear = 'linear'
    #: Perceptual quantizer (SMPTE ST 2084), used by HDR video
    pq = 'pq'
    #: Hybrid log-gamma (ARIB STD-B67), used by HDR video
    hlg = 'hlg'


#: The string values of :obj:`VideoTransferCharacteristics`, which parameters accept in place of its members
VideoTransferCharacteristicsValue = Literal['bt709', 'smpte170m', 'iec61966-2-1', 'linear', 'pq', 'hlg']


class VideoMatrixCoefficients(_StrEnum):
    """The matrix coefficients of a :obj:`webrtc.VideoColorSpace`, which convert between RGB and YUV.

    See :mdn:`VideoColorSpace/matrix`.
    """

    #: No conversion, because the samples are already RGB
    rgb = 'rgb'
    #: BT.709
    bt709 = 'bt709'
    #: BT.470 B/G
    bt470bg = 'bt470bg'
    #: SMPTE 170M
    smpte170m = 'smpte170m'
    #: BT.2020, non-constant luminance
    bt2020_ncl = 'bt2020-ncl'


#: The string values of :obj:`VideoMatrixCoefficients`, which parameters accept in place of its members
VideoMatrixCoefficientsValue = Literal['rgb', 'bt709', 'bt470bg', 'smpte170m', 'bt2020-ncl']


class AlphaOption(_StrEnum):
    """Whether a :obj:`webrtc.VideoFrame` created from another one keeps its alpha channel.

    See :mdn:`VideoFrame/VideoFrame`.
    """

    #: Keeps the alpha channel
    keep = 'keep'
    #: Drops the alpha channel and uses the matching format without alpha
    discard = 'discard'


#: The string values of :obj:`AlphaOption`, which parameters accept in place of its members
AlphaOptionValue = Literal['keep', 'discard']


class PredefinedColorSpace(_StrEnum):
    """The color space :meth:`webrtc.VideoFrame.copy_to` writes RGB pixels in. Only ``srgb`` is supported.

    See :mdn:`VideoFrame/copyTo`.
    """

    #: sRGB
    srgb = 'srgb'
    #: sRGB primaries with linear light
    srgb_linear = 'srgb-linear'
    #: Display P3
    display_p3 = 'display-p3'
    #: Display P3 primaries with linear light
    display_p3_linear = 'display-p3-linear'


#: The string values of :obj:`PredefinedColorSpace`, which parameters accept in place of its members
PredefinedColorSpaceValue = Literal['srgb', 'srgb-linear', 'display-p3', 'display-p3-linear']


class AudioSampleFormat(_StrEnum):
    """The type of the samples of an :obj:`webrtc.AudioData`, and whether channels are interleaved or planar.

    See :mdn:`AudioData/format`.
    """

    #: Unsigned 8-bit, interleaved
    u8 = 'u8'
    #: Signed 16-bit, interleaved
    s16 = 's16'
    #: Signed 32-bit, interleaved
    s32 = 's32'
    #: 32-bit float, interleaved
    f32 = 'f32'
    #: Unsigned 8-bit, a plane per channel
    u8_planar = 'u8-planar'
    #: Signed 16-bit, a plane per channel
    s16_planar = 's16-planar'
    #: Signed 32-bit, a plane per channel
    s32_planar = 's32-planar'
    #: 32-bit float, a plane per channel
    f32_planar = 'f32-planar'


#: The string values of :obj:`AudioSampleFormat`, which parameters accept in place of its members
AudioSampleFormatValue = Literal['u8', 's16', 's32', 'f32', 'u8-planar', 's16-planar', 's32-planar', 'f32-planar']


class ReadableStreamReaderMode(_StrEnum):
    """The type of reader :meth:`webrtc.ReadableStream.get_reader` returns. Its only member is rejected.

    See :mdn:`ReadableStream/getReader`.
    """

    #: A reader that fills a buffer of the caller. It needs a byte stream, and this library has none
    byob = 'byob'


#: The string values of :obj:`ReadableStreamReaderMode`, which parameters accept in place of its members
ReadableStreamReaderModeValue = Literal['byob']


class EncodedVideoChunkType(_StrEnum):
    """Whether an encoded video frame is a key frame.

    See :mdn:`RTCEncodedVideoFrame/type`.
    """

    #: A key frame, which decodes on its own
    key = 'key'
    #: A delta frame, which needs the frames before it
    delta = 'delta'


class RTCRtpScriptTransformType(_StrEnum):
    """What the worker of an :obj:`webrtc.RTCRtpScriptTransform` outputs.

    The value is accepted but has no effect. Frames are packetized as usual, because the native WebRTC engine has
    no SFrame packetization.
    """

    #: The worker outputs SFrame-encrypted frames
    sframe = 'sframe'


#: The string values of :obj:`RTCRtpScriptTransformType`, which parameters accept in place of its members
RTCRtpScriptTransformTypeValue = Literal['sframe']


class SFrameCipherSuite(_StrEnum):
    """An SFrame cipher suite of RFC 9605 or draft-barnes-sframe-iana-256.

    The CTR suites authenticate with a truncated HMAC tag, whose bit length ends the name. The GCM suites use a
    128-bit tag.
    """

    #: AES-128-CTR, HMAC-SHA-256, 80-bit tag
    AES_128_CTR_HMAC_SHA256_80 = 'AES_128_CTR_HMAC_SHA256_80'
    #: AES-128-CTR, HMAC-SHA-256, 64-bit tag
    AES_128_CTR_HMAC_SHA256_64 = 'AES_128_CTR_HMAC_SHA256_64'
    #: AES-128-CTR, HMAC-SHA-256, 32-bit tag
    AES_128_CTR_HMAC_SHA256_32 = 'AES_128_CTR_HMAC_SHA256_32'
    #: AES-128-GCM, SHA-256 key derivation, 128-bit tag
    AES_128_GCM_SHA256_128 = 'AES_128_GCM_SHA256_128'
    #: AES-256-GCM, SHA-512 key derivation, 128-bit tag
    AES_256_GCM_SHA512_128 = 'AES_256_GCM_SHA512_128'
    #: AES-256-CTR, HMAC-SHA-512, 80-bit tag
    AES_256_CTR_HMAC_SHA512_80 = 'AES_256_CTR_HMAC_SHA512_80'
    #: AES-256-CTR, HMAC-SHA-512, 64-bit tag
    AES_256_CTR_HMAC_SHA512_64 = 'AES_256_CTR_HMAC_SHA512_64'
    #: AES-256-CTR, HMAC-SHA-512, 32-bit tag
    AES_256_CTR_HMAC_SHA512_32 = 'AES_256_CTR_HMAC_SHA512_32'


#: The string values of :obj:`SFrameCipherSuite`, which parameters accept in place of its members
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

    #: Encrypts each frame before packetization
    per_frame = 'per-frame'
    #: Would encrypt each RTP packet, but isn't supported because the native WebRTC engine has no SFrame packetization
    per_packet = 'per-packet'


#: The string values of :obj:`SFrameType`, which parameters accept in place of its members
SFrameTypeValue = Literal['per-frame', 'per-packet']


class SFrameTransformErrorEventType(_StrEnum):
    """Why an SFrame decryptor dropped a frame."""

    #: The frame didn't authenticate with the key of its key id
    authentication = 'authentication'
    #: No key is set for the key id of the frame
    key_id = 'keyID'
    #: The frame isn't valid SFrame
    syntax = 'syntax'


#: The string values of :obj:`SFrameTransformErrorEventType`, which parameters accept in place of its members
SFrameTransformErrorEventTypeValue = Literal['authentication', 'keyID', 'syntax']
