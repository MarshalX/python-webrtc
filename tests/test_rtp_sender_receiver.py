#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Senders and receivers: capabilities, parameters, codecs, tracks, DTMF and synchronization sources."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

import webrtc
import wrtc
from tests.helpers import (
    connect,
    exchange_offer,
    exchange_offer_answer,
    mistyped,
    next_task,
    stats_of_type,
    wait_for_event,
    wait_until,
)
from tests.timing import seconds

if TYPE_CHECKING:
    from collections.abc import Callable


def test_capabilities() -> None:
    """Senders and receivers of audio and video have codecs and header extensions, of data none."""
    audio = webrtc.RTCRtpSender.get_capabilities(webrtc.MediaType.audio)
    assert audio is not None
    assert any(codec.mime_type == 'audio/opus' for codec in audio.codecs)
    assert len(audio.header_extensions) > 0
    video = webrtc.RTCRtpReceiver.get_capabilities('video')
    assert video is not None
    assert len(video.codecs) > 0
    assert webrtc.RTCRtpSender.get_capabilities('data') is None


def add_simulcast_sender(pc: webrtc.RTCPeerConnection) -> webrtc.RTCRtpSender:
    init = webrtc.RTCRtpTransceiverInit(
        send_encodings=[webrtc.RTCRtpEncodingParameters(rid='hi'), webrtc.RTCRtpEncodingParameters(rid='lo')]
    )
    return pc.add_transceiver(webrtc.MediaType.video, init).sender


def test_default_send_parameters(pc: webrtc.RTCPeerConnection) -> None:
    """Video encodings scale down by powers of 2 by default, and the parameters of a task share a transaction."""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    assert [e.scale_resolution_down_by for e in parameters.encodings] == [2.0, 1.0]
    assert sender.get_parameters().transaction_id == parameters.transaction_id


@pytest.mark.asyncio
async def test_set_send_parameters(pc: webrtc.RTCPeerConnection) -> None:
    """Changed encodings are applied."""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    parameters.encodings[0].max_bitrate = 500_000
    parameters.encodings[1].active = False
    await sender.set_parameters(parameters)
    # read back in a later task, which gets new parameters
    await next_task()

    changed = sender.get_parameters()
    assert changed.encodings[0].max_bitrate == 500_000
    assert not changed.encodings[1].active


@pytest.mark.asyncio
async def test_send_parameters_out_of_range(pc: webrtc.RTCPeerConnection) -> None:
    """An encoding can't scale the resolution up."""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    parameters.encodings[0].scale_resolution_down_by = 0.5
    with pytest.raises(webrtc.InvalidRangeError):
        await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_send_parameters_with_other_encodings(pc: webrtc.RTCPeerConnection) -> None:
    """The number of encodings can't change."""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    parameters.encodings.pop()
    with pytest.raises(webrtc.InvalidModificationError):
        await sender.set_parameters(parameters)


def flip_reduced_size(parameters: webrtc.RTCRtpSendParameters) -> None:
    parameters.rtcp.reduced_size = parameters.rtcp.reduced_size is not True


def add_header_extension(parameters: webrtc.RTCRtpSendParameters) -> None:
    parameters.header_extensions.append(webrtc.RTCRtpHeaderExtensionParameters('urn:example', 14))


def add_codec(parameters: webrtc.RTCRtpSendParameters) -> None:
    parameters.codecs.append(webrtc.RTCRtpCodecParameters(96, 'video/VP8', 90000))


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [flip_reduced_size, add_header_extension, add_codec])
async def test_send_parameters_keep_what_is_negotiated(
    pc: webrtc.RTCPeerConnection, change: Callable[[webrtc.RTCRtpSendParameters], None]
) -> None:
    """The RTCP parameters, header extensions and codecs can't change."""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    change(parameters)
    with pytest.raises(webrtc.InvalidModificationError, match='can not be changed'):
        await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_send_parameters_negative_framerate(pc: webrtc.RTCPeerConnection) -> None:
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    parameters.encodings[0].max_framerate = -1
    with pytest.raises(webrtc.InvalidRangeError):
        await sender.set_parameters(parameters)


def test_scale_resolution_down_by_defaults_to_1_once_one_is_set(pc: webrtc.RTCPeerConnection) -> None:
    encodings = [
        webrtc.RTCRtpEncodingParameters(rid='hi'),
        webrtc.RTCRtpEncodingParameters(rid='lo', scale_resolution_down_by=4),
    ]
    init = webrtc.RTCRtpTransceiverInit(send_encodings=encodings)
    sender = pc.add_transceiver(webrtc.MediaType.video, init).sender
    assert [e.scale_resolution_down_by for e in sender.get_parameters().encodings] == [1.0, 4.0]


@pytest.mark.asyncio
async def test_send_parameters_of_simulcast_negotiated_away(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Parameters from before simulcast was negotiated away can't be set."""
    sender = add_simulcast_sender(caller)
    parameters = sender.get_parameters()
    await exchange_offer(caller, callee)
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    # an answerer that doesn't receive simulcast
    sdp = ''.join(
        line for line in answer.sdp.splitlines(keepends=True) if not line.startswith(('a=rid:', 'a=simulcast:'))
    )
    await caller.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', sdp))
    with pytest.raises(webrtc.InvalidModificationError, match='encodings of the sender changed'):
        await sender.set_parameters(parameters)
    assert [e.rid for e in sender.get_parameters().encodings] == ['hi']


@pytest.mark.asyncio
async def test_parameters_of_an_earlier_task(pc: webrtc.RTCPeerConnection) -> None:
    """The last parameters can be set after their task, but only once."""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    await next_task()
    await sender.set_parameters(parameters)
    with pytest.raises(webrtc.InvalidStateError):
        await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_parameters_replaced_in_a_later_task(pc: webrtc.RTCPeerConnection) -> None:
    """A later task gets new parameters, which the earlier ones can't be set over."""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    await next_task()
    assert sender.get_parameters().transaction_id != parameters.transaction_id
    with pytest.raises(webrtc.InvalidModificationError):
        await sender.set_parameters(parameters)


@pytest.mark.parametrize(
    ('rids', 'error'),
    [
        (['a', 'a'], 'needs a distinct rid'),
        (['a', None], 'needs a distinct rid'),
        (['no-dash'], 'not a valid rid'),
        ([''], 'not a valid rid'),
    ],
    ids=['duplicate rid', 'missing rid', 'invalid rid', 'empty rid'],
)
def test_invalid_send_encodings(pc: webrtc.RTCPeerConnection, rids: list[str | None], error: str) -> None:
    """The rids of send encodings are unique, present when there are several, and alphanumeric."""
    init = webrtc.RTCRtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(rid=rid) for rid in rids])
    with pytest.raises(TypeError, match=error):
        pc.add_transceiver(webrtc.MediaType.video, init)


def test_send_encoding_of_an_unknown_codec(pc: webrtc.RTCPeerConnection) -> None:
    """The codec of a send encoding must be one the sender supports."""
    unknown = webrtc.RTCRtpEncodingParameters(codec=webrtc.RTCRtpCodec('audio/unknown', 8000))
    with pytest.raises(webrtc.OperationError):
        pc.add_transceiver(webrtc.MediaType.audio, webrtc.RTCRtpTransceiverInit(send_encodings=[unknown]))


def test_send_encoding_codec_matches_its_parameters(pc: webrtc.RTCPeerConnection) -> None:
    """The fmtp parameters match in any order."""
    capabilities = webrtc.RTCRtpSender.get_capabilities(webrtc.MediaType.audio)
    assert capabilities is not None
    opus = next(c for c in capabilities.codecs if c.mime_type == 'audio/opus')
    assert opus.sdp_fmtp_line == 'minptime=10;useinbandfec=1'
    reordered = webrtc.RTCRtpCodec('audio/opus', 48000, 2, 'useinbandfec=1; minptime=10')
    init = webrtc.RTCRtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(codec=reordered)])
    (encoding,) = pc.add_transceiver(webrtc.MediaType.audio, init).sender.get_parameters().encodings
    assert encoding.codec == opus

    # a nameless parameter, as RED has, counts too
    red = webrtc.RTCRtpCodec('audio/red', 48000, 2, '111/111')
    with pytest.raises(webrtc.OperationError, match='audio/red can not be sent'):
        pc.add_transceiver(
            webrtc.MediaType.audio,
            webrtc.RTCRtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(codec=red)]),
        )


@pytest.mark.asyncio
async def test_set_parameters_codec_without_a_mime_type(pc: webrtc.RTCPeerConnection) -> None:
    """A codec that isn't type/subtype matches no codec."""
    sender = pc.add_transceiver(webrtc.MediaType.audio).sender
    cases = [
        (webrtc.RTCRtpCodec('opus', 48000, 2), 'not a valid MIME type'),
        (webrtc.RTCRtpCodec('audio/x', 8000), 'unsupported codec'),
    ]
    for codec, error in cases:
        parameters = sender.get_parameters()
        parameters.encodings[0].codec = codec
        with pytest.raises(webrtc.InvalidModificationError, match=error):
            await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_negotiated_codecs(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Codecs are listed once negotiated, none before."""
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    assert transceiver.receiver.get_parameters().codecs == []
    await exchange_offer_answer(caller, callee)

    assert len(transceiver.sender.get_parameters().codecs) > 0
    assert len(callee.get_transceivers()[0].receiver.get_parameters().codecs) > 0


@pytest.mark.asyncio
async def test_replace_track(
    pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream, video_stream: webrtc.MediaStream
) -> None:
    """A track is replaced by one of the same kind, or by None."""
    (audio,), (video,) = audio_stream.get_tracks(), video_stream.get_tracks()
    sender = pc.add_transceiver(webrtc.MediaType.audio).sender
    await sender.replace_track(audio)
    assert sender.track == audio
    with pytest.raises(TypeError):
        await sender.replace_track(video)
    await sender.replace_track(None)
    assert sender.track is None


@pytest.mark.asyncio
async def test_sender_track_is_the_one_it_was_given(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """addTrack, addTransceiver and replaceTrack give a sender its track, removeTrack takes it, close() keeps it."""
    [audio] = audio_stream.get_tracks()
    other = audio.clone()
    sender = caller.add_track(audio, audio_stream)
    assert sender.track is audio
    await sender.replace_track(None)
    assert sender.track is None
    await sender.replace_track(other)
    assert sender.track is other
    caller.remove_track(sender)
    assert sender.track is None
    assert caller.add_transceiver(webrtc.MediaType.audio).sender.track is None
    assert caller.add_transceiver(other).sender.track is other

    # addTrack reuses the transceiver a remote offer made, whose sender had no track
    await exchange_offer(caller, callee)
    created = callee.get_transceivers()[0].sender
    assert created.track is None
    reused = callee.add_track(audio)
    assert reused is created
    assert reused.track is audio

    callee.close()
    assert reused.track is audio
    other.stop()


@pytest.mark.asyncio
async def test_replace_track_of_a_stopped_transceiver(pc: webrtc.RTCPeerConnection) -> None:
    """The track of a stopped transceiver's sender can't be replaced."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    transceiver.stop()
    with pytest.raises(webrtc.InvalidStateError):
        await transceiver.sender.replace_track(None)


def test_set_streams_on_a_closed_connection(pc: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream) -> None:
    """A sender of a closed connection can't set its streams."""
    sender = pc.add_transceiver(webrtc.MediaType.audio).sender
    sender.set_streams(audio_stream)
    pc.close()
    with pytest.raises(webrtc.InvalidStateError):
        sender.set_streams(audio_stream)


def test_receiver_capabilities_of_another_kind() -> None:
    """Receivers of data have no capabilities."""
    assert webrtc.RTCRtpReceiver.get_capabilities('data') is None


def test_codec_preferences_and_header_extensions(pc: webrtc.RTCPeerConnection) -> None:
    """Codec preferences take supported codecs only, and header extensions to negotiate can be stopped."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    capabilities = webrtc.RTCRtpReceiver.get_capabilities('audio')
    assert capabilities is not None
    opus = [c for c in capabilities.codecs if c.mime_type == 'audio/opus']
    transceiver.set_codec_preferences(opus)
    transceiver.set_codec_preferences([])
    with pytest.raises(webrtc.InvalidModificationError):
        transceiver.set_codec_preferences([webrtc.RTCRtpCodec('audio/nonsense', 8000)])

    extensions = transceiver.get_header_extensions_to_negotiate()
    extensions[-1].direction = webrtc.RTCRtpTransceiverDirection.stopped
    transceiver.set_header_extensions_to_negotiate(extensions)
    assert transceiver.get_header_extensions_to_negotiate()[-1].direction == webrtc.RTCRtpTransceiverDirection.stopped
    extensions[0].uri = ''
    with pytest.raises(TypeError, match='must not be empty'):
        transceiver.set_header_extensions_to_negotiate(extensions)


def test_transceiver_changes_the_engine_refuses(pc: webrtc.RTCPeerConnection) -> None:
    """Resiliency codecs, header extension changes, and a stopped direction."""
    transceiver = pc.add_transceiver(webrtc.MediaType.video)
    capabilities = webrtc.RTCRtpReceiver.get_capabilities('video')
    assert capabilities is not None
    rtx = [c for c in capabilities.codecs if c.mime_type == 'video/rtx']
    with pytest.raises(webrtc.InvalidModificationError, match='non RTX'):
        transceiver.set_codec_preferences(rtx)

    extensions = transceiver.get_header_extensions_to_negotiate()
    with pytest.raises(webrtc.InvalidModificationError, match='does not match'):
        transceiver.set_header_extensions_to_negotiate(extensions[:-1])
    with pytest.raises(webrtc.InvalidModificationError, match='Reordering'):
        transceiver.set_header_extensions_to_negotiate(extensions[::-1])
    # an extension the engine doesn't implement
    unknown = [*extensions[:-1], webrtc.RTCRtpHeaderExtensionCapability('urn:example:unknown')]
    with pytest.raises(webrtc.InvalidModificationError):
        transceiver.set_header_extensions_to_negotiate(unknown)

    transceiver.stop()
    with pytest.raises(webrtc.InvalidStateError, match='stopping'):
        transceiver.direction = webrtc.RTCRtpTransceiverDirection.sendrecv


@pytest.mark.asyncio
async def test_negotiated_header_extensions(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Only offered, non-stopped extensions are negotiated."""
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    stopped = webrtc.RTCRtpTransceiverDirection.stopped
    negotiated = transceiver.get_negotiated_header_extensions()
    assert len(negotiated) > 0
    assert all(e.direction == stopped for e in negotiated)

    extensions = transceiver.get_header_extensions_to_negotiate()
    offered = [e for e in extensions if e.direction != stopped]
    audio_level = next(e for e in offered if e.uri == 'urn:ietf:params:rtp-hdrext:ssrc-audio-level')
    audio_level.direction = stopped
    transceiver.set_header_extensions_to_negotiate(extensions)
    await exchange_offer_answer(caller, callee)

    directions = {e.uri: e.direction for e in transceiver.get_negotiated_header_extensions()}
    assert directions.pop(audio_level.uri) == stopped
    assert {directions[e.uri] for e in offered if e is not audio_level} == {webrtc.RTCRtpTransceiverDirection.sendrecv}


@pytest.mark.asyncio
async def test_sender_codecs_leave_out_unknown_remote_codecs(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The codecs of a sender are the negotiated ones it knows, and are read-only."""
    sender = caller.add_transceiver(webrtc.MediaType.audio).sender
    await caller.set_local_description()
    assert caller.local_description is not None
    await callee.set_remote_description(caller.local_description)
    await callee.set_local_description()
    # the answer lists a codec this side doesn't know first
    assert callee.local_description is not None
    sdp = callee.local_description.sdp
    m_line = next(line for line in sdp.split('\r\n') if line.startswith('m=audio'))
    sdp = sdp.replace(m_line, m_line + ' 125').replace(
        '\r\na=rtpmap:', '\r\na=rtpmap:125 flarglblurp/8000/2\r\na=rtpmap:', 1
    )
    await caller.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', sdp))

    parameters = sender.get_parameters()
    assert len(parameters.codecs) > 0
    assert all('flarglblurp' not in codec.mime_type for codec in parameters.codecs)
    await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_parameters_set_after_a_description(pc: webrtc.RTCPeerConnection) -> None:
    """Parameters got before a description is set can be set after it."""
    sender = pc.add_transceiver(webrtc.MediaType.audio).sender
    parameters = sender.get_parameters()
    parameters.encodings[0].max_bitrate = 32000
    await pc.set_local_description()
    await sender.set_parameters(parameters)
    assert sender.get_parameters().encodings[0].max_bitrate == 32000


@pytest.mark.asyncio
async def test_set_parameters_key_frames(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """A key frame is requested per encoding."""
    sender = caller.add_transceiver(webrtc.MediaType.video).sender
    await exchange_offer_answer(caller, callee)
    with pytest.raises(webrtc.InvalidModificationError):
        await sender.set_parameters(
            sender.get_parameters(),
            webrtc.RTCSetParameterOptions([webrtc.RTCEncodingOptions(key_frame=True), webrtc.RTCEncodingOptions()]),
        )
    await sender.set_parameters(
        sender.get_parameters(), webrtc.RTCSetParameterOptions([webrtc.RTCEncodingOptions(key_frame=True)])
    )


@pytest.mark.asyncio
async def test_set_parameters_with_default_options(pc: webrtc.RTCPeerConnection) -> None:
    """Empty encoding options, the default, are the same as none."""
    sender = add_simulcast_sender(pc)
    await sender.set_parameters(sender.get_parameters(), webrtc.RTCSetParameterOptions())
    await sender.set_parameters(sender.get_parameters(), webrtc.RTCSetParameterOptions.from_json({}))


@pytest.mark.asyncio
async def test_set_parameters_after_rollback(pc: webrtc.RTCPeerConnection) -> None:
    """A sender rolled back out of its offer has no media channel: setting parameters rejects, not hangs."""
    sender = pc.add_transceiver(webrtc.MediaType.video).sender
    await pc.set_local_description()
    await pc.set_local_description(webrtc.RTCSessionDescriptionInit('rollback'))
    with pytest.raises(webrtc.InvalidStateError):
        await asyncio.wait_for(sender.set_parameters(sender.get_parameters()), seconds(5))


@pytest.mark.asyncio
async def test_simulcast_receiver_parameters(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The receiver of simulcast has the negotiated codecs and header extensions."""
    encodings = [webrtc.RTCRtpEncodingParameters(rid='a'), webrtc.RTCRtpEncodingParameters(rid='b')]
    caller.add_transceiver(webrtc.MediaType.video, webrtc.RTCRtpTransceiverInit(send_encodings=encodings))
    await exchange_offer_answer(caller, callee)
    parameters = callee.get_transceivers()[0].receiver.get_parameters()
    assert len(parameters.codecs) > 0
    assert len(parameters.header_extensions) > 0


@pytest.mark.asyncio
async def test_dtmf(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """An audio sender plays tones, normalized and checked, announcing each one, then an empty one."""
    sender = caller.add_track(audio_stream.get_tracks()[0], audio_stream)
    await connect(caller, callee)
    dtmf = sender.dtmf
    assert dtmf is not None
    assert dtmf.can_insert_dtmf

    tones: list[str] = []

    def on_tone_change(event: webrtc.RTCDTMFToneChangeEvent) -> None:
        tones.append(event.tone)

    def is_last(event: webrtc.Event) -> bool:
        assert isinstance(event, webrtc.RTCDTMFToneChangeEvent)
        return event.tone == ''

    dtmf.on('tonechange', on_tone_change)
    done = wait_for_event(dtmf, 'tonechange', timeout=seconds(5), predicate=is_last)

    with pytest.raises(webrtc.InvalidCharacterError):
        dtmf.insert_dtmf('12X')
    dtmf.insert_dtmf('1a#', duration=70, inter_tone_gap=50)
    assert dtmf.tone_buffer == '1A#'
    await done
    assert tones == ['1', 'A', '#', '']


def test_dtmf_before_a_negotiation(pc: webrtc.RTCPeerConnection) -> None:
    """Tones need a negotiated telephone-event codec."""
    dtmf = pc.add_transceiver(webrtc.MediaType.audio).sender.dtmf
    assert dtmf is not None
    assert dtmf.tone_buffer == ''
    assert not dtmf.can_insert_dtmf
    with pytest.raises(webrtc.InvalidStateError):
        dtmf.insert_dtmf('1')


@pytest.mark.asyncio
async def test_dtmf_of_a_transceiver_that_stopped_sending(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """A transceiver negotiated not to send can't send tones."""
    sender = caller.add_track(audio_stream.get_tracks()[0], audio_stream)
    await connect(caller, callee)
    dtmf = sender.dtmf
    assert dtmf is not None
    dtmf.insert_dtmf('')
    assert dtmf.tone_buffer == ''

    [transceiver] = caller.get_transceivers()
    transceiver.direction = webrtc.RTCRtpTransceiverDirection.recvonly
    await exchange_offer_answer(caller, callee)
    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.inactive
    with pytest.raises(webrtc.InvalidStateError, match="doesn't send"):
        dtmf.insert_dtmf('1')

    # receiving only, once the callee sends
    callee.get_transceivers()[0].direction = webrtc.RTCRtpTransceiverDirection.sendrecv
    await exchange_offer_answer(caller, callee)
    assert transceiver.current_direction == webrtc.RTCRtpTransceiverDirection.recvonly
    with pytest.raises(webrtc.InvalidStateError, match="doesn't send"):
        dtmf.insert_dtmf('1')

    # stopped and negotiated away
    transceiver.stop()
    await exchange_offer_answer(caller, callee)
    assert caller.get_transceivers() == []
    with pytest.raises(webrtc.InvalidStateError, match='stopped'):
        dtmf.insert_dtmf('1')


@pytest.mark.asyncio
async def test_dtmf_cancel(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """An empty insertDTMF() cancels the tones not played yet."""
    sender = caller.add_track(audio_stream.get_tracks()[0], audio_stream)
    await connect(caller, callee)
    dtmf = sender.dtmf
    assert dtmf is not None

    def is_last(event: webrtc.Event) -> bool:
        assert isinstance(event, webrtc.RTCDTMFToneChangeEvent)
        return event.tone == ''

    done = wait_for_event(dtmf, 'tonechange', timeout=seconds(5), predicate=is_last)
    dtmf.insert_dtmf('123456789')
    assert dtmf.tone_buffer == '123456789'
    dtmf.insert_dtmf('')
    assert dtmf.tone_buffer == ''
    await done
    assert dtmf.tone_buffer == ''


@pytest.mark.asyncio
async def test_dtmf_of_a_negotiated_transceiver_stopped_since(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """stop() ends the tones of a negotiated sender at once, before any negotiation shows it."""
    sender = caller.add_track(audio_stream.get_tracks()[0], audio_stream)
    await connect(caller, callee)
    dtmf = sender.dtmf
    assert dtmf is not None
    assert dtmf.can_insert_dtmf
    caller.get_transceivers()[0].stop()
    with pytest.raises(webrtc.InvalidStateError, match='stopped'):
        dtmf.insert_dtmf('1')


def test_dtmf_of_a_stopped_transceiver_checks_the_state_first(pc: webrtc.RTCPeerConnection) -> None:
    """Stopped beats bad tones."""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    dtmf = transceiver.sender.dtmf
    assert dtmf is not None
    transceiver.stop()
    with pytest.raises(webrtc.InvalidStateError):
        dtmf.insert_dtmf('1')
    with pytest.raises(webrtc.InvalidStateError):
        dtmf.insert_dtmf('XYZ')


@pytest.mark.asyncio
async def test_synchronization_sources(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, video_stream: webrtc.MediaStream
) -> None:
    """A receiver reports the source of the media it decodes."""
    caller.add_track(video_stream.get_tracks()[0], video_stream)
    remote_track = wait_for_event(callee, 'track')
    await connect(caller, callee)
    track_event = await remote_track
    assert isinstance(track_event, webrtc.RTCTrackEvent)
    receiver = track_event.receiver

    # sources are known once media is decoded (audio is only played out by a real audio device)
    await wait_until(receiver.get_synchronization_sources, 'a synchronization source', timeout=seconds(5))
    [source] = receiver.get_synchronization_sources()
    inbound = stats_of_type(await receiver.get_stats(), 'inbound-rtp')[0]
    assert isinstance(inbound, webrtc.RTCInboundRtpStreamStats)
    assert isinstance(source, webrtc.RTCRtpSynchronizationSource)
    assert source.source == inbound.ssrc
    assert abs(source.timestamp - time.time() * 1000) < 5_000
    assert 0 <= source.rtp_timestamp < 2**32
    assert source.audio_level is None
    assert receiver.get_contributing_sources() == []


@pytest.mark.asyncio
async def test_synchronization_sources_of_audio_have_its_level(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, audio_stream: webrtc.MediaStream
) -> None:
    """The audio level header extension gives the linear level."""
    caller.add_track(audio_stream.get_tracks()[0], audio_stream)
    remote_track = wait_for_event(callee, 'track')
    await connect(caller, callee)
    track_event = await remote_track
    assert isinstance(track_event, webrtc.RTCTrackEvent)
    receiver = track_event.receiver

    await wait_until(receiver.get_synchronization_sources, 'a synchronization source')
    [source] = receiver.get_synchronization_sources()
    assert source.audio_level is not None
    assert 0 <= source.audio_level <= 1


@pytest.mark.asyncio
async def test_sources_are_read_once_per_task(pc: webrtc.RTCPeerConnection, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both getters in one task share one read of the native sources, a later task reads them again."""
    receiver = pc.add_transceiver(webrtc.MediaType.audio).receiver
    reads = 0

    def counted(_native: wrtc.RTCRtpReceiver) -> list[tuple[bool, int, float, int, int | None]]:
        nonlocal reads
        reads += 1
        return [(True, reads, 0.0, 0, None), (False, reads, 0.0, 0, None)]

    monkeypatch.setattr(wrtc.RTCRtpReceiver, '_getSources', counted)

    [synchronization] = receiver.get_synchronization_sources()
    [contributing] = receiver.get_contributing_sources()
    assert reads == 1
    assert synchronization.source == contributing.source == 1
    await next_task()
    [synchronization] = receiver.get_synchronization_sources()
    assert reads == 2
    assert synchronization.source == 2


@pytest.mark.parametrize(
    'encoding',
    [
        lambda: webrtc.RTCRtpEncodingParameters(max_bitrate=-1),
        lambda: webrtc.RTCRtpEncodingParameters(max_bitrate=2**32),
        lambda: webrtc.RTCRtpEncodingParameters(max_bitrate=mistyped(1.5)),
        lambda: webrtc.RTCRtpEncodingParameters(max_framerate=float('inf')),
        lambda: webrtc.RTCRtpEncodingParameters(scale_resolution_down_by=float('nan')),
    ],
)
def test_encodings_have_their_webidl_types(
    pc: webrtc.RTCPeerConnection, encoding: Callable[[], webrtc.RTCRtpEncodingParameters]
) -> None:
    """An [EnforceRange] unsigned long and restricted doubles: other values are a TypeError, not sent to libwebrtc."""
    with pytest.raises(TypeError):
        pc.add_transceiver(
            webrtc.MediaType.video,
            webrtc.RTCRtpTransceiverInit(send_encodings=[encoding()]),
        )


def test_encoding_bitrate_beyond_an_int_is_no_limit(pc: webrtc.RTCPeerConnection) -> None:
    init = webrtc.RTCRtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(max_bitrate=2**32 - 1)])
    sender = pc.add_transceiver(webrtc.MediaType.video, init).sender
    assert sender.get_parameters().encodings[0].max_bitrate == 2**31 - 1


def test_transceiver_init_from_json(pc: webrtc.RTCPeerConnection) -> None:
    """From the JSON form, with camelCase or snake_case names, the encodings too; unknown members are ignored."""
    init = webrtc.RTCRtpTransceiverInit.from_json({
        'direction': 'sendonly',
        'sendEncodings': [{'rid': 'a', 'maxBitrate': 100000}, {'rid': 'b'}],
        'x': 1,
    })
    transceiver = pc.add_transceiver(webrtc.MediaType.video, init)
    assert transceiver.direction == webrtc.RTCRtpTransceiverDirection.sendonly
    encodings = transceiver.sender.get_parameters().encodings
    assert [(e.rid, e.max_bitrate) for e in encodings] == [('a', 100000), ('b', None)]


def test_add_transceiver_closed_check_comes_first(pc: webrtc.RTCPeerConnection) -> None:
    """A closed connection raises InvalidStateError first."""
    pc.close()
    init = webrtc.RTCRtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(rid='no-dash')])
    with pytest.raises(webrtc.InvalidStateError):
        pc.add_transceiver(webrtc.MediaType.video, init)


@pytest.mark.parametrize('value', [float('nan'), float('inf')])
def test_jitter_buffer_target_is_a_restricted_double(pc: webrtc.RTCPeerConnection, value: float) -> None:
    """A non-finite target raises TypeError."""
    receiver = pc.add_transceiver(webrtc.MediaType.audio).receiver
    with pytest.raises(TypeError):
        receiver.jitter_buffer_target = value


def test_jitter_buffer_target_keeps_the_value_set(pc: webrtc.RTCPeerConnection) -> None:
    """None by default, and kept until set to None."""
    receiver = pc.add_transceiver(webrtc.MediaType.audio).receiver
    assert receiver.jitter_buffer_target is None
    receiver.jitter_buffer_target = 250
    assert receiver.jitter_buffer_target == 250
    receiver.jitter_buffer_target = None
    assert receiver.jitter_buffer_target is None


@pytest.mark.parametrize('value', [-1, 4000.5])
def test_jitter_buffer_target_out_of_range(pc: webrtc.RTCPeerConnection, value: float) -> None:
    """A target outside 0 to 4000 ms raises InvalidRangeError."""
    receiver = pc.add_transceiver(webrtc.MediaType.audio).receiver
    receiver.jitter_buffer_target = 4000
    with pytest.raises(webrtc.InvalidRangeError):
        receiver.jitter_buffer_target = value
    assert receiver.jitter_buffer_target == 4000
