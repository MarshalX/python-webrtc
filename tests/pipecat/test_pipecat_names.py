#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The framework's names the package uses, and the package's names it imports, so a bump fails here first.

``IMPORTED`` rows cite ``path:line`` at 6f777a0 (1.15.0); a row goes when its use does.
"""

from __future__ import annotations

import dataclasses
import importlib
from dataclasses import dataclass

import pytest
from pipecat.processors.frame_processor import FrameProcessorSetup
from pipecat.transports.base_transport import TransportParams

from tests.isolation import isolated
from webrtc.pipecat import install_alias


@dataclass(frozen=True)
class Name:
    """A name read from a module: a class, function or constant, or an attribute of one with dots."""

    module: str
    name: str


#: the private ones keep it behaving as the framework's own transports
USED = [
    Name('pipecat.audio.utils', 'create_stream_resampler'),
    Name('pipecat.frames.frames', 'CancelFrame'),
    Name('pipecat.frames.frames', 'ClientConnectedFrame'),
    Name('pipecat.frames.frames', 'EndFrame'),
    Name('pipecat.frames.frames', 'Frame'),
    Name('pipecat.frames.frames', 'InputAudioRawFrame'),
    Name('pipecat.frames.frames', 'InputTransportMessageFrame'),
    Name('pipecat.frames.frames', 'InterruptionFrame'),
    Name('pipecat.frames.frames', 'OutputAudioRawFrame'),
    Name('pipecat.frames.frames', 'OutputImageRawFrame'),
    Name('pipecat.frames.frames', 'OutputTransportMessageFrame'),
    Name('pipecat.frames.frames', 'OutputTransportMessageUrgentFrame'),
    Name('pipecat.frames.frames', 'SpriteFrame'),
    Name('pipecat.frames.frames', 'StartFrame'),
    Name('pipecat.frames.frames', 'UserImageRawFrame'),
    Name('pipecat.frames.frames', 'UserImageRequestFrame'),
    Name('pipecat.processors.frame_processor', 'FrameDirection.DOWNSTREAM'),
    Name('pipecat.processors.frame_processor', 'FrameProcessor.broadcast_frame'),
    Name('pipecat.processors.frame_processor', 'FrameProcessor.create_task'),
    Name('pipecat.processors.frame_processor', 'FrameProcessor.cancel_task'),
    Name('pipecat.processors.frame_processor', 'FrameProcessor.push_frame'),
    Name('pipecat.processors.frame_processor', 'FrameProcessor.queue_frame'),
    Name('pipecat.processors.frame_processor', 'FrameProcessorSetup'),
    Name('pipecat.runner.utils', 'smallwebrtc_sdp_munging'),
    Name('pipecat.transports.base_input', 'BaseInputTransport'),
    Name('pipecat.transports.base_input', 'BaseInputTransport._answer_image_requests'),
    Name('pipecat.transports.base_input', 'BaseInputTransport._supports_video_in_source'),
    Name('pipecat.transports.base_input', 'BaseInputTransport.push_audio_frame'),
    Name('pipecat.transports.base_input', 'BaseInputTransport.push_video_frame'),
    Name('pipecat.transports.base_input', 'BaseInputTransport.set_transport_ready'),
    Name('pipecat.transports.base_output', 'BaseOutputTransport'),
    Name('pipecat.transports.base_output', 'BaseOutputTransport.set_transport_ready'),
    Name('pipecat.transports.base_output', 'BaseOutputTransport.write_audio_frame'),
    Name('pipecat.transports.base_output', 'BaseOutputTransport.write_video_frame'),
    Name('pipecat.transports.base_output', 'BaseOutputTransport.send_message'),
    Name('pipecat.transports.base_transport', 'BaseTransport'),
    Name('pipecat.transports.base_transport', 'BaseTransport.capture_participant_video'),
    Name('pipecat.transports.base_transport', 'BaseTransport.get_client_id'),
    Name('pipecat.transports.base_transport', 'TransportParams'),
    Name('pipecat.transports.video_in_sampler', '_VideoInSamplers.add_request'),
    Name('pipecat.transports.video_in_sampler', '_VideoInSamplers.capture'),
    Name('pipecat.transports.video_in_sampler', '_VideoInSamplers.clear'),
    Name('pipecat.transports.video_in_sampler', '_VideoInSamplers.is_capturing'),
    Name('pipecat.transports.video_in_sampler', '_VideoInSamplers.sample'),
    Name('pipecat.transports.video_in_sampler', '_VideoInSamplers.take_requests'),
    Name('pipecat.transports.video_in_sampler', '_capture_framerate'),
    Name('pipecat.utils.base_object', 'BaseObject._call_event_handler'),
    Name('pipecat.utils.base_object', 'BaseObject._register_event_handler'),
    Name('pipecat.utils.base_object', 'BaseObject.add_event_handler'),
    Name('pipecat.utils.shared', 'acquires'),
    Name('pipecat.utils.shared', 'releases'),
]

TRANSPORT_PARAMS = [
    'audio_in_channels',
    'audio_in_enabled',
    'audio_in_sample_rate',
    'audio_out_auto_silence',
    'audio_out_enabled',
    'audio_out_sample_rate',
    'video_in_enabled',
    'video_in_sources',
    'video_out_enabled',
]
FRAME_FIELDS = {
    'InputAudioRawFrame': ['audio', 'sample_rate', 'num_channels'],
    'OutputAudioRawFrame': ['audio', 'num_channels'],
    'OutputImageRawFrame': ['image', 'size', 'format'],
    'UserImageRawFrame': ['user_id', 'image', 'size', 'format', 'text', 'append_to_context', 'request'],
    'UserImageRequestFrame': ['user_id', 'text', 'append_to_context', 'video_source', 'result_callback'],
    'InputTransportMessageFrame': ['message'],
    'OutputTransportMessageFrame': ['message'],
}


@dataclass(frozen=True)
class Imported:
    """A name the framework imports from its transport, by the module it imports it from."""

    module: str
    name: str
    use: str


RUN = 'src/pipecat/runner/run.py'
RUNNER_UTILS = 'src/pipecat/runner/utils.py'
WHATSAPP = 'src/pipecat/transports/whatsapp/client.py'
EXAMPLE = 'examples/transports/transports-small-webrtc.py'
CONNECTION = 'connection'
REQUEST_HANDLER = 'request_handler'
TRANSPORT = 'transport'

IMPORTED = [
    Imported(CONNECTION, 'IceServer', f'{RUN}:1089'),
    Imported(CONNECTION, 'SmallWebRTCConnection', f'{RUN}:1089'),
    Imported(CONNECTION, 'SmallWebRTCConnection.disconnect', f'{WHATSAPP}:120'),
    Imported(CONNECTION, 'SmallWebRTCConnection.event_handler', f'{WHATSAPP}:387'),
    Imported(CONNECTION, 'SmallWebRTCConnection.get_answer', f'{WHATSAPP}:345'),
    Imported(CONNECTION, 'SmallWebRTCConnection.initialize', f'{WHATSAPP}:344'),
    Imported(CONNECTION, 'SmallWebRTCConnection.pc_id', f'{WHATSAPP}:390'),
    Imported(REQUEST_HANDLER, 'IceCandidate', f'{RUN}:1091'),
    Imported(REQUEST_HANDLER, 'SmallWebRTCPatchRequest', f'{RUN}:1092'),
    Imported(REQUEST_HANDLER, 'SmallWebRTCRequest', f'{RUN}:1093'),
    Imported(REQUEST_HANDLER, 'SmallWebRTCRequestHandler', f'{RUN}:1094'),
    Imported(REQUEST_HANDLER, 'SmallWebRTCRequestHandler.close', f'{RUN}:1208'),
    Imported(REQUEST_HANDLER, 'SmallWebRTCRequestHandler.handle_patch_request', f'{RUN}:1161'),
    Imported(REQUEST_HANDLER, 'SmallWebRTCRequestHandler.handle_web_request', f'{RUN}:1151'),
    Imported(TRANSPORT, 'SmallWebRTCTransport', f'{RUNNER_UTILS}:763'),
    Imported(TRANSPORT, 'SmallWebRTCTransport.capture_participant_video', f'{RUNNER_UTILS}:414'),
    Imported(TRANSPORT, 'SmallWebRTCTransport.event_handler', f'{EXAMPLE}:81'),
    Imported(TRANSPORT, 'SmallWebRTCTransport.input', f'{EXAMPLE}:58'),
    Imported(TRANSPORT, 'SmallWebRTCTransport.output', f'{EXAMPLE}:63'),
]


def lookup(module: object, name: str) -> object:
    value = module
    for part in name.split('.'):
        value = getattr(value, part)
    return value


def used_id(row: Name) -> str:
    return f'{row.module}:{row.name}'


def imported_id(row: Imported) -> str:
    return f'{row.module}:{row.name}'


@pytest.mark.parametrize('row', USED, ids=used_id)
def test_a_name_used_is_there(row: Name) -> None:
    _ = lookup(importlib.import_module(row.module), row.name)


def test_the_parameters_read_are_there() -> None:
    assert set(TRANSPORT_PARAMS) <= set(TransportParams.model_fields)
    setup_fields = {field.name for field in dataclasses.fields(FrameProcessorSetup)}
    assert {'audio_in_sample_rate', 'audio_out_sample_rate'} <= setup_fields


@pytest.mark.parametrize(('frame', 'fields'), FRAME_FIELDS.items())
def test_the_frame_fields_used_are_there(frame: str, fields: list[str]) -> None:
    frame_class = lookup(importlib.import_module('pipecat.frames.frames'), frame)
    assert dataclasses.is_dataclass(frame_class)

    names = {field.name for field in dataclasses.fields(frame_class)}
    assert set(fields) <= names


@pytest.mark.parametrize('row', IMPORTED, ids=imported_id)
def test_a_name_imported_is_ours(row: Imported) -> None:
    _ = lookup(importlib.import_module(f'webrtc.pipecat.{row.module}'), row.name)


@isolated
def test_names_import_through_the_alias() -> None:
    install_alias()

    for row in IMPORTED:
        module = importlib.import_module(f'pipecat.transports.smallwebrtc.{row.module}')
        assert module is importlib.import_module(f'webrtc.pipecat.{row.module}')
        _ = lookup(module, row.name)
