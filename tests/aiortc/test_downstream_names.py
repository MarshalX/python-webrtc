#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The aiortc names dependents use, each row citing one use as ``project:path:line@commit``.

A row goes when its project drops the use.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import importlib
import pkgutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pytest

import webrtc
from tests.aiortc.test_media import CONFIGURATION, write_media
from tests.isolation import isolated
from webrtc.aiortc import RTCIceServer, RTCPeerConnection, RTCRtpTransceiver, install_alias
from webrtc.aiortc.contrib.media import MediaPlayer, MediaRelay
from webrtc.aiortc.jitterbuffer import JitterBuffer, JitterFrame
from webrtc.aiortc.rtcicetransport import STUN_REGEX, TURN_REGEX, connection_kwargs, parse_stun_turn_uri
from webrtc.aiortc.rtcrtpreceiver import RemoteStreamTrack
from webrtc.aiortc.rtp import RtpPacket

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@dataclass(frozen=True)
class Name:
    """A module, or a name read from one, by its aiortc path."""

    module: str
    name: str | None
    use: str


class Mode(enum.Enum):
    READ = 'read'
    WRITE = 'write'
    CALL = 'call'


class Expected(enum.Enum):
    WORKS = 'works'
    NO_OP = 'settable no-op'
    #: the dependent checks with hasattr or getattr first, and skips the use
    GUARDED = 'absent, guarded'
    #: guarded too, and the layer can't offer it honestly
    UNSUPPORTED = 'unsupported'


#: stands for the running loop
RUNNING_LOOP = object()


@dataclass(frozen=True)
class Attribute:
    """An attribute of an aiortc object or module, as a dependent uses it."""

    owner: str
    attribute: str
    mode: Mode
    expected: Expected
    use: str
    value: object = None
    reason: str = ''


@dataclass(frozen=True)
class Dependency:
    """A module of aiortc's own dependencies, which a dependent imports itself."""

    module: str
    use: str
    reason: str


PIPECAT = 'pipecat:src/pipecat/transports/smallwebrtc/connection.py'
VISION_AGENTS = 'vision-agents:agents-core/vision_agents/core'
VISION_INWORLD = 'vision-agents:plugins/inworld/vision_agents/plugins/inworld/rtc_manager.py'
FASTRTC_TRACKS = 'fastrtc:backend/fastrtc/tracks.py'
ROBOFLOW_MANAGER = 'roboflow:stream_vision/streamvision/stream_manager/manager_app/webrtc.py'
ROBOFLOW_WORKER = 'roboflow:stream_vision/streamvision/webrtc_worker/webrtc.py'
GRADIO_BITRATE = 'gradio-pr:gradio/webrtc/bitrate.py'
NO_ENCODER = 'the engine encodes in its own threads, with no encoder object per sender; bitrates go through the codecs'

NAMES = [
    Name('aiortc', None, f'{VISION_AGENTS}/avatars/avatar.py:4@902db86'),
    Name('aiortc', 'AudioStreamTrack', 'vision-agents:plugins/local/vision_agents/plugins/local/tracks.py:20@902db86'),
    Name('aiortc', 'MediaStreamError', f'{VISION_AGENTS}/utils/video_forwarder.py:8@902db86'),
    Name('aiortc', 'MediaStreamTrack', f'{VISION_AGENTS}/edge/edge_transport.py:119@902db86'),
    Name('aiortc', 'RTCBundlePolicy', f'{PIPECAT}:28@6f777a0'),
    Name('aiortc', 'RTCBundlePolicy.MAX_BUNDLE', f'{PIPECAT}:336@6f777a0'),
    Name('aiortc', 'RTCConfiguration', f'{VISION_INWORLD}:15@902db86'),
    Name('aiortc', 'RTCDataChannel', f'{VISION_INWORLD}:15@902db86'),
    Name('aiortc', 'RTCIceCandidate', 'fastrtc:backend/fastrtc/webrtc_connection_mixin.py:19@59ca4f7'),
    Name('aiortc', 'RTCIceServer', f'{VISION_INWORLD}:15@902db86'),
    Name('aiortc', 'RTCPeerConnection', f'{VISION_INWORLD}:15@902db86'),
    Name(
        'aiortc', 'RTCRtpSender', 'vision-agents:plugins/openai/vision_agents/plugins/openai/rtc_manager.py:7@902db86'
    ),
    Name('aiortc', 'RTCSessionDescription', f'{VISION_INWORLD}:15@902db86'),
    Name('aiortc', 'VideoStreamTrack', f'{VISION_AGENTS}/agents/agents.py:14@902db86'),
    Name('aiortc', 'VideoStreamTrack.__init__', f'{ROBOFLOW_WORKER}:769@f79bf9f'),
    Name('aiortc', '__version__', 'stream-py:getstream/video/rtc/__init__.py:55@8d7c51f'),
    Name('aiortc', 'mediastreams', f'{VISION_AGENTS}/agents/agent_types.py:40@902db86'),
    Name('aiortc', 'rtcdtlstransport', 'unitree:unitree_webrtc_connect/__init__.py:32@e0abc57'),
    Name('aiortc.codecs', 'h264', f'{GRADIO_BITRATE}:21@b84a025'),
    Name('aiortc.codecs', 'vpx', f'{GRADIO_BITRATE}:21@b84a025'),
    Name('aiortc.contrib.media', 'AudioFrame', f'{FASTRTC_TRACKS}:32@59ca4f7'),
    Name('aiortc.contrib.media', 'MediaPlayer', 'unitree:examples/go2/audio/internet_radio/stream_radio.py:6@e0abc57'),
    Name('aiortc.contrib.media', 'MediaRecorder', 'streamlit-webrtc:pages/7_record.py:7@7484880'),
    Name('aiortc.contrib.media', 'MediaRelay', 'vidgear:vidgear/gears/asyncio/webgear_rtc.py:80@3d37ad8'),
    Name('aiortc.contrib.media', 'MediaStreamError', f'{ROBOFLOW_MANAGER}:18@f79bf9f'),
    Name('aiortc.contrib.media', 'PlayerStreamTrack', f'{ROBOFLOW_WORKER}:24@f79bf9f'),
    Name('aiortc.contrib.media', 'RelayStreamTrack', 'streamlit-webrtc:streamlit_webrtc/mix.py:13@7484880'),
    Name('aiortc.contrib.media', 'VideoFrame', f'{FASTRTC_TRACKS}:32@59ca4f7'),
    Name('aiortc.contrib.media', 'VideoFrame.from_ndarray', f'{FASTRTC_TRACKS}:132@59ca4f7'),
    Name('aiortc.jitterbuffer', 'JitterBuffer', f'{PIPECAT}:35@6f777a0'),
    Name('aiortc.mediastreams', None, f'{VISION_AGENTS}/agents/agent_types.py:5@902db86'),
    Name('aiortc.mediastreams', 'AUDIO_PTIME', 'stream-py:getstream/video/rtc/audio_track.py:71@8d7c51f'),
    Name(
        'aiortc.mediastreams', 'AudioStreamTrack', 'pipecat:src/pipecat/transports/smallwebrtc/transport.py:59@6f777a0'
    ),
    Name('aiortc.mediastreams', 'MediaStreamError', f'{VISION_AGENTS}/avatars/av_synchronizer.py:9@902db86'),
    Name('aiortc.mediastreams', 'MediaStreamTrack', f'{VISION_AGENTS}/llm/llm.py:497@902db86'),
    Name('aiortc.mediastreams', 'VIDEO_CLOCK_RATE', f'{FASTRTC_TRACKS}:33@59ca4f7'),
    Name('aiortc.mediastreams', 'VIDEO_PTIME', 'roboflow:inference_sdk/webrtc/sources.py:21@f79bf9f'),
    Name('aiortc.mediastreams', 'VIDEO_TIME_BASE', f'{FASTRTC_TRACKS}:33@59ca4f7'),
    Name('aiortc.mediastreams', 'VideoStreamTrack', f'{VISION_AGENTS}/agents/agent_types.py:40@902db86'),
    Name('aiortc.rtcdtlstransport', 'X509_DIGEST_ALGORITHMS', 'unitree:unitree_webrtc_connect/__init__.py:32@e0abc57'),
    Name('aiortc.rtcicetransport', 'connection_kwargs', 'roboflow:inference_sdk/webrtc/turn_probe.py:16@f79bf9f'),
    Name('aiortc.rtcicetransport', 'parse_stun_turn_uri', 'roboflow:inference_sdk/webrtc/turn_probe.py:16@f79bf9f'),
    Name('aiortc.rtcrtpreceiver', 'RTCRtpReceiver', f'{ROBOFLOW_MANAGER}:19@f79bf9f'),
    Name('aiortc.rtcrtpreceiver', 'RemoteStreamTrack', f'{PIPECAT}:36@6f777a0'),
    Name('aiortc.rtcrtpsender', 'RTCRtpSender', 'vidgear:vidgear/gears/asyncio/webgear_rtc.py:82@3d37ad8'),
    Name(
        'aiortc.rtcrtpsender',
        'RTCRtpSender.getCapabilities',
        'vidgear:vidgear/gears/asyncio/webgear_rtc.py:646@3d37ad8',
    ),
    Name('aiortc.rtcsctptransport', None, f'{PIPECAT}:27@6f777a0'),
    Name('aiortc.rtcsctptransport', 'USERDATA_MAX_LENGTH', f'{PIPECAT}:79@6f777a0'),
    Name('aiortc.rtp', 'RtpPacket', 'pipecat:tests/test_smallwebrtc_transport.py:430@6f777a0'),
    Name('aiortc.sdp', 'candidate_from_sdp', 'gradio-pr:gradio/webrtc/connection.py:42@b84a025'),
]

ATTRIBUTES = [
    Attribute('RTCPeerConnection', '_loop', Mode.WRITE, Expected.WORKS, f'{ROBOFLOW_WORKER}:217@f79bf9f', RUNNING_LOOP),
    Attribute(
        'RTCPeerConnection',
        'emit',
        Mode.CALL,
        Expected.WORKS,
        'pipecat:tests/test_smallwebrtc_transport.py:131@6f777a0',
    ),
    Attribute('RTCPeerConnection', 'on', Mode.CALL, Expected.WORKS, f'{PIPECAT}:355@6f777a0'),
    Attribute('RTCPeerConnection', 'remove_all_listeners', Mode.CALL, Expected.WORKS, f'{PIPECAT}:481@6f777a0'),
    Attribute('RTCRtpTransceiver', 'direction', Mode.WRITE, Expected.WORKS, f'{PIPECAT}:508@6f777a0', 'recvonly'),
    Attribute('RTCRtpReceiver', '_enabled', Mode.WRITE, Expected.WORKS, f'{PIPECAT}:156@6f777a0', value=False),
    Attribute('RTCRtpReceiver', '_enabled', Mode.READ, Expected.WORKS, f'{PIPECAT}:219@6f777a0'),
    Attribute(
        'RTCRtpReceiver',
        '_RTCRtpReceiver__jitter_buffer',
        Mode.WRITE,
        Expected.NO_OP,
        f'{PIPECAT}:158@6f777a0',
        JitterBuffer(capacity=512, is_video=True),
        reason="the engine's packet buffer grows to 2048 packets for large frames",
    ),
    Attribute(
        'RTCRtpReceiver',
        '_RTCRtpReceiver__jitter_buffer',
        Mode.READ,
        Expected.GUARDED,
        f'{ROBOFLOW_MANAGER}:212@f79bf9f',
    ),
    Attribute(
        'RTCRtpReceiver',
        '_RTCRtpReceiver__decoder_queue',
        Mode.READ,
        Expected.GUARDED,
        f'{ROBOFLOW_MANAGER}:202@f79bf9f',
    ),
    Attribute(
        'RTCRtpReceiver',
        '_RTCRtpReceiver__stop_decoder',
        Mode.READ,
        Expected.GUARDED,
        'streamlit-webrtc:streamlit_webrtc/webrtc.py:372@7484880',
    ),
    Attribute('RemoteStreamTrack', '_queue', Mode.READ, Expected.WORKS, f'{PIPECAT}:188@6f777a0'),
    Attribute('RemoteStreamTrack', '_queue.empty', Mode.CALL, Expected.WORKS, f'{PIPECAT}:194@6f777a0'),
    Attribute('RemoteStreamTrack', '_queue.get_nowait', Mode.CALL, Expected.WORKS, f'{PIPECAT}:195@6f777a0'),
    Attribute('RemoteStreamTrack', '_queue.task_done', Mode.CALL, Expected.WORKS, f'{PIPECAT}:196@6f777a0'),
    Attribute('RemoteStreamTrack', '_queue.qsize', Mode.CALL, Expected.WORKS, f'{ROBOFLOW_MANAGER}:228@f79bf9f'),
    Attribute('RelayStreamTrack', '_queue.qsize', Mode.CALL, Expected.WORKS, f'{ROBOFLOW_MANAGER}:193@f79bf9f'),
    Attribute('PlayerStreamTrack', '_queue.qsize', Mode.CALL, Expected.WORKS, f'{ROBOFLOW_WORKER}:608@f79bf9f'),
    Attribute('PlayerStreamTrack', '_queue.get_nowait', Mode.CALL, Expected.WORKS, f'{ROBOFLOW_WORKER}:609@f79bf9f'),
    Attribute(
        'RTCRtpTransceiver',
        '_codecs',
        Mode.READ,
        Expected.UNSUPPORTED,
        f'{GRADIO_BITRATE}:119@b84a025',
        reason=NO_ENCODER,
    ),
    Attribute(
        'RTCRtpSender',
        '_RTCRtpSender__encoder',
        Mode.READ,
        Expected.UNSUPPORTED,
        f'{GRADIO_BITRATE}:121@b84a025',
        reason=NO_ENCODER,
    ),
    Attribute(
        'codecs.vpx', 'Vp8Encoder', Mode.READ, Expected.UNSUPPORTED, f'{GRADIO_BITRATE}:105@b84a025', reason=NO_ENCODER
    ),
    Attribute(
        'codecs.h264',
        'H264Encoder',
        Mode.READ,
        Expected.UNSUPPORTED,
        f'{GRADIO_BITRATE}:106@b84a025',
        reason=NO_ENCODER,
    ),
]

DEPENDENCIES = [
    Dependency('aioice', 'unitree:unitree_webrtc_connect/__init__.py:3@e0abc57', 'its patched connections go unused'),
    Dependency('aioice', 'roboflow:inference_sdk/webrtc/turn_probe.py:14@f79bf9f', 'its TURN probe still runs'),
    Dependency('aioice', f'{ROBOFLOW_WORKER}:14@f79bf9f', 'its mDNS lock goes unused'),
    Dependency('cryptography', 'unitree:unitree_webrtc_connect/__init__.py:36@e0abc57', 'its digests go unused'),
]


def lookup(owner: object, dotted: str) -> object:
    """The attribute at a dotted path, such as ``VideoFrame.from_ndarray``."""
    found = owner
    for attribute in dotted.split('.'):
        found = getattr(found, attribute)
    return found


@contextlib.asynccontextmanager
async def connection() -> AsyncGenerator[RTCPeerConnection]:
    pc = RTCPeerConnection(CONFIGURATION)
    try:
        yield pc
    finally:
        await pc.close()


@contextlib.asynccontextmanager
async def transceiver() -> AsyncGenerator[RTCRtpTransceiver]:
    async with connection() as pc:
        yield pc.addTransceiver('video')


@contextlib.asynccontextmanager
async def sender() -> AsyncGenerator[object]:
    async with transceiver() as found:
        yield found.sender


@contextlib.asynccontextmanager
async def receiver() -> AsyncGenerator[object]:
    async with transceiver() as found:
        yield found.receiver


@contextlib.asynccontextmanager
async def remote_track() -> AsyncGenerator[RemoteStreamTrack]:
    generator = webrtc.VideoTrackGenerator()
    track = RemoteStreamTrack._of(generator.track, None)
    try:
        yield track
    finally:
        track.stop()


@contextlib.asynccontextmanager
async def relayed_track() -> AsyncGenerator[object]:
    async with remote_track() as track:
        relayed = MediaRelay().subscribe(track)
        try:
            yield relayed
        finally:
            relayed.stop()


@contextlib.asynccontextmanager
async def player_track() -> AsyncGenerator[object]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'media.webm'
        write_media(path)
        player = MediaPlayer(str(path))
        assert player.video is not None
        try:
            yield player.video
        finally:
            player.video.stop()


@contextlib.asynccontextmanager
async def vpx() -> AsyncGenerator[object]:
    yield importlib.import_module('webrtc.aiortc.codecs.vpx')


@contextlib.asynccontextmanager
async def h264() -> AsyncGenerator[object]:
    yield importlib.import_module('webrtc.aiortc.codecs.h264')


OWNERS: dict[str, Callable[[], contextlib.AbstractAsyncContextManager[object]]] = {
    'RTCPeerConnection': connection,
    'RTCRtpTransceiver': transceiver,
    'RTCRtpSender': sender,
    'RTCRtpReceiver': receiver,
    'RemoteStreamTrack': remote_track,
    'RelayStreamTrack': relayed_track,
    'PlayerStreamTrack': player_track,
    'codecs.vpx': vpx,
    'codecs.h264': h264,
}


def name_id(row: Name) -> str:
    return f'{row.module}:{row.name}'


def attribute_id(row: Attribute) -> str:
    return f'{row.owner}.{row.attribute}:{row.mode.value}'


@pytest.mark.parametrize('row', NAMES, ids=name_id)
def test_name(row: Name) -> None:
    module = importlib.import_module(f'webrtc.{row.module}')

    if row.name is not None:
        lookup(module, row.name)


@pytest.mark.asyncio
@pytest.mark.parametrize('row', ATTRIBUTES, ids=attribute_id)
async def test_attribute(row: Attribute) -> None:
    async with OWNERS[row.owner]() as owner:
        if row.expected in {Expected.GUARDED, Expected.UNSUPPORTED}:
            assert not hasattr(owner, row.attribute)
        elif row.mode is Mode.WRITE:
            value = asyncio.get_running_loop() if row.value is RUNNING_LOOP else row.value
            setattr(owner, row.attribute, value)
            assert getattr(owner, row.attribute) is value
        elif row.mode is Mode.CALL:
            assert callable(lookup(owner, row.attribute))
        else:
            lookup(owner, row.attribute)


def test_rows_say_why() -> None:
    """A no-op or unsupported row gives its reason."""
    unexplained = [
        row for row in ATTRIBUTES if row.expected in {Expected.NO_OP, Expected.UNSUPPORTED} and row.reason == ''
    ]

    assert unexplained == []


@isolated
def test_names_import_through_the_alias() -> None:
    install_alias()

    for row in NAMES:
        module = importlib.import_module(row.module)
        assert module is importlib.import_module(f'webrtc.{row.module}')
        if row.name is not None:
            lookup(module, row.name)


@isolated
def test_layer_imports_none_of_the_dependencies() -> None:
    package = importlib.import_module('webrtc.aiortc')
    for module in pkgutil.walk_packages(package.__path__, 'webrtc.aiortc.'):
        importlib.import_module(module.name)

    imported = [row.module for row in DEPENDENCIES if row.module in sys.modules]
    assert imported == []


def test_jitter_buffer_assembles_a_frame_of_many_packets() -> None:
    """A 300-packet frame comes out whole once the next frame's first packet arrives."""
    buffer = JitterBuffer(capacity=512, is_video=True)

    frames: list[JitterFrame] = []
    for sequence_number in range(301):
        timestamp = 0 if sequence_number < 300 else 3000
        packet = RtpPacket(payload_type=96, sequence_number=sequence_number, timestamp=timestamp)
        # the depayloader sets it in a receiver
        packet._data = b'x'  # pyrefly: ignore[missing-attribute]
        pli, frame = buffer.add(packet)
        assert not pli
        if frame is not None:
            frames.append(frame)

    assert [len(frame.data) for frame in frames] == [300]


def test_stun_and_turn_urls_parse() -> None:
    servers = [
        RTCIceServer('stun:stun.example.com'),
        RTCIceServer('turns:turn.example.com:443', username='user', credential='secret'),
    ]

    kwargs = connection_kwargs(servers)

    assert STUN_REGEX.fullmatch('stun:stun.example.com:3478') is not None
    assert TURN_REGEX.fullmatch('turn:turn.example.com?transport=tcp') is not None
    assert parse_stun_turn_uri('turn:turn.example.com') == {
        'scheme': 'turn',
        'host': 'turn.example.com',
        'port': 3478,
        'transport': 'udp',
    }
    assert kwargs == {
        'stun_server': ('stun.example.com', 3478),
        'turn_server': ('turn.example.com', 443),
        'turn_ssl': True,
        'turn_transport': 'tcp',
        'turn_username': 'user',
        'turn_password': 'secret',
    }
