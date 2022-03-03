#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import wrtc

from .base import WebRTCObject

from .interfaces.rtc_peer_connection import RTCPeerConnection
from .interfaces.media_stream_track import MediaStreamTrack
from .interfaces.media_stream import MediaStream
from .interfaces.rtc_rtp_sender import RTCRtpSender
from .interfaces.rtc_rtp_receiver import RTCRtpReceiver
from .interfaces.rtc_rtp_transceiver import RTCRtpTransceiver
from .interfaces.rtc_ice_transport import RTCIceTransport
from .interfaces.rtc_dtls_transport import RTCDtlsTransport
from .interfaces.rtc_audio_source import RTCAudioSource

from .functions.get_user_media import getUserMedia, get_user_media

from .models.rtc_session_description_init import RTCSessionDescriptionInit
from .models.rtc_session_description import RTCSessionDescription
from .models.rtc_on_data_event import RTCOnDataEvent
from .models.rtp_encoding_parameters import RtpEncodingParameters
from .models.rtp_transceiver_init import RtpTransceiverInit

# exception
PythonWebRTCExceptionBase = wrtc.PythonWebRTCExceptionBase
PythonWebRTCException = wrtc.PythonWebRTCException
RTCException = wrtc.RTCException
SdpParseException = wrtc.SdpParseException

# enums
RTCPeerConnectionState = wrtc.RTCPeerConnectionState
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
MediaType = wrtc.MediaType

__all__ = [
    # exceptions
    'PythonWebRTCExceptionBase',
    'PythonWebRTCException',
    'RTCException',
    'SdpParseException',
    # enums
    'RTCPeerConnectionState',
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
    'MediaType',
    # base
    'WebRTCObject',
    # interfaces
    'RTCPeerConnection',
    'MediaStreamTrack',
    'MediaStream',
    'RTCRtpSender',
    'RTCRtpReceiver',
    'RTCRtpTransceiver',
    'RTCIceTransport',
    'RTCDtlsTransport',
    'RTCAudioSource',
    # functions
    'getUserMedia',
    'get_user_media',
    # models
    'RTCSessionDescriptionInit',
    'RTCSessionDescription',
    'RTCOnDataEvent',
    'RtpEncodingParameters',
    'RtpTransceiverInit',
]
