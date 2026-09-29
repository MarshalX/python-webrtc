#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTP parameters and capabilities of senders, receivers and transceivers."""

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from webrtc import MediaType, RTCDegradationPreference, RTCPriorityType, TransceiverDirection, wrtc
from webrtc.utils.names import alias

# the bitrate priorities of libwebrtc for RTCRtpEncodingParameters.priority, as Chromium maps them
_BITRATE_PRIORITY = {
    RTCPriorityType.very_low: 0.5,
    RTCPriorityType.low: 1.0,
    RTCPriorityType.medium: 2.0,
    RTCPriorityType.high: 4.0,
}


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


def _codec_members(native: 'wrtc.RtpCodec') -> Dict[str, Any]:
    """The members RTCRtpCodec and RTCRtpCodecParameters share."""
    return {
        'mime_type': native.mimeType,
        'clock_rate': native.clockRate,
        'channels': native.numChannels,
        'sdp_fmtp_line': _format_fmtp(native.parameters),
    }


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
        return cls(**_codec_members(native))

    def _to_native(self, native_class: type):
        """Creates a native codec of a class: ``wrtc.RtpCodec`` or ``wrtc.RtpCodecCapability``."""
        kind, _, name = self.mime_type.partition('/')
        if not name:
            raise ValueError(f'{self.mime_type!r} is not a valid MIME type of a codec')
        native = native_class()
        native.kind = MediaType.video if kind.lower() == 'video' else MediaType.audio
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

    #: Alias for :attr:`mime_type`
    mimeType = alias('mime_type')
    #: Alias for :attr:`clock_rate`
    clockRate = alias('clock_rate')
    #: Alias for :attr:`sdp_fmtp_line`
    sdpFmtpLine = alias('sdp_fmtp_line')


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
        return cls(payload_type=native.payloadType, **_codec_members(native))

    #: Alias for :attr:`payload_type`
    payloadType = alias('payload_type')
    #: Alias for :attr:`mime_type`
    mimeType = alias('mime_type')
    #: Alias for :attr:`clock_rate`
    clockRate = alias('clock_rate')
    #: Alias for :attr:`sdp_fmtp_line`
    sdpFmtpLine = alias('sdp_fmtp_line')


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

    #: Alias for :attr:`reduced_size`
    reducedSize = alias('reduced_size')


@dataclass
class RTCRtpEncodingParameters:
    """An encoding of a sender, one per simulcast layer.

    Args:
        active (:obj:`bool`, optional): Whether the encoding is sent.
        max_bitrate (:obj:`int`, optional): The highest bitrate in bits per second.
        max_framerate (:obj:`float`, optional): The highest frame rate of video.
        rid (:obj:`str`, optional): The RTP stream id of a simulcast layer. Can't be changed once set.
        scale_resolution_down_by (:obj:`float`, optional): How much video is scaled down (at least 1).
        priority (:obj:`webrtc.RTCPriorityType`, optional): The share of the bitrate the encoding gets.
        network_priority (:obj:`webrtc.RTCPriorityType`, optional): The DSCP marking of its packets.
        scalability_mode (:obj:`str`, optional): The SVC mode of video, like ``'L1T3'``.
        adaptive_ptime (:obj:`bool`, optional): Whether audio may use longer packets when bandwidth is low.
        codec (:obj:`webrtc.RTCRtpCodec`, optional): The codec to send with, instead of the negotiated first one.
    """

    active: bool = True
    max_bitrate: Optional[int] = None
    max_framerate: Optional[float] = None
    rid: Optional[str] = None
    scale_resolution_down_by: Optional[float] = None
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
            network_priority=native.networkPriority,
            scalability_mode=native.scalabilityMode,
            adaptive_ptime=native.adaptivePtime,
            codec=RTCRtpCodec._from_native(native.codec) if native.codec is not None else None,
        )

    def _for_kind(self, kind: MediaType) -> 'RTCRtpEncodingParameters':
        """The encoding for a sender of a kind: members of video encodings are ignored for audio, whatever
        their value."""
        if kind == MediaType.video:
            return self
        return dataclasses.replace(self, max_framerate=None, scale_resolution_down_by=None)

    def _apply(self, native: 'wrtc.RtpEncodingParameters') -> 'wrtc.RtpEncodingParameters':
        """:meth:`_to_native` into an existing native encoding: sets the members that can be changed."""
        # the WebIDL types: an [EnforceRange] unsigned long and restricted doubles
        bitrate = self.max_bitrate
        if bitrate is not None and (
            isinstance(bitrate, bool) or not isinstance(bitrate, int) or not 0 <= bitrate < 2**32
        ):
            raise TypeError(f'max_bitrate must be an unsigned 32-bit integer, not {bitrate!r}')
        for name in ('max_framerate', 'scale_resolution_down_by'):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise TypeError(f'{name} must be a finite number, not {value!r}')
        native.active = bool(self.active)
        native.maxBitrate = min(bitrate, 2**31 - 1) if bitrate is not None else None
        native.maxFramerate = self.max_framerate
        native.scaleResolutionDownBy = self.scale_resolution_down_by
        native.bitratePriority = _BITRATE_PRIORITY[RTCPriorityType(self.priority)]
        native.networkPriority = self.network_priority
        native.scalabilityMode = self.scalability_mode
        native.adaptivePtime = bool(self.adaptive_ptime)
        native.codec = self.codec._to_native(wrtc.RtpCodec) if self.codec is not None else None
        return native

    def _to_native(self) -> 'wrtc.RtpEncodingParameters':
        native = self._apply(wrtc.RtpEncodingParameters())
        native.rid = self.rid or ''
        return native

    #: Alias for :attr:`max_bitrate`
    maxBitrate = alias('max_bitrate')
    #: Alias for :attr:`max_framerate`
    maxFramerate = alias('max_framerate')
    #: Alias for :attr:`scale_resolution_down_by`
    scaleResolutionDownBy = alias('scale_resolution_down_by')
    #: Alias for :attr:`network_priority`
    networkPriority = alias('network_priority')
    #: Alias for :attr:`scalability_mode`
    scalabilityMode = alias('scalability_mode')
    #: Alias for :attr:`adaptive_ptime`
    adaptivePtime = alias('adaptive_ptime')


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

    #: Alias for :attr:`header_extensions`
    headerExtensions = alias('header_extensions')


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
        return cls(
            transaction_id=native.transactionId,
            encodings=[RTCRtpEncodingParameters._from_native(e) for e in native.encodings],
            codecs=[RTCRtpCodecParameters._from_native(c) for c in native.codecs],
            header_extensions=[RTCRtpHeaderExtensionParameters._from_native(e) for e in native.headerExtensions],
            rtcp=RTCRtcpParameters(cname=native.rtcp.cname, reduced_size=native.rtcp.reducedSize),
            degradation_preference=native.degradationPreference,
        )

    #: Alias for :attr:`transaction_id`
    transactionId = alias('transaction_id')
    #: Alias for :attr:`header_extensions`
    headerExtensions = alias('header_extensions')
    #: Alias for :attr:`degradation_preference`
    degradationPreference = alias('degradation_preference')


@dataclass
class RTCRtpHeaderExtensionCapability:
    """An RTP header extension that can be negotiated.

    Args:
        uri (:obj:`str`): The URI of the extension.
        direction (:obj:`webrtc.TransceiverDirection`, optional): In which directions it's negotiated,
            :attr:`webrtc.TransceiverDirection.stopped` for not at all.
    """

    uri: str
    direction: TransceiverDirection = TransceiverDirection.sendrecv

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
            # only the URIs: the directions are the ones of a transceiver (see get_header_extensions_to_negotiate)
            header_extensions=[RTCRtpHeaderExtensionCapability(uri=e.uri) for e in native.headerExtensions],
        )

    @classmethod
    def _supported(cls, native_class: type, kind: MediaType) -> Optional['RTCRtpCapabilities']:
        """The capabilities of ``wrtc.RTCRtpSender`` or ``wrtc.RTCRtpReceiver`` for a kind, :obj:`None` for
        another kind."""
        native = native_class.getCapabilities(str(kind))
        return cls._from_native(native) if native is not None else None

    #: Alias for :attr:`header_extensions`
    headerExtensions = alias('header_extensions')
