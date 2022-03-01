from __future__ import annotations
import wrtc
import typing

__all__ = [
    "CallbackPythonWebRTCException",
    "MediaStream",
    "MediaStreamSourceState",
    "MediaStreamTrack",
    "MediaStreamTrackState",
    "PeerConnectionFactory",
    "PythonWebRTCException",
    "PythonWebRTCExceptionBase",
    "RTCAudioSource",
    "RTCCallbackException",
    "RTCException",
    "RTCIceConnectionState",
    "RTCIceGatheringState",
    "RTCOnDataEvent",
    "RTCPeerConnection",
    "RTCPeerConnectionState",
    "RTCRtpSender",
    "RTCRtpTransceiver",
    "RTCSdpType",
    "RTCSessionDescription",
    "RTCSessionDescriptionInit",
    "SdpParseException",
    "TransceiverDirection",
    "answer",
    "checking",
    "closed",
    "complete",
    "completed",
    "connected",
    "connecting",
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
    "stopped"
]


class CallbackPythonWebRTCException():
    def what(self) -> str: ...
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
    def kind(self) -> str:
        """
        :type: str
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
class RTCException(PythonWebRTCExceptionBase, Exception, BaseException):
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
    @staticmethod
    def addTrack(*args, **kwargs) -> typing.Any: ...
    def close(self) -> None: ...
    def createAnswer(self, arg0: typing.Callable[[RTCSessionDescription], None], arg1: typing.Callable[[CallbackPythonWebRTCException], None]) -> None: ...
    def createOffer(self, arg0: typing.Callable[[RTCSessionDescription], None], arg1: typing.Callable[[CallbackPythonWebRTCException], None]) -> None: ...
    def getTransceivers(self) -> typing.List[python_webrtc::RTCRtpTransceiver]: ...
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
class RTCRtpSender():
    @property
    def track(self) -> typing.Optional[MediaStreamTrack]:
        """
        :type: typing.Optional[MediaStreamTrack]
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
answer: wrtc.RTCSdpType # value = <RTCSdpType.answer: 2>
checking: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.checking: 1>
closed: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.closed: 6>
complete: wrtc.RTCIceGatheringState # value = <RTCIceGatheringState.complete: 2>
completed: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.completed: 3>
connected: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.connected: 2>
connecting: wrtc.RTCPeerConnectionState # value = <RTCPeerConnectionState.connecting: 1>
disconnected: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.disconnected: 5>
ended: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.ended: 2>
failed: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.failed: 4>
gathering: wrtc.RTCIceGatheringState # value = <RTCIceGatheringState.gathering: 1>
inactive: wrtc.TransceiverDirection # value = <TransceiverDirection.inactive: 3>
initializing: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.initializing: 0>
live: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.live: 1>
max: wrtc.RTCIceConnectionState # value = <RTCIceConnectionState.max: 7>
muted: wrtc.MediaStreamSourceState # value = <MediaStreamSourceState.muted: 3>
new: wrtc.RTCIceGatheringState # value = <RTCIceGatheringState.new: 0>
offer: wrtc.RTCSdpType # value = <RTCSdpType.offer: 0>
pranswer: wrtc.RTCSdpType # value = <RTCSdpType.pranswer: 1>
recvonly: wrtc.TransceiverDirection # value = <TransceiverDirection.recvonly: 2>
rollback: wrtc.RTCSdpType # value = <RTCSdpType.rollback: 3>
sendonly: wrtc.TransceiverDirection # value = <TransceiverDirection.sendonly: 1>
sendrecv: wrtc.TransceiverDirection # value = <TransceiverDirection.sendrecv: 0>
stopped: wrtc.TransceiverDirection # value = <TransceiverDirection.stopped: 4>
