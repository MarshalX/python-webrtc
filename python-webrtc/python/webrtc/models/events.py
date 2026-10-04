#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The event objects that :obj:`webrtc.EventTarget` handlers are called with, and their init dictionaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from typing_extensions import Never

from webrtc.enums import SFrameTransformErrorEventType
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc
    from webrtc.enums import SFrameTransformErrorEventTypeValue


class Event:
    """An event of a WebRTC object. Events that carry nothing but their name are of this class.

    See :mdn:`Event`.

    Args:
        type (:obj:`str`): The name of the event, like ``'signalingstatechange'``.

    Attributes:
        type (:obj:`str`): The name of the event. See :mdn:`Event/type`.
        target (:obj:`webrtc.EventTarget`, optional): The object that emitted the event, or :obj:`None` until
            it's dispatched. See :mdn:`Event/target`.
    """

    def __init__(self, type: str) -> None:
        self.type = type
        self.target: webrtc.EventTarget[Never] | None = None

    def __repr__(self) -> str:
        fields = ', '.join(f'{k}={v!r}' for k, v in vars(self).items() if k != 'target')
        return f'{type(self).__name__}({fields})'


@dataclass
class RTCPeerConnectionIceEventInit(Dictionary):
    """The members of an :obj:`RTCPeerConnectionIceEvent`.

    See :mdn:`RTCPeerConnectionIceEvent/RTCPeerConnectionIceEvent`.

    Args:
        candidate (:obj:`webrtc.RTCIceCandidate`, optional): The gathered candidate, or :obj:`None` when gathering
            has ended.
        url (:obj:`str`, optional): The address of the STUN or TURN server that found the candidate.
    """

    candidate: webrtc.RTCIceCandidate | None = None
    url: str | None = None


class RTCPeerConnectionIceEvent(Event):
    """An ``icecandidate`` event of :obj:`webrtc.RTCPeerConnection` or :obj:`webrtc.RTCIceTransport`.

    It's fired when a candidate is gathered and should be sent to the remote peer. The last event has no candidate
    and marks the end of gathering.

    See :mdn:`RTCPeerConnectionIceEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCPeerConnectionIceEventInit`, optional): The members of the event.
    """

    #: :obj:`webrtc.RTCIceCandidate`, optional: The gathered candidate, or :obj:`None` when gathering has ended.
    #: See :mdn:`RTCPeerConnectionIceEvent/candidate`.
    candidate: webrtc.RTCIceCandidate | None
    #: :obj:`str`, optional: The address of the STUN or TURN server that found the candidate. Events of an
    #: :obj:`webrtc.RTCIceTransport` don't set it. See :mdn:`RTCPeerConnectionIceEvent/url`.
    url: str | None

    def __init__(self, type: str, event_init_dict: RTCPeerConnectionIceEventInit | None = None) -> None:
        super().__init__(type)
        init = event_init_dict if event_init_dict is not None else RTCPeerConnectionIceEventInit()
        self.candidate = init.candidate
        self.url = init.url


@dataclass
class RTCPeerConnectionIceErrorEventInit(Dictionary):
    """The members of an :obj:`RTCPeerConnectionIceErrorEvent`.

    See :mdn:`RTCPeerConnectionIceErrorEvent/RTCPeerConnectionIceErrorEvent`.

    Args:
        error_code (:obj:`int`): The STUN or TURN error code, or 701 if the server couldn't be reached.
        address (:obj:`str`, optional): The local address the server was contacted from.
        port (:obj:`int`, optional): The local port the server was contacted from.
        url (:obj:`str`, optional): The URL of the server.
        error_text (:obj:`str`, optional): The reason text of the server's response.
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
    """An ``icecandidateerror`` event of :obj:`webrtc.RTCPeerConnection`.

    It's fired when gathering from a STUN or TURN server fails. Gathering goes on with the other servers and
    interfaces.

    See :mdn:`RTCPeerConnectionIceErrorEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCPeerConnectionIceErrorEventInit`): The members of the event.
    """

    #: :obj:`str`, optional: The local address the server was contacted from, or :obj:`None` if it isn't known.
    #: See :mdn:`RTCPeerConnectionIceErrorEvent/address`.
    address: str | None
    #: :obj:`int`, optional: The local port the server was contacted from, or :obj:`None` if it isn't known.
    #: See :mdn:`RTCPeerConnectionIceErrorEvent/port`.
    port: int | None
    #: :obj:`str`: The URL of the server. See :mdn:`RTCPeerConnectionIceErrorEvent/url`.
    url: str
    #: :obj:`int`: The STUN or TURN error code, or 701 if the server couldn't be reached.
    #: See :mdn:`RTCPeerConnectionIceErrorEvent/errorCode`.
    error_code: int
    #: :obj:`str`: The reason text of the server's response. See :mdn:`RTCPeerConnectionIceErrorEvent/errorText`.
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
    """A ``message`` event of :obj:`webrtc.RTCDataChannel`, fired when a message is received.

    See :mdn:`MessageEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        data (:obj:`str`, :obj:`bytes` or :obj:`webrtc.Blob`): The message.
    """

    #: :obj:`str`, :obj:`bytes` or :obj:`webrtc.Blob`: The message. It's a :obj:`str` if it was sent as text.
    #: Otherwise it's :obj:`bytes`, or a :obj:`webrtc.Blob` with the ``blob`` binary type.
    #: See :mdn:`MessageEvent/data`.
    data: str | bytes | webrtc.Blob

    def __init__(self, type: str, data: str | bytes | webrtc.Blob) -> None:
        super().__init__(type)
        self.data = data


@dataclass
class RTCDataChannelEventInit(Dictionary):
    """The members of an :obj:`RTCDataChannelEvent`.

    See :mdn:`RTCDataChannelEvent/RTCDataChannelEvent`.

    Args:
        channel (:obj:`webrtc.RTCDataChannel`): The channel the remote peer created.
    """

    channel: webrtc.RTCDataChannel


class RTCDataChannelEvent(Event):
    """A ``datachannel`` event of :obj:`webrtc.RTCPeerConnection`, fired when the remote peer creates a channel.

    See :mdn:`RTCDataChannelEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCDataChannelEventInit`): The members of the event.
    """

    #: :obj:`webrtc.RTCDataChannel`: The channel the remote peer created. See :mdn:`RTCDataChannelEvent/channel`.
    channel: webrtc.RTCDataChannel

    def __init__(self, type: str, event_init_dict: RTCDataChannelEventInit) -> None:
        super().__init__(type)
        self.channel = event_init_dict.channel


@dataclass
class MediaStreamTrackEventInit(Dictionary):
    """The members of a :obj:`MediaStreamTrackEvent`.

    See :mdn:`MediaStreamTrackEvent/MediaStreamTrackEvent`.

    Args:
        track (:obj:`webrtc.MediaStreamTrack`): The track added to or removed from the stream.
    """

    track: webrtc.MediaStreamTrack


class MediaStreamTrackEvent(Event):
    """An ``addtrack`` or ``removetrack`` event of :obj:`webrtc.MediaStream`.

    It's fired when the remote peer changes the tracks of the stream.

    See :mdn:`MediaStreamTrackEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`MediaStreamTrackEventInit`): The members of the event.
    """

    #: :obj:`webrtc.MediaStreamTrack`: The track added to or removed from the stream.
    #: See :mdn:`MediaStreamTrackEvent/track`.
    track: webrtc.MediaStreamTrack

    def __init__(self, type: str, event_init_dict: MediaStreamTrackEventInit) -> None:
        super().__init__(type)
        self.track = event_init_dict.track


@dataclass
class RTCDTMFToneChangeEventInit(Dictionary):
    """The members of an :obj:`RTCDTMFToneChangeEvent`.

    See :mdn:`RTCDTMFToneChangeEvent/RTCDTMFToneChangeEvent`.

    Args:
        tone (:obj:`str`, optional): The tone that started playing, or empty when the queue ran out.
    """

    tone: str = ''


class RTCDTMFToneChangeEvent(Event):
    """A ``tonechange`` event of :obj:`webrtc.RTCDTMFSender`, fired when a tone starts playing or the queue runs out.

    See :mdn:`RTCDTMFToneChangeEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCDTMFToneChangeEventInit`, optional): The members of the event.
    """

    #: :obj:`str`: The tone that started playing, like ``'1'``, or ``','`` for a pause. It's empty when the queue
    #: ran out. See :mdn:`RTCDTMFToneChangeEvent/tone`.
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

    It's never fired, because the devices of this library are fixed.

    See :mdn:`MediaDevices/devicechange_event`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`DeviceChangeEventInit`, optional): The members of the event.
    """

    #: :obj:`list` of :obj:`webrtc.MediaDeviceInfo`: The devices after the change.
    devices: list[webrtc.MediaDeviceInfo]
    #: :obj:`list` of :obj:`webrtc.MediaDeviceInfo`: The devices the user connected. It's always empty.
    user_inserted_devices: list[webrtc.MediaDeviceInfo]

    def __init__(self, type: str, event_init_dict: DeviceChangeEventInit | None = None) -> None:
        super().__init__(type)
        self.devices = list(event_init_dict.devices) if event_init_dict is not None else []
        self.user_inserted_devices = []

    #: Alias for :attr:`user_inserted_devices`
    userInsertedDevices: ClassVar[Alias[list[webrtc.MediaDeviceInfo]]] = alias('user_inserted_devices')


@dataclass
class RTCErrorEventInit(Dictionary):
    """The members of an :obj:`RTCErrorEvent`.

    See :mdn:`RTCErrorEvent/RTCErrorEvent`.

    Args:
        error (:obj:`webrtc.RTCError`): The error that occurred.
    """

    error: webrtc.RTCError


class RTCErrorEvent(Event):
    """An ``error`` event of :obj:`webrtc.RTCDataChannel` or :obj:`webrtc.RTCDtlsTransport`.

    See :mdn:`RTCErrorEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCErrorEventInit`): The members of the event.
    """

    #: :obj:`webrtc.RTCError`: The error that occurred, with its detail. See :mdn:`RTCErrorEvent/error`.
    error: webrtc.RTCError

    def __init__(self, type: str, event_init_dict: RTCErrorEventInit) -> None:
        super().__init__(type)
        self.error = event_init_dict.error


@dataclass
class RTCTrackEventInit(Dictionary):
    """The members of an :obj:`RTCTrackEvent`.

    See :mdn:`RTCTrackEvent/RTCTrackEvent`.

    Args:
        receiver (:obj:`webrtc.RTCRtpReceiver`): The receiver of the track.
        track (:obj:`webrtc.MediaStreamTrack`): The remote track.
        transceiver (:obj:`webrtc.RTCRtpTransceiver`): The transceiver of the receiver.
        streams (:obj:`list` of :obj:`webrtc.MediaStream`, optional): The remote streams the track is in.
    """

    receiver: webrtc.RTCRtpReceiver
    track: webrtc.MediaStreamTrack
    transceiver: webrtc.RTCRtpTransceiver
    streams: list[webrtc.MediaStream] = field(default_factory=list)


class RTCTrackEvent(Event):
    """A ``track`` event of :obj:`webrtc.RTCPeerConnection`, fired when a remote description adds a track to receive.

    See :mdn:`RTCTrackEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`RTCTrackEventInit`): The members of the event.
    """

    #: :obj:`webrtc.RTCRtpReceiver`: The receiver of the track. See :mdn:`RTCTrackEvent/receiver`.
    receiver: webrtc.RTCRtpReceiver
    #: :obj:`webrtc.MediaStreamTrack`: The remote track. See :mdn:`RTCTrackEvent/track`.
    track: webrtc.MediaStreamTrack
    #: :obj:`list` of :obj:`webrtc.MediaStream`: The remote streams the track is in. See :mdn:`RTCTrackEvent/streams`.
    streams: list[webrtc.MediaStream]
    #: :obj:`webrtc.RTCRtpTransceiver`: The transceiver of the receiver. See :mdn:`RTCTrackEvent/transceiver`.
    transceiver: webrtc.RTCRtpTransceiver

    def __init__(self, type: str, event_init_dict: RTCTrackEventInit) -> None:
        super().__init__(type)
        self.receiver = event_init_dict.receiver
        self.track = event_init_dict.track
        self.streams = list(event_init_dict.streams)
        self.transceiver = event_init_dict.transceiver


class RTCTransformEvent(Event):
    """The ``rtctransform`` event the worker of a :obj:`webrtc.RTCRtpScriptTransform` is called with.

    The worker is a Python callable that runs on the event loop. There is no worker script.

    See :mdn:`RTCTransformEvent`.

    Args:
        type (:obj:`str`): The name of the event.
        transformer (:obj:`webrtc.RTCRtpScriptTransformer`): The transformer of the transform.
    """

    #: :obj:`webrtc.RTCRtpScriptTransformer`: The transformer, with the streams of frames to transform.
    #: See :mdn:`RTCTransformEvent/transformer`.
    transformer: webrtc.RTCRtpScriptTransformer

    def __init__(self, type: str, transformer: webrtc.RTCRtpScriptTransformer) -> None:
        super().__init__(type)
        self.transformer = transformer


class KeyFrameRequestEvent(Event):
    """A ``keyframerequest`` event of :obj:`webrtc.RTCRtpScriptTransformer`.

    It's fired when the remote peer asks for a key frame.

    Args:
        type (:obj:`str`): The name of the event.
        rid (:obj:`str`, optional): The ``rid`` of the layer the key frame is asked for, or :obj:`None` for any layer.
    """

    #: :obj:`str`, optional: The ``rid`` of the layer the key frame is asked for, or :obj:`None` for any layer.
    rid: str | None

    def __init__(self, type: str, rid: str | None = None) -> None:
        super().__init__(type)
        self.rid = rid


@dataclass
class SFrameTransformErrorEventInit(Dictionary):
    """The members of an :obj:`SFrameTransformErrorEvent`.

    Args:
        error_type (:obj:`webrtc.SFrameTransformErrorEventType`): Why the frame didn't decrypt, as a member or its
            string value.
        frame (:obj:`webrtc.RTCEncodedVideoFrame`, :obj:`webrtc.RTCEncodedAudioFrame` or :obj:`bytes`): The frame
            that didn't decrypt. For a buffer written to an :obj:`webrtc.SFrameDecryptorStream`, it's the chunk.
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
    """An ``error`` event of an SFrame decryptor, fired when a frame doesn't decrypt and is dropped.

    It's an event of :obj:`webrtc.RTCRtpSFrameDecryptor` and :obj:`webrtc.SFrameDecryptorStream`.

    Args:
        type (:obj:`str`): The name of the event.
        event_init_dict (:obj:`SFrameTransformErrorEventInit`): The members of the event.
    """

    #: :obj:`webrtc.SFrameTransformErrorEventType`: Why the frame didn't decrypt.
    error_type: SFrameTransformErrorEventType
    #: :obj:`int`, optional: The unknown key id for a ``keyID`` error, or :obj:`None` otherwise.
    key_id: int | None
    #: :obj:`webrtc.RTCEncodedVideoFrame`, :obj:`webrtc.RTCEncodedAudioFrame` or :obj:`bytes`: The dropped frame.
    #: For a buffer written to an :obj:`webrtc.SFrameDecryptorStream`, it's the chunk.
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
