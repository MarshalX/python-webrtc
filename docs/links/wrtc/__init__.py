from __future__ import annotations
import wrtc
import typing

__all__ = [
    "CallbackPythonWebRTCException",
    "CricketIceGatheringState",
    "DtlsTransportState",
    "MediaStream",
    "MediaStreamSourceState",
    "MediaStreamTrack",
    "MediaStreamTrackState",
    "MediaType",
    "PeerConnectionFactory",
    "PythonWebRTCException",
    "PythonWebRTCExceptionBase",
    "RTCAudioSource",
    "RTCCallbackException",
    "RTCDtlsTransport",
    "RTCException",
    "RTCIceComponent",
    "RTCIceConnectionState",
    "RTCIceGatheringState",
    "RTCIceRole",
    "RTCIceTransport",
    "RTCIceTransportState",
    "RTCOnDataEvent",
    "RTCP",
    "RTCPeerConnection",
    "RTCPeerConnectionState",
    "RTCRtpReceiver",
    "RTCRtpSender",
    "RTCRtpTransceiver",
    "RTCSdpType",
    "RTCSessionDescription",
    "RTCSessionDescriptionInit",
    "RTP",
    "RtpEncodingParameters",
    "RtpTransceiverInit",
    "SdpParseException",
    "TransceiverDirection",
    "answer",
    "audio",
    "checking",
    "closed",
    "complete",
    "completed",
    "connected",
    "connecting",
    "controlled",
    "controlling",
    "data",
    "disconnected",
    "ended",
    "failed",
    "gathering",
    "getUserMedia",
    "inactive",
    "initializing",
    "live",
    "max",
    "muted",
    "new",
    "offer",
    "ping",
    "pranswer",
    "recvonly",
    "rollback",
    "sendonly",
    "sendrecv",
    "stopped",
    "unknown",
    "unsupported",
    "video"
]


class CallbackPythonWebRTCException():
    def what(self) -> str: ...
    pass
class CricketIceGatheringState():
    """
    Members:

      new

      gathering

      complete
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'new': <CricketIceGatheringState.new: 0>, 'gathering': <CricketIceGatheringState.gathering: 1>, 'complete': <CricketIceGatheringState.complete: 2>}
    complete: wrtc.CricketIceGatheringState # value = <CricketIceGatheringState.complete: 2>
    gathering: wrtc.CricketIceGatheringState # value = <CricketIceGatheringState.gathering: 1>
    new: wrtc.CricketIceGatheringState # value = <CricketIceGatheringState.new: 0>
    pass
class DtlsTransportState():
    """
    Members:

      new

      connecting

      connected

      closed

      failed
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'new': <DtlsTransportState.new: 0>, 'connecting': <DtlsTransportState.connecting: 1>, 'connected': <DtlsTransportState.connected: 2>, 'closed': <DtlsTransportState.closed: 3>, 'failed': <DtlsTransportState.failed: 4>}
    closed: wrtc.DtlsTransportState # value = <DtlsTransportState.closed: 3>
    connected: wrtc.DtlsTransportState # value = <DtlsTransportState.connected: 2>
    connecting: wrtc.DtlsTransportState # value = <DtlsTransportState.connecting: 1>
    failed: wrtc.DtlsTransportState # value = <DtlsTransportState.failed: 4>
    new: wrtc.DtlsTransportState # value = <DtlsTransportState.new: 0>
    pass
class MediaStream():
    def addTrack(self, arg0: MediaStreamTrack) -> None: ...
    def clone(self) -> MediaStream: ...
    def getAudioTracks(self) -> typing.List[MediaStreamTrack]: ...
    def getTrackById(self, arg0: str) -> typing.Optional[MediaStreamTrack]: ...
    def getTracks(self) -> typing.List[MediaStreamTrack]: ...
    def getVideoTracks(self) -> typing.List[MediaStreamTrack]: ...
    def removeTrack(self, arg0: MediaStreamTrack) -> None: ...
    @property
    def active(self) -> bool:
        """
        :type: bool
        """
    @property
    def id(self) -> str:
        """
        :type: str
        """
    pass
class MediaStreamSourceState():
    """
    Members:

      initializing

      live

      ended

      muted
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'initializing': <MediaStreamSourceState.initializing: 0>, 'live': <MediaStreamSourceState.live: 1>, 'ended': <MediaStreamSourceState.ended: 2>, 'muted': <MediaStreamSourceState.muted: 3>}
    ended: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.ended: 2>
    initializing: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.initializing: 0>
    live: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.live: 1>
    muted: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.muted: 3>
    pass
class MediaStreamTrack():
    def clone(self) -> MediaStreamTrack: ...
    def stop(self) -> None: ...
    @property
    def enabled(self) -> bool:
        """
        :type: bool
        """
    @enabled.setter
    def enabled(self, arg1: bool) -> None:
        pass
    @property
    def id(self) -> str:
        """
        :type: str
        """
    @property
    def kind(self) -> MediaType:
        """
        :type: MediaType
        """
    @property
    def muted(self) -> bool:
        """
        :type: bool
        """
    @property
    def readyState(self) -> MediaStreamTrackState:
        """
        :type: MediaStreamTrackState
        """
    pass
class MediaStreamTrackState():
    """
    Members:

      live

      ended
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'live': <MediaStreamTrackState.live: 0>, 'ended': <MediaStreamTrackState.ended: 1>}
    ended: wrtc.MediaStreamTrackState # value = <MediaStreamTrackState.ended: 1>
    live: wrtc.MediaStreamTrackState # value = <MediaStreamTrackState.live: 0>
    pass
class MediaType():
    """
    Members:

      audio

      video

      data

      unsupported
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'audio': <MediaType.audio: 0>, 'video': <MediaType.video: 1>, 'data': <MediaType.data: 2>, 'unsupported': <MediaType.unsupported: 3>}
    audio: wrtc.MediaType # value = <MediaType.audio: 0>
    data: wrtc.MediaType # value = <MediaType.data: 2>
    unsupported: wrtc.MediaType # value = <MediaType.unsupported: 3>
    video: wrtc.MediaType # value = <MediaType.video: 1>
    pass
class PeerConnectionFactory():
    def __init__(self) -> None: ...
    @staticmethod
    def dispose() -> None: ...
    @staticmethod
    def getOrCreateDefault() -> PeerConnectionFactory: ...
    @staticmethod
    def release() -> None: ...
    pass
class PythonWebRTCExceptionBase(Exception, BaseException):
    pass
class PythonWebRTCException(PythonWebRTCExceptionBase, Exception, BaseException):
    pass
class RTCAudioSource():
    def __init__(self) -> None: ...
    def createTrack(self) -> MediaStreamTrack: ...
    def onData(self, arg0: RTCOnDataEvent) -> None: ...
    pass
class RTCCallbackException():
    def what(self) -> str: ...
    pass
class RTCDtlsTransport():
    @property
    def iceTransport(self) -> RTCIceTransport:
        """
        :type: RTCIceTransport
        """
    @property
    def state(self) -> DtlsTransportState:
        """
        :type: DtlsTransportState
        """
    pass
class RTCException(PythonWebRTCExceptionBase, Exception, BaseException):
    pass
class RTCIceComponent():
    """
    Members:

      RTP

      RTCP
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    RTCP: wrtc.RTCIceComponent # value = <RTCIceComponent.RTCP: 1>
    RTP: wrtc.RTCIceComponent # value = <RTCIceComponent.RTP: 0>
    __members__: dict # value = {'RTP': <RTCIceComponent.RTP: 0>, 'RTCP': <RTCIceComponent.RTCP: 1>}
    pass
class RTCIceConnectionState():
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
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'new': <RTCIceConnectionState.new: 0>, 'checking': <RTCIceConnectionState.checking: 1>, 'connected': <RTCIceConnectionState.connected: 2>, 'completed': <RTCIceConnectionState.completed: 3>, 'failed': <RTCIceConnectionState.failed: 4>, 'disconnected': <RTCIceConnectionState.disconnected: 5>, 'closed': <RTCIceConnectionState.closed: 6>, 'max': <RTCIceConnectionState.max: 7>}
    checking: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.checking: 1>
    closed: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.closed: 6>
    completed: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.completed: 3>
    connected: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.connected: 2>
    disconnected: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.disconnected: 5>
    failed: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.failed: 4>
    max: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.max: 7>
    new: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.new: 0>
    pass
class RTCIceGatheringState():
    """
    Members:

      new

      gathering

      complete
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'new': <RTCIceGatheringState.new: 0>, 'gathering': <RTCIceGatheringState.gathering: 1>, 'complete': <RTCIceGatheringState.complete: 2>}
    complete: wrtc.RTCIceGatheringState # value = <RTCIceGatheringState.complete: 2>
    gathering: wrtc.RTCIceGatheringState # value = <RTCIceGatheringState.gathering: 1>
    new: wrtc.RTCIceGatheringState # value = <RTCIceGatheringState.new: 0>
    pass
class RTCIceRole():
    """
    Members:

      controlling

      controlled

      unknown
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'controlling': <RTCIceRole.controlling: 0>, 'controlled': <RTCIceRole.controlled: 1>, 'unknown': <RTCIceRole.unknown: 2>}
    controlled: wrtc.RTCIceRole # value = <RTCIceRole.controlled: 1>
    controlling: wrtc.RTCIceRole # value = <RTCIceRole.controlling: 0>
    unknown: wrtc.RTCIceRole # value = <RTCIceRole.unknown: 2>
    pass
class RTCIceTransport():
    @property
    def component(self) -> RTCIceComponent:
        """
        :type: RTCIceComponent
        """
    @property
    def gatheringState (self) -> CricketIceGatheringState:
        """
        :type: CricketIceGatheringState
        """
    @property
    def role(self) -> RTCIceRole:
        """
        :type: RTCIceRole
        """
    @property
    def state(self) -> RTCIceTransportState:
        """
        :type: RTCIceTransportState
        """
    pass
class RTCIceTransportState():
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
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'new': <RTCIceTransportState.new: 0>, 'checking': <RTCIceTransportState.checking: 1>, 'connected': <RTCIceTransportState.connected: 2>, 'completed': <RTCIceTransportState.completed: 3>, 'disconnected': <RTCIceTransportState.disconnected: 5>, 'failed': <RTCIceTransportState.failed: 4>, 'closed': <RTCIceTransportState.closed: 6>}
    checking: wrtc.RTCIceTransportState # value = <RTCIceTransportState.checking: 1>
    closed: wrtc.RTCIceTransportState # value = <RTCIceTransportState.closed: 6>
    completed: wrtc.RTCIceTransportState # value = <RTCIceTransportState.completed: 3>
    connected: wrtc.RTCIceTransportState # value = <RTCIceTransportState.connected: 2>
    disconnected: wrtc.RTCIceTransportState # value = <RTCIceTransportState.disconnected: 5>
    failed: wrtc.RTCIceTransportState # value = <RTCIceTransportState.failed: 4>
    new: wrtc.RTCIceTransportState # value = <RTCIceTransportState.new: 0>
    pass
class RTCOnDataEvent():
    def __init__(self, arg0: str, arg1: int) -> None: ...
    @property
    def audioData(self) -> int:
        """
        :type: int
        """
    @audioData.setter
    def audioData(self, arg0: int) -> None:
        pass
    @property
    def bitsPerSample(self) -> int:
        """
        :type: int
        """
    @bitsPerSample.setter
    def bitsPerSample(self, arg0: int) -> None:
        pass
    @property
    def channelCount(self) -> int:
        """
        :type: int
        """
    @channelCount.setter
    def channelCount(self, arg0: int) -> None:
        pass
    @property
    def numberOfFrames(self) -> int:
        """
        :type: int
        """
    @numberOfFrames.setter
    def numberOfFrames(self, arg0: int) -> None:
        pass
    @property
    def sampleRate(self) -> int:
        """
        :type: int
        """
    @sampleRate.setter
    def sampleRate(self, arg0: int) -> None:
        pass
    pass
class RTCPeerConnection():
    def __init__(self) -> None: ...
    @typing.overload
    def addTrack(self, arg0: MediaStreamTrack, arg1: typing.List[MediaStream]) -> RTCRtpSender: ...
    @typing.overload
    def addTrack(self, arg0: MediaStreamTrack, arg1: typing.Optional[MediaStream]) -> RTCRtpSender: ...
    @typing.overload
    def addTransceiver(self, arg0: MediaStreamTrack, arg1: typing.Optional[RtpTransceiverInit]) -> RTCRtpTransceiver: ...
    @typing.overload
    def addTransceiver(self, arg0: MediaType, arg1: typing.Optional[RtpTransceiverInit]) -> RTCRtpTransceiver: ...
    def close(self) -> None: ...
    def createAnswer(self, arg0: typing.Callable[[RTCSessionDescription], None], arg1: typing.Callable[[CallbackPythonWebRTCException], None]) -> None: ...
    def createOffer(self, arg0: typing.Callable[[RTCSessionDescription], None], arg1: typing.Callable[[CallbackPythonWebRTCException], None]) -> None: ...
    def getReceivers(self) -> typing.List[RTCRtpReceiver]: ...
    def getSenders(self) -> typing.List[RTCRtpSender]: ...
    def getTransceivers(self) -> typing.List[RTCRtpTransceiver]: ...
    def setLocalDescription(self, arg0: typing.Callable[[], None], arg1: typing.Callable[[CallbackPythonWebRTCException], None], arg2: RTCSessionDescription) -> None: ...
    def setRemoteDescription(self, arg0: typing.Callable[[], None], arg1: typing.Callable[[CallbackPythonWebRTCException], None], arg2: RTCSessionDescription) -> None: ...
    pass
class RTCPeerConnectionState():
    """
    Members:

      new

      connecting

      connected

      disconnected

      failed

      closed
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'new': <RTCPeerConnectionState.new: 0>, 'connecting': <RTCPeerConnectionState.connecting: 1>, 'connected': <RTCPeerConnectionState.connected: 2>, 'disconnected': <RTCPeerConnectionState.disconnected: 3>, 'failed': <RTCPeerConnectionState.failed: 4>, 'closed': <RTCPeerConnectionState.closed: 5>}
    closed: wrtc.RTCPeerConnectionState # value = <RTCPeerConnectionState.closed: 5>
    connected: wrtc.RTCPeerConnectionState # value = <RTCPeerConnectionState.connected: 2>
    connecting: wrtc.RTCPeerConnectionState # value = <RTCPeerConnectionState.connecting: 1>
    disconnected: wrtc.RTCPeerConnectionState # value = <RTCPeerConnectionState.disconnected: 3>
    failed: wrtc.RTCPeerConnectionState # value = <RTCPeerConnectionState.failed: 4>
    new: wrtc.RTCPeerConnectionState # value = <RTCPeerConnectionState.new: 0>
    pass
class RTCRtpReceiver():
    @property
    def track(self) -> MediaStreamTrack:
        """
        :type: MediaStreamTrack
        """
    @property
    def transport(self) -> typing.Optional[RTCDtlsTransport]:
        """
        :type: typing.Optional[RTCDtlsTransport]
        """
    pass
class RTCRtpSender():
    @property
    def track(self) -> typing.Optional[MediaStreamTrack]:
        """
        :type: typing.Optional[MediaStreamTrack]
        """
    @property
    def transport(self) -> typing.Optional[RTCDtlsTransport]:
        """
        :type: typing.Optional[RTCDtlsTransport]
        """
    pass
class RTCRtpTransceiver():
    def stop(self) -> None: ...
    @property
    def currentDirection(self) -> typing.Optional[TransceiverDirection]:
        """
        :type: typing.Optional[TransceiverDirection]
        """
    @property
    def direction(self) -> TransceiverDirection:
        """
        :type: TransceiverDirection
        """
    @direction.setter
    def direction(self, arg1: TransceiverDirection) -> None:
        pass
    @property
    def mid(self) -> typing.Optional[str]:
        """
        :type: typing.Optional[str]
        """
    @property
    def receiver(self) -> RTCRtpReceiver:
        """
        :type: RTCRtpReceiver
        """
    @property
    def sender(self) -> RTCRtpSender:
        """
        :type: RTCRtpSender
        """
    @property
    def stopped(self) -> bool:
        """
        :type: bool
        """
    pass
class RTCSdpType():
    """
    Members:

      offer

      pranswer

      answer

      rollback
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'offer': <RTCSdpType.offer: 0>, 'pranswer': <RTCSdpType.pranswer: 1>, 'answer': <RTCSdpType.answer: 2>, 'rollback': <RTCSdpType.rollback: 3>}
    answer: wrtc.RTCSdpType # value = <RTCSdpType.answer: 2>
    offer: wrtc.RTCSdpType # value = <RTCSdpType.offer: 0>
    pranswer: wrtc.RTCSdpType # value = <RTCSdpType.pranswer: 1>
    rollback: wrtc.RTCSdpType # value = <RTCSdpType.rollback: 3>
    pass
class RTCSessionDescription():
    def __init__(self, arg0: RTCSessionDescriptionInit) -> None: ...
    @property
    def sdp(self) -> str:
        """
        :type: str
        """
    @property
    def type(self) -> RTCSdpType:
        """
        :type: RTCSdpType
        """
    pass
class RTCSessionDescriptionInit():
    def __init__(self, arg0: RTCSdpType, arg1: str) -> None: ...
    @property
    def sdp(self) -> str:
        """
        :type: str
        """
    @sdp.setter
    def sdp(self, arg0: str) -> None:
        pass
    @property
    def type(self) -> RTCSdpType:
        """
        :type: RTCSdpType
        """
    @type.setter
    def type(self, arg0: RTCSdpType) -> None:
        pass
    pass
class RtpEncodingParameters():
    def __init__(self) -> None: ...
    @property
    def active(self) -> bool:
        """
        :type: bool
        """
    @active.setter
    def active(self, arg0: bool) -> None:
        pass
    @property
    def maxBitrate(self) -> typing.Optional[int]:
        """
        :type: typing.Optional[int]
        """
    @maxBitrate.setter
    def maxBitrate(self, arg0: typing.Optional[int]) -> None:
        pass
    @property
    def maxFramerate(self) -> typing.Optional[float]:
        """
        :type: typing.Optional[float]
        """
    @maxFramerate.setter
    def maxFramerate(self, arg0: typing.Optional[float]) -> None:
        pass
    @property
    def rid(self) -> str:
        """
        :type: str
        """
    @rid.setter
    def rid(self, arg0: str) -> None:
        pass
    @property
    def scaleResolutionDownBy(self) -> typing.Optional[float]:
        """
        :type: typing.Optional[float]
        """
    @scaleResolutionDownBy.setter
    def scaleResolutionDownBy(self, arg0: typing.Optional[float]) -> None:
        pass
    @property
    def ssrc(self) -> typing.Optional[int]:
        """
        :type: typing.Optional[int]
        """
    @ssrc.setter
    def ssrc(self, arg0: typing.Optional[int]) -> None:
        pass
    pass
class RtpTransceiverInit():
    def __init__(self) -> None: ...
    @property
    def direction(self) -> TransceiverDirection:
        """
        :type: TransceiverDirection
        """
    @direction.setter
    def direction(self, arg0: TransceiverDirection) -> None:
        pass
    @property
    def sendEncodings(self) -> typing.List[webrtc::RtpEncodingParameters]:
        """
        :type: typing.List[webrtc::RtpEncodingParameters]
        """
    @sendEncodings.setter
    def sendEncodings(self, arg0: typing.List[webrtc::RtpEncodingParameters]) -> None:
        pass
    @property
    def streamIds(self) -> typing.List[str]:
        """
        :type: typing.List[str]
        """
    @streamIds.setter
    def streamIds(self, arg0: typing.List[str]) -> None:
        pass
    pass
class SdpParseException(PythonWebRTCExceptionBase, Exception, BaseException):
    pass
class TransceiverDirection():
    """
    Members:

      sendrecv

      sendonly

      recvonly

      inactive

      stopped
    """
    def __eq__(self, other: object) -> bool: ...
    def __getstate__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __index__(self) -> int: ...
    def __init__(self, value: int) -> None: ...
    def __int__(self) -> int: ...
    def __ne__(self, other: object) -> bool: ...
    def __repr__(self) -> str: ...
    def __setstate__(self, state: int) -> None: ...
    @property
    def name(self) -> str:
        """
        :type: str
        """
    @property
    def value(self) -> int:
        """
        :type: int
        """
    __members__: dict # value = {'sendrecv': <TransceiverDirection.sendrecv: 0>, 'sendonly': <TransceiverDirection.sendonly: 1>, 'recvonly': <TransceiverDirection.recvonly: 2>, 'inactive': <TransceiverDirection.inactive: 3>, 'stopped': <TransceiverDirection.stopped: 4>}
    inactive: wrtc.TransceiverDirection # value = <TransceiverDirection.inactive: 3>
    recvonly: wrtc.TransceiverDirection # value = <TransceiverDirection.recvonly: 2>
    sendonly: wrtc.TransceiverDirection # value = <TransceiverDirection.sendonly: 1>
    sendrecv: wrtc.TransceiverDirection # value = <TransceiverDirection.sendrecv: 0>
    stopped: wrtc.TransceiverDirection # value = <TransceiverDirection.stopped: 4>
    pass
def getUserMedia() -> MediaStream:
    pass
def ping() -> None:
    pass
RTCP: wrtc.RTCIceComponent # value = <RTCIceComponent.RTCP: 1>
RTP: wrtc.RTCIceComponent # value = <RTCIceComponent.RTP: 0>
answer: wrtc.RTCSdpType # value = <RTCSdpType.answer: 2>
audio: wrtc.MediaType # value = <MediaType.audio: 0>
checking: wrtc.RTCIceTransportState # value = <RTCIceTransportState.checking: 1>
closed: wrtc.DtlsTransportState # value = <DtlsTransportState.closed: 3>
complete: wrtc.CricketIceGatheringState # value = <CricketIceGatheringState.complete: 2>
completed: wrtc.RTCIceTransportState # value = <RTCIceTransportState.completed: 3>
connected: wrtc.DtlsTransportState # value = <DtlsTransportState.connected: 2>
connecting: wrtc.DtlsTransportState # value = <DtlsTransportState.connecting: 1>
controlled: wrtc.RTCIceRole # value = <RTCIceRole.controlled: 1>
controlling: wrtc.RTCIceRole # value = <RTCIceRole.controlling: 0>
data: wrtc.MediaType # value = <MediaType.data: 2>
disconnected: wrtc.RTCIceTransportState # value = <RTCIceTransportState.disconnected: 5>
ended: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.ended: 2>
failed: wrtc.DtlsTransportState # value = <DtlsTransportState.failed: 4>
gathering: wrtc.CricketIceGatheringState # value = <CricketIceGatheringState.gathering: 1>
inactive: wrtc.TransceiverDirection # value = <TransceiverDirection.inactive: 3>
initializing: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.initializing: 0>
live: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.live: 1>
max: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.max: 7>
muted: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.muted: 3>
new: wrtc.DtlsTransportState # value = <DtlsTransportState.new: 0>
offer: wrtc.RTCSdpType # value = <RTCSdpType.offer: 0>
pranswer: wrtc.RTCSdpType # value = <RTCSdpType.pranswer: 1>
recvonly: wrtc.TransceiverDirection # value = <TransceiverDirection.recvonly: 2>
rollback: wrtc.RTCSdpType # value = <RTCSdpType.rollback: 3>
sendonly: wrtc.TransceiverDirection # value = <TransceiverDirection.sendonly: 1>
sendrecv: wrtc.TransceiverDirection # value = <TransceiverDirection.sendrecv: 0>
stopped: wrtc.TransceiverDirection # value = <TransceiverDirection.stopped: 4>
unknown: wrtc.RTCIceRole # value = <RTCIceRole.unknown: 2>
unsupported: wrtc.MediaType # value = <MediaType.unsupported: 3>
video: wrtc.MediaType # value = <MediaType.video: 1>
