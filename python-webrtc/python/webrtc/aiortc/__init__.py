#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""aiortc 1.15's API over wrtc: import ``webrtc.aiortc`` instead of ``aiortc``, see https://aiortc.readthedocs.io."""

from __future__ import annotations

from webrtc.aiortc._alias import install_alias as install_alias
from webrtc.aiortc.events import RTCTrackEvent as RTCTrackEvent
from webrtc.aiortc.exceptions import InternalError, InvalidAccessError, InvalidStateError, OperationError
from webrtc.aiortc.mediastreams import AudioStreamTrack, MediaStreamError, MediaStreamTrack, VideoStreamTrack
from webrtc.aiortc.rtcconfiguration import RTCBundlePolicy, RTCConfiguration, RTCIceServer
from webrtc.aiortc.rtcdatachannel import RTCDataChannel, RTCDataChannelParameters
from webrtc.aiortc.rtcdtlstransport import RTCCertificate, RTCDtlsFingerprint, RTCDtlsParameters, RTCDtlsTransport
from webrtc.aiortc.rtcicetransport import RTCIceCandidate, RTCIceGatherer, RTCIceParameters, RTCIceTransport
from webrtc.aiortc.rtcpeerconnection import RTCPeerConnection
from webrtc.aiortc.rtcrtpparameters import (
    RTCRtcpParameters,
    RTCRtpCapabilities,
    RTCRtpCodecCapability,
    RTCRtpCodecParameters,
    RTCRtpHeaderExtensionCapability,
    RTCRtpHeaderExtensionParameters,
    RTCRtpParameters,
)
from webrtc.aiortc.rtcrtpreceiver import (
    RemoteStreamTrack as RemoteStreamTrack,
    RTCRtpContributingSource,
    RTCRtpReceiver,
    RTCRtpSynchronizationSource,
)
from webrtc.aiortc.rtcrtpsender import RTCRtpSender
from webrtc.aiortc.rtcrtptransceiver import RTCRtpTransceiver
from webrtc.aiortc.rtcsctptransport import RTCSctpCapabilities, RTCSctpTransport
from webrtc.aiortc.rtcsessiondescription import RTCSessionDescription
from webrtc.aiortc.stats import (
    RTCInboundRtpStreamStats,
    RTCOutboundRtpStreamStats,
    RTCRemoteInboundRtpStreamStats,
    RTCRemoteOutboundRtpStreamStats,
    RTCStatsReport,
    RTCTransportStats,
)

__version__ = '1.15.0'

__all__ = [
    'AudioStreamTrack',
    'InternalError',
    'InvalidAccessError',
    'InvalidStateError',
    'MediaStreamError',
    'MediaStreamTrack',
    'OperationError',
    'RTCBundlePolicy',
    'RTCCertificate',
    'RTCConfiguration',
    'RTCDataChannel',
    'RTCDataChannelParameters',
    'RTCDtlsFingerprint',
    'RTCDtlsParameters',
    'RTCDtlsTransport',
    'RTCIceCandidate',
    'RTCIceGatherer',
    'RTCIceParameters',
    'RTCIceServer',
    'RTCIceTransport',
    'RTCInboundRtpStreamStats',
    'RTCOutboundRtpStreamStats',
    'RTCPeerConnection',
    'RTCRemoteInboundRtpStreamStats',
    'RTCRemoteOutboundRtpStreamStats',
    'RTCRtcpParameters',
    'RTCRtpCapabilities',
    'RTCRtpCodecCapability',
    'RTCRtpCodecParameters',
    'RTCRtpContributingSource',
    'RTCRtpHeaderExtensionCapability',
    'RTCRtpHeaderExtensionParameters',
    'RTCRtpParameters',
    'RTCRtpReceiver',
    'RTCRtpSender',
    'RTCRtpSynchronizationSource',
    'RTCRtpTransceiver',
    'RTCSctpCapabilities',
    'RTCSctpTransport',
    'RTCSessionDescription',
    'RTCStatsReport',
    'RTCTransportStats',
    'VideoStreamTrack',
]
