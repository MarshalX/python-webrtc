#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Event objects passed to the handlers registered with ``on()`` (see :obj:`webrtc.utils.events.EventTarget`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from webrtc.enums import SFrameTransformErrorEventType
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc
    from webrtc.enums import SFrameTransformErrorEventTypeValue


class Event:
    """An event of a WebRTC object.

    Args:
        type (:obj:`str`): The name of the event, like ``'signalingstatechange'``.

    Attributes:
        target (:obj:`object`): The object that emitted the event, :obj:`None` until it's dispatched.
    """

    def __init__(self, type: str) -> None:
        self.type = type
        self.target: webrtc.EventTarget | None = None

    def __repr__(self) -> str:
        fields = ', '.join(f'{k}={v!r}' for k, v in vars(self).items() if k != 'target')
        return f'{type(self).__name__}({fields})'


@dataclass
class RTCPeerConnectionIceEventInit(Dictionary):
    """The members of a :obj:`RTCPeerConnectionIceEvent`.

    Args:
        candidate (:obj:`webrtc.RTCIceCandidate`, optional): The new candidate, :obj:`None` at the end of candidates.
        url (:obj:`str`, optional): The URL of the STUN or TURN server that gathered the candidate.
    """

    candidate: webrtc.RTCIceCandidate | None = None
    url: str | None = None


class RTCPeerConnectionIceEvent(Event):
    """An ``icecandidate`` event of :obj:`webrtc.RTCPeerConnection`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCPeerConnectionIceEventInit`, optional): The members of the event.
    """

    candidate: webrtc.RTCIceCandidate | None
    url: str | None

    def __init__(self, type: str, event_init_dict: RTCPeerConnectionIceEventInit | None = None) -> None:
        super().__init__(type)
        init = event_init_dict if event_init_dict is not None else RTCPeerConnectionIceEventInit()
        self.candidate = init.candidate
        self.url = init.url


@dataclass
class RTCPeerConnectionIceErrorEventInit(Dictionary):
    """The members of a :obj:`RTCPeerConnectionIceErrorEvent`.

    Args:
        error_code (:obj:`int`): The STUN error code, or 701 if the server couldn't be reached.
        address (:obj:`str`, optional): The local address used to reach the server.
        port (:obj:`int`, optional): The local port used to reach the server.
        url (:obj:`str`, optional): The URL of the server.
        error_text (:obj:`str`, optional): The STUN reason text.
    """

    error_code: int
    address: str | None = None
    port: int | None = None
    url: str = ''
    error_text: str = ''

    #: Alias for :attr:`error_code`
    errorCode: ClassVar[Alias[int]] = alias('error_code')
    #: Alias for :attr:`error_text`
    errorText: ClassVar[Alias[str]] = alias('error_text')


class RTCPeerConnectionIceErrorEvent(Event):
    """An ``icecandidateerror`` event of :obj:`webrtc.RTCPeerConnection`: a STUN or TURN server failed.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCPeerConnectionIceErrorEventInit`): The members of the event.
    """

    address: str | None
    port: int | None
    url: str
    error_code: int
    error_text: str

    def __init__(self, type: str, event_init_dict: RTCPeerConnectionIceErrorEventInit) -> None:
        super().__init__(type)
        self.address = event_init_dict.address
        self.port = event_init_dict.port
        self.url = event_init_dict.url
        self.error_code = event_init_dict.error_code
        self.error_text = event_init_dict.error_text

    #: Alias for :attr:`error_code`
    errorCode: ClassVar[Alias[int]] = alias('error_code')
    #: Alias for :attr:`error_text`
    errorText: ClassVar[Alias[str]] = alias('error_text')


class MessageEvent(Event):
    """A ``message`` event of :obj:`webrtc.RTCDataChannel`.

    Args:
        type (:obj:`str`): The name of the event.
        data (:obj:`str`, :obj:`bytes` or :obj:`webrtc.Blob`): The message, :obj:`bytes` (or a :obj:`webrtc.Blob`
            with the ``blob`` binary type) if it was sent as binary.
    """

    data: str | bytes | webrtc.Blob

    def __init__(self, type: str, data: str | bytes | webrtc.Blob) -> None:
        super().__init__(type)
        self.data = data


@dataclass
class RTCDataChannelEventInit(Dictionary):
    """The members of a :obj:`RTCDataChannelEvent`.

    Args:
        channel (:obj:`webrtc.RTCDataChannel`): The new channel.
    """

    channel: webrtc.RTCDataChannel


class RTCDataChannelEvent(Event):
    """A ``datachannel`` event of :obj:`webrtc.RTCPeerConnection`: the remote peer created a channel.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCDataChannelEventInit`): The members of the event.
    """

    channel: webrtc.RTCDataChannel

    def __init__(self, type: str, event_init_dict: RTCDataChannelEventInit) -> None:
        super().__init__(type)
        self.channel = event_init_dict.channel


@dataclass
class MediaStreamTrackEventInit(Dictionary):
    """The members of a :obj:`MediaStreamTrackEvent`.

    Args:
        track (:obj:`webrtc.MediaStreamTrack`): The track added or removed.
    """

    track: webrtc.MediaStreamTrack


class MediaStreamTrackEvent(Event):
    """An ``addtrack`` or ``removetrack`` event of :obj:`webrtc.MediaStream`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`MediaStreamTrackEventInit`): The members of the event.
    """

    track: webrtc.MediaStreamTrack

    def __init__(self, type: str, event_init_dict: MediaStreamTrackEventInit) -> None:
        super().__init__(type)
        self.track = event_init_dict.track


@dataclass
class RTCDTMFToneChangeEventInit(Dictionary):
    """The members of a :obj:`RTCDTMFToneChangeEvent`.

    Args:
        tone (:obj:`str`, optional): The tone that started playing, empty when all tones were played.
    """

    tone: str = ''


class RTCDTMFToneChangeEvent(Event):
    """A ``tonechange`` event of :obj:`webrtc.RTCDTMFSender`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCDTMFToneChangeEventInit`, optional): The members of the event.
    """

    tone: str

    def __init__(self, type: str, event_init_dict: RTCDTMFToneChangeEventInit | None = None) -> None:
        super().__init__(type)
        self.tone = event_init_dict.tone if event_init_dict is not None else ''


@dataclass
class DeviceChangeEventInit(Dictionary):
    """The members of a :obj:`DeviceChangeEvent`.

    Args:
        devices (:obj:`list` of :obj:`webrtc.MediaDeviceInfo`, optional): The devices after the change.
    """

    devices: list[webrtc.MediaDeviceInfo] = field(default_factory=list)


class DeviceChangeEvent(Event):
    """A ``devicechange`` event of :obj:`webrtc.MediaDevices`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`DeviceChangeEventInit`, optional): The members of the event.
    """

    devices: list[webrtc.MediaDeviceInfo]
    user_inserted_devices: list[webrtc.MediaDeviceInfo]

    def __init__(self, type: str, event_init_dict: DeviceChangeEventInit | None = None) -> None:
        super().__init__(type)
        self.devices = list(event_init_dict.devices) if event_init_dict is not None else []
        self.user_inserted_devices = []

    #: Alias for :attr:`user_inserted_devices`
    userInsertedDevices: ClassVar[Alias[list[webrtc.MediaDeviceInfo]]] = alias('user_inserted_devices')


@dataclass
class RTCErrorEventInit(Dictionary):
    """The members of a :obj:`RTCErrorEvent`.

    Args:
        error (:obj:`webrtc.RTCError`): The error.
    """

    error: webrtc.RTCError


class RTCErrorEvent(Event):
    """An ``error`` event, carrying the :obj:`webrtc.RTCError` that occurred.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCErrorEventInit`): The members of the event.
    """

    error: webrtc.RTCError

    def __init__(self, type: str, event_init_dict: RTCErrorEventInit) -> None:
        super().__init__(type)
        self.error = event_init_dict.error


@dataclass
class RTCTrackEventInit(Dictionary):
    """The members of a :obj:`RTCTrackEvent`.

    Args:
        receiver (:obj:`webrtc.RTCRtpReceiver`): The receiver of the track.
        track (:obj:`webrtc.MediaStreamTrack`): The remote track.
        transceiver (:obj:`webrtc.RTCRtpTransceiver`): The transceiver of the receiver.
        streams (:obj:`list` of :obj:`webrtc.MediaStream`, optional): The remote streams of the track.
    """

    receiver: webrtc.RTCRtpReceiver
    track: webrtc.MediaStreamTrack
    transceiver: webrtc.RTCRtpTransceiver
    streams: list[webrtc.MediaStream] = field(default_factory=list)


class RTCTrackEvent(Event):
    """A ``track`` event of :obj:`webrtc.RTCPeerConnection`: a remote track was negotiated.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCTrackEventInit`): The members of the event.
    """

    receiver: webrtc.RTCRtpReceiver
    track: webrtc.MediaStreamTrack
    streams: list[webrtc.MediaStream]
    transceiver: webrtc.RTCRtpTransceiver

    def __init__(self, type: str, event_init_dict: RTCTrackEventInit) -> None:
        super().__init__(type)
        self.receiver = event_init_dict.receiver
        self.track = event_init_dict.track
        self.streams = list(event_init_dict.streams)
        self.transceiver = event_init_dict.transceiver


class RTCTransformEvent(Event):
    """The ``rtctransform`` event the worker of a :obj:`webrtc.RTCRtpScriptTransform` is called with.

    Args:
        type (:obj:`str`): The name of the event.
        transformer (:obj:`webrtc.RTCRtpScriptTransformer`): The transformer of the transform.
    """

    transformer: webrtc.RTCRtpScriptTransformer

    def __init__(self, type: str, transformer: webrtc.RTCRtpScriptTransformer) -> None:
        super().__init__(type)
        self.transformer = transformer


class KeyFrameRequestEvent(Event):
    """A ``keyframerequest`` event of :obj:`webrtc.RTCRtpScriptTransformer`: the receiver asked for a key frame.

    Args:
        type (:obj:`str`): The name of the event.
        rid (:obj:`str`, optional): The ``rid`` of the layer the key frame is asked for, :obj:`None` for any.
    """

    rid: str | None

    def __init__(self, type: str, rid: str | None = None) -> None:
        super().__init__(type)
        self.rid = rid


@dataclass
class SFrameTransformErrorEventInit(Dictionary):
    """The members of a :obj:`SFrameTransformErrorEvent`.

    Args:
        error_type (:obj:`webrtc.SFrameTransformErrorEventType`): Why the frame didn't decrypt, or its value.
        frame (:obj:`webrtc.RTCEncodedVideoFrame`, :obj:`webrtc.RTCEncodedAudioFrame` or :obj:`bytes`): The frame
            that didn't decrypt, the chunk for a buffer written to an :obj:`webrtc.SFrameDecryptorStream`.
        key_id (:obj:`int`, optional): The unknown key id, for a ``keyID`` error.

    Raises:
        ValueError: If the error type isn't a member of :obj:`webrtc.SFrameTransformErrorEventType`.
    """

    error_type: SFrameTransformErrorEventType | SFrameTransformErrorEventTypeValue
    frame: webrtc.RTCEncodedVideoFrame | webrtc.RTCEncodedAudioFrame | bytes
    key_id: int | None = None

    def __post_init__(self) -> None:
        self.error_type = SFrameTransformErrorEventType(self.error_type)

    #: Alias for :attr:`error_type`
    errorType: ClassVar[Alias[SFrameTransformErrorEventType | SFrameTransformErrorEventTypeValue]] = alias('error_type')
    #: Alias for :attr:`key_id`
    keyID: ClassVar[Alias[int | None]] = alias('key_id')


class SFrameTransformErrorEvent(Event):
    """An ``error`` event of an SFrame decryptor: a frame didn't decrypt, and was dropped.

    It's an event of :obj:`webrtc.RTCRtpSFrameDecryptor` and :obj:`webrtc.SFrameDecryptorStream`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`SFrameTransformErrorEventInit`): The members of the event.
    """

    error_type: SFrameTransformErrorEventType
    key_id: int | None
    frame: webrtc.RTCEncodedVideoFrame | webrtc.RTCEncodedAudioFrame | bytes

    def __init__(self, type: str, event_init_dict: SFrameTransformErrorEventInit) -> None:
        super().__init__(type)
        self.error_type = SFrameTransformErrorEventType(event_init_dict.error_type)
        self.key_id = event_init_dict.key_id
        self.frame = event_init_dict.frame

    #: Alias for :attr:`error_type`
    errorType: ClassVar[Alias[SFrameTransformErrorEventType]] = alias('error_type')
    #: Alias for :attr:`key_id`
    keyID: ClassVar[Alias[int | None]] = alias('key_id')
