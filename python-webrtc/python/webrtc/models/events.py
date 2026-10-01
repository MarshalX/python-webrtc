#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Event objects passed to the handlers registered with ``on()`` (see :obj:`webrtc.utils.events.EventTarget`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import webrtc


class Event:
    """An event of a WebRTC object.

    Args:
        type (:obj:`str`): The name of the event, like ``'signalingstatechange'``.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(self, type: str, target: webrtc.EventTarget | None = None) -> None:
        self.type = type
        self.target = target

    def __repr__(self) -> str:
        fields = ', '.join(f'{k}={v!r}' for k, v in vars(self).items() if k != 'target')
        return f'{type(self).__name__}({fields})'


@dataclass(eq=False, repr=False)
class RTCPeerConnectionIceEvent(Event):
    """An ``icecandidate`` event of :obj:`webrtc.RTCPeerConnection`.

    Args:
        type (:obj:`str`): The name of the event.
        candidate (:obj:`webrtc.RTCIceCandidate`, optional): The new candidate, :obj:`None` at the end of candidates.
        url (:obj:`str`, optional): The URL of the STUN or TURN server that gathered the candidate.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    candidate: webrtc.RTCIceCandidate | None = None
    url: str | None = None
    target: webrtc.EventTarget | None = None


@dataclass(eq=False, repr=False)
class RTCPeerConnectionIceErrorEvent(Event):
    """An ``icecandidateerror`` event of :obj:`webrtc.RTCPeerConnection`: a STUN or TURN server failed.

    Args:
        type (:obj:`str`): The name of the event.
        address (:obj:`str`, optional): The local address used to reach the server.
        port (:obj:`int`, optional): The local port used to reach the server.
        url (:obj:`str`): The URL of the server.
        error_code (:obj:`int`): The STUN error code, or 701 if the server couldn't be reached.
        error_text (:obj:`str`): The STUN reason text.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    address: str | None
    port: int | None
    url: str
    error_code: int
    error_text: str
    target: webrtc.EventTarget | None = None

    #: Alias for :attr:`error_code`
    errorCode: ClassVar[Alias[int]] = alias('error_code')
    #: Alias for :attr:`error_text`
    errorText: ClassVar[Alias[str]] = alias('error_text')


@dataclass(eq=False, repr=False)
class MessageEvent(Event):
    """A ``message`` event of :obj:`webrtc.RTCDataChannel`.

    Args:
        type (:obj:`str`): The name of the event.
        data (:obj:`str`, :obj:`bytes` or :obj:`webrtc.Blob`): The message, :obj:`bytes` (or a :obj:`webrtc.Blob`
            with the ``blob`` binary type) if it was sent as binary.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    data: str | bytes | webrtc.Blob
    target: webrtc.EventTarget | None = None


@dataclass(eq=False, repr=False)
class RTCDataChannelEvent(Event):
    """A ``datachannel`` event of :obj:`webrtc.RTCPeerConnection`: the remote peer created a channel.

    Args:
        type (:obj:`str`): The name of the event.
        channel (:obj:`webrtc.RTCDataChannel`): The new channel.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    channel: webrtc.RTCDataChannel
    target: webrtc.EventTarget | None = None


@dataclass(eq=False, repr=False)
class MediaStreamTrackEvent(Event):
    """An ``addtrack`` or ``removetrack`` event of :obj:`webrtc.MediaStream`.

    Args:
        type (:obj:`str`): The name of the event.
        track (:obj:`webrtc.MediaStreamTrack`): The track added or removed.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    track: webrtc.MediaStreamTrack
    target: webrtc.EventTarget | None = None


@dataclass(eq=False, repr=False)
class RTCDTMFToneChangeEvent(Event):
    """A ``tonechange`` event of :obj:`webrtc.RTCDTMFSender`.

    Args:
        type (:obj:`str`): The name of the event.
        tone (:obj:`str`): The tone that started playing, empty when all tones were played.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    tone: str = ''
    target: webrtc.EventTarget | None = None


@dataclass(eq=False, repr=False)
class RTCErrorEvent(Event):
    """An ``error`` event, carrying the :obj:`webrtc.RTCError` that occurred.

    Args:
        type (:obj:`str`): The name of the event.
        error (:obj:`webrtc.RTCError`): The error.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    error: webrtc.RTCError
    target: webrtc.EventTarget | None = None


@dataclass(eq=False, repr=False)
class RTCTrackEvent(Event):
    """A ``track`` event of :obj:`webrtc.RTCPeerConnection`: a remote track was negotiated.

    Args:
        type (:obj:`str`): The name of the event.
        receiver (:obj:`webrtc.RTCRtpReceiver`): The receiver of the track.
        track (:obj:`webrtc.MediaStreamTrack`): The remote track.
        streams (:obj:`list` of :obj:`webrtc.MediaStream`): The remote streams of the track.
        transceiver (:obj:`webrtc.RTCRtpTransceiver`): The transceiver of the receiver.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    type: str
    receiver: webrtc.RTCRtpReceiver
    track: webrtc.MediaStreamTrack
    streams: list[webrtc.MediaStream]
    transceiver: webrtc.RTCRtpTransceiver
    target: webrtc.EventTarget | None = None
