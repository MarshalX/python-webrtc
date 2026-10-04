#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTP parameters and capabilities of senders, receivers and transceivers."""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, TypeVar

from typing_extensions import TypedDict

from webrtc import MediaType, RTCDegradationPreference, RTCPriorityType, RTCRtpTransceiverDirection, wrtc
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from webrtc.enums import (
        MediaTypeValue,
        RTCDegradationPreferenceValue,
        RTCPriorityTypeValue,
        RTCRtpTransceiverDirectionValue,
    )

_NativeCodecT = TypeVar('_NativeCodecT', bound='wrtc.RtpCodec')

# the bitrate priorities of libwebrtc for RTCRtpEncodingParameters.priority, as Chromium maps them
_BITRATE_PRIORITY = {
    RTCPriorityType.very_low: 0.5,
    RTCPriorityType.low: 1.0,
    RTCPriorityType.medium: 2.0,
    RTCPriorityType.high: 4.0,
}


def _is_unsigned_long(value: object) -> bool:
    """Whether a value is an [EnforceRange] unsigned long of WebIDL."""
    return not isinstance(value, bool) and isinstance(value, int) and 0 <= value < 2**32


def _parse_fmtp(line: str | None) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for raw_item in (line if line is not None else '').split(';'):
        item = raw_item.strip()
        if item == '':
            continue
        if '=' in item:
            key, _, value = item.partition('=')
            parameters[key.strip()] = value.strip()
        else:
            # a parameter that isn't a name-value pair, like the payload types of RED, has no name in libwebrtc
            parameters[''] = item
    return parameters


def _format_fmtp(parameters: dict[str, str]) -> str | None:
    if len(parameters) == 0:
        return None
    return ';'.join(f'{key}={value}' if key != '' else value for key, value in parameters.items())


class _CodecMembers(TypedDict, closed=True):
    mime_type: str
    clock_rate: int
    channels: int | None
    sdp_fmtp_line: str | None


def _channels_or_one(channels: int | None) -> int:
    return channels if channels is not None and channels != 0 else 1


def _codec_members(native: wrtc.RtpCodec) -> _CodecMembers:
    """The members RTCRtpCodec and RTCRtpCodecParameters share."""
    clock_rate = native.clockRate
    # libwebrtc sets it for every codec it reports, while the specification requires it
    if clock_rate is None:
        msg = f'{native.mimeType} has no clock rate'
        raise ValueError(msg)
    return {
        'mime_type': native.mimeType,
        'clock_rate': clock_rate,
        'channels': native.numChannels,
        'sdp_fmtp_line': _format_fmtp(native.parameters),
    }


@dataclass
class RTCRtpCodec(Dictionary):
    """A codec a sender or a receiver supports, or the one an encoding sends with.

    Codecs given to the library match a supported one by MIME type (ignoring case), clock rate, channels and fmtp
    parameters (in any order).

    See :mdn:`RTCRtpSender/getCapabilities_static`.

    Args:
        mime_type (:obj:`str`): The type and subtype of the codec, like ``'audio/opus'``.
        clock_rate (:obj:`int`): The RTP clock rate in Hz.
        channels (:obj:`int`, optional): The number of audio channels. It's :obj:`None` for video.
        sdp_fmtp_line (:obj:`str`, optional): The codec parameters, as in the ``a=fmtp`` line of SDP,
            like ``'minptime=10;useinbandfec=1'``.
    """

    mime_type: str
    clock_rate: int
    channels: int | None = None
    sdp_fmtp_line: str | None = None

    @classmethod
    def _from_native(cls, native: wrtc.RtpCodec) -> RTCRtpCodec:
        return cls(**_codec_members(native))

    def _to_native(self, native_class: type[_NativeCodecT]) -> _NativeCodecT:
        """Creates a native codec of a class: ``wrtc.RtpCodec`` or ``wrtc.RtpCodecCapability``."""
        kind, _, name = self.mime_type.partition('/')
        if name == '':
            msg = f'{self.mime_type!r} is not a valid MIME type of a codec'
            raise ValueError(msg)
        native = native_class()
        native.kind = MediaType.video if kind.lower() == 'video' else MediaType.audio
        native.name = name
        native.clockRate = self.clock_rate
        native.numChannels = self.channels
        native.parameters = _parse_fmtp(self.sdp_fmtp_line)
        return native

    def _matches(self, other: RTCRtpCodec) -> bool:
        # codecs match with a case-insensitive MIME type and the same parameters, in any order
        return (
            self.mime_type.lower() == other.mime_type.lower()
            and self.clock_rate == other.clock_rate
            and _channels_or_one(self.channels) == _channels_or_one(other.channels)
            and _parse_fmtp(self.sdp_fmtp_line) == _parse_fmtp(other.sdp_fmtp_line)
        )

    #: Alias for :attr:`mime_type`
    mimeType: ClassVar[Alias[str]] = alias('mime_type')
    #: Alias for :attr:`clock_rate`
    clockRate: ClassVar[Alias[int]] = alias('clock_rate')
    #: Alias for :attr:`sdp_fmtp_line`
    sdpFmtpLine: ClassVar[Alias[str | None]] = alias('sdp_fmtp_line')


@dataclass
class RTCRtpCodecParameters(Dictionary):
    """A codec negotiated for a sender or a receiver, with its payload type.

    See :mdn:`RTCRtpSender/getParameters`.

    Args:
        payload_type (:obj:`int`): The RTP payload type the codec is negotiated with.
        mime_type (:obj:`str`): The type and subtype of the codec, like ``'audio/opus'``.
        clock_rate (:obj:`int`): The RTP clock rate in Hz.
        channels (:obj:`int`, optional): The number of audio channels. It's :obj:`None` for video.
        sdp_fmtp_line (:obj:`str`, optional): The codec parameters, as in the ``a=fmtp`` line of SDP.
    """

    payload_type: int
    mime_type: str
    clock_rate: int
    channels: int | None = None
    sdp_fmtp_line: str | None = None

    @classmethod
    def _from_native(cls, native: wrtc.RtpCodecParameters) -> RTCRtpCodecParameters:
        return cls(payload_type=native.payloadType, **_codec_members(native))

    #: Alias for :attr:`payload_type`
    payloadType: ClassVar[Alias[int]] = alias('payload_type')
    #: Alias for :attr:`mime_type`
    mimeType: ClassVar[Alias[str]] = alias('mime_type')
    #: Alias for :attr:`clock_rate`
    clockRate: ClassVar[Alias[int]] = alias('clock_rate')
    #: Alias for :attr:`sdp_fmtp_line`
    sdpFmtpLine: ClassVar[Alias[str | None]] = alias('sdp_fmtp_line')


@dataclass
class RTCRtpHeaderExtensionParameters(Dictionary):
    """An RTP header extension negotiated for a sender or a receiver.

    See :mdn:`RTCRtpSender/getParameters`.

    Args:
        uri (:obj:`str`): The URI that names the extension.
        id (:obj:`int`): The id that marks the extension in RTP packets.
        encrypted (:obj:`bool`, optional): Whether the extension is encrypted.
    """

    uri: str
    id: int
    encrypted: bool = False

    @classmethod
    def _from_native(cls, native: wrtc.RtpExtension) -> RTCRtpHeaderExtensionParameters:
        return cls(uri=native.uri, id=native.id, encrypted=native.encrypt)


@dataclass
class RTCRtcpParameters(Dictionary):
    """The RTCP parameters of a sender or a receiver.

    See :mdn:`RTCRtpSender/getParameters`.

    Args:
        cname (:obj:`str`, optional): The canonical name sent in RTCP. It's :obj:`None` for receivers.
        reduced_size (:obj:`bool`, optional): Whether reduced-size RTCP is negotiated.
    """

    cname: str | None = None
    reduced_size: bool | None = None

    #: Alias for :attr:`reduced_size`
    reducedSize: ClassVar[Alias[bool | None]] = alias('reduced_size')


@dataclass
class RTCRtpCodingParameters(Dictionary):
    """The member of an encoding that identifies it.

    See :mdn:`RTCRtpSender/getParameters`.

    Args:
        rid (:obj:`str`, optional): The RTP stream id of a simulcast layer. It can't be changed once set.
    """

    rid: str | None = None


@dataclass
class RTCRtpEncodingParameters(RTCRtpCodingParameters):
    """An encoding of a sender. A sender has one per simulcast layer, or a single one.

    For audio senders, ``max_framerate`` and ``scale_resolution_down_by`` are ignored.

    See :mdn:`RTCRtpSender/setParameters`.

    Args:
        rid (:obj:`str`, optional): The RTP stream id of a simulcast layer. It can't be changed once set.
        active (:obj:`bool`, optional): Whether the encoding is sent.
        max_bitrate (:obj:`int`, optional): The bitrate cap in bits per second.
        max_framerate (:obj:`float`, optional): The frame rate cap of video.
        scale_resolution_down_by (:obj:`float`, optional): The factor video is scaled down by, at least 1.
        priority (:obj:`webrtc.RTCPriorityType`, optional): The relative share of the bitrate the encoding gets.
            It's read back as the level closest to what the encoder uses.
        network_priority (:obj:`webrtc.RTCPriorityType`, optional): The DSCP marking of its packets.
        scalability_mode (:obj:`str`, optional): The SVC mode of video, like ``'L1T3'``.
        adaptive_ptime (:obj:`bool`, optional): Whether audio may use longer packets when bandwidth is low.
        codec (:obj:`webrtc.RTCRtpCodec`, optional): The codec to send with. The first negotiated one is used
            by default.
    """

    active: bool = True
    max_bitrate: int | None = None
    max_framerate: float | None = None
    scale_resolution_down_by: float | None = None
    priority: RTCPriorityType | RTCPriorityTypeValue = RTCPriorityType.low
    network_priority: RTCPriorityType | RTCPriorityTypeValue = RTCPriorityType.low
    scalability_mode: str | None = None
    adaptive_ptime: bool = False
    codec: RTCRtpCodec | None = None

    _dictionaries: ClassVar = {'codec': RTCRtpCodec}

    @classmethod
    def _from_native(cls, native: wrtc.RtpEncodingParameters) -> RTCRtpEncodingParameters:
        priority = min(_BITRATE_PRIORITY, key=lambda p: abs(_BITRATE_PRIORITY[p] - native.bitratePriority))
        return cls(
            active=native.active,
            max_bitrate=native.maxBitrate,
            max_framerate=native.maxFramerate,
            scale_resolution_down_by=native.scaleResolutionDownBy,
            rid=native.rid if native.rid != '' else None,
            priority=priority,
            network_priority=native.networkPriority,
            scalability_mode=native.scalabilityMode,
            adaptive_ptime=native.adaptivePtime,
            codec=RTCRtpCodec._from_native(native.codec) if native.codec is not None else None,
        )

    def _for_kind(self, kind: MediaType) -> RTCRtpEncodingParameters:
        """The encoding for a sender of a kind.

        Returns:
            :obj:`RTCRtpEncodingParameters`: The encoding, without the members of video ones for audio.
        """
        if kind == MediaType.video:
            return self
        return dataclasses.replace(self, max_framerate=None, scale_resolution_down_by=None)

    def _apply(self, native: wrtc.RtpEncodingParameters) -> wrtc.RtpEncodingParameters:
        """:meth:`_to_native` into an existing native encoding: sets the members that can be changed."""
        # the WebIDL types: an [EnforceRange] unsigned long and restricted doubles
        bitrate = self.max_bitrate
        if bitrate is not None and not _is_unsigned_long(bitrate):
            msg = f'max_bitrate must be an unsigned 32-bit integer, not {bitrate!r}'
            raise TypeError(msg)
        for name in ('max_framerate', 'scale_resolution_down_by'):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                msg = f'{name} must be a finite number, not {value!r}'
                raise TypeError(msg)
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

    def _to_native(self) -> wrtc.RtpEncodingParameters:
        native = self._apply(wrtc.RtpEncodingParameters())
        native.rid = self.rid if self.rid is not None else ''
        return native

    #: Alias for :attr:`max_bitrate`
    maxBitrate: ClassVar[Alias[int | None]] = alias('max_bitrate')
    #: Alias for :attr:`max_framerate`
    maxFramerate: ClassVar[Alias[float | None]] = alias('max_framerate')
    #: Alias for :attr:`scale_resolution_down_by`
    scaleResolutionDownBy: ClassVar[Alias[float | None]] = alias('scale_resolution_down_by')
    #: Alias for :attr:`network_priority`
    networkPriority: ClassVar[Alias[RTCPriorityType]] = alias('network_priority')
    #: Alias for :attr:`scalability_mode`
    scalabilityMode: ClassVar[Alias[str | None]] = alias('scalability_mode')
    #: Alias for :attr:`adaptive_ptime`
    adaptivePtime: ClassVar[Alias[bool]] = alias('adaptive_ptime')


@dataclass
class RTCRtpParameters(Dictionary):
    """The parameters a sender and a receiver share.

    See :mdn:`RTCRtpSender/getParameters`.

    Args:
        header_extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionParameters`): The header extensions.
        rtcp (:obj:`webrtc.RTCRtcpParameters`): The RTCP parameters.
        codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodecParameters`): The negotiated codecs.
    """

    header_extensions: list[RTCRtpHeaderExtensionParameters]
    rtcp: RTCRtcpParameters
    codecs: list[RTCRtpCodecParameters]

    _dictionaries: ClassVar = {
        'codecs': RTCRtpCodecParameters,
        'header_extensions': RTCRtpHeaderExtensionParameters,
        'rtcp': RTCRtcpParameters,
    }

    #: Alias for :attr:`header_extensions`
    headerExtensions: ClassVar[Alias[list[RTCRtpHeaderExtensionParameters]]] = alias('header_extensions')


@dataclass
class RTCRtpReceiveParameters(RTCRtpParameters):
    """The parameters a receiver receives with, from :meth:`webrtc.RTCRtpReceiver.get_parameters`.

    See :mdn:`RTCRtpReceiver/getParameters`.

    Args:
        header_extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionParameters`): The header extensions.
        rtcp (:obj:`webrtc.RTCRtcpParameters`): The RTCP parameters.
        codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodecParameters`): The codecs it can receive.
    """

    @classmethod
    def _from_native(cls, native: wrtc.RtpParameters) -> RTCRtpReceiveParameters:
        return cls(
            codecs=[RTCRtpCodecParameters._from_native(c) for c in native.codecs],
            header_extensions=[RTCRtpHeaderExtensionParameters._from_native(e) for e in native.headerExtensions],
            rtcp=RTCRtcpParameters(reduced_size=native.rtcp.reducedSize),
        )


@dataclass
class RTCRtpSendParameters(RTCRtpParameters):
    """The parameters a sender sends with, from :meth:`webrtc.RTCRtpSender.get_parameters`.

    Only :attr:`encodings` (all but their ``rid``) and :attr:`degradation_preference` can be changed with
    :meth:`webrtc.RTCRtpSender.set_parameters`.

    See :mdn:`RTCRtpSender/getParameters`.

    Args:
        header_extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionParameters`): The header extensions.
        rtcp (:obj:`webrtc.RTCRtcpParameters`): The RTCP parameters.
        codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodecParameters`): The negotiated codecs.
        transaction_id (:obj:`str`): Identifies the ``get_parameters`` call the parameters come from.
        encodings (:obj:`list` of :obj:`webrtc.RTCRtpEncodingParameters`): The encodings.
        degradation_preference (:obj:`webrtc.RTCDegradationPreference`, optional): Whether video drops frame
            rate or resolution first when bandwidth or CPU is short.
    """

    transaction_id: str
    encodings: list[RTCRtpEncodingParameters]
    degradation_preference: RTCDegradationPreference | RTCDegradationPreferenceValue | None = None

    _dictionaries: ClassVar = {
        'encodings': RTCRtpEncodingParameters,
        'codecs': RTCRtpCodecParameters,
        'header_extensions': RTCRtpHeaderExtensionParameters,
        'rtcp': RTCRtcpParameters,
    }

    @classmethod
    def _from_native(cls, native: wrtc.RtpParameters) -> RTCRtpSendParameters:
        return cls(
            transaction_id=native.transactionId,
            encodings=[RTCRtpEncodingParameters._from_native(e) for e in native.encodings],
            codecs=[RTCRtpCodecParameters._from_native(c) for c in native.codecs],
            header_extensions=[RTCRtpHeaderExtensionParameters._from_native(e) for e in native.headerExtensions],
            rtcp=RTCRtcpParameters(cname=native.rtcp.cname, reduced_size=native.rtcp.reducedSize),
            degradation_preference=native.degradationPreference,
        )

    #: Alias for :attr:`transaction_id`
    transactionId: ClassVar[Alias[str]] = alias('transaction_id')
    #: Alias for :attr:`degradation_preference`
    degradationPreference: ClassVar[Alias[RTCDegradationPreference | None]] = alias('degradation_preference')


@dataclass
class RTCRtpHeaderExtensionCapability(Dictionary):
    """An RTP header extension that can be negotiated.

    In :obj:`webrtc.RTCRtpCapabilities` only the URI is meaningful, since the direction is set per transceiver.

    See :mdn:`RTCRtpSender/getCapabilities_static`.

    Args:
        uri (:obj:`str`): The URI that names the extension.
        direction (:obj:`webrtc.RTCRtpTransceiverDirection`, optional): The directions it's negotiated in.
            It's :attr:`webrtc.RTCRtpTransceiverDirection.stopped` for none.
    """

    uri: str
    direction: RTCRtpTransceiverDirection | RTCRtpTransceiverDirectionValue = RTCRtpTransceiverDirection.sendrecv

    @classmethod
    def _from_native(cls, native: wrtc.RtpHeaderExtensionCapability) -> RTCRtpHeaderExtensionCapability:
        return cls(uri=native.uri, direction=native.direction)


@dataclass
class RTCRtpCapabilities(Dictionary):
    """The codecs and header extensions a sender or a receiver supports.

    See :mdn:`RTCRtpSender/getCapabilities_static`.

    Args:
        codecs (:obj:`list` of :obj:`webrtc.RTCRtpCodec`): The codecs.
        header_extensions (:obj:`list` of :obj:`webrtc.RTCRtpHeaderExtensionCapability`): The header extensions.
    """

    codecs: list[RTCRtpCodec]
    header_extensions: list[RTCRtpHeaderExtensionCapability]

    _dictionaries: ClassVar = {'codecs': RTCRtpCodec, 'header_extensions': RTCRtpHeaderExtensionCapability}

    @classmethod
    def _from_native(cls, native: wrtc.RtpCapabilities) -> RTCRtpCapabilities:
        return cls(
            codecs=[RTCRtpCodec._from_native(c) for c in native.codecs],
            # only the URIs: the directions are the ones of a transceiver (see get_header_extensions_to_negotiate)
            header_extensions=[RTCRtpHeaderExtensionCapability(uri=e.uri) for e in native.headerExtensions],
        )

    @classmethod
    def _supported(
        cls, native_class: type[wrtc.RTCRtpSender | wrtc.RTCRtpReceiver], kind: MediaType | MediaTypeValue
    ) -> RTCRtpCapabilities | None:
        """The capabilities of ``wrtc.RTCRtpSender`` or ``wrtc.RTCRtpReceiver`` for a kind.

        Returns:
            :obj:`RTCRtpCapabilities`: The capabilities, :obj:`None` for another kind.
        """
        native = native_class.getCapabilities(str(kind))
        return cls._from_native(native) if native is not None else None

    #: Alias for :attr:`header_extensions`
    headerExtensions: ClassVar[Alias[list[RTCRtpHeaderExtensionCapability]]] = alias('header_extensions')


@dataclass
class RTCEncodingOptions(Dictionary):
    """How :meth:`webrtc.RTCRtpSender.set_parameters` changes one encoding, from WebRTC Extensions.

    Args:
        key_frame (:obj:`bool`, optional): Whether the encoding sends a key frame right away.
    """

    key_frame: bool = False

    #: Alias for :attr:`key_frame`
    keyFrame: ClassVar[Alias[bool]] = alias('key_frame')


@dataclass
class RTCSetParameterOptions(Dictionary):
    """The options of :meth:`webrtc.RTCRtpSender.set_parameters`, from WebRTC Extensions.

    Args:
        encoding_options (:obj:`list` of :obj:`webrtc.RTCEncodingOptions`, optional): One per encoding, in order,
            or empty for none.
    """

    encoding_options: list[RTCEncodingOptions] = field(default_factory=list)

    _dictionaries: ClassVar = {'encoding_options': RTCEncodingOptions}

    #: Alias for :attr:`encoding_options`
    encodingOptions: ClassVar[Alias[list[RTCEncodingOptions]]] = alias('encoding_options')
