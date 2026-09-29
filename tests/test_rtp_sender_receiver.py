#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Senders and receivers: capabilities, parameters, codecs, tracks, DTMF and synchronization sources."""

import time

import pytest

import webrtc
from tests.helpers import connect, exchange_offer_answer, next_task, wait_for_event, wait_until


def test_capabilities():
    """Senders and receivers of audio and video have codecs and header extensions, of data none"""
    audio = webrtc.RTCRtpSender.get_capabilities(webrtc.MediaType.audio)
    assert any(codec.mime_type == 'audio/opus' for codec in audio.codecs)
    assert audio.header_extensions
    assert webrtc.RTCRtpReceiver.get_capabilities('video').codecs
    assert webrtc.RTCRtpSender.get_capabilities('data') is None


def add_simulcast_sender(pc):
    init = webrtc.RtpTransceiverInit(
        send_encodings=[webrtc.RTCRtpEncodingParameters(rid='hi'), webrtc.RTCRtpEncodingParameters(rid='lo')]
    )
    return pc.add_transceiver(webrtc.MediaType.video, init).sender


def test_default_send_parameters(pc):
    """Video encodings scale down by powers of 2 by default, and the parameters of a task share a transaction"""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    assert [e.scale_resolution_down_by for e in parameters.encodings] == [2.0, 1.0]
    assert sender.get_parameters().transaction_id == parameters.transaction_id


@pytest.mark.asyncio
async def test_set_send_parameters(pc):
    """Changed encodings are applied"""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    parameters.encodings[0].max_bitrate = 500_000
    parameters.encodings[1].active = False
    await sender.set_parameters(parameters)
    # read back in a later task, which gets new parameters
    await next_task()

    changed = sender.get_parameters()
    assert changed.encodings[0].max_bitrate == 500_000 and not changed.encodings[1].active


@pytest.mark.asyncio
async def test_send_parameters_out_of_range(pc):
    """An encoding can't scale the resolution up"""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    parameters.encodings[0].scale_resolution_down_by = 0.5
    with pytest.raises(webrtc.InvalidRangeError):
        await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_send_parameters_with_other_encodings(pc):
    """The number of encodings can't change"""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    parameters.encodings.pop()
    with pytest.raises(webrtc.InvalidModificationError):
        await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_parameters_expire_with_their_task(pc):
    """Parameters are only accepted in the task that got them"""
    sender = add_simulcast_sender(pc)
    parameters = sender.get_parameters()
    await next_task()
    with pytest.raises(webrtc.InvalidStateError):
        await sender.set_parameters(parameters)


@pytest.mark.parametrize(
    'encodings',
    [
        [{'rid': 'a'}, {'rid': 'a'}],
        [{'rid': 'a'}, {}],
        [{'rid': 'no-dash'}],
        [{'rid': ''}],
    ],
    ids=['duplicate rid', 'missing rid', 'invalid rid', 'empty rid'],
)
def test_invalid_send_encodings(pc, encodings):
    """The rids of send encodings are unique, present when there are several, and alphanumeric"""
    init = webrtc.RtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(**e) for e in encodings])
    with pytest.raises(ValueError):
        pc.add_transceiver(webrtc.MediaType.video, init)


def test_send_encoding_of_an_unknown_codec(pc):
    """The codec of a send encoding must be one the sender supports"""
    unknown = webrtc.RTCRtpEncodingParameters(codec=webrtc.RTCRtpCodec('audio/unknown', 8000))
    with pytest.raises(webrtc.OperationError):
        pc.add_transceiver(webrtc.MediaType.audio, webrtc.RtpTransceiverInit(send_encodings=[unknown]))


@pytest.mark.asyncio
async def test_negotiated_codecs(caller, callee):
    """The parameters of senders and receivers list their negotiated codecs"""
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer_answer(caller, callee)

    assert transceiver.sender.get_parameters().codecs
    assert callee.get_transceivers()[0].receiver.get_parameters().codecs


@pytest.mark.asyncio
async def test_replace_track(pc, audio_stream, video_stream):
    """A track is replaced by one of the same kind, or by None"""
    (audio,), (video,) = audio_stream.get_tracks(), video_stream.get_tracks()
    sender = pc.add_transceiver(webrtc.MediaType.audio).sender
    await sender.replace_track(audio)
    assert sender.track == audio
    with pytest.raises(TypeError):
        await sender.replace_track(video)
    await sender.replace_track(None)
    assert sender.track is None


def test_codec_preferences_and_header_extensions(pc):
    """Codec preferences take supported codecs only, and header extensions to negotiate can be stopped"""
    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    opus = [c for c in webrtc.RTCRtpReceiver.get_capabilities('audio').codecs if c.mime_type == 'audio/opus']
    transceiver.set_codec_preferences(opus)
    transceiver.set_codec_preferences([])
    with pytest.raises(webrtc.InvalidModificationError):
        transceiver.set_codec_preferences([webrtc.RTCRtpCodec('audio/nonsense', 8000)])

    extensions = transceiver.get_header_extensions_to_negotiate()
    extensions[-1].direction = webrtc.TransceiverDirection.stopped
    transceiver.set_header_extensions_to_negotiate(extensions)
    assert transceiver.get_header_extensions_to_negotiate()[-1].direction == webrtc.TransceiverDirection.stopped


@pytest.mark.asyncio
async def test_sender_codecs_leave_out_unknown_remote_codecs(caller, callee):
    """The codecs of a sender are the negotiated ones it knows, and are read-only"""
    sender = caller.add_transceiver(webrtc.MediaType.audio).sender
    await caller.set_local_description()
    await callee.set_remote_description(caller.local_description)
    await callee.set_local_description()
    # the answer lists a codec this side doesn't know first
    sdp = callee.local_description.sdp
    m_line = next(line for line in sdp.split('\r\n') if line.startswith('m=audio'))
    sdp = sdp.replace(m_line, m_line + ' 125').replace(
        '\r\na=rtpmap:', '\r\na=rtpmap:125 flarglblurp/8000/2\r\na=rtpmap:', 1
    )
    await caller.set_remote_description({'type': 'answer', 'sdp': sdp})

    parameters = sender.get_parameters()
    assert parameters.codecs
    assert all('flarglblurp' not in codec.mime_type for codec in parameters.codecs)
    await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_setting_a_description_expires_sender_parameters(pc):
    """Setting a description changes what parameters are valid, so earlier ones expire"""
    sender = pc.add_transceiver(webrtc.MediaType.audio).sender
    parameters = sender.get_parameters()
    await pc.set_local_description()
    with pytest.raises(webrtc.InvalidStateError):
        await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_set_parameters_key_frames(caller, callee):
    """A key frame is requested per encoding"""
    sender = caller.add_transceiver(webrtc.MediaType.video).sender
    await exchange_offer_answer(caller, callee)
    with pytest.raises(webrtc.InvalidModificationError):
        await sender.set_parameters(sender.get_parameters(), key_frames=[True, False])
    await sender.set_parameters(sender.get_parameters(), key_frames=[True])


@pytest.mark.asyncio
async def test_simulcast_receiver_parameters(caller, callee):
    """The receiver of simulcast has the negotiated codecs and header extensions"""
    encodings = [webrtc.RTCRtpEncodingParameters(rid='a'), webrtc.RTCRtpEncodingParameters(rid='b')]
    caller.add_transceiver(webrtc.MediaType.video, webrtc.RtpTransceiverInit(send_encodings=encodings))
    await exchange_offer_answer(caller, callee)
    parameters = callee.get_transceivers()[0].receiver.get_parameters()
    assert parameters.codecs and parameters.header_extensions


@pytest.mark.asyncio
async def test_dtmf(caller, callee, audio_stream):
    """An audio sender plays tones, normalized and checked, announcing each one, then an empty one"""
    sender = caller.add_track(audio_stream.get_tracks()[0], audio_stream)
    await connect(caller, callee)
    dtmf = sender.dtmf
    assert dtmf is not None and dtmf.can_insert_dtmf

    tones = []
    dtmf.on('tonechange', lambda event: tones.append(event.tone))
    done = wait_for_event(dtmf, 'tonechange', timeout=5, predicate=lambda event: event.tone == '')

    with pytest.raises(webrtc.InvalidCharacterError):
        dtmf.insert_dtmf('12X')
    dtmf.insert_dtmf('1a#', duration=70, inter_tone_gap=50)
    assert dtmf.tone_buffer == '1A#'
    await done
    assert tones == ['1', 'A', '#', '']


@pytest.mark.asyncio
async def test_synchronization_sources(caller, callee, video_stream):
    """A receiver reports the source of the media it decodes"""
    caller.add_track(video_stream.get_tracks()[0], video_stream)
    remote_track = wait_for_event(callee, 'track')
    await connect(caller, callee)
    receiver = (await remote_track).receiver

    # sources are known once media is decoded (audio is only played out by a real audio device)
    await wait_until(receiver.get_synchronization_sources, 'a synchronization source', timeout=5)
    [source] = receiver.get_synchronization_sources()
    inbound = (await receiver.get_stats()).of_type('inbound-rtp')[0]
    assert isinstance(source, webrtc.RTCRtpSynchronizationSource)
    assert source.source == inbound.ssrc
    assert abs(source.timestamp - time.time() * 1000) < 5_000
    assert 0 <= source.rtp_timestamp < 2**32
    assert source.audio_level is None
    assert receiver.get_contributing_sources() == []


@pytest.mark.parametrize(
    'encoding',
    [
        {'max_bitrate': -1},
        {'max_bitrate': 2**32},
        {'max_bitrate': 1.5},
        {'max_framerate': float('inf')},
        {'scale_resolution_down_by': float('nan')},
    ],
)
def test_encodings_have_their_webidl_types(pc, encoding):
    """An [EnforceRange] unsigned long and restricted doubles: other values are a TypeError, not sent to libwebrtc"""
    with pytest.raises(TypeError):
        pc.add_transceiver(
            webrtc.MediaType.video,
            webrtc.RtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(**encoding)]),
        )


def test_encoding_bitrate_beyond_an_int_is_no_limit(pc):
    init = webrtc.RtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(max_bitrate=2**32 - 1)])
    sender = pc.add_transceiver(webrtc.MediaType.video, init).sender
    assert sender.get_parameters().encodings[0].max_bitrate == 2**31 - 1


def test_transceiver_init_as_a_dictionary(pc):
    """As in browsers, with camelCase or snake_case names, the encodings too; unknown members are ignored"""
    init = {'direction': 'sendonly', 'sendEncodings': [{'rid': 'a', 'maxBitrate': 100000}, {'rid': 'b'}], 'x': 1}
    transceiver = pc.add_transceiver(webrtc.MediaType.video, init)
    assert transceiver.direction == webrtc.TransceiverDirection.sendonly
    encodings = transceiver.sender.get_parameters().encodings
    assert [(e.rid, e.max_bitrate) for e in encodings] == [('a', 100000), ('b', None)]
