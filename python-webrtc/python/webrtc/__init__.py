#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Python bindings to WebRTC, with the API of the browsers."""

from __future__ import annotations

import wrtc as wrtc  # re-exported, the modules import it from the package

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
    BinaryType,
    VideoPixelFormat,
    VideoColorPrimaries,
    VideoTransferCharacteristics,
    VideoMatrixCoefficients,
    AlphaOption,
    AudioSampleFormat,
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
    OverconstrainedError,
    RTCError,
    RTCErrorInit,
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
from .models.rtc_session_description_init import RTCSessionDescriptionInit, RTCLocalSessionDescriptionInit
from .models.rtc_session_description import RTCSessionDescription
from .models.media_track_constraints import (
    ULongRange,
    DoubleRange,
    ConstrainULongRange,
    ConstrainDoubleRange,
    ConstrainBooleanParameters,
    ConstrainDOMStringParameters,
    ConstrainBooleanOrDOMStringParameters,
    MediaTrackSettings,
    MediaTrackCapabilities,
    MediaTrackConstraintSet,
    MediaTrackConstraints,
)
from .models.blob import Blob
from .models.video_frame import (
    DOMRectReadOnly,
    DOMRectInit,
    PlaneLayout,
    VideoColorSpace,
    VideoColorSpaceInit,
    VideoFrameMetadata,
    VideoFrameBufferInit,
    VideoFrameInit,
    VideoFrameCopyToOptions,
    VideoFrame,
)
from .models.audio_data import AudioDataInit, AudioDataCopyToOptions, AudioData
from .streams import (
    ReadableStream,
    ReadableStreamDefaultReader,
    ReadableStreamDefaultController,
    ReadableStreamReadResult,
    WritableStream,
    WritableStreamDefaultWriter,
    WritableStreamDefaultController,
    TransformStream,
    TransformStreamDefaultController,
)
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
from .models.rtc_rtp_transceiver_init import RTCRtpTransceiverInit
from .models.rtc_stats import RTCStats, RTCStatsReport
from .models.rtp_source import RTCRtpContributingSource, RTCRtpSynchronizationSource
from .models.rtc_certificate import (
    Algorithm,
    EcKeyGenParams,
    RsaHashedKeyGenParams,
    RTCCertificate,
    RTCDtlsFingerprint,
)
from .models.rtc_configuration import (
    RTCConfiguration,
    RTCIceServer,
    RTCOAuthCredential,
)
from .models.rtc_ice_candidate import (
    RTCIceCandidate,
    RTCIceCandidateInit,
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
from .interfaces.rtc_data_channel import RTCDataChannel, RTCDataChannelInit
from .interfaces.media_stream_track_processor import MediaStreamTrackProcessorInit, MediaStreamTrackProcessor
from .interfaces.track_generator import (
    VideoTrackGenerator,
    MediaStreamTrackGeneratorInit,
    MediaStreamTrackGenerator,
)
from .interfaces.rtc_dtmf_sender import RTCDTMFSender

from .functions.get_user_media import getUserMedia, get_user_media


__all__ = [
    'Algorithm',
    'AlphaOption',
    'AudioData',
    'AudioDataCopyToOptions',
    'AudioDataInit',
    'AudioSampleFormat',
    'BinaryType',
    'Blob',
    'ConstrainBooleanOrDOMStringParameters',
    'ConstrainBooleanParameters',
    'ConstrainDOMStringParameters',
    'ConstrainDoubleRange',
    'ConstrainULongRange',
    'CricketIceGatheringState',
    'DOMRectInit',
    'DOMRectReadOnly',
    'DoubleRange',
    'DtlsTransportState',
    'EcKeyGenParams',
    'Event',
    'EventTarget',
    'InvalidAccessError',
    'InvalidCharacterError',
    'InvalidModificationError',
    'InvalidRangeError',
    'InvalidStateError',
    'InvalidSyntaxError',
    'MediaStream',
    'MediaStreamSourceState',
    'MediaStreamTrack',
    'MediaStreamTrackEvent',
    'MediaStreamTrackGenerator',
    'MediaStreamTrackGeneratorInit',
    'MediaStreamTrackProcessor',
    'MediaStreamTrackProcessorInit',
    'MediaStreamTrackState',
    'MediaTrackCapabilities',
    'MediaTrackConstraintSet',
    'MediaTrackConstraints',
    'MediaTrackSettings',
    'MediaType',
    'MessageEvent',
    'NetworkError',
    'NotSupportedError',
    'OperationError',
    'OverconstrainedError',
    'PlaneLayout',
    'PythonWebRTCException',
    'PythonWebRTCExceptionBase',
    'RTCBundlePolicy',
    'RTCCertificate',
    'RTCConfiguration',
    'RTCDTMFSender',
    'RTCDTMFToneChangeEvent',
    'RTCDataChannel',
    'RTCDataChannelEvent',
    'RTCDataChannelInit',
    'RTCDataChannelState',
    'RTCDegradationPreference',
    'RTCDtlsFingerprint',
    'RTCDtlsTransport',
    'RTCError',
    'RTCErrorDetailType',
    'RTCErrorEvent',
    'RTCErrorInit',
    'RTCException',
    'RTCIceCandidate',
    'RTCIceCandidateInit',
    'RTCIceCandidatePair',
    'RTCIceCandidateType',
    'RTCIceComponent',
    'RTCIceConnectionState',
    'RTCIceGatheringState',
    'RTCIceParameters',
    'RTCIceProtocol',
    'RTCIceRole',
    'RTCIceServer',
    'RTCIceServerTransportProtocol',
    'RTCIceTcpCandidateType',
    'RTCIceTransport',
    'RTCIceTransportPolicy',
    'RTCIceTransportState',
    'RTCLocalSessionDescriptionInit',
    'RTCOAuthCredential',
    'RTCPeerConnection',
    'RTCPeerConnectionIceErrorEvent',
    'RTCPeerConnectionIceEvent',
    'RTCPeerConnectionState',
    'RTCPriorityType',
    'RTCRtcpMuxPolicy',
    'RTCRtcpParameters',
    'RTCRtpCapabilities',
    'RTCRtpCodec',
    'RTCRtpCodecParameters',
    'RTCRtpContributingSource',
    'RTCRtpEncodingParameters',
    'RTCRtpHeaderEncryptionPolicy',
    'RTCRtpHeaderExtensionCapability',
    'RTCRtpHeaderExtensionParameters',
    'RTCRtpReceiveParameters',
    'RTCRtpReceiver',
    'RTCRtpSendParameters',
    'RTCRtpSender',
    'RTCRtpSynchronizationSource',
    'RTCRtpTransceiver',
    'RTCRtpTransceiverInit',
    'RTCSctpTransport',
    'RTCSdpType',
    'RTCSessionDescription',
    'RTCSessionDescriptionInit',
    'RTCSignalingState',
    'RTCStats',
    'RTCStatsReport',
    'RTCTrackEvent',
    'ReadableStream',
    'ReadableStreamDefaultController',
    'ReadableStreamDefaultReader',
    'ReadableStreamReadResult',
    'RsaHashedKeyGenParams',
    'SctpTransportState',
    'SdpParseException',
    'TransceiverDirection',
    'TransformStream',
    'TransformStreamDefaultController',
    'ULongRange',
    'VideoColorPrimaries',
    'VideoColorSpace',
    'VideoColorSpaceInit',
    'VideoFrame',
    'VideoFrameBufferInit',
    'VideoFrameCopyToOptions',
    'VideoFrameInit',
    'VideoFrameMetadata',
    'VideoMatrixCoefficients',
    'VideoPixelFormat',
    'VideoTrackGenerator',
    'VideoTransferCharacteristics',
    'WebRTCObject',
    'WritableStream',
    'WritableStreamDefaultController',
    'WritableStreamDefaultWriter',
    'getUserMedia',
    'get_user_media',
]
