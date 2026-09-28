#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import wrtc  # noqa: F401 (the modules import it from the package)

from .enums import (
    RTCPeerConnectionState,
    RTCSignalingState,
    RTCIceConnectionState,
    RTCIceGatheringState,
    RTCSdpType,
    MediaStreamTrackState,
    MediaStreamSourceState,
    TransceiverDirection,
    RTCIceComponent,
    RTCIceRole,
    RTCIceTransportState,
    CricketIceGatheringState,
    DtlsTransportState,
    SctpTransportState,
    MediaType,
    RTCDataChannelState,
    RTCPriorityType,
    RTCDegradationPreference,
    RTCIceTransportPolicy,
    RTCBundlePolicy,
    RTCRtcpMuxPolicy,
    RTCRtpHeaderEncryptionPolicy,
    RTCIceCandidateType,
    RTCIceProtocol,
    RTCIceTcpCandidateType,
    RTCIceServerTransportProtocol,
    RTCErrorDetailType,
)
from .base import WebRTCObject
from .exceptions import (
    PythonWebRTCExceptionBase,
    PythonWebRTCException,
    SdpParseException,
    RTCException,
    InvalidStateError,
    InvalidAccessError,
    InvalidModificationError,
    OperationError,
    NotSupportedError,
    NetworkError,
    InvalidSyntaxError,
    InvalidRangeError,
    InvalidCharacterError,
    RTCError,
)
from .utils.events import EventTarget
from .models.events import (
    Event,
    RTCPeerConnectionIceEvent,
    RTCPeerConnectionIceErrorEvent,
    RTCTrackEvent,
    RTCErrorEvent,
    MessageEvent,
    RTCDataChannelEvent,
    MediaStreamTrackEvent,
    RTCDTMFToneChangeEvent,
)

# the order matters: modules import each other through the package namespace
from .models.rtc_session_description_init import RTCSessionDescriptionInit
from .models.rtc_session_description import RTCSessionDescription
from .models.rtc_on_data_event import RTCOnDataEvent
from .models.rtc_video_frame import RTCVideoFrame
from .models.rtp_parameters import (
    RTCRtpCodec,
    RTCRtpCodecParameters,
    RTCRtpHeaderExtensionParameters,
    RTCRtcpParameters,
    RTCRtpEncodingParameters,
    RTCRtpReceiveParameters,
    RTCRtpSendParameters,
    RTCRtpHeaderExtensionCapability,
    RTCRtpCapabilities,
)
from .models.rtp_transceiver_init import RtpTransceiverInit
from .models.rtc_stats import RTCStats, RTCStatsReport
from .models.rtp_source import RTCRtpContributingSource, RTCRtpSynchronizationSource
from .models.rtc_certificate import RTCCertificate, RTCDtlsFingerprint
from .models.rtc_configuration import (
    RTCConfiguration,
    RTCIceServer,
    RTCOAuthCredential,
)
from .models.rtc_ice_candidate import (
    RTCIceCandidate,
    RTCIceCandidatePair,
    RTCIceParameters,
)

from .interfaces.rtc_peer_connection import RTCPeerConnection
from .interfaces.media_stream_track import MediaStreamTrack
from .interfaces.media_stream import MediaStream
from .interfaces.rtc_rtp_sender import RTCRtpSender
from .interfaces.rtc_rtp_receiver import RTCRtpReceiver
from .interfaces.rtc_rtp_transceiver import RTCRtpTransceiver
from .interfaces.rtc_ice_transport import RTCIceTransport
from .interfaces.rtc_dtls_transport import RTCDtlsTransport
from .interfaces.rtc_sctp_transport import RTCSctpTransport
from .interfaces.rtc_audio_source import RTCAudioSource
from .interfaces.rtc_video_source import RTCVideoSource
from .interfaces.rtc_data_channel import RTCDataChannel
from .interfaces.rtc_dtmf_sender import RTCDTMFSender

from .functions.get_user_media import getUserMedia, get_user_media

#: Alias for :obj:`RTCRtpEncodingParameters`
RtpEncodingParameters = RTCRtpEncodingParameters

__all__ = [
    'PythonWebRTCExceptionBase',
    'PythonWebRTCException',
    'RTCException',
    'SdpParseException',
    'InvalidStateError',
    'InvalidAccessError',
    'InvalidModificationError',
    'OperationError',
    'NotSupportedError',
    'NetworkError',
    'InvalidSyntaxError',
    'InvalidRangeError',
    'InvalidCharacterError',
    'RTCError',
    'RTCPeerConnectionState',
    'RTCSignalingState',
    'RTCIceConnectionState',
    'RTCIceGatheringState',
    'RTCSdpType',
    'MediaStreamTrackState',
    'MediaStreamSourceState',
    'TransceiverDirection',
    'RTCIceComponent',
    'RTCIceRole',
    'RTCIceTransportState',
    'CricketIceGatheringState',
    'DtlsTransportState',
    'SctpTransportState',
    'MediaType',
    'RTCErrorDetailType',
    'RTCIceCandidateType',
    'RTCIceProtocol',
    'RTCIceTcpCandidateType',
    'RTCIceServerTransportProtocol',
    'RTCIceTransportPolicy',
    'RTCBundlePolicy',
    'RTCRtcpMuxPolicy',
    'RTCRtpHeaderEncryptionPolicy',
    'RTCDataChannelState',
    'RTCPriorityType',
    'RTCDegradationPreference',
    'WebRTCObject',
    'EventTarget',
    'Event',
    'RTCPeerConnectionIceEvent',
    'RTCPeerConnectionIceErrorEvent',
    'RTCTrackEvent',
    'RTCErrorEvent',
    'MessageEvent',
    'RTCDataChannelEvent',
    'MediaStreamTrackEvent',
    'RTCDTMFToneChangeEvent',
    'RTCPeerConnection',
    'MediaStreamTrack',
    'MediaStream',
    'RTCRtpSender',
    'RTCRtpReceiver',
    'RTCRtpTransceiver',
    'RTCIceTransport',
    'RTCDtlsTransport',
    'RTCSctpTransport',
    'RTCAudioSource',
    'RTCVideoSource',
    'RTCDataChannel',
    'RTCDTMFSender',
    'getUserMedia',
    'get_user_media',
    'RTCSessionDescriptionInit',
    'RTCSessionDescription',
    'RTCOnDataEvent',
    'RTCVideoFrame',
    'RtpEncodingParameters',
    'RTCRtpCodec',
    'RTCRtpCodecParameters',
    'RTCRtpHeaderExtensionParameters',
    'RTCRtcpParameters',
    'RTCRtpEncodingParameters',
    'RTCRtpReceiveParameters',
    'RTCRtpSendParameters',
    'RTCRtpHeaderExtensionCapability',
    'RTCRtpCapabilities',
    'RtpTransceiverInit',
    'RTCIceCandidate',
    'RTCIceCandidatePair',
    'RTCIceParameters',
    'RTCStats',
    'RTCRtpContributingSource',
    'RTCRtpSynchronizationSource',
    'RTCStatsReport',
    'RTCCertificate',
    'RTCDtlsFingerprint',
    'RTCConfiguration',
    'RTCIceServer',
    'RTCOAuthCredential',
]
