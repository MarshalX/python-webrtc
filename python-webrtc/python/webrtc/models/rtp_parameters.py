#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTP parameters and capabilities of senders, receivers and transceivers."""

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import wrtc
from webrtc.interfaces.rtc_data_channel import RTCPriorityType

# the bitrate priorities of libwebrtc for RTCRtpEncodingParameters.priority, as Chromium maps them
_BITRATE_PRIORITY = {
    RTCPriorityType.very_low: 0.5,
    RTCPriorityType.low: 1.0,
    RTCPriorityType.medium: 2.0,
    RTCPriorityType.high: 4.0,
}


class RTCDegradationPreference(str, enum.Enum):
    """What a video sender degrades first when it can't keep up."""

    maintain_framerate = 'maintain-framerate'
    maintain_resolution = 'maintain-resolution'
    balanced = 'balanced'
    maintain_framerate_and_resolution = 'maintain-framerate-and-resolution'


def _parse_fmtp(line: Optional[str]) -> Dict[str, str]:
    parameters = {}
    for item in (line or '').split(';'):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            key, _, value = item.partition('=')
            parameters[key.strip()] = value.strip()
        else:
            # a parameter that isn't a name-value pair, like the payload types of RED, has no name in libwebrtc
            parameters[''] = item
    return parameters


def _format_fmtp(parameters: Dict[str, str]) -> Optional[str]:
    if not parameters:
        return None
    return ';'.join(f'{key}={value}' if key else value for key, value in parameters.items())


@dataclass
class RTCRtpCodec:
    """A codec.

    Args:
        mime_type (:obj:`str`): The type and subtype of the codec, like ``'audio/opus'``.
        clock_rate (:obj:`int`): The clock rate in Hz.
        channels (:obj:`int`, optional): The number of audio channels.
        sdp_fmtp_line (:obj:`str`, optional): The parameters of the codec, as in the ``a=fmtp`` line of SDP,
            like ``'minptime=10;useinbandfec=1'``.
    """

    mime_type: str
    clock_rate: int
    channels: Optional[int] = None
    sdp_fmtp_line: Optional[str] = None

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpCodec') -> 'RTCRtpCodec':
        return cls(
            mime_type=native.mimeType,
            clock_rate=native.clockRate,
            channels=native.numChannels,
            sdp_fmtp_line=_format_fmtp(native.parameters),
        )

    def _to_native(self, native_class=wrtc.RtpCodecCapability):
        kind, _, name = self.mime_type.partition('/')
        if not name:
            raise ValueError(f'{self.mime_type!r} is not a valid MIME type of a codec')
        native = native_class()
        native.kind = wrtc.MediaType.video if kind.lower() == 'video' else wrtc.MediaType.audio
        native.name = name
        native.clockRate = self.clock_rate
        native.numChannels = self.channels
        native.parameters = _parse_fmtp(self.sdp_fmtp_line)
        return native

    def _matches(self, other: 'RTCRtpCodec') -> bool:
        # codecs match with a case-insensitive MIME type and the same parameters, in any order
        return (
            self.mime_type.lower() == other.mime_type.lower()
            and self.clock_rate == other.clock_rate
            and (self.channels or 1) == (other.channels or 1)
            and _parse_fmtp(self.sdp_fmtp_line) == _parse_fmtp(other.sdp_fmtp_line)
        )


@dataclass
class RTCRtpCodecParameters:
    """A codec negotiated for a sender or a receiver.

    Args:
        payload_type (:obj:`int`): The RTP payload type of the codec.
        mime_type (:obj:`str`): The type and subtype of the codec, like ``'audio/opus'``.
        clock_rate (:obj:`int`): The clock rate in Hz.
        channels (:obj:`int`, optional): The number of audio channels.
        sdp_fmtp_line (:obj:`str`, optional): The parameters of the codec, as in the ``a=fmtp`` line of SDP.
    """

    payload_type: int
    mime_type: str
    clock_rate: int
    channels: Optional[int] = None
    sdp_fmtp_line: Optional[str] = None

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpCodecParameters') -> 'RTCRtpCodecParameters':
        return cls(
            payload_type=native.payloadType,
            mime_type=native.mimeType,
            clock_rate=native.clockRate,
            channels=native.numChannels,
            sdp_fmtp_line=_format_fmtp(native.parameters),
        )


@dataclass
class RTCRtpHeaderExtensionParameters:
    """An RTP header extension negotiated for a sender or a receiver.

    Args:
        uri (:obj:`str`): The URI of the extension.
        id (:obj:`int`): The id used in RTP packets.
        encrypted (:obj:`bool`, optional): Whether the extension is encrypted.
    """

    uri: str
    id: int
    encrypted: bool = False

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpExtension') -> 'RTCRtpHeaderExtensionParameters':
        return cls(uri=native.uri, id=native.id, encrypted=native.encrypt)


@dataclass
class RTCRtcpParameters:
    """RTCP parameters of a sender or a receiver.

    Args:
        cname (:obj:`str`, optional): The canonical name used in RTCP, only known for senders.
        reduced_size (:obj:`bool`, optional): Whether reduced-size RTCP is negotiated.
    """

    cname: Optional[str] = None
    reduced_size: Optional[bool] = None


@dataclass
class RTCRtpEncodingParameters:
    """An encoding of a sender, one per simulcast layer.

    Args:
        active (:obj:`bool`, optional): Whether the encoding is sent.
        max_bitrate (:obj:`int`, optional): The highest bitrate in bits per second.
        max_framerate (:obj:`float`, optional): The highest frame rate of video.
        scale_resolution_down_by (:obj:`float`, optional): How much video is scaled down (at least 1).
        rid (:obj:`str`, optional): The RTP stream id of a simulcast layer. Can't be changed once set.
        priority (:obj:`webrtc.RTCPriorityType`, optional): The share of the bitrate the encoding gets.
        network_priority (:obj:`webrtc.RTCPriorityType`, optional): The DSCP marking of its packets.
        scalability_mode (:obj:`str`, optional): The SVC mode of video, like ``'L1T3'``.
        adaptive_ptime (:obj:`bool`, optional): Whether audio may use longer packets when bandwidth is low.
        codec (:obj:`webrtc.RTCRtpCodec`, optional): The codec to send with, instead of the negotiated first one.
    """

    active: bool = True
    max_bitrate: Optional[int] = None
    max_framerate: Optional[float] = None
    scale_resolution_down_by: Optional[float] = None
    rid: Optional[str] = None
    priority: RTCPriorityType = RTCPriorityType.low
    network_priority: RTCPriorityType = RTCPriorityType.low
    scalability_mode: Optional[str] = None
    adaptive_ptime: bool = False
    codec: Optional[RTCRtpCodec] = None

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpEncodingParameters') -> 'RTCRtpEncodingParameters':
        priority = min(_BITRATE_PRIORITY, key=lambda p: abs(_BITRATE_PRIORITY[p] - native.bitratePriority))
        return cls(
            active=native.active,
            max_bitrate=native.maxBitrate,
            max_framerate=native.maxFramerate,
            scale_resolution_down_by=native.scaleResolutionDownBy,
            rid=native.rid or None,
            priority=priority,
            network_priority=RTCPriorityType(native.networkPriority.name.replace('_', '-')),
            scalability_mode=native.scalabilityMode,
            adaptive_ptime=native.adaptivePtime,
            codec=RTCRtpCodec._from_native(native.codec) if native.codec is not None else None,
        )

    def _apply(self, native: 'wrtc.RtpEncodingParameters') -> 'wrtc.RtpEncodingParameters':
        """Sets the members that can be set on a native encoding"""
        native.active = bool(self.active)
        native.maxBitrate = self.max_bitrate
        native.maxFramerate = self.max_framerate
        native.scaleResolutionDownBy = self.scale_resolution_down_by
        native.bitratePriority = _BITRATE_PRIORITY[RTCPriorityType(self.priority)]
        native.networkPriority = getattr(wrtc.NativePriority, RTCPriorityType(self.network_priority).name)
        native.scalabilityMode = self.scalability_mode
        native.adaptivePtime = bool(self.adaptive_ptime)
        native.codec = self.codec._to_native(wrtc.RtpCodec) if self.codec is not None else None
        return native

    def _to_native(self) -> 'wrtc.RtpEncodingParameters':
        native = self._apply(wrtc.RtpEncodingParameters())
        native.rid = self.rid or ''
        return native


@dataclass
class RTCRtpReceiveParameters:
    """The parameters a receiver receives with.

    Args:
        codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodecParameters`): The codecs it can receive.
        header_extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionParameters`): The header extensions.
        rtcp (:obj:`webrtc.RTCRtcpParameters`): The RTCP parameters.
    """

    codecs: List[RTCRtpCodecParameters] = field(default_factory=list)
    header_extensions: List[RTCRtpHeaderExtensionParameters] = field(default_factory=list)
    rtcp: RTCRtcpParameters = field(default_factory=RTCRtcpParameters)

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpParameters') -> 'RTCRtpReceiveParameters':
        return cls(
            codecs=[RTCRtpCodecParameters._from_native(c) for c in native.codecs],
            header_extensions=[RTCRtpHeaderExtensionParameters._from_native(e) for e in native.headerExtensions],
            rtcp=RTCRtcpParameters(reduced_size=native.rtcp.reducedSize),
        )


@dataclass
class RTCRtpSendParameters:
    """The parameters a sender sends with, from :meth:`webrtc.RTCRtpSender.get_parameters`.

    Only :attr:`encodings` (all but their ``rid``) and :attr:`degradation_preference` can be changed with
    :meth:`webrtc.RTCRtpSender.set_parameters`.

    Args:
        transaction_id (:obj:`str`): Identifies the call of ``get_parameters`` the parameters come from.
        encodings (:obj:`list` of :obj:`webrtc.RTCRtpEncodingParameters`): The encodings.
        codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodecParameters`): The negotiated codecs.
        header_extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionParameters`): The header extensions.
        rtcp (:obj:`webrtc.RTCRtcpParameters`): The RTCP parameters.
        degradation_preference (:obj:`webrtc.RTCDegradationPreference`, optional): What video degrades first.
    """

    transaction_id: str
    encodings: List[RTCRtpEncodingParameters] = field(default_factory=list)
    codecs: List[RTCRtpCodecParameters] = field(default_factory=list)
    header_extensions: List[RTCRtpHeaderExtensionParameters] = field(default_factory=list)
    rtcp: RTCRtcpParameters = field(default_factory=RTCRtcpParameters)
    degradation_preference: Optional[RTCDegradationPreference] = None

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpParameters') -> 'RTCRtpSendParameters':
        preference = native.degradationPreference
        return cls(
            transaction_id=native.transactionId,
            encodings=[RTCRtpEncodingParameters._from_native(e) for e in native.encodings],
            codecs=[RTCRtpCodecParameters._from_native(c) for c in native.codecs],
            header_extensions=[RTCRtpHeaderExtensionParameters._from_native(e) for e in native.headerExtensions],
            rtcp=RTCRtcpParameters(cname=native.rtcp.cname, reduced_size=native.rtcp.reducedSize),
            degradation_preference=(
                RTCDegradationPreference(preference.name.replace('_', '-')) if preference is not None else None
            ),
        )


@dataclass
class RTCRtpHeaderExtensionCapability:
    """An RTP header extension that can be negotiated.

    Args:
        uri (:obj:`str`): The URI of the extension.
        direction (:obj:`webrtc.TransceiverDirection`, optional): In which directions it's negotiated,
            :attr:`webrtc.TransceiverDirection.stopped` for not at all.
    """

    uri: str
    direction: 'wrtc.TransceiverDirection' = wrtc.TransceiverDirection.sendrecv

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpHeaderExtensionCapability') -> 'RTCRtpHeaderExtensionCapability':
        return cls(uri=native.uri, direction=native.direction)


@dataclass
class RTCRtpCapabilities:
    """The codecs and header extensions a sender or a receiver supports.

    Args:
        codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodec`): The codecs.
        header_extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`): The header extensions.
    """

    codecs: List[RTCRtpCodec] = field(default_factory=list)
    header_extensions: List[RTCRtpHeaderExtensionCapability] = field(default_factory=list)

    @classmethod
    def _from_native(cls, native: 'wrtc.RtpCapabilities') -> 'RTCRtpCapabilities':
        return cls(
            codecs=[RTCRtpCodec._from_native(c) for c in native.codecs],
            header_extensions=[
                RTCRtpHeaderExtensionCapability(uri=e.uri, direction=wrtc.TransceiverDirection.sendrecv)
                for e in native.headerExtensions
            ],
        )
