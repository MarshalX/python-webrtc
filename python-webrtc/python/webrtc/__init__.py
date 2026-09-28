#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import wrtc

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
    RTCErrorDetailType,
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
from .interfaces.rtc_video_source import RTCVideoSource, RTCVideoFrame
from .interfaces.rtc_data_channel import RTCDataChannel, RTCDataChannelState, RTCPriorityType
from .interfaces.rtc_dtmf_sender import RTCDTMFSender

from .functions.get_user_media import getUserMedia, get_user_media

from .models.rtc_session_description_init import RTCSessionDescriptionInit
from .models.rtc_session_description import RTCSessionDescription
from .models.rtc_on_data_event import RTCOnDataEvent
from .models.rtp_parameters import (
    RTCDegradationPreference,
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

#: The former name of :obj:`RTCRtpEncodingParameters`
RtpEncodingParameters = RTCRtpEncodingParameters
from .models.rtp_transceiver_init import RtpTransceiverInit
from .models.rtc_stats import RTCStats, RTCStatsReport
from .models.rtp_source import RTCRtpContributingSource, RTCRtpSynchronizationSource
from .models.rtc_certificate import RTCCertificate, RTCDtlsFingerprint
from .models.rtc_configuration import (
    RTCConfiguration,
    RTCIceServer,
    RTCOAuthCredential,
    RTCIceTransportPolicy,
    RTCBundlePolicy,
    RTCRtcpMuxPolicy,
    RTCRtpHeaderEncryptionPolicy,
)
from .models.rtc_ice_candidate import (
    RTCIceCandidate,
    RTCIceCandidatePair,
    RTCIceParameters,
    RTCIceCandidateType,
    RTCIceProtocol,
    RTCIceTcpCandidateType,
    RTCIceServerTransportProtocol,
)

# enums
RTCPeerConnectionState = wrtc.RTCPeerConnectionState
RTCSignalingState = wrtc.RTCSignalingState
RTCIceConnectionState = wrtc.RTCIceConnectionState
RTCIceGatheringState = wrtc.RTCIceGatheringState
RTCSdpType = wrtc.RTCSdpType
MediaStreamTrackState = wrtc.MediaStreamTrackState
MediaStreamSourceState = wrtc.MediaStreamSourceState
TransceiverDirection = wrtc.TransceiverDirection
RTCIceComponent = wrtc.RTCIceComponent
RTCIceRole = wrtc.RTCIceRole
RTCIceTransportState = wrtc.RTCIceTransportState
CricketIceGatheringState = wrtc.CricketIceGatheringState
DtlsTransportState = wrtc.DtlsTransportState
SctpTransportState = wrtc.SctpTransportState
MediaType = wrtc.MediaType

__all__ = [
    # exceptions
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
    # enums
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
    # base
    'WebRTCObject',
    'EventTarget',
    # events
    'Event',
    'RTCPeerConnectionIceEvent',
    'RTCPeerConnectionIceErrorEvent',
    'RTCTrackEvent',
    'RTCErrorEvent',
    'MessageEvent',
    'RTCDataChannelEvent',
    'MediaStreamTrackEvent',
    'RTCDTMFToneChangeEvent',
    'RTCDTMFSender',
    # interfaces
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
    'RTCVideoFrame',
    'RTCDataChannel',
    # functions
    'getUserMedia',
    'get_user_media',
    # models
    'RTCSessionDescriptionInit',
    'RTCSessionDescription',
    'RTCOnDataEvent',
    'RtpEncodingParameters',
    'RTCDegradationPreference',
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
