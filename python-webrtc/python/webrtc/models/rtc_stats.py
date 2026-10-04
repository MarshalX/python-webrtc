#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The stats dictionaries of the WebRTC Statistics specification, and the report that holds them."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import MISSING, dataclass, fields
from typing import TYPE_CHECKING, ClassVar

from webrtc import (
    RTCDataChannelState,
    RTCDtlsRole,
    RTCDtlsTransportState,
    RTCIceCandidateType,
    RTCIceRole,
    RTCIceServerTransportProtocol,
    RTCIceTcpCandidateType,
    RTCIceTransportState,
    RTCQualityLimitationReason,
    RTCStatsIceCandidatePairState,
    RTCStatsType,
)
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    import enum

    import webrtc


def _enum_value(cls: type[enum.Enum], value: object) -> object:
    """The member of an enum with a value, or the value itself if the native engine reports one the enum lacks."""
    try:
        return cls(value)
    except ValueError:
        return value


@dataclass(init=False)
class RTCStats(Dictionary):
    """The members every stats dictionary has, and the base of all of them.

    A report holds the dictionary of the type of the stats, like :obj:`webrtc.RTCOutboundRtpStreamStats`. It holds
    this base one for a type this library doesn't model, or when a required member is missing from the stats.
    Members are keyword-only. A string value that its enum lacks is kept as a plain :obj:`str`.

    Args:
        timestamp (:obj:`float`): When the stats were collected, in milliseconds since the Unix epoch.
        type (:obj:`webrtc.RTCStatsType`): The type of the stats, like ``'outbound-rtp'``.
        id (:obj:`str`): Identifies the stats in its report.

    Raises:
        TypeError: If a required member is missing, or a member is unknown.
    """

    timestamp: float
    type: RTCStatsType | str
    id: str

    _enums: ClassVar[Mapping[str, type[enum.Enum]]] = {'type': RTCStatsType}

    def __init__(self, **members: object) -> None:
        cls = self.__class__
        unknown = sorted(members.keys() - {field.name for field in fields(cls)})
        if len(unknown) > 0:
            msg = f'{cls.__name__} has no member {unknown[0]!r}'
            raise TypeError(msg)
        enums: dict[str, type[enum.Enum]] = {}
        for klass in cls.__mro__:
            own: Mapping[str, type[enum.Enum]] = vars(klass).get('_enums', {})
            enums.update(own)
        for field in fields(cls):
            if field.name in members:
                value = members[field.name]
            elif field.default is not MISSING:
                value = field.default
            else:
                msg = f'{cls.__name__} is missing the required member {field.name!r}'
                raise TypeError(msg)
            if field.name in enums and isinstance(value, str):
                value = _enum_value(enums[field.name], value)
            setattr(self, field.name, value)


@dataclass(init=False)
class RTCRtpStreamStats(RTCStats):
    """Stats of an RTP stream.

    It has the members of :obj:`webrtc.RTCStats` too.

    Args:
        ssrc (:obj:`int`): The SSRC of the RTP stream. See :mdn:`RTCInboundRtpStreamStats/ssrc`.
        kind (:obj:`str`): The kind of the media, ``'audio'`` or ``'video'``. See :mdn:`RTCInboundRtpStreamStats/kind`.
        transport_id (:obj:`str`, optional): The id of the stats of the transport of the stream. See
            :mdn:`RTCInboundRtpStreamStats/transportId`.
        codec_id (:obj:`str`, optional): The id of the stats of the codec of the stream. See
            :mdn:`RTCInboundRtpStreamStats/codecId`.
    """

    ssrc: int
    kind: str
    transport_id: str | None = None
    codec_id: str | None = None

    #: Alias for :attr:`transport_id`
    transportId: ClassVar[Alias[str | None]] = alias('transport_id')
    #: Alias for :attr:`codec_id`
    codecId: ClassVar[Alias[str | None]] = alias('codec_id')


@dataclass(init=False)
class RTCCodecStats(RTCStats):
    """Stats of a codec negotiated on a transport, of type ``'codec'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    See :mdn:`RTCCodecStats`.

    Args:
        payload_type (:obj:`int`): The RTP payload type of the codec. See :mdn:`RTCCodecStats/payloadType`.
        transport_id (:obj:`str`): The id of the stats of the transport the codec is negotiated on. See
            :mdn:`RTCCodecStats/transportId`.
        mime_type (:obj:`str`): The type and subtype of the codec, like ``'audio/opus'``. See
            :mdn:`RTCCodecStats/mimeType`.
        clock_rate (:obj:`int`, optional): The clock rate in Hz. See :mdn:`RTCCodecStats/clockRate`.
        channels (:obj:`int`, optional): The number of audio channels. See :mdn:`RTCCodecStats/channels`.
        sdp_fmtp_line (:obj:`str`, optional): The parameters of the codec, as in the ``a=fmtp`` line of SDP. See
            :mdn:`RTCCodecStats/sdpFmtpLine`.
    """

    payload_type: int
    transport_id: str
    mime_type: str
    clock_rate: int | None = None
    channels: int | None = None
    sdp_fmtp_line: str | None = None

    #: Alias for :attr:`payload_type`
    payloadType: ClassVar[Alias[int]] = alias('payload_type')
    #: Alias for :attr:`transport_id`
    transportId: ClassVar[Alias[str]] = alias('transport_id')
    #: Alias for :attr:`mime_type`
    mimeType: ClassVar[Alias[str]] = alias('mime_type')
    #: Alias for :attr:`clock_rate`
    clockRate: ClassVar[Alias[int | None]] = alias('clock_rate')
    #: Alias for :attr:`sdp_fmtp_line`
    sdpFmtpLine: ClassVar[Alias[str | None]] = alias('sdp_fmtp_line')


@dataclass(init=False)
class RTCReceivedRtpStreamStats(RTCRtpStreamStats):
    """Stats of an RTP stream, as its receiver measures it.

    It has the members of :obj:`webrtc.RTCRtpStreamStats` too.

    Args:
        packets_received (:obj:`int`, optional): The packets received. See
            :mdn:`RTCInboundRtpStreamStats/packetsReceived`.
        packets_received_with_ect1 (:obj:`int`, optional): The packets received with the ECT(1) ECN marking.
        packets_received_with_ce (:obj:`int`, optional): The packets received with the CE ECN marking.
        packets_reported_as_lost (:obj:`int`, optional): The packets reported lost in congestion control feedback.
        packets_reported_as_lost_but_recovered (:obj:`int`, optional): The packets reported lost that were received
            later.
        packets_lost (:obj:`int`, optional): The packets lost, as RTCP reports count them. See
            :mdn:`RTCInboundRtpStreamStats/packetsLost`.
        jitter (:obj:`float`, optional): The packet jitter in seconds. See :mdn:`RTCInboundRtpStreamStats/jitter`.
    """

    packets_received: int | None = None
    packets_received_with_ect1: int | None = None
    packets_received_with_ce: int | None = None
    packets_reported_as_lost: int | None = None
    packets_reported_as_lost_but_recovered: int | None = None
    packets_lost: int | None = None
    jitter: float | None = None

    #: Alias for :attr:`packets_received`
    packetsReceived: ClassVar[Alias[int | None]] = alias('packets_received')
    #: Alias for :attr:`packets_received_with_ect1`
    packetsReceivedWithEct1: ClassVar[Alias[int | None]] = alias('packets_received_with_ect1')
    #: Alias for :attr:`packets_received_with_ce`
    packetsReceivedWithCe: ClassVar[Alias[int | None]] = alias('packets_received_with_ce')
    #: Alias for :attr:`packets_reported_as_lost`
    packetsReportedAsLost: ClassVar[Alias[int | None]] = alias('packets_reported_as_lost')
    #: Alias for :attr:`packets_reported_as_lost_but_recovered`
    packetsReportedAsLostButRecovered: ClassVar[Alias[int | None]] = alias('packets_reported_as_lost_but_recovered')
    #: Alias for :attr:`packets_lost`
    packetsLost: ClassVar[Alias[int | None]] = alias('packets_lost')


@dataclass(init=False)
class RTCInboundRtpStreamStats(RTCReceivedRtpStreamStats):
    """Stats of an RTP stream the connection receives, of type ``'inbound-rtp'``.

    It has the members of :obj:`webrtc.RTCReceivedRtpStreamStats` too.

    See :mdn:`RTCInboundRtpStreamStats`.

    Args:
        track_identifier (:obj:`str`): The id of the track. See :mdn:`RTCInboundRtpStreamStats/trackIdentifier`.
        mid (:obj:`str`, optional): The media id of the transceiver. See :mdn:`RTCInboundRtpStreamStats/mid`.
        remote_id (:obj:`str`, optional): The id of the remote-outbound-rtp stats of the stream. See
            :mdn:`RTCInboundRtpStreamStats/remoteId`.
        frames_decoded (:obj:`int`, optional): The frames decoded. See :mdn:`RTCInboundRtpStreamStats/framesDecoded`.
        key_frames_decoded (:obj:`int`, optional): The key frames decoded. See
            :mdn:`RTCInboundRtpStreamStats/keyFramesDecoded`.
        frames_rendered (:obj:`int`, optional): The frames rendered.
        frames_dropped (:obj:`int`, optional): The frames dropped before decoding.
        frame_width (:obj:`int`, optional): The width of the last frame. See :mdn:`RTCInboundRtpStreamStats/frameWidth`.
        frame_height (:obj:`int`, optional): The height of the last frame. See
            :mdn:`RTCInboundRtpStreamStats/frameHeight`.
        frames_per_second (:obj:`float`, optional): The frames per second over the last second. See
            :mdn:`RTCInboundRtpStreamStats/framesPerSecond`.
        qp_sum (:obj:`int`, optional): The sum of the quantization parameters of the frames. See
            :mdn:`RTCInboundRtpStreamStats/qpSum`.
        total_decode_time (:obj:`float`, optional): The total seconds spent decoding. See
            :mdn:`RTCInboundRtpStreamStats/totalDecodeTime`.
        total_inter_frame_delay (:obj:`float`, optional): The total seconds between rendered frames. See
            :mdn:`RTCInboundRtpStreamStats/totalInterFrameDelay`.
        total_squared_inter_frame_delay (:obj:`float`, optional): The sum of the squared seconds between rendered
            frames. See :mdn:`RTCInboundRtpStreamStats/totalSquaredInterFrameDelay`.
        pause_count (:obj:`int`, optional): The video pauses. See :mdn:`RTCInboundRtpStreamStats/pauseCount`.
        total_pauses_duration (:obj:`float`, optional): The total seconds of the pauses. See
            :mdn:`RTCInboundRtpStreamStats/totalPausesDuration`.
        freeze_count (:obj:`int`, optional): The video freezes. See :mdn:`RTCInboundRtpStreamStats/freezeCount`.
        total_freezes_duration (:obj:`float`, optional): The total seconds of the freezes. See
            :mdn:`RTCInboundRtpStreamStats/totalFreezesDuration`.
        last_packet_received_timestamp (:obj:`float`, optional): When the last packet was received, in milliseconds
            since the epoch. See :mdn:`RTCInboundRtpStreamStats/lastPacketReceivedTimestamp`.
        header_bytes_received (:obj:`int`, optional): The bytes of RTP headers and padding received. See
            :mdn:`RTCInboundRtpStreamStats/headerBytesReceived`.
        packets_discarded (:obj:`int`, optional): The packets the jitter buffer discarded. See
            :mdn:`RTCInboundRtpStreamStats/packetsDiscarded`.
        fec_bytes_received (:obj:`int`, optional): The bytes of FEC payload received.
        fec_packets_received (:obj:`int`, optional): The FEC packets received. See
            :mdn:`RTCInboundRtpStreamStats/fecPacketsReceived`.
        fec_packets_discarded (:obj:`int`, optional): The FEC packets discarded. See
            :mdn:`RTCInboundRtpStreamStats/fecPacketsDiscarded`.
        bytes_received (:obj:`int`, optional): The bytes received. See :mdn:`RTCInboundRtpStreamStats/bytesReceived`.
        nack_count (:obj:`int`, optional): The NACK packets. See :mdn:`RTCInboundRtpStreamStats/nackCount`.
        fir_count (:obj:`int`, optional): The FIR packets.
        pli_count (:obj:`int`, optional): The PLI packets.
        total_processing_delay (:obj:`float`, optional): The total seconds from receiving frames or samples to decoding
            them. See :mdn:`RTCInboundRtpStreamStats/totalProcessingDelay`.
        estimated_playout_timestamp (:obj:`float`, optional): When the last frame or sample is estimated to play out, in
            milliseconds since the epoch. See :mdn:`RTCInboundRtpStreamStats/estimatedPlayoutTimestamp`.
        jitter_buffer_delay (:obj:`float`, optional): The total seconds frames or samples spent in the jitter buffer.
            See :mdn:`RTCInboundRtpStreamStats/jitterBufferDelay`.
        jitter_buffer_target_delay (:obj:`float`, optional): The sum of the target delays of the jitter buffer, in
            seconds. See :mdn:`RTCInboundRtpStreamStats/jitterBufferTargetDelay`.
        jitter_buffer_emitted_count (:obj:`int`, optional): The frames or samples that left the jitter buffer. See
            :mdn:`RTCInboundRtpStreamStats/jitterBufferEmittedCount`.
        jitter_buffer_minimum_delay (:obj:`float`, optional): The sum of the minimum delays of the jitter buffer, in
            seconds. See :mdn:`RTCInboundRtpStreamStats/jitterBufferMinimumDelay`.
        total_samples_received (:obj:`int`, optional): The audio samples received. See
            :mdn:`RTCInboundRtpStreamStats/totalSamplesReceived`.
        concealed_samples (:obj:`int`, optional): The audio samples concealed. See
            :mdn:`RTCInboundRtpStreamStats/concealedSamples`.
        silent_concealed_samples (:obj:`int`, optional): The audio samples concealed with silence. See
            :mdn:`RTCInboundRtpStreamStats/silentConcealedSamples`.
        concealment_events (:obj:`int`, optional): The concealment events. See
            :mdn:`RTCInboundRtpStreamStats/concealmentEvents`.
        inserted_samples_for_deceleration (:obj:`int`, optional): The audio samples inserted to slow playout down. See
            :mdn:`RTCInboundRtpStreamStats/insertedSamplesForDeceleration`.
        removed_samples_for_acceleration (:obj:`int`, optional): The audio samples removed to speed playout up. See
            :mdn:`RTCInboundRtpStreamStats/removedSamplesForAcceleration`.
        audio_level (:obj:`float`, optional): The audio level, between 0 and 1. See
            :mdn:`RTCInboundRtpStreamStats/audioLevel`.
        total_audio_energy (:obj:`float`, optional): The total audio energy. See
            :mdn:`RTCInboundRtpStreamStats/totalAudioEnergy`.
        total_samples_duration (:obj:`float`, optional): The total seconds of the audio samples. See
            :mdn:`RTCInboundRtpStreamStats/totalSamplesDuration`.
        frames_received (:obj:`int`, optional): The complete frames received. See
            :mdn:`RTCInboundRtpStreamStats/framesReceived`.
        decoder_implementation (:obj:`str`, optional): The decoder, like ``libvpx``.
        playout_id (:obj:`str`, optional): The id of the media-playout stats of the audio. See
            :mdn:`RTCInboundRtpStreamStats/playoutId`.
        power_efficient_decoder (:obj:`bool`, optional): Whether the decoder is power efficient.
        frames_assembled_from_multiple_packets (:obj:`int`, optional): The frames assembled from more than one packet.
            See :mdn:`RTCInboundRtpStreamStats/framesAssembledFromMultiplePackets`.
        total_assembly_time (:obj:`float`, optional): The total seconds spent assembling those frames. See
            :mdn:`RTCInboundRtpStreamStats/totalAssemblyTime`.
        retransmitted_packets_received (:obj:`int`, optional): The retransmitted packets received.
        retransmitted_bytes_received (:obj:`int`, optional): The bytes of retransmitted payload received.
        rtx_ssrc (:obj:`int`, optional): The SSRC of the RTX stream.
        fec_ssrc (:obj:`int`, optional): The SSRC of the FEC stream.
        total_corruption_probability (:obj:`float`, optional): The sum of the probabilities of video corruption.
        total_squared_corruption_probability (:obj:`float`, optional): The sum of the squared probabilities of video
            corruption.
        corruption_measurements (:obj:`int`, optional): The video corruption measurements.
    """

    track_identifier: str
    mid: str | None = None
    remote_id: str | None = None
    frames_decoded: int | None = None
    key_frames_decoded: int | None = None
    frames_rendered: int | None = None
    frames_dropped: int | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    frames_per_second: float | None = None
    qp_sum: int | None = None
    total_decode_time: float | None = None
    total_inter_frame_delay: float | None = None
    total_squared_inter_frame_delay: float | None = None
    pause_count: int | None = None
    total_pauses_duration: float | None = None
    freeze_count: int | None = None
    total_freezes_duration: float | None = None
    last_packet_received_timestamp: float | None = None
    header_bytes_received: int | None = None
    packets_discarded: int | None = None
    fec_bytes_received: int | None = None
    fec_packets_received: int | None = None
    fec_packets_discarded: int | None = None
    bytes_received: int | None = None
    nack_count: int | None = None
    fir_count: int | None = None
    pli_count: int | None = None
    total_processing_delay: float | None = None
    estimated_playout_timestamp: float | None = None
    jitter_buffer_delay: float | None = None
    jitter_buffer_target_delay: float | None = None
    jitter_buffer_emitted_count: int | None = None
    jitter_buffer_minimum_delay: float | None = None
    total_samples_received: int | None = None
    concealed_samples: int | None = None
    silent_concealed_samples: int | None = None
    concealment_events: int | None = None
    inserted_samples_for_deceleration: int | None = None
    removed_samples_for_acceleration: int | None = None
    audio_level: float | None = None
    total_audio_energy: float | None = None
    total_samples_duration: float | None = None
    frames_received: int | None = None
    decoder_implementation: str | None = None
    playout_id: str | None = None
    power_efficient_decoder: bool | None = None
    frames_assembled_from_multiple_packets: int | None = None
    total_assembly_time: float | None = None
    retransmitted_packets_received: int | None = None
    retransmitted_bytes_received: int | None = None
    rtx_ssrc: int | None = None
    fec_ssrc: int | None = None
    total_corruption_probability: float | None = None
    total_squared_corruption_probability: float | None = None
    corruption_measurements: int | None = None

    #: Alias for :attr:`track_identifier`
    trackIdentifier: ClassVar[Alias[str]] = alias('track_identifier')
    #: Alias for :attr:`remote_id`
    remoteId: ClassVar[Alias[str | None]] = alias('remote_id')
    #: Alias for :attr:`frames_decoded`
    framesDecoded: ClassVar[Alias[int | None]] = alias('frames_decoded')
    #: Alias for :attr:`key_frames_decoded`
    keyFramesDecoded: ClassVar[Alias[int | None]] = alias('key_frames_decoded')
    #: Alias for :attr:`frames_rendered`
    framesRendered: ClassVar[Alias[int | None]] = alias('frames_rendered')
    #: Alias for :attr:`frames_dropped`
    framesDropped: ClassVar[Alias[int | None]] = alias('frames_dropped')
    #: Alias for :attr:`frame_width`
    frameWidth: ClassVar[Alias[int | None]] = alias('frame_width')
    #: Alias for :attr:`frame_height`
    frameHeight: ClassVar[Alias[int | None]] = alias('frame_height')
    #: Alias for :attr:`frames_per_second`
    framesPerSecond: ClassVar[Alias[float | None]] = alias('frames_per_second')
    #: Alias for :attr:`qp_sum`
    qpSum: ClassVar[Alias[int | None]] = alias('qp_sum')
    #: Alias for :attr:`total_decode_time`
    totalDecodeTime: ClassVar[Alias[float | None]] = alias('total_decode_time')
    #: Alias for :attr:`total_inter_frame_delay`
    totalInterFrameDelay: ClassVar[Alias[float | None]] = alias('total_inter_frame_delay')
    #: Alias for :attr:`total_squared_inter_frame_delay`
    totalSquaredInterFrameDelay: ClassVar[Alias[float | None]] = alias('total_squared_inter_frame_delay')
    #: Alias for :attr:`pause_count`
    pauseCount: ClassVar[Alias[int | None]] = alias('pause_count')
    #: Alias for :attr:`total_pauses_duration`
    totalPausesDuration: ClassVar[Alias[float | None]] = alias('total_pauses_duration')
    #: Alias for :attr:`freeze_count`
    freezeCount: ClassVar[Alias[int | None]] = alias('freeze_count')
    #: Alias for :attr:`total_freezes_duration`
    totalFreezesDuration: ClassVar[Alias[float | None]] = alias('total_freezes_duration')
    #: Alias for :attr:`last_packet_received_timestamp`
    lastPacketReceivedTimestamp: ClassVar[Alias[float | None]] = alias('last_packet_received_timestamp')
    #: Alias for :attr:`header_bytes_received`
    headerBytesReceived: ClassVar[Alias[int | None]] = alias('header_bytes_received')
    #: Alias for :attr:`packets_discarded`
    packetsDiscarded: ClassVar[Alias[int | None]] = alias('packets_discarded')
    #: Alias for :attr:`fec_bytes_received`
    fecBytesReceived: ClassVar[Alias[int | None]] = alias('fec_bytes_received')
    #: Alias for :attr:`fec_packets_received`
    fecPacketsReceived: ClassVar[Alias[int | None]] = alias('fec_packets_received')
    #: Alias for :attr:`fec_packets_discarded`
    fecPacketsDiscarded: ClassVar[Alias[int | None]] = alias('fec_packets_discarded')
    #: Alias for :attr:`bytes_received`
    bytesReceived: ClassVar[Alias[int | None]] = alias('bytes_received')
    #: Alias for :attr:`nack_count`
    nackCount: ClassVar[Alias[int | None]] = alias('nack_count')
    #: Alias for :attr:`fir_count`
    firCount: ClassVar[Alias[int | None]] = alias('fir_count')
    #: Alias for :attr:`pli_count`
    pliCount: ClassVar[Alias[int | None]] = alias('pli_count')
    #: Alias for :attr:`total_processing_delay`
    totalProcessingDelay: ClassVar[Alias[float | None]] = alias('total_processing_delay')
    #: Alias for :attr:`estimated_playout_timestamp`
    estimatedPlayoutTimestamp: ClassVar[Alias[float | None]] = alias('estimated_playout_timestamp')
    #: Alias for :attr:`jitter_buffer_delay`
    jitterBufferDelay: ClassVar[Alias[float | None]] = alias('jitter_buffer_delay')
    #: Alias for :attr:`jitter_buffer_target_delay`
    jitterBufferTargetDelay: ClassVar[Alias[float | None]] = alias('jitter_buffer_target_delay')
    #: Alias for :attr:`jitter_buffer_emitted_count`
    jitterBufferEmittedCount: ClassVar[Alias[int | None]] = alias('jitter_buffer_emitted_count')
    #: Alias for :attr:`jitter_buffer_minimum_delay`
    jitterBufferMinimumDelay: ClassVar[Alias[float | None]] = alias('jitter_buffer_minimum_delay')
    #: Alias for :attr:`total_samples_received`
    totalSamplesReceived: ClassVar[Alias[int | None]] = alias('total_samples_received')
    #: Alias for :attr:`concealed_samples`
    concealedSamples: ClassVar[Alias[int | None]] = alias('concealed_samples')
    #: Alias for :attr:`silent_concealed_samples`
    silentConcealedSamples: ClassVar[Alias[int | None]] = alias('silent_concealed_samples')
    #: Alias for :attr:`concealment_events`
    concealmentEvents: ClassVar[Alias[int | None]] = alias('concealment_events')
    #: Alias for :attr:`inserted_samples_for_deceleration`
    insertedSamplesForDeceleration: ClassVar[Alias[int | None]] = alias('inserted_samples_for_deceleration')
    #: Alias for :attr:`removed_samples_for_acceleration`
    removedSamplesForAcceleration: ClassVar[Alias[int | None]] = alias('removed_samples_for_acceleration')
    #: Alias for :attr:`audio_level`
    audioLevel: ClassVar[Alias[float | None]] = alias('audio_level')
    #: Alias for :attr:`total_audio_energy`
    totalAudioEnergy: ClassVar[Alias[float | None]] = alias('total_audio_energy')
    #: Alias for :attr:`total_samples_duration`
    totalSamplesDuration: ClassVar[Alias[float | None]] = alias('total_samples_duration')
    #: Alias for :attr:`frames_received`
    framesReceived: ClassVar[Alias[int | None]] = alias('frames_received')
    #: Alias for :attr:`decoder_implementation`
    decoderImplementation: ClassVar[Alias[str | None]] = alias('decoder_implementation')
    #: Alias for :attr:`playout_id`
    playoutId: ClassVar[Alias[str | None]] = alias('playout_id')
    #: Alias for :attr:`power_efficient_decoder`
    powerEfficientDecoder: ClassVar[Alias[bool | None]] = alias('power_efficient_decoder')
    #: Alias for :attr:`frames_assembled_from_multiple_packets`
    framesAssembledFromMultiplePackets: ClassVar[Alias[int | None]] = alias('frames_assembled_from_multiple_packets')
    #: Alias for :attr:`total_assembly_time`
    totalAssemblyTime: ClassVar[Alias[float | None]] = alias('total_assembly_time')
    #: Alias for :attr:`retransmitted_packets_received`
    retransmittedPacketsReceived: ClassVar[Alias[int | None]] = alias('retransmitted_packets_received')
    #: Alias for :attr:`retransmitted_bytes_received`
    retransmittedBytesReceived: ClassVar[Alias[int | None]] = alias('retransmitted_bytes_received')
    #: Alias for :attr:`rtx_ssrc`
    rtxSsrc: ClassVar[Alias[int | None]] = alias('rtx_ssrc')
    #: Alias for :attr:`fec_ssrc`
    fecSsrc: ClassVar[Alias[int | None]] = alias('fec_ssrc')
    #: Alias for :attr:`total_corruption_probability`
    totalCorruptionProbability: ClassVar[Alias[float | None]] = alias('total_corruption_probability')
    #: Alias for :attr:`total_squared_corruption_probability`
    totalSquaredCorruptionProbability: ClassVar[Alias[float | None]] = alias('total_squared_corruption_probability')
    #: Alias for :attr:`corruption_measurements`
    corruptionMeasurements: ClassVar[Alias[int | None]] = alias('corruption_measurements')


@dataclass(init=False)
class RTCRemoteInboundRtpStreamStats(RTCReceivedRtpStreamStats):
    """Stats of a stream the connection sends, as the remote peer receives it. Its type is ``'remote-inbound-rtp'``.

    It has the members of :obj:`webrtc.RTCReceivedRtpStreamStats` too.

    See :mdn:`RTCRemoteInboundRtpStreamStats`.

    Args:
        local_id (:obj:`str`, optional): The id of the outbound-rtp stats of the stream. See
            :mdn:`RTCRemoteInboundRtpStreamStats/localId`.
        round_trip_time (:obj:`float`, optional): The last round trip time in seconds. See
            :mdn:`RTCRemoteInboundRtpStreamStats/roundTripTime`.
        total_round_trip_time (:obj:`float`, optional): The total seconds of the round trip times. See
            :mdn:`RTCRemoteInboundRtpStreamStats/totalRoundTripTime`.
        fraction_lost (:obj:`float`, optional): The fraction of packets lost in the last RTCP report. See
            :mdn:`RTCRemoteInboundRtpStreamStats/fractionLost`.
        round_trip_time_measurements (:obj:`int`, optional): The round trip time measurements. See
            :mdn:`RTCRemoteInboundRtpStreamStats/roundTripTimeMeasurements`.
        packets_with_bleached_ect1_marking (:obj:`int`, optional): The packets sent with ECT(1) that arrived without it.
    """

    local_id: str | None = None
    round_trip_time: float | None = None
    total_round_trip_time: float | None = None
    fraction_lost: float | None = None
    round_trip_time_measurements: int | None = None
    packets_with_bleached_ect1_marking: int | None = None

    #: Alias for :attr:`local_id`
    localId: ClassVar[Alias[str | None]] = alias('local_id')
    #: Alias for :attr:`round_trip_time`
    roundTripTime: ClassVar[Alias[float | None]] = alias('round_trip_time')
    #: Alias for :attr:`total_round_trip_time`
    totalRoundTripTime: ClassVar[Alias[float | None]] = alias('total_round_trip_time')
    #: Alias for :attr:`fraction_lost`
    fractionLost: ClassVar[Alias[float | None]] = alias('fraction_lost')
    #: Alias for :attr:`round_trip_time_measurements`
    roundTripTimeMeasurements: ClassVar[Alias[int | None]] = alias('round_trip_time_measurements')
    #: Alias for :attr:`packets_with_bleached_ect1_marking`
    packetsWithBleachedEct1Marking: ClassVar[Alias[int | None]] = alias('packets_with_bleached_ect1_marking')


@dataclass(init=False)
class RTCSentRtpStreamStats(RTCRtpStreamStats):
    """Stats of an RTP stream, as its sender measures it.

    It has the members of :obj:`webrtc.RTCRtpStreamStats` too.

    Args:
        packets_sent (:obj:`int`, optional): The packets sent. See :mdn:`RTCOutboundRtpStreamStats/packetsSent`.
        bytes_sent (:obj:`int`, optional): The bytes sent. See :mdn:`RTCOutboundRtpStreamStats/bytesSent`.
    """

    packets_sent: int | None = None
    bytes_sent: int | None = None

    #: Alias for :attr:`packets_sent`
    packetsSent: ClassVar[Alias[int | None]] = alias('packets_sent')
    #: Alias for :attr:`bytes_sent`
    bytesSent: ClassVar[Alias[int | None]] = alias('bytes_sent')


@dataclass(init=False)
class RTCOutboundRtpStreamStats(RTCSentRtpStreamStats):
    """Stats of an RTP stream the connection sends, of type ``'outbound-rtp'``.

    It has the members of :obj:`webrtc.RTCSentRtpStreamStats` too.

    See :mdn:`RTCOutboundRtpStreamStats`.

    Args:
        mid (:obj:`str`, optional): The media id of the transceiver. See :mdn:`RTCOutboundRtpStreamStats/mid`.
        media_source_id (:obj:`str`, optional): The id of the media-source stats of the track sent. See
            :mdn:`RTCOutboundRtpStreamStats/mediaSourceId`.
        remote_id (:obj:`str`, optional): The id of the remote-inbound-rtp stats of the stream. See
            :mdn:`RTCOutboundRtpStreamStats/remoteId`.
        rid (:obj:`str`, optional): The RTP stream id of the simulcast layer. See :mdn:`RTCOutboundRtpStreamStats/rid`.
        encoding_index (:obj:`int`, optional): The index of the encoding in the parameters of the sender.
        header_bytes_sent (:obj:`int`, optional): The bytes of RTP headers and padding sent. See
            :mdn:`RTCOutboundRtpStreamStats/headerBytesSent`.
        retransmitted_packets_sent (:obj:`int`, optional): The packets retransmitted. See
            :mdn:`RTCOutboundRtpStreamStats/retransmittedPacketsSent`.
        retransmitted_bytes_sent (:obj:`int`, optional): The bytes of payload retransmitted. See
            :mdn:`RTCOutboundRtpStreamStats/retransmittedBytesSent`.
        rtx_ssrc (:obj:`int`, optional): The SSRC of the RTX stream.
        target_bitrate (:obj:`float`, optional): The target bitrate of the encoder, in bits per second. See
            :mdn:`RTCOutboundRtpStreamStats/targetBitrate`.
        total_encoded_bytes_target (:obj:`int`, optional): The sum of the target sizes of the encoded frames, in bytes.
            See :mdn:`RTCOutboundRtpStreamStats/totalEncodedBytesTarget`.
        frame_width (:obj:`int`, optional): The width of the last frame. See
            :mdn:`RTCOutboundRtpStreamStats/frameWidth`.
        frame_height (:obj:`int`, optional): The height of the last frame. See
            :mdn:`RTCOutboundRtpStreamStats/frameHeight`.
        frames_per_second (:obj:`float`, optional): The frames per second over the last second. See
            :mdn:`RTCOutboundRtpStreamStats/framesPerSecond`.
        frames_sent (:obj:`int`, optional): The frames sent. See :mdn:`RTCOutboundRtpStreamStats/framesSent`.
        huge_frames_sent (:obj:`int`, optional): The huge frames sent, like key frames.
        frames_encoded (:obj:`int`, optional): The frames encoded. See :mdn:`RTCOutboundRtpStreamStats/framesEncoded`.
        key_frames_encoded (:obj:`int`, optional): The key frames encoded. See
            :mdn:`RTCOutboundRtpStreamStats/keyFramesEncoded`.
        qp_sum (:obj:`int`, optional): The sum of the quantization parameters of the frames. See
            :mdn:`RTCOutboundRtpStreamStats/qpSum`.
        psnr_sum (:obj:`dict` of :obj:`str` to :obj:`float`, optional): The sums of the PSNR of the encoded frames, by
            component (``y``, ``u``, ``v``).
        psnr_measurements (:obj:`int`, optional): The PSNR measurements.
        total_encode_time (:obj:`float`, optional): The total seconds spent encoding. See
            :mdn:`RTCOutboundRtpStreamStats/totalEncodeTime`.
        total_packet_send_delay (:obj:`float`, optional): The total seconds packets waited to be sent. See
            :mdn:`RTCOutboundRtpStreamStats/totalPacketSendDelay`.
        quality_limitation_reason (:obj:`webrtc.RTCQualityLimitationReason`, optional): What limits the resolution or
            frame rate the most. See :mdn:`RTCOutboundRtpStreamStats/qualityLimitationReason`.
        quality_limitation_durations (:obj:`dict` of :obj:`str` to :obj:`float`, optional): The seconds limited by each
            reason. See :mdn:`RTCOutboundRtpStreamStats/qualityLimitationDurations`.
        quality_limitation_resolution_changes (:obj:`int`, optional): The resolution changes because of quality
            limitations.
        nack_count (:obj:`int`, optional): The NACK packets. See :mdn:`RTCOutboundRtpStreamStats/nackCount`.
        fir_count (:obj:`int`, optional): The FIR packets.
        pli_count (:obj:`int`, optional): The PLI packets.
        encoder_implementation (:obj:`str`, optional): The encoder, like ``libvpx``.
        power_efficient_encoder (:obj:`bool`, optional): Whether the encoder is power efficient.
        active (:obj:`bool`, optional): Whether the encoding is sent. See :mdn:`RTCOutboundRtpStreamStats/active`.
        scalability_mode (:obj:`str`, optional): The scalability mode, like ``'L1T3'``. See
            :mdn:`RTCOutboundRtpStreamStats/scalabilityMode`.
        packets_sent_with_ect1 (:obj:`int`, optional): The packets sent with the ECT(1) ECN marking.
    """

    mid: str | None = None
    media_source_id: str | None = None
    remote_id: str | None = None
    rid: str | None = None
    encoding_index: int | None = None
    header_bytes_sent: int | None = None
    retransmitted_packets_sent: int | None = None
    retransmitted_bytes_sent: int | None = None
    rtx_ssrc: int | None = None
    target_bitrate: float | None = None
    total_encoded_bytes_target: int | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    frames_per_second: float | None = None
    frames_sent: int | None = None
    huge_frames_sent: int | None = None
    frames_encoded: int | None = None
    key_frames_encoded: int | None = None
    qp_sum: int | None = None
    psnr_sum: dict[str, float] | None = None
    psnr_measurements: int | None = None
    total_encode_time: float | None = None
    total_packet_send_delay: float | None = None
    quality_limitation_reason: RTCQualityLimitationReason | str | None = None
    quality_limitation_durations: dict[str, float] | None = None
    quality_limitation_resolution_changes: int | None = None
    nack_count: int | None = None
    fir_count: int | None = None
    pli_count: int | None = None
    encoder_implementation: str | None = None
    power_efficient_encoder: bool | None = None
    active: bool | None = None
    scalability_mode: str | None = None
    packets_sent_with_ect1: int | None = None

    _enums: ClassVar = {'quality_limitation_reason': RTCQualityLimitationReason}

    #: Alias for :attr:`media_source_id`
    mediaSourceId: ClassVar[Alias[str | None]] = alias('media_source_id')
    #: Alias for :attr:`remote_id`
    remoteId: ClassVar[Alias[str | None]] = alias('remote_id')
    #: Alias for :attr:`encoding_index`
    encodingIndex: ClassVar[Alias[int | None]] = alias('encoding_index')
    #: Alias for :attr:`header_bytes_sent`
    headerBytesSent: ClassVar[Alias[int | None]] = alias('header_bytes_sent')
    #: Alias for :attr:`retransmitted_packets_sent`
    retransmittedPacketsSent: ClassVar[Alias[int | None]] = alias('retransmitted_packets_sent')
    #: Alias for :attr:`retransmitted_bytes_sent`
    retransmittedBytesSent: ClassVar[Alias[int | None]] = alias('retransmitted_bytes_sent')
    #: Alias for :attr:`rtx_ssrc`
    rtxSsrc: ClassVar[Alias[int | None]] = alias('rtx_ssrc')
    #: Alias for :attr:`target_bitrate`
    targetBitrate: ClassVar[Alias[float | None]] = alias('target_bitrate')
    #: Alias for :attr:`total_encoded_bytes_target`
    totalEncodedBytesTarget: ClassVar[Alias[int | None]] = alias('total_encoded_bytes_target')
    #: Alias for :attr:`frame_width`
    frameWidth: ClassVar[Alias[int | None]] = alias('frame_width')
    #: Alias for :attr:`frame_height`
    frameHeight: ClassVar[Alias[int | None]] = alias('frame_height')
    #: Alias for :attr:`frames_per_second`
    framesPerSecond: ClassVar[Alias[float | None]] = alias('frames_per_second')
    #: Alias for :attr:`frames_sent`
    framesSent: ClassVar[Alias[int | None]] = alias('frames_sent')
    #: Alias for :attr:`huge_frames_sent`
    hugeFramesSent: ClassVar[Alias[int | None]] = alias('huge_frames_sent')
    #: Alias for :attr:`frames_encoded`
    framesEncoded: ClassVar[Alias[int | None]] = alias('frames_encoded')
    #: Alias for :attr:`key_frames_encoded`
    keyFramesEncoded: ClassVar[Alias[int | None]] = alias('key_frames_encoded')
    #: Alias for :attr:`qp_sum`
    qpSum: ClassVar[Alias[int | None]] = alias('qp_sum')
    #: Alias for :attr:`psnr_sum`
    psnrSum: ClassVar[Alias[dict[str, float] | None]] = alias('psnr_sum')
    #: Alias for :attr:`psnr_measurements`
    psnrMeasurements: ClassVar[Alias[int | None]] = alias('psnr_measurements')
    #: Alias for :attr:`total_encode_time`
    totalEncodeTime: ClassVar[Alias[float | None]] = alias('total_encode_time')
    #: Alias for :attr:`total_packet_send_delay`
    totalPacketSendDelay: ClassVar[Alias[float | None]] = alias('total_packet_send_delay')
    #: Alias for :attr:`quality_limitation_reason`
    qualityLimitationReason: ClassVar[Alias[RTCQualityLimitationReason | str | None]] = alias(
        'quality_limitation_reason'
    )
    #: Alias for :attr:`quality_limitation_durations`
    qualityLimitationDurations: ClassVar[Alias[dict[str, float] | None]] = alias('quality_limitation_durations')
    #: Alias for :attr:`quality_limitation_resolution_changes`
    qualityLimitationResolutionChanges: ClassVar[Alias[int | None]] = alias('quality_limitation_resolution_changes')
    #: Alias for :attr:`nack_count`
    nackCount: ClassVar[Alias[int | None]] = alias('nack_count')
    #: Alias for :attr:`fir_count`
    firCount: ClassVar[Alias[int | None]] = alias('fir_count')
    #: Alias for :attr:`pli_count`
    pliCount: ClassVar[Alias[int | None]] = alias('pli_count')
    #: Alias for :attr:`encoder_implementation`
    encoderImplementation: ClassVar[Alias[str | None]] = alias('encoder_implementation')
    #: Alias for :attr:`power_efficient_encoder`
    powerEfficientEncoder: ClassVar[Alias[bool | None]] = alias('power_efficient_encoder')
    #: Alias for :attr:`scalability_mode`
    scalabilityMode: ClassVar[Alias[str | None]] = alias('scalability_mode')
    #: Alias for :attr:`packets_sent_with_ect1`
    packetsSentWithEct1: ClassVar[Alias[int | None]] = alias('packets_sent_with_ect1')


@dataclass(init=False)
class RTCRemoteOutboundRtpStreamStats(RTCSentRtpStreamStats):
    """Stats of a stream the connection receives, as the remote peer sends it. Its type is ``'remote-outbound-rtp'``.

    It has the members of :obj:`webrtc.RTCSentRtpStreamStats` too.

    See :mdn:`RTCRemoteOutboundRtpStreamStats`.

    Args:
        local_id (:obj:`str`, optional): The id of the inbound-rtp stats of the stream. See
            :mdn:`RTCRemoteOutboundRtpStreamStats/localId`.
        remote_timestamp (:obj:`float`, optional): When the remote peer sent its report, in milliseconds since the
            epoch. See :mdn:`RTCRemoteOutboundRtpStreamStats/remoteTimestamp`.
        reports_sent (:obj:`int`, optional): The RTCP sender reports sent.
        round_trip_time (:obj:`float`, optional): The last round trip time in seconds.
        total_round_trip_time (:obj:`float`, optional): The total seconds of the round trip times. See
            :mdn:`RTCRemoteOutboundRtpStreamStats/totalRoundTripTime`.
        round_trip_time_measurements (:obj:`int`, optional): The round trip time measurements. See
            :mdn:`RTCRemoteOutboundRtpStreamStats/roundTripTimeMeasurements`.
    """

    local_id: str | None = None
    remote_timestamp: float | None = None
    reports_sent: int | None = None
    round_trip_time: float | None = None
    total_round_trip_time: float | None = None
    round_trip_time_measurements: int | None = None

    #: Alias for :attr:`local_id`
    localId: ClassVar[Alias[str | None]] = alias('local_id')
    #: Alias for :attr:`remote_timestamp`
    remoteTimestamp: ClassVar[Alias[float | None]] = alias('remote_timestamp')
    #: Alias for :attr:`reports_sent`
    reportsSent: ClassVar[Alias[int | None]] = alias('reports_sent')
    #: Alias for :attr:`round_trip_time`
    roundTripTime: ClassVar[Alias[float | None]] = alias('round_trip_time')
    #: Alias for :attr:`total_round_trip_time`
    totalRoundTripTime: ClassVar[Alias[float | None]] = alias('total_round_trip_time')
    #: Alias for :attr:`round_trip_time_measurements`
    roundTripTimeMeasurements: ClassVar[Alias[int | None]] = alias('round_trip_time_measurements')


@dataclass(init=False)
class RTCMediaSourceStats(RTCStats):
    """Stats of a track a sender sends, of type ``'media-source'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    Args:
        track_identifier (:obj:`str`): The id of the track. See :mdn:`RTCAudioSourceStats/trackIdentifier`.
        kind (:obj:`str`): The kind of the track, ``'audio'`` or ``'video'``. See :mdn:`RTCAudioSourceStats/kind`.
    """

    track_identifier: str
    kind: str

    #: Alias for :attr:`track_identifier`
    trackIdentifier: ClassVar[Alias[str]] = alias('track_identifier')


@dataclass(init=False)
class RTCAudioSourceStats(RTCMediaSourceStats):
    """Stats of an audio track a sender sends, of type ``'media-source'``.

    It has the members of :obj:`webrtc.RTCMediaSourceStats` too.

    See :mdn:`RTCAudioSourceStats`.

    Args:
        audio_level (:obj:`float`, optional): The audio level, between 0 and 1. See
            :mdn:`RTCAudioSourceStats/audioLevel`.
        total_audio_energy (:obj:`float`, optional): The total audio energy. See
            :mdn:`RTCAudioSourceStats/totalAudioEnergy`.
        total_samples_duration (:obj:`float`, optional): The total seconds of the audio samples. See
            :mdn:`RTCAudioSourceStats/totalSamplesDuration`.
        echo_return_loss (:obj:`float`, optional): The echo return loss in decibels.
        echo_return_loss_enhancement (:obj:`float`, optional): The echo return loss enhancement in decibels.
    """

    audio_level: float | None = None
    total_audio_energy: float | None = None
    total_samples_duration: float | None = None
    echo_return_loss: float | None = None
    echo_return_loss_enhancement: float | None = None

    #: Alias for :attr:`audio_level`
    audioLevel: ClassVar[Alias[float | None]] = alias('audio_level')
    #: Alias for :attr:`total_audio_energy`
    totalAudioEnergy: ClassVar[Alias[float | None]] = alias('total_audio_energy')
    #: Alias for :attr:`total_samples_duration`
    totalSamplesDuration: ClassVar[Alias[float | None]] = alias('total_samples_duration')
    #: Alias for :attr:`echo_return_loss`
    echoReturnLoss: ClassVar[Alias[float | None]] = alias('echo_return_loss')
    #: Alias for :attr:`echo_return_loss_enhancement`
    echoReturnLossEnhancement: ClassVar[Alias[float | None]] = alias('echo_return_loss_enhancement')


@dataclass(init=False)
class RTCVideoSourceStats(RTCMediaSourceStats):
    """Stats of a video track a sender sends, of type ``'media-source'``.

    It has the members of :obj:`webrtc.RTCMediaSourceStats` too.

    See :mdn:`RTCVideoSourceStats`.

    Args:
        width (:obj:`int`, optional): The width of the last frame. See :mdn:`RTCVideoSourceStats/width`.
        height (:obj:`int`, optional): The height of the last frame. See :mdn:`RTCVideoSourceStats/height`.
        frames (:obj:`int`, optional): The frames from the source. See :mdn:`RTCVideoSourceStats/frames`.
        frames_per_second (:obj:`float`, optional): The frames per second over the last second. See
            :mdn:`RTCVideoSourceStats/framesPerSecond`.
    """

    width: int | None = None
    height: int | None = None
    frames: int | None = None
    frames_per_second: float | None = None

    #: Alias for :attr:`frames_per_second`
    framesPerSecond: ClassVar[Alias[float | None]] = alias('frames_per_second')


@dataclass(init=False)
class RTCAudioPlayoutStats(RTCStats):
    """Stats of the playout of received audio, of type ``'media-playout'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    Args:
        kind (:obj:`str`): The kind of the media, ``'audio'``.
        synthesized_samples_duration (:obj:`float`, optional): The total seconds of samples synthesized for playout.
        synthesized_samples_events (:obj:`int`, optional): The events of synthesizing samples.
        total_samples_duration (:obj:`float`, optional): The total seconds of samples played out.
        total_playout_delay (:obj:`float`, optional): The sum of the playout delays of the samples, in seconds.
        total_samples_count (:obj:`int`, optional): The samples played out.
    """

    kind: str
    synthesized_samples_duration: float | None = None
    synthesized_samples_events: int | None = None
    total_samples_duration: float | None = None
    total_playout_delay: float | None = None
    total_samples_count: int | None = None

    #: Alias for :attr:`synthesized_samples_duration`
    synthesizedSamplesDuration: ClassVar[Alias[float | None]] = alias('synthesized_samples_duration')
    #: Alias for :attr:`synthesized_samples_events`
    synthesizedSamplesEvents: ClassVar[Alias[int | None]] = alias('synthesized_samples_events')
    #: Alias for :attr:`total_samples_duration`
    totalSamplesDuration: ClassVar[Alias[float | None]] = alias('total_samples_duration')
    #: Alias for :attr:`total_playout_delay`
    totalPlayoutDelay: ClassVar[Alias[float | None]] = alias('total_playout_delay')
    #: Alias for :attr:`total_samples_count`
    totalSamplesCount: ClassVar[Alias[int | None]] = alias('total_samples_count')


@dataclass(init=False)
class RTCPeerConnectionStats(RTCStats):
    """Stats of the connection, of type ``'peer-connection'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    See :mdn:`RTCPeerConnectionStats`.

    Args:
        data_channels_opened (:obj:`int`, optional): The data channels opened. See
            :mdn:`RTCPeerConnectionStats/dataChannelsOpened`.
        data_channels_closed (:obj:`int`, optional): The data channels closed. See
            :mdn:`RTCPeerConnectionStats/dataChannelsClosed`.
    """

    data_channels_opened: int | None = None
    data_channels_closed: int | None = None

    #: Alias for :attr:`data_channels_opened`
    dataChannelsOpened: ClassVar[Alias[int | None]] = alias('data_channels_opened')
    #: Alias for :attr:`data_channels_closed`
    dataChannelsClosed: ClassVar[Alias[int | None]] = alias('data_channels_closed')


@dataclass(init=False)
class RTCDataChannelStats(RTCStats):
    """Stats of a data channel, of type ``'data-channel'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    See :mdn:`RTCDataChannelStats`.

    Args:
        label (:obj:`str`, optional): The label of the channel. See :mdn:`RTCDataChannelStats/label`.
        protocol (:obj:`str`, optional): The subprotocol of the channel. See :mdn:`RTCDataChannelStats/protocol`.
        data_channel_identifier (:obj:`int`, optional): The id of the channel. See
            :mdn:`RTCDataChannelStats/dataChannelIdentifier`.
        state (:obj:`webrtc.RTCDataChannelState`): The state of the channel. See :mdn:`RTCDataChannelStats/state`.
        messages_sent (:obj:`int`, optional): The messages sent. See :mdn:`RTCDataChannelStats/messagesSent`.
        bytes_sent (:obj:`int`, optional): The bytes sent. See :mdn:`RTCDataChannelStats/bytesSent`.
        messages_received (:obj:`int`, optional): The messages received. See
            :mdn:`RTCDataChannelStats/messagesReceived`.
        bytes_received (:obj:`int`, optional): The bytes received. See :mdn:`RTCDataChannelStats/bytesReceived`.
    """

    label: str | None = None
    protocol: str | None = None
    data_channel_identifier: int | None = None
    state: RTCDataChannelState | str
    messages_sent: int | None = None
    bytes_sent: int | None = None
    messages_received: int | None = None
    bytes_received: int | None = None

    _enums: ClassVar = {'state': RTCDataChannelState}

    #: Alias for :attr:`data_channel_identifier`
    dataChannelIdentifier: ClassVar[Alias[int | None]] = alias('data_channel_identifier')
    #: Alias for :attr:`messages_sent`
    messagesSent: ClassVar[Alias[int | None]] = alias('messages_sent')
    #: Alias for :attr:`bytes_sent`
    bytesSent: ClassVar[Alias[int | None]] = alias('bytes_sent')
    #: Alias for :attr:`messages_received`
    messagesReceived: ClassVar[Alias[int | None]] = alias('messages_received')
    #: Alias for :attr:`bytes_received`
    bytesReceived: ClassVar[Alias[int | None]] = alias('bytes_received')


@dataclass(init=False)
class RTCTransportStats(RTCStats):
    """Stats of a transport, of type ``'transport'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    See :mdn:`RTCTransportStats`.

    Args:
        packets_sent (:obj:`int`, optional): The packets sent. See :mdn:`RTCTransportStats/packetsSent`.
        packets_received (:obj:`int`, optional): The packets received. See :mdn:`RTCTransportStats/packetsReceived`.
        bytes_sent (:obj:`int`, optional): The bytes sent. See :mdn:`RTCTransportStats/bytesSent`.
        bytes_received (:obj:`int`, optional): The bytes received. See :mdn:`RTCTransportStats/bytesReceived`.
        ice_role (:obj:`webrtc.RTCIceRole`, optional): The ICE role. See :mdn:`RTCTransportStats/iceRole`.
        ice_local_username_fragment (:obj:`str`, optional): The local ICE username fragment. See
            :mdn:`RTCTransportStats/iceLocalUsernameFragment`.
        dtls_state (:obj:`webrtc.RTCDtlsTransportState`): The DTLS state. See :mdn:`RTCTransportStats/dtlsState`.
        ice_state (:obj:`webrtc.RTCIceTransportState`, optional): The ICE state. See :mdn:`RTCTransportStats/iceState`.
        selected_candidate_pair_id (:obj:`str`, optional): The id of the stats of the selected candidate pair. See
            :mdn:`RTCTransportStats/selectedCandidatePairId`.
        local_certificate_id (:obj:`str`, optional): The id of the stats of the local certificate. See
            :mdn:`RTCTransportStats/localCertificateId`.
        remote_certificate_id (:obj:`str`, optional): The id of the stats of the remote certificate. See
            :mdn:`RTCTransportStats/remoteCertificateId`.
        tls_version (:obj:`str`, optional): The DTLS version, in hex. See :mdn:`RTCTransportStats/tlsVersion`.
        dtls_cipher (:obj:`str`, optional): The DTLS cipher suite. See :mdn:`RTCTransportStats/dtlsCipher`.
        dtls_role (:obj:`webrtc.RTCDtlsRole`, optional): The DTLS role. See :mdn:`RTCTransportStats/dtlsRole`.
        srtp_cipher (:obj:`str`, optional): The SRTP protection profile. See :mdn:`RTCTransportStats/srtpCipher`.
        selected_candidate_pair_changes (:obj:`int`, optional): The changes of the selected candidate pair. See
            :mdn:`RTCTransportStats/selectedCandidatePairChanges`.
        ccfb_messages_sent (:obj:`int`, optional): The congestion control feedback messages sent.
        ccfb_messages_received (:obj:`int`, optional): The congestion control feedback messages received.
    """

    packets_sent: int | None = None
    packets_received: int | None = None
    bytes_sent: int | None = None
    bytes_received: int | None = None
    ice_role: RTCIceRole | str | None = None
    ice_local_username_fragment: str | None = None
    dtls_state: RTCDtlsTransportState | str
    ice_state: RTCIceTransportState | str | None = None
    selected_candidate_pair_id: str | None = None
    local_certificate_id: str | None = None
    remote_certificate_id: str | None = None
    tls_version: str | None = None
    dtls_cipher: str | None = None
    dtls_role: RTCDtlsRole | str | None = None
    srtp_cipher: str | None = None
    selected_candidate_pair_changes: int | None = None
    ccfb_messages_sent: int | None = None
    ccfb_messages_received: int | None = None

    _enums: ClassVar = {
        'ice_role': RTCIceRole,
        'dtls_state': RTCDtlsTransportState,
        'ice_state': RTCIceTransportState,
        'dtls_role': RTCDtlsRole,
    }

    #: Alias for :attr:`packets_sent`
    packetsSent: ClassVar[Alias[int | None]] = alias('packets_sent')
    #: Alias for :attr:`packets_received`
    packetsReceived: ClassVar[Alias[int | None]] = alias('packets_received')
    #: Alias for :attr:`bytes_sent`
    bytesSent: ClassVar[Alias[int | None]] = alias('bytes_sent')
    #: Alias for :attr:`bytes_received`
    bytesReceived: ClassVar[Alias[int | None]] = alias('bytes_received')
    #: Alias for :attr:`ice_role`
    iceRole: ClassVar[Alias[RTCIceRole | str | None]] = alias('ice_role')
    #: Alias for :attr:`ice_local_username_fragment`
    iceLocalUsernameFragment: ClassVar[Alias[str | None]] = alias('ice_local_username_fragment')
    #: Alias for :attr:`dtls_state`
    dtlsState: ClassVar[Alias[RTCDtlsTransportState | str]] = alias('dtls_state')
    #: Alias for :attr:`ice_state`
    iceState: ClassVar[Alias[RTCIceTransportState | str | None]] = alias('ice_state')
    #: Alias for :attr:`selected_candidate_pair_id`
    selectedCandidatePairId: ClassVar[Alias[str | None]] = alias('selected_candidate_pair_id')
    #: Alias for :attr:`local_certificate_id`
    localCertificateId: ClassVar[Alias[str | None]] = alias('local_certificate_id')
    #: Alias for :attr:`remote_certificate_id`
    remoteCertificateId: ClassVar[Alias[str | None]] = alias('remote_certificate_id')
    #: Alias for :attr:`tls_version`
    tlsVersion: ClassVar[Alias[str | None]] = alias('tls_version')
    #: Alias for :attr:`dtls_cipher`
    dtlsCipher: ClassVar[Alias[str | None]] = alias('dtls_cipher')
    #: Alias for :attr:`dtls_role`
    dtlsRole: ClassVar[Alias[RTCDtlsRole | str | None]] = alias('dtls_role')
    #: Alias for :attr:`srtp_cipher`
    srtpCipher: ClassVar[Alias[str | None]] = alias('srtp_cipher')
    #: Alias for :attr:`selected_candidate_pair_changes`
    selectedCandidatePairChanges: ClassVar[Alias[int | None]] = alias('selected_candidate_pair_changes')
    #: Alias for :attr:`ccfb_messages_sent`
    ccfbMessagesSent: ClassVar[Alias[int | None]] = alias('ccfb_messages_sent')
    #: Alias for :attr:`ccfb_messages_received`
    ccfbMessagesReceived: ClassVar[Alias[int | None]] = alias('ccfb_messages_received')


@dataclass(init=False)
class RTCIceCandidateStats(RTCStats):
    """Stats of an ICE candidate, of type ``'local-candidate'`` or ``'remote-candidate'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    See :mdn:`RTCIceCandidateStats`.

    Args:
        transport_id (:obj:`str`): The id of the stats of the transport of the candidate. See
            :mdn:`RTCIceCandidateStats/transportId`.
        address (:obj:`str`, optional): The address of the candidate, or :obj:`None` if it isn't exposed. See
            :mdn:`RTCIceCandidateStats/address`.
        port (:obj:`int`, optional): The port. See :mdn:`RTCIceCandidateStats/port`.
        protocol (:obj:`str`, optional): The protocol, ``'udp'`` or ``'tcp'``. See :mdn:`RTCIceCandidateStats/protocol`.
        candidate_type (:obj:`webrtc.RTCIceCandidateType`): The type of the candidate. See
            :mdn:`RTCIceCandidateStats/candidateType`.
        priority (:obj:`int`, optional): The priority. See :mdn:`RTCIceCandidateStats/priority`.
        url (:obj:`str`, optional): The URL of the ICE server the candidate is from. See
            :mdn:`RTCIceCandidateStats/url`.
        relay_protocol (:obj:`webrtc.RTCIceServerTransportProtocol`, optional): The protocol between the client and the
            TURN server. See :mdn:`RTCIceCandidateStats/relayProtocol`.
        foundation (:obj:`str`, optional): The foundation. See :mdn:`RTCIceCandidateStats/foundation`.
        related_address (:obj:`str`, optional): The related address.
        related_port (:obj:`int`, optional): The related port.
        username_fragment (:obj:`str`, optional): The ICE username fragment. See
            :mdn:`RTCIceCandidateStats/usernameFragment`.
        tcp_type (:obj:`webrtc.RTCIceTcpCandidateType`, optional): The type of a TCP candidate.
    """

    transport_id: str
    address: str | None = None
    port: int | None = None
    protocol: str | None = None
    candidate_type: RTCIceCandidateType | str
    priority: int | None = None
    url: str | None = None
    relay_protocol: RTCIceServerTransportProtocol | str | None = None
    foundation: str | None = None
    related_address: str | None = None
    related_port: int | None = None
    username_fragment: str | None = None
    tcp_type: RTCIceTcpCandidateType | str | None = None

    _enums: ClassVar = {
        'candidate_type': RTCIceCandidateType,
        'relay_protocol': RTCIceServerTransportProtocol,
        'tcp_type': RTCIceTcpCandidateType,
    }

    #: Alias for :attr:`transport_id`
    transportId: ClassVar[Alias[str]] = alias('transport_id')
    #: Alias for :attr:`candidate_type`
    candidateType: ClassVar[Alias[RTCIceCandidateType | str]] = alias('candidate_type')
    #: Alias for :attr:`relay_protocol`
    relayProtocol: ClassVar[Alias[RTCIceServerTransportProtocol | str | None]] = alias('relay_protocol')
    #: Alias for :attr:`related_address`
    relatedAddress: ClassVar[Alias[str | None]] = alias('related_address')
    #: Alias for :attr:`related_port`
    relatedPort: ClassVar[Alias[int | None]] = alias('related_port')
    #: Alias for :attr:`username_fragment`
    usernameFragment: ClassVar[Alias[str | None]] = alias('username_fragment')
    #: Alias for :attr:`tcp_type`
    tcpType: ClassVar[Alias[RTCIceTcpCandidateType | str | None]] = alias('tcp_type')


@dataclass(init=False)
class RTCIceCandidatePairStats(RTCStats):
    """Stats of an ICE candidate pair, of type ``'candidate-pair'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    See :mdn:`RTCIceCandidatePairStats`.

    Args:
        transport_id (:obj:`str`): The id of the stats of the transport of the pair. See
            :mdn:`RTCIceCandidatePairStats/transportId`.
        local_candidate_id (:obj:`str`): The id of the stats of the local candidate. See
            :mdn:`RTCIceCandidatePairStats/localCandidateId`.
        remote_candidate_id (:obj:`str`): The id of the stats of the remote candidate. See
            :mdn:`RTCIceCandidatePairStats/remoteCandidateId`.
        state (:obj:`webrtc.RTCStatsIceCandidatePairState`): The state of the pair in the checklist. See
            :mdn:`RTCIceCandidatePairStats/state`.
        nominated (:obj:`bool`, optional): Whether the pair is nominated. See :mdn:`RTCIceCandidatePairStats/nominated`.
        packets_sent (:obj:`int`, optional): The packets sent. See :mdn:`RTCIceCandidatePairStats/packetsSent`.
        packets_received (:obj:`int`, optional): The packets received. See
            :mdn:`RTCIceCandidatePairStats/packetsReceived`.
        bytes_sent (:obj:`int`, optional): The bytes sent. See :mdn:`RTCIceCandidatePairStats/bytesSent`.
        bytes_received (:obj:`int`, optional): The bytes received. See :mdn:`RTCIceCandidatePairStats/bytesReceived`.
        last_packet_sent_timestamp (:obj:`float`, optional): When the last packet was sent, in milliseconds since the
            epoch. See :mdn:`RTCIceCandidatePairStats/lastPacketSentTimestamp`.
        last_packet_received_timestamp (:obj:`float`, optional): When the last packet was received, in milliseconds
            since the epoch. See :mdn:`RTCIceCandidatePairStats/lastPacketReceivedTimestamp`.
        total_round_trip_time (:obj:`float`, optional): The total seconds of the round trip times of STUN requests. See
            :mdn:`RTCIceCandidatePairStats/totalRoundTripTime`.
        current_round_trip_time (:obj:`float`, optional): The last round trip time of STUN requests, in seconds. See
            :mdn:`RTCIceCandidatePairStats/currentRoundTripTime`.
        available_outgoing_bitrate (:obj:`float`, optional): The estimated outgoing bitrate available, in bits per
            second. See :mdn:`RTCIceCandidatePairStats/availableOutgoingBitrate`.
        available_incoming_bitrate (:obj:`float`, optional): The estimated incoming bitrate available, in bits per
            second. See :mdn:`RTCIceCandidatePairStats/availableIncomingBitrate`.
        requests_received (:obj:`int`, optional): The connectivity check requests received. See
            :mdn:`RTCIceCandidatePairStats/requestsReceived`.
        requests_sent (:obj:`int`, optional): The connectivity check requests sent. See
            :mdn:`RTCIceCandidatePairStats/requestsSent`.
        responses_received (:obj:`int`, optional): The connectivity check responses received. See
            :mdn:`RTCIceCandidatePairStats/responsesReceived`.
        responses_sent (:obj:`int`, optional): The connectivity check responses sent. See
            :mdn:`RTCIceCandidatePairStats/responsesSent`.
        consent_requests_sent (:obj:`int`, optional): The consent requests sent. See
            :mdn:`RTCIceCandidatePairStats/consentRequestsSent`.
        packets_discarded_on_send (:obj:`int`, optional): The packets that failed to be sent. See
            :mdn:`RTCIceCandidatePairStats/packetsDiscardedOnSend`.
        bytes_discarded_on_send (:obj:`int`, optional): The bytes that failed to be sent. See
            :mdn:`RTCIceCandidatePairStats/bytesDiscardedOnSend`.
    """

    transport_id: str
    local_candidate_id: str
    remote_candidate_id: str
    state: RTCStatsIceCandidatePairState | str
    nominated: bool | None = None
    packets_sent: int | None = None
    packets_received: int | None = None
    bytes_sent: int | None = None
    bytes_received: int | None = None
    last_packet_sent_timestamp: float | None = None
    last_packet_received_timestamp: float | None = None
    total_round_trip_time: float | None = None
    current_round_trip_time: float | None = None
    available_outgoing_bitrate: float | None = None
    available_incoming_bitrate: float | None = None
    requests_received: int | None = None
    requests_sent: int | None = None
    responses_received: int | None = None
    responses_sent: int | None = None
    consent_requests_sent: int | None = None
    packets_discarded_on_send: int | None = None
    bytes_discarded_on_send: int | None = None

    _enums: ClassVar = {'state': RTCStatsIceCandidatePairState}

    #: Alias for :attr:`transport_id`
    transportId: ClassVar[Alias[str]] = alias('transport_id')
    #: Alias for :attr:`local_candidate_id`
    localCandidateId: ClassVar[Alias[str]] = alias('local_candidate_id')
    #: Alias for :attr:`remote_candidate_id`
    remoteCandidateId: ClassVar[Alias[str]] = alias('remote_candidate_id')
    #: Alias for :attr:`packets_sent`
    packetsSent: ClassVar[Alias[int | None]] = alias('packets_sent')
    #: Alias for :attr:`packets_received`
    packetsReceived: ClassVar[Alias[int | None]] = alias('packets_received')
    #: Alias for :attr:`bytes_sent`
    bytesSent: ClassVar[Alias[int | None]] = alias('bytes_sent')
    #: Alias for :attr:`bytes_received`
    bytesReceived: ClassVar[Alias[int | None]] = alias('bytes_received')
    #: Alias for :attr:`last_packet_sent_timestamp`
    lastPacketSentTimestamp: ClassVar[Alias[float | None]] = alias('last_packet_sent_timestamp')
    #: Alias for :attr:`last_packet_received_timestamp`
    lastPacketReceivedTimestamp: ClassVar[Alias[float | None]] = alias('last_packet_received_timestamp')
    #: Alias for :attr:`total_round_trip_time`
    totalRoundTripTime: ClassVar[Alias[float | None]] = alias('total_round_trip_time')
    #: Alias for :attr:`current_round_trip_time`
    currentRoundTripTime: ClassVar[Alias[float | None]] = alias('current_round_trip_time')
    #: Alias for :attr:`available_outgoing_bitrate`
    availableOutgoingBitrate: ClassVar[Alias[float | None]] = alias('available_outgoing_bitrate')
    #: Alias for :attr:`available_incoming_bitrate`
    availableIncomingBitrate: ClassVar[Alias[float | None]] = alias('available_incoming_bitrate')
    #: Alias for :attr:`requests_received`
    requestsReceived: ClassVar[Alias[int | None]] = alias('requests_received')
    #: Alias for :attr:`requests_sent`
    requestsSent: ClassVar[Alias[int | None]] = alias('requests_sent')
    #: Alias for :attr:`responses_received`
    responsesReceived: ClassVar[Alias[int | None]] = alias('responses_received')
    #: Alias for :attr:`responses_sent`
    responsesSent: ClassVar[Alias[int | None]] = alias('responses_sent')
    #: Alias for :attr:`consent_requests_sent`
    consentRequestsSent: ClassVar[Alias[int | None]] = alias('consent_requests_sent')
    #: Alias for :attr:`packets_discarded_on_send`
    packetsDiscardedOnSend: ClassVar[Alias[int | None]] = alias('packets_discarded_on_send')
    #: Alias for :attr:`bytes_discarded_on_send`
    bytesDiscardedOnSend: ClassVar[Alias[int | None]] = alias('bytes_discarded_on_send')


@dataclass(init=False)
class RTCCertificateStats(RTCStats):
    """Stats of a certificate, of type ``'certificate'``.

    It has the members of :obj:`webrtc.RTCStats` too.

    See :mdn:`RTCCertificateStats`.

    Args:
        fingerprint (:obj:`str`): The fingerprint of the certificate. See :mdn:`RTCCertificateStats/fingerprint`.
        fingerprint_algorithm (:obj:`str`): The hash function of the fingerprint, like ``'sha-256'``. See
            :mdn:`RTCCertificateStats/fingerprintAlgorithm`.
        base64_certificate (:obj:`str`): The DER of the certificate, in base64. See
            :mdn:`RTCCertificateStats/base64Certificate`.
        issuer_certificate_id (:obj:`str`, optional): The id of the stats of the issuer certificate. See
            :mdn:`RTCCertificateStats/issuerCertificateId`.
    """

    fingerprint: str
    fingerprint_algorithm: str
    base64_certificate: str
    issuer_certificate_id: str | None = None

    #: Alias for :attr:`fingerprint_algorithm`
    fingerprintAlgorithm: ClassVar[Alias[str]] = alias('fingerprint_algorithm')
    #: Alias for :attr:`base64_certificate`
    base64Certificate: ClassVar[Alias[str]] = alias('base64_certificate')
    #: Alias for :attr:`issuer_certificate_id`
    issuerCertificateId: ClassVar[Alias[str | None]] = alias('issuer_certificate_id')


# the dictionary of each type of stats, but media-source, which also depends on the kind
_DICTIONARIES: Mapping[str, type[RTCStats]] = {
    'codec': RTCCodecStats,
    'inbound-rtp': RTCInboundRtpStreamStats,
    'outbound-rtp': RTCOutboundRtpStreamStats,
    'remote-inbound-rtp': RTCRemoteInboundRtpStreamStats,
    'remote-outbound-rtp': RTCRemoteOutboundRtpStreamStats,
    'media-playout': RTCAudioPlayoutStats,
    'peer-connection': RTCPeerConnectionStats,
    'data-channel': RTCDataChannelStats,
    'transport': RTCTransportStats,
    'candidate-pair': RTCIceCandidatePairStats,
    'local-candidate': RTCIceCandidateStats,
    'remote-candidate': RTCIceCandidateStats,
    'certificate': RTCCertificateStats,
}
_SOURCES: Mapping[object, type[RTCStats]] = {'audio': RTCAudioSourceStats, 'video': RTCVideoSourceStats}


def _dictionary(entry: Mapping[str, object]) -> type[RTCStats]:
    if entry.get('type') == 'media-source':
        return _SOURCES.get(entry.get('kind'), RTCMediaSourceStats)
    stats_type = entry.get('type')
    return _DICTIONARIES.get(stats_type, RTCStats) if isinstance(stats_type, str) else RTCStats


def _stats(entry: Mapping[str, object]) -> RTCStats:
    try:
        return _dictionary(entry).from_json(entry)
    except TypeError:
        # libwebrtc lacks a required member of the dictionary: only the members of every stats are left
        return RTCStats.from_json(entry)


class RTCStatsReport(Mapping[str, RTCStats]):
    """The stats of a connection, a sender or a receiver, as a read-only mapping of stats ids to stats.

    Each value is the dictionary of its type, like :obj:`webrtc.RTCInboundRtpStreamStats` for ``'inbound-rtp'``.
    The ``track_identifier`` of inbound RTP stats is the :attr:`webrtc.MediaStreamTrack.id` of the remote track, and
    the ``address`` of a candidate is :obj:`None` when it isn't exposed, like for peer-reflexive ones.

    See :mdn:`RTCStatsReport`.

    Args:
        stats (:obj:`dict` of :obj:`str` to :obj:`webrtc.RTCStats`): The stats, by their ids.
    """

    def __init__(self, stats: Mapping[str, RTCStats]) -> None:
        self._stats = dict(stats)

    @classmethod
    def _from_native(cls, report: str, receivers: Iterable[webrtc.RTCRtpReceiver] = ()) -> RTCStatsReport:
        """The report from its native JSON, with the receivers whose tracks it refers to."""
        # remote tracks have their own ids, rather than the libwebrtc ones in the stats
        track_ids = {receiver.track._native_obj._nativeId: receiver.track.id for receiver in receivers}
        entries: list[dict[str, object]] = json.loads(report if report != '' else '[]')
        for entry in entries:
            # libwebrtc serializes microseconds
            timestamp = entry.get('timestamp')
            if isinstance(timestamp, (int, float)):
                entry['timestamp'] = timestamp / 1000
            track_id = entry.get('trackIdentifier')
            if entry.get('type') == 'inbound-rtp' and isinstance(track_id, str) and track_id in track_ids:
                entry['trackIdentifier'] = track_ids[track_id]
            # libwebrtc leaves the addresses of candidates it doesn't expose (like peer-reflexive ones) empty
            if entry.get('type') in {'local-candidate', 'remote-candidate'} and entry.get('address') == '':
                entry['address'] = None
        stats = [_stats(entry) for entry in entries]
        return cls({entry.id: entry for entry in stats})

    def __getitem__(self, stats_id: str) -> RTCStats:
        return self._stats[stats_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._stats)

    def __len__(self) -> int:
        return len(self._stats)

    def __repr__(self) -> str:
        return f'RTCStatsReport({len(self)} stats)'
