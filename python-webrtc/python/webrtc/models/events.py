#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Event objects passed to the handlers registered with ``on()`` (see :obj:`webrtc.utils.events.EventTarget`)."""

from typing import TYPE_CHECKING, Any, List, Optional, Union

if TYPE_CHECKING:
    import webrtc


class Event:
    """An event of a WebRTC object.

    Args:
        type (:obj:`str`): The name of the event, like ``'signalingstatechange'``.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(self, type: str, target: Any = None):
        self.type = type
        self.target = target

    def __repr__(self):
        fields = ', '.join(f'{k}={v!r}' for k, v in vars(self).items() if k != 'target')
        return f'{type(self).__name__}({fields})'


class RTCPeerConnectionIceEvent(Event):
    """An ``icecandidate`` event of :obj:`webrtc.RTCPeerConnection`.

    Args:
        type (:obj:`str`): The name of the event.
        candidate (:obj:`webrtc.RTCIceCandidate`, optional): The new candidate, :obj:`None` at the end of candidates.
        url (:obj:`str`, optional): The URL of the STUN or TURN server that gathered the candidate.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(
        self,
        type: str,
        candidate: Optional['webrtc.RTCIceCandidate'] = None,
        url: Optional[str] = None,
        target: Any = None,
    ):
        super().__init__(type, target)
        self.candidate = candidate
        self.url = url


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

    def __init__(
        self,
        type: str,
        address: Optional[str],
        port: Optional[int],
        url: str,
        error_code: int,
        error_text: str,
        target: Any = None,
    ):
        super().__init__(type, target)
        self.address = address
        self.port = port
        self.url = url
        self.error_code = error_code
        self.error_text = error_text


class MessageEvent(Event):
    """A ``message`` event of :obj:`webrtc.RTCDataChannel`.

    Args:
        type (:obj:`str`): The name of the event.
        data (:obj:`str` or :obj:`bytes`): The message, :obj:`bytes` if it was sent as binary.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(self, type: str, data: Union[str, bytes], target: Any = None):
        super().__init__(type, target)
        self.data = data


class RTCDataChannelEvent(Event):
    """A ``datachannel`` event of :obj:`webrtc.RTCPeerConnection`: the remote peer created a channel.

    Args:
        type (:obj:`str`): The name of the event.
        channel (:obj:`webrtc.RTCDataChannel`): The new channel.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(self, type: str, channel: 'webrtc.RTCDataChannel', target: Any = None):
        super().__init__(type, target)
        self.channel = channel


class MediaStreamTrackEvent(Event):
    """An ``addtrack`` or ``removetrack`` event of :obj:`webrtc.MediaStream`.

    Args:
        type (:obj:`str`): The name of the event.
        track (:obj:`webrtc.MediaStreamTrack`): The track added or removed.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(self, type: str, track: 'webrtc.MediaStreamTrack', target: Any = None):
        super().__init__(type, target)
        self.track = track


class RTCDTMFToneChangeEvent(Event):
    """A ``tonechange`` event of :obj:`webrtc.RTCDTMFSender`.

    Args:
        type (:obj:`str`): The name of the event.
        tone (:obj:`str`): The tone that started playing, empty when all tones were played.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(self, type: str, tone: str = '', target: Any = None):
        super().__init__(type, target)
        self.tone = tone


class RTCErrorEvent(Event):
    """An ``error`` event, carrying the :obj:`webrtc.RTCError` that occurred.

    Args:
        type (:obj:`str`): The name of the event.
        error (:obj:`webrtc.RTCError`): The error.
        target (:obj:`object`, optional): The object that emitted the event.
    """

    def __init__(self, type: str, error: 'webrtc.RTCError', target: Any = None):
        super().__init__(type, target)
        self.error = error


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

    def __init__(
        self,
        type: str,
        receiver: 'webrtc.RTCRtpReceiver',
        track: 'webrtc.MediaStreamTrack',
        streams: List['webrtc.MediaStream'],
        transceiver: 'webrtc.RTCRtpTransceiver',
        target: Any = None,
    ):
        super().__init__(type, target)
        self.receiver = receiver
        self.track = track
        self.streams = streams
        self.transceiver = transceiver
