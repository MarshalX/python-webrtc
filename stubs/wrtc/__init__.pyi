from __future__ import annotations
import collections.abc
import typing
__all__: list[str] = ['CallbackPythonWebRTCException', 'CricketIceGatheringState', 'DtlsTransportState', 'MediaStream', 'MediaStreamSourceState', 'MediaStreamTrack', 'MediaStreamTrackState', 'MediaType', 'PeerConnectionFactory', 'PythonWebRTCException', 'PythonWebRTCExceptionBase', 'RTCAudioSource', 'RTCCallbackException', 'RTCDtlsTransport', 'RTCException', 'RTCIceComponent', 'RTCIceConnectionState', 'RTCIceGatheringState', 'RTCIceRole', 'RTCIceTransport', 'RTCIceTransportState', 'RTCOnDataEvent', 'RTCP', 'RTCPeerConnection', 'RTCPeerConnectionState', 'RTCRtpReceiver', 'RTCRtpSender', 'RTCRtpTransceiver', 'RTCSctpTransport', 'RTCSdpType', 'RTCSessionDescription', 'RTCSessionDescriptionInit', 'RTCSignalingState', 'RTP', 'RtpEncodingParameters', 'RtpTransceiverInit', 'SctpTransportState', 'SdpParseException', 'TransceiverDirection', 'answer', 'audio', 'checking', 'closed', 'complete', 'completed', 'connected', 'connecting', 'controlled', 'controlling', 'data', 'disconnected', 'ended', 'failed', 'gathering', 'getUserMedia', 'have_local_offer', 'have_local_pranswer', 'have_remote_offer', 'have_remote_pranswer', 'inactive', 'initializing', 'live', 'max', 'muted', 'new', 'offer', 'ping', 'pranswer', 'recvonly', 'rollback', 'sendonly', 'sendrecv', 'stable', 'stopped', 'unknown', 'unsupported', 'video']
class CallbackPythonWebRTCException:
    def what(self) -> str:
        ...
class RTCCallbackException:
    def what(self) -> str:
        ...
class PythonWebRTCExceptionBase(Exception):
    pass
class PythonWebRTCException(PythonWebRTCExceptionBase):
    pass
class RTCException(PythonWebRTCExceptionBase):
    pass
class SdpParseException(PythonWebRTCExceptionBase):
    pass
class RTCPeerConnectionState:
    """
    Members:
    
      new
    
      connecting
    
      connected
    
      disconnected
    
      failed
    
      closed
    """
    __members__: typing.ClassVar[dict[str, RTCPeerConnectionState]]
    closed: typing.ClassVar[RTCPeerConnectionState]
    connected: typing.ClassVar[RTCPeerConnectionState]
    connecting: typing.ClassVar[RTCPeerConnectionState]
    disconnected: typing.ClassVar[RTCPeerConnectionState]
    failed: typing.ClassVar[RTCPeerConnectionState]
    new: typing.ClassVar[RTCPeerConnectionState]
    @typing.overload
    def __eq__(self, other: RTCPeerConnectionState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCPeerConnectionState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCSignalingState:
    """
    Members:
    
      stable
    
      have_local_offer
    
      have_local_pranswer
    
      have_remote_offer
    
      have_remote_pranswer
    
      closed
    """
    __members__: typing.ClassVar[dict[str, RTCSignalingState]]
    closed: typing.ClassVar[RTCSignalingState]
    have_local_offer: typing.ClassVar[RTCSignalingState]
    have_local_pranswer: typing.ClassVar[RTCSignalingState]
    have_remote_offer: typing.ClassVar[RTCSignalingState]
    have_remote_pranswer: typing.ClassVar[RTCSignalingState]
    stable: typing.ClassVar[RTCSignalingState]
    @typing.overload
    def __eq__(self, other: RTCSignalingState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCSignalingState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCIceConnectionState:
    """
    Members:
    
      new
    
      checking
    
      connected
    
      completed
    
      failed
    
      disconnected
    
      closed
    
      max
    """
    __members__: typing.ClassVar[dict[str, RTCIceConnectionState]]
    checking: typing.ClassVar[RTCIceConnectionState]
    closed: typing.ClassVar[RTCIceConnectionState]
    completed: typing.ClassVar[RTCIceConnectionState]
    connected: typing.ClassVar[RTCIceConnectionState]
    disconnected: typing.ClassVar[RTCIceConnectionState]
    failed: typing.ClassVar[RTCIceConnectionState]
    max: typing.ClassVar[RTCIceConnectionState]
    new: typing.ClassVar[RTCIceConnectionState]
    @typing.overload
    def __eq__(self, other: RTCIceConnectionState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCIceConnectionState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCIceGatheringState:
    """
    Members:
    
      new
    
      gathering
    
      complete
    """
    __members__: typing.ClassVar[dict[str, RTCIceGatheringState]]
    complete: typing.ClassVar[RTCIceGatheringState]
    gathering: typing.ClassVar[RTCIceGatheringState]
    new: typing.ClassVar[RTCIceGatheringState]
    @typing.overload
    def __eq__(self, other: RTCIceGatheringState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCIceGatheringState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCSdpType:
    """
    Members:
    
      offer
    
      pranswer
    
      answer
    
      rollback
    """
    __members__: typing.ClassVar[dict[str, RTCSdpType]]
    answer: typing.ClassVar[RTCSdpType]
    offer: typing.ClassVar[RTCSdpType]
    pranswer: typing.ClassVar[RTCSdpType]
    rollback: typing.ClassVar[RTCSdpType]
    @typing.overload
    def __eq__(self, other: RTCSdpType) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCSdpType) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class MediaStreamTrackState:
    """
    Members:
    
      live
    
      ended
    """
    __members__: typing.ClassVar[dict[str, MediaStreamTrackState]]
    ended: typing.ClassVar[MediaStreamTrackState]
    live: typing.ClassVar[MediaStreamTrackState]
    @typing.overload
    def __eq__(self, other: MediaStreamTrackState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: MediaStreamTrackState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class MediaStreamSourceState:
    """
    Members:
    
      initializing
    
      live
    
      ended
    
      muted
    """
    __members__: typing.ClassVar[dict[str, MediaStreamSourceState]]
    ended: typing.ClassVar[MediaStreamSourceState]
    initializing: typing.ClassVar[MediaStreamSourceState]
    live: typing.ClassVar[MediaStreamSourceState]
    muted: typing.ClassVar[MediaStreamSourceState]
    @typing.overload
    def __eq__(self, other: MediaStreamSourceState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: MediaStreamSourceState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class MediaType:
    """
    Members:
    
      audio
    
      video
    
      data
    
      unsupported
    """
    __members__: typing.ClassVar[dict[str, MediaType]]
    audio: typing.ClassVar[MediaType]
    data: typing.ClassVar[MediaType]
    unsupported: typing.ClassVar[MediaType]
    video: typing.ClassVar[MediaType]
    @typing.overload
    def __eq__(self, other: MediaType) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: MediaType) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class TransceiverDirection:
    """
    Members:
    
      sendrecv
    
      sendonly
    
      recvonly
    
      inactive
    
      stopped
    """
    __members__: typing.ClassVar[dict[str, TransceiverDirection]]
    inactive: typing.ClassVar[TransceiverDirection]
    recvonly: typing.ClassVar[TransceiverDirection]
    sendonly: typing.ClassVar[TransceiverDirection]
    sendrecv: typing.ClassVar[TransceiverDirection]
    stopped: typing.ClassVar[TransceiverDirection]
    @typing.overload
    def __eq__(self, other: TransceiverDirection) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: TransceiverDirection) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class CricketIceGatheringState:
    """
    Members:
    
      new
    
      gathering
    
      complete
    """
    __members__: typing.ClassVar[dict[str, CricketIceGatheringState]]
    complete: typing.ClassVar[CricketIceGatheringState]
    gathering: typing.ClassVar[CricketIceGatheringState]
    new: typing.ClassVar[CricketIceGatheringState]
    @typing.overload
    def __eq__(self, other: CricketIceGatheringState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: CricketIceGatheringState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCIceRole:
    """
    Members:
    
      controlling
    
      controlled
    
      unknown
    """
    __members__: typing.ClassVar[dict[str, RTCIceRole]]
    controlled: typing.ClassVar[RTCIceRole]
    controlling: typing.ClassVar[RTCIceRole]
    unknown: typing.ClassVar[RTCIceRole]
    @typing.overload
    def __eq__(self, other: RTCIceRole) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCIceRole) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCIceTransportState:
    """
    Members:
    
      new
    
      checking
    
      connected
    
      completed
    
      disconnected
    
      failed
    
      closed
    """
    __members__: typing.ClassVar[dict[str, RTCIceTransportState]]
    checking: typing.ClassVar[RTCIceTransportState]
    closed: typing.ClassVar[RTCIceTransportState]
    completed: typing.ClassVar[RTCIceTransportState]
    connected: typing.ClassVar[RTCIceTransportState]
    disconnected: typing.ClassVar[RTCIceTransportState]
    failed: typing.ClassVar[RTCIceTransportState]
    new: typing.ClassVar[RTCIceTransportState]
    @typing.overload
    def __eq__(self, other: RTCIceTransportState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCIceTransportState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class DtlsTransportState:
    """
    Members:
    
      new
    
      connecting
    
      connected
    
      closed
    
      failed
    """
    __members__: typing.ClassVar[dict[str, DtlsTransportState]]
    closed: typing.ClassVar[DtlsTransportState]
    connected: typing.ClassVar[DtlsTransportState]
    connecting: typing.ClassVar[DtlsTransportState]
    failed: typing.ClassVar[DtlsTransportState]
    new: typing.ClassVar[DtlsTransportState]
    @typing.overload
    def __eq__(self, other: DtlsTransportState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: DtlsTransportState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class SctpTransportState:
    """
    Members:
    
      new
    
      connecting
    
      connected
    
      closed
    """
    __members__: typing.ClassVar[dict[str, SctpTransportState]]
    closed: typing.ClassVar[SctpTransportState]
    connected: typing.ClassVar[SctpTransportState]
    connecting: typing.ClassVar[SctpTransportState]
    new: typing.ClassVar[SctpTransportState]
    @typing.overload
    def __eq__(self, other: SctpTransportState) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: SctpTransportState) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCIceComponent:
    """
    Members:
    
      RTP
    
      RTCP
    """
    RTCP: typing.ClassVar[RTCIceComponent]
    RTP: typing.ClassVar[RTCIceComponent]
    __members__: typing.ClassVar[dict[str, RTCIceComponent]]
    @typing.overload
    def __eq__(self, other: RTCIceComponent) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RTCIceComponent) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RTCSessionDescriptionInit:
    sdp: str
    type: RTCSdpType
    def __init__(self, arg0: RTCSdpType, arg1: str) -> None:
        ...
class RTCSessionDescription:
    def __init__(self, arg0: RTCSessionDescriptionInit) -> None:
        ...
    @property
    def sdp(self) -> str:
        ...
    @property
    def type(self) -> RTCSdpType:
        ...
class RTCOnDataEvent:
    audioData: bytes
    def __init__(self, arg0: str, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def bitsPerSample(self) -> int:
        ...
    @bitsPerSample.setter
    def bitsPerSample(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def channelCount(self) -> int:
        ...
    @channelCount.setter
    def channelCount(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def numberOfFrames(self) -> int:
        ...
    @numberOfFrames.setter
    def numberOfFrames(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def sampleRate(self) -> int:
        ...
    @sampleRate.setter
    def sampleRate(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class RtpTransceiverInit:
    direction: TransceiverDirection
    def __init__(self) -> None:
        ...
    @property
    def sendEncodings(self) -> list[...]:
        ...
    @sendEncodings.setter
    def sendEncodings(self, arg0: collections.abc.Sequence[...]) -> None:
        ...
    @property
    def streamIds(self) -> list[str]:
        ...
    @streamIds.setter
    def streamIds(self, arg0: collections.abc.Sequence[str]) -> None:
        ...
class RtpEncodingParameters:
    active: bool
    rid: str
    def __init__(self) -> None:
        ...
    @property
    def maxBitrate(self) -> int | None:
        ...
    @maxBitrate.setter
    def maxBitrate(self, arg0: typing.SupportsInt | typing.SupportsIndex | None) -> None:
        ...
    @property
    def maxFramerate(self) -> float | None:
        ...
    @maxFramerate.setter
    def maxFramerate(self, arg0: typing.SupportsFloat | typing.SupportsIndex | None) -> None:
        ...
    @property
    def scaleResolutionDownBy(self) -> float | None:
        ...
    @scaleResolutionDownBy.setter
    def scaleResolutionDownBy(self, arg0: typing.SupportsFloat | typing.SupportsIndex | None) -> None:
        ...
    @property
    def ssrc(self) -> int | None:
        ...
    @ssrc.setter
    def ssrc(self, arg0: typing.SupportsInt | typing.SupportsIndex | None) -> None:
        ...
class PeerConnectionFactory:
    @staticmethod
    def dispose() -> None:
        ...
    @staticmethod
    def getOrCreateDefault() -> PeerConnectionFactory:
        ...
    @staticmethod
    def release() -> None:
        ...
    def __init__(self) -> None:
        ...
class MediaStreamTrack:
    enabled: bool
    def clone(self) -> MediaStreamTrack:
        ...
    def stop(self) -> None:
        ...
    @property
    def id(self) -> str:
        ...
    @property
    def kind(self) -> MediaType:
        ...
    @property
    def muted(self) -> bool:
        ...
    @property
    def readyState(self) -> MediaStreamTrackState:
        ...
class MediaStream:
    def addTrack(self, arg0: MediaStreamTrack) -> None:
        ...
    def clone(self) -> MediaStream:
        ...
    def getAudioTracks(self) -> list[MediaStreamTrack]:
        ...
    def getTrackById(self, arg0: str) -> MediaStreamTrack | None:
        ...
    def getTracks(self) -> list[MediaStreamTrack]:
        ...
    def getVideoTracks(self) -> list[MediaStreamTrack]:
        ...
    def removeTrack(self, arg0: MediaStreamTrack) -> None:
        ...
    @property
    def active(self) -> bool:
        ...
    @property
    def id(self) -> str:
        ...
class RTCIceTransport:
    @property
    def component(self) -> RTCIceComponent:
        ...
    @property
    def gatheringState(self) -> CricketIceGatheringState:
        ...
    @property
    def role(self) -> RTCIceRole:
        ...
    @property
    def state(self) -> RTCIceTransportState:
        ...
class RTCDtlsTransport:
    @property
    def iceTransport(self) -> RTCIceTransport:
        ...
    @property
    def state(self) -> DtlsTransportState:
        ...
class RTCSctpTransport:
    @property
    def maxChannels(self) -> int | None:
        ...
    @property
    def maxMessageSize(self) -> float | None:
        ...
    @property
    def state(self) -> SctpTransportState:
        ...
    @property
    def transport(self) -> RTCDtlsTransport:
        ...
class RTCRtpSender:
    @property
    def track(self) -> MediaStreamTrack | None:
        ...
    @property
    def transport(self) -> RTCDtlsTransport | None:
        ...
class RTCRtpReceiver:
    @property
    def track(self) -> MediaStreamTrack:
        ...
    @property
    def transport(self) -> RTCDtlsTransport | None:
        ...
class RTCRtpTransceiver:
    direction: TransceiverDirection
    def stop(self) -> None:
        ...
    @property
    def currentDirection(self) -> TransceiverDirection | None:
        ...
    @property
    def mid(self) -> str | None:
        ...
    @property
    def receiver(self) -> RTCRtpReceiver:
        ...
    @property
    def sender(self) -> RTCRtpSender:
        ...
    @property
    def stopped(self) -> bool:
        ...
class RTCPeerConnection:
    def __init__(self) -> None:
        ...
    @typing.overload
    def addTrack(self, arg0: MediaStreamTrack, arg1: MediaStream | None) -> RTCRtpSender:
        ...
    @typing.overload
    def addTrack(self, arg0: MediaStreamTrack, arg1: collections.abc.Sequence[MediaStream]) -> RTCRtpSender:
        ...
    @typing.overload
    def addTransceiver(self, arg0: MediaType, arg1: RtpTransceiverInit | None) -> RTCRtpTransceiver:
        ...
    @typing.overload
    def addTransceiver(self, arg0: MediaStreamTrack, arg1: RtpTransceiverInit | None) -> RTCRtpTransceiver:
        ...
    def close(self) -> None:
        ...
    def createAnswer(self, arg0: collections.abc.Callable[[RTCSessionDescription], None], arg1: collections.abc.Callable[[CallbackPythonWebRTCException], None]) -> None:
        ...
    def createOffer(self, arg0: collections.abc.Callable[[RTCSessionDescription], None], arg1: collections.abc.Callable[[CallbackPythonWebRTCException], None]) -> None:
        ...
    def getReceivers(self) -> list[RTCRtpReceiver]:
        ...
    def getSenders(self) -> list[RTCRtpSender]:
        ...
    def getTransceivers(self) -> list[RTCRtpTransceiver]:
        ...
    def removeTrack(self, arg0: RTCRtpSender) -> None:
        ...
    def restartIce(self) -> None:
        ...
    def setLocalDescription(self, arg0: collections.abc.Callable[[], None], arg1: collections.abc.Callable[[CallbackPythonWebRTCException], None], arg2: RTCSessionDescription) -> None:
        ...
    def setRemoteDescription(self, arg0: collections.abc.Callable[[], None], arg1: collections.abc.Callable[[CallbackPythonWebRTCException], None], arg2: RTCSessionDescription) -> None:
        ...
    @property
    def connectionState(self) -> RTCPeerConnectionState:
        ...
    @property
    def iceConnectionState(self) -> RTCIceConnectionState:
        ...
    @property
    def iceGatheringState(self) -> RTCIceGatheringState:
        ...
    @property
    def localDescription(self) -> RTCSessionDescription | None:
        ...
    @property
    def remoteDescription(self) -> RTCSessionDescription | None:
        ...
    @property
    def sctp(self) -> RTCSctpTransport | None:
        ...
    @property
    def signalingState(self) -> RTCSignalingState:
        ...
class RTCAudioSource:
    def __init__(self) -> None:
        ...
    def createTrack(self) -> MediaStreamTrack:
        ...
    def onData(self, arg0: RTCOnDataEvent) -> None:
        ...
def getUserMedia() -> MediaStream:
    ...
def ping() -> None:
    ...
RTCP: RTCIceComponent
RTP: RTCIceComponent
answer: RTCSdpType
audio: MediaType
checking: RTCIceTransportState
closed: SctpTransportState
complete: CricketIceGatheringState
completed: RTCIceTransportState
connected: SctpTransportState
connecting: SctpTransportState
controlled: RTCIceRole
controlling: RTCIceRole
data: MediaType
disconnected: RTCIceTransportState
ended: MediaStreamSourceState
failed: DtlsTransportState
gathering: CricketIceGatheringState
have_local_offer: RTCSignalingState
have_local_pranswer: RTCSignalingState
have_remote_offer: RTCSignalingState
have_remote_pranswer: RTCSignalingState
inactive: TransceiverDirection
initializing: MediaStreamSourceState
live: MediaStreamSourceState
max: RTCIceConnectionState
muted: MediaStreamSourceState
new: SctpTransportState
offer: RTCSdpType
pranswer: RTCSdpType
recvonly: TransceiverDirection
rollback: RTCSdpType
sendonly: TransceiverDirection
sendrecv: TransceiverDirection
stable: RTCSignalingState
stopped: TransceiverDirection
unknown: RTCIceRole
unsupported: MediaType
video: MediaType
