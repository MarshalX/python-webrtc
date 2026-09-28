#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio

import pytest

import webrtc
from tests.helpers import exchange_offer_answer


def test_capabilities():
    audio = webrtc.RTCRtpSender.get_capabilities(webrtc.MediaType.audio)
    assert any(codec.mime_type == 'audio/opus' for codec in audio.codecs)
    assert audio.header_extensions
    assert webrtc.RTCRtpReceiver.get_capabilities('video').codecs
    assert webrtc.RTCRtpSender.get_capabilities('data') is None


@pytest.mark.asyncio
async def test_send_parameters(pc):
    init = webrtc.RtpTransceiverInit(
        send_encodings=[webrtc.RTCRtpEncodingParameters(rid='hi'), webrtc.RTCRtpEncodingParameters(rid='lo')]
    )
    sender = pc.add_transceiver(webrtc.MediaType.video, init).sender
    parameters = sender.get_parameters()
    # video encodings scale down by powers of 2 by default
    assert [e.scale_resolution_down_by for e in parameters.encodings] == [2.0, 1.0]
    assert sender.get_parameters().transaction_id == parameters.transaction_id

    parameters.encodings[0].max_bitrate = 500_000
    parameters.encodings[1].active = False
    await sender.set_parameters(parameters)
    await asyncio.sleep(0)
    changed = sender.get_parameters()
    assert changed.encodings[0].max_bitrate == 500_000 and not changed.encodings[1].active

    changed.encodings[0].scale_resolution_down_by = 0.5
    with pytest.raises(webrtc.InvalidRangeError):
        await sender.set_parameters(changed)
    changed.encodings.pop()
    with pytest.raises(webrtc.InvalidModificationError):
        await sender.set_parameters(changed)

    await asyncio.sleep(0.05)
    # the parameters expire with the task that got them
    with pytest.raises(webrtc.InvalidStateError):
        await sender.set_parameters(parameters)


def test_send_encodings_validation(pc):
    for encodings in ([{'rid': 'a'}, {'rid': 'a'}], [{'rid': 'a'}, {}], [{'rid': 'no-dash'}], [{'rid': ''}]):
        with pytest.raises(ValueError):
            init = webrtc.RtpTransceiverInit(send_encodings=[webrtc.RTCRtpEncodingParameters(**e) for e in encodings])
            pc.add_transceiver(webrtc.MediaType.video, init)
    unknown = webrtc.RTCRtpEncodingParameters(codec=webrtc.RTCRtpCodec('audio/unknown', 8000))
    with pytest.raises(webrtc.OperationError):
        pc.add_transceiver(webrtc.MediaType.audio, webrtc.RtpTransceiverInit(send_encodings=[unknown]))


@pytest.mark.asyncio
async def test_negotiated_codecs_and_replace_track(caller, callee):
    transceiver = caller.add_transceiver(webrtc.MediaType.audio)
    await exchange_offer_answer(caller, callee)

    assert transceiver.sender.get_parameters().codecs
    assert callee.get_transceivers()[0].receiver.get_parameters().codecs

    audio = webrtc.get_user_media(audio=True).get_tracks()[0]
    video = webrtc.get_user_media(audio=False, video=True).get_tracks()[0]
    await transceiver.sender.replace_track(audio)
    assert transceiver.sender.track == audio
    with pytest.raises(TypeError):
        await transceiver.sender.replace_track(video)
    await transceiver.sender.replace_track(None)
    assert transceiver.sender.track is None
    video.stop()


def test_codec_preferences_and_header_extensions(pc):
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
    # the codecs are read-only, and parameters from getParameters can be set
    await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_setting_a_description_expires_sender_parameters(caller, callee):
    sender = caller.add_transceiver(webrtc.MediaType.audio).sender
    parameters = sender.get_parameters()
    await caller.set_local_description()
    with pytest.raises(webrtc.InvalidStateError):
        await sender.set_parameters(parameters)


@pytest.mark.asyncio
async def test_set_parameters_key_frames(caller, callee):
    sender = caller.add_transceiver(webrtc.MediaType.video).sender
    await exchange_offer_answer(caller, callee)
    with pytest.raises(webrtc.InvalidModificationError):
        await sender.set_parameters(sender.get_parameters(), key_frames=[True, False])
    await sender.set_parameters(sender.get_parameters(), key_frames=[True])


@pytest.mark.asyncio
async def test_simulcast_receiver_parameters(caller, callee):
    encodings = [webrtc.RtpEncodingParameters(rid='a'), webrtc.RtpEncodingParameters(rid='b')]
    caller.add_transceiver(webrtc.MediaType.video, webrtc.RtpTransceiverInit(send_encodings=encodings))
    await exchange_offer_answer(caller, callee)
    parameters = callee.get_transceivers()[0].receiver.get_parameters()
    assert parameters.codecs and parameters.header_extensions
