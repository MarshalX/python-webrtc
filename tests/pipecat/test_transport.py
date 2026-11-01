#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The transport in a running pipeline, against a native peer shaped like the browser client."""

from __future__ import annotations

import array
import asyncio
import collections
import contextlib
import re
from typing import TYPE_CHECKING

import pytest
from loguru import logger
from pipecat.frames.frames import (
    ClientConnectedFrame,
    EndFrame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputImageRawFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
    UserImageRawFrame,
    UserImageRequestFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.base_transport import TransportParams, VideoInSourceParams
from pipecat.workers.runner import WorkerRunner

import webrtc
from tests.helpers import UdpRelay, reader_of, wait_until, write_frames
from tests.pipecat._audio import dominant_frequency, sine
from tests.pipecat._client import BrowserClient, add_candidates, connect_client
from tests.timing import seconds
from webrtc.pipecat._media import AudioPacer  # ruff: ignore[import-private-name]
from webrtc.pipecat.connection import (
    _DISCONNECTED_CLIENT_SECS,  # ruff: ignore[import-private-name]
    SIGNALLING_TYPE,
    SmallWebRTCConnection,
)
from webrtc.pipecat.transport import SmallWebRTCTransport

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from pipecat.frames.frames import Frame

SAMPLE_RATE = 48000
CHUNK_SAMPLES = 480
BOT_SAMPLE_RATE = 16000
CAMERA_SIZE = (320, 240)
SCREEN_SIZE = (640, 360)
#: I420 of a red and of a blue, limited range
RED_YUV = (81, 90, 240)
BLUE_YUV = (41, 240, 110)
#: how close a tone heard back is to the one sent, in Hz
TONE_TOLERANCE = 15
#: long enough for a few frames of a source to arrive, when checking they don't
FEW_FRAMES_SECS = 0.5


def solid_i420(size: tuple[int, int], yuv: tuple[int, int, int]) -> bytes:
    width, height = size
    y, u, v = yuv
    chroma = (width // 2) * (height // 2)
    return bytes([y] * (width * height) + [u] * chroma + [v] * chroma)


async def write_tone(generator: webrtc.MediaStreamTrackGenerator, frequency: float, *, stop: asyncio.Event) -> None:
    """Writes a sine of 48 kHz mono in 10 ms chunks, at the pace of real time."""
    writer = generator.writable.get_writer()
    loop = asyncio.get_running_loop()
    start = loop.time()
    written = 0
    while not stop.is_set():
        init = webrtc.AudioDataInit(
            format='s16',
            sample_rate=SAMPLE_RATE,
            number_of_frames=CHUNK_SAMPLES,
            number_of_channels=1,
            timestamp=written * 1_000_000 // SAMPLE_RATE,
            data=sine(frequency, SAMPLE_RATE, first=written, count=CHUNK_SAMPLES),
        )
        await writer.write(webrtc.AudioData(init))
        written += CHUNK_SAMPLES
        await asyncio.sleep(max(0.0, start + written / SAMPLE_RATE - loop.time()))
    writer.release_lock()


class Media:
    """Tasks that feed a client's sources and read what the bot sends it, until stopped."""

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._generators: list[webrtc.MediaStreamTrack] = []

    async def send_tone(self, transceiver: webrtc.RTCRtpTransceiver, frequency: float) -> None:
        generator = webrtc.MediaStreamTrackGenerator('audio')
        await transceiver.sender.replace_track(generator)
        self._generators.append(generator)
        self._tasks.append(asyncio.ensure_future(write_tone(generator, frequency, stop=self._stop)))

    async def send_video(
        self,
        transceiver: webrtc.RTCRtpTransceiver,
        size: tuple[int, int],
        yuv: tuple[int, int, int],
        *,
        rotation: int = 0,
    ) -> None:
        generator = webrtc.VideoTrackGenerator()
        await transceiver.sender.replace_track(generator.track)
        self._generators.append(generator.track)
        width, height = size
        init = webrtc.VideoFrameBufferInit(
            format='I420', coded_width=width, coded_height=height, timestamp=0, rotation=rotation
        )
        self._tasks.append(asyncio.ensure_future(write_frames(generator, solid_i420(size, yuv), init, stop=self._stop)))

    def listen(self, transceiver: webrtc.RTCRtpTransceiver) -> Listener:
        listener = Listener(transceiver.receiver.track)
        self._tasks.append(asyncio.ensure_future(listener.run()))
        return listener

    async def stop(self) -> None:
        self._stop.set()
        tasks = self._tasks
        self._tasks = []
        for task in tasks:
            _ = task.cancel()
        _ = await asyncio.gather(*tasks, return_exceptions=True)
        for generator in self._generators:
            generator.stop()


class Listener:
    """The last half second of audio a client receives."""

    def __init__(self, track: webrtc.MediaStreamTrack) -> None:
        self._track = track
        self.samples: collections.deque[int] = collections.deque(maxlen=SAMPLE_RATE // 2)

    async def run(self) -> None:
        reader = reader_of(self._track, max_buffer_size=100)
        try:
            while True:
                audio = (await reader.read()).value
                if audio is None:
                    return
                assert isinstance(audio, webrtc.AudioData)
                with audio:
                    plane = array.array('h', bytes(audio.number_of_frames * 2))
                    options = webrtc.AudioDataCopyToOptions(plane_index=0, format='s16-planar')
                    audio.copy_to(memoryview(plane).cast('B'), options)
                self.samples.extend(plane)
        finally:
            _ = reader.cancel()

    def frequency(self) -> float | None:
        return dominant_frequency(list(self.samples), SAMPLE_RATE)

    async def wait_for_tone(self, frequency: float) -> None:
        def heard() -> bool:
            heard = self.frequency()
            return heard is not None and abs(heard - frequency) < TONE_TOLERANCE

        await wait_until(heard, f'{frequency} Hz back', timeout=seconds(15))


class Recorder(FrameProcessor):
    """Echoes the client's audio and app messages back, and keeps the images and frames it sees."""

    def __init__(self) -> None:
        super().__init__()
        self.audio: list[InputAudioRawFrame] = []
        self.images: list[UserImageRawFrame] = []
        self.messages: list[object] = []
        self.connected = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame):
            self.audio.append(frame)
            echo = OutputAudioRawFrame(frame.audio, frame.sample_rate, frame.num_channels)
            await self.push_frame(echo)
        elif isinstance(frame, UserImageRawFrame):
            self.images.append(frame)
        elif isinstance(frame, InputTransportMessageFrame):
            self.messages.append(frame.message)
            await self.push_frame(OutputTransportMessageUrgentFrame(message={'echo': frame.message}))
        else:
            if isinstance(frame, ClientConnectedFrame):
                self.connected += 1
            await self.push_frame(frame, direction)

    def images_of(self, source: str) -> list[UserImageRawFrame]:
        return [image for image in self.images if image.transport_source == source]


class SolidVideo(FrameProcessor):
    """Sends a green image of the camera's size at 15 frames a second once the pipeline starts."""

    def __init__(self) -> None:
        super().__init__()
        self._task: asyncio.Task[None] | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame) and self._task is None:
            self._task = self.create_task(self._send())
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        await super().cleanup()
        if self._task is not None:
            await self.cancel_task(self._task)

    async def _send(self) -> None:
        width, height = CAMERA_SIZE
        green = bytes([0, 200, 0]) * (width * height)
        while True:
            await self.push_frame(OutputImageRawFrame(image=green, size=CAMERA_SIZE, format='RGB'))
            await asyncio.sleep(1 / 15)


class Bot:
    """A pipeline of the transport over a connection, and the transport's events."""

    def __init__(self, connection: SmallWebRTCConnection, params: TransportParams) -> None:
        self.connection = connection
        self.transport = SmallWebRTCTransport(webrtc_connection=connection, params=params)
        self.recorder = Recorder()
        processors: list[FrameProcessor] = [self.transport.input(), self.recorder]
        if params.video_out_enabled:
            processors.append(SolidVideo())
        processors.append(self.transport.output())
        self.worker = PipelineWorker(
            Pipeline(processors),
            params=PipelineParams(audio_in_sample_rate=BOT_SAMPLE_RATE),
            enable_rtvi=False,
            idle_timeout_secs=None,
        )

        self.connected: list[SmallWebRTCConnection] = []
        self.disconnected: list[SmallWebRTCConnection] = []
        self.app_messages: list[tuple[object, str]] = []
        self.transport.add_event_handler('on_client_connected', self._on_connected)
        self.transport.add_event_handler('on_client_disconnected', self._on_disconnected)
        self.transport.add_event_handler('on_app_message', self._on_app_message)

    async def _on_connected(self, _transport: SmallWebRTCTransport, connection: SmallWebRTCConnection) -> None:
        self.connected.append(connection)

    async def _on_disconnected(self, _transport: SmallWebRTCTransport, connection: SmallWebRTCConnection) -> None:
        self.disconnected.append(connection)
        # what a bot does when its client leaves
        await self.worker.cancel()

    async def _on_app_message(self, _transport: SmallWebRTCTransport, message: object, sender: str) -> None:
        self.app_messages.append((message, sender))


class Session:
    """A bot running for a client, and the media of the client."""

    def __init__(self, bot: Bot, client: BrowserClient, *, media: Media, run: asyncio.Task[None]) -> None:
        self.bot = bot
        self.client = client
        self.media = media
        self.run = run

    @property
    def connection(self) -> SmallWebRTCConnection:
        return self.bot.connection

    @property
    def recorder(self) -> Recorder:
        return self.bot.recorder

    async def wait_ended(self) -> None:
        await asyncio.wait_for(asyncio.shield(self.run), seconds(10))


def default_params() -> TransportParams:
    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_in_enabled=True,
        video_in_sources={'camera': VideoInSourceParams(framerate=10), 'screenVideo': VideoInSourceParams()},
    )


async def offer_to(connection: SmallWebRTCConnection, client: BrowserClient, *, restart_pc: bool = False) -> None:
    offer = await client.offer()
    await connection.renegotiate(sdp=offer['sdp'], type=offer['type'], restart_pc=restart_pc)
    await client.accept(connection.get_answer())


async def start_client(media: Media, *, tone: float = 440) -> BrowserClient:
    """A client sending a tone, a red camera and a blue screen share."""
    client = BrowserClient()
    assert client.camera is not None
    assert client.screen is not None
    await media.send_tone(client.microphone, tone)
    await media.send_video(client.camera, CAMERA_SIZE, RED_YUV)
    await media.send_video(client.screen, SCREEN_SIZE, BLUE_YUV)
    return client


def without_candidates(answer: dict[str, str] | None) -> dict[str, str]:
    assert answer is not None
    return {**answer, 'sdp': re.sub(r'^a=candidate:.*\r\n', '', answer['sdp'], flags=re.MULTILINE)}


async def connect_through(relay: UdpRelay, connection: SmallWebRTCConnection, client: BrowserClient) -> None:
    """Connects the client to the bot's answer through the relay only."""
    await client.accept(without_candidates(connection.get_answer()))
    await wait_until(lambda: connection.pc.ice_gathering_state == 'complete', 'the bot gathering')

    for_bot, for_client = await relay.bridge(await client.gathered_candidates(), bot_candidates(connection))
    await connection.add_ice_candidate(candidate_init(for_bot))
    await client.pc.add_ice_candidate(candidate_init(for_client))


def bot_candidates(connection: SmallWebRTCConnection) -> list[webrtc.RTCIceCandidate]:
    """The candidates of the bot's first media section, which bundles the others."""
    description = connection.pc.local_description
    assert description is not None
    attributes: list[str] = re.findall(r'^a=(candidate:[^\r\n]*)', description.sdp, re.MULTILINE)
    return [webrtc.RTCIceCandidate(attribute, '0', 0) for attribute in attributes]


def candidate_init(candidate: webrtc.RTCIceCandidate) -> webrtc.RTCIceCandidateInit:
    return webrtc.RTCIceCandidateInit(
        candidate=candidate.candidate, sdp_mid=candidate.sdp_mid, sdp_m_line_index=candidate.sdp_m_line_index
    )


@contextlib.asynccontextmanager
async def session(
    params: TransportParams | None = None, *, relay: UdpRelay | None = None
) -> AsyncGenerator[Session, None]:
    """A bot started on a client's first offer, as the runner starts one; it all ends after the block."""
    media = Media()
    client = await start_client(media)
    connection = SmallWebRTCConnection()
    bot = Bot(connection, default_params() if params is None else params)

    offer = await client.offer()
    await connection.initialize(sdp=offer['sdp'], type=offer['type'])
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(bot.worker)
    run = asyncio.ensure_future(runner.run())
    try:
        # with a relay, the client and the bot reach each other only through it
        if relay is None:
            await client.accept(connection.get_answer())
            await add_candidates(connection, client)
        else:
            await connect_through(relay, connection, client)
        await client.wait_connected()
        await wait_until(lambda: len(bot.connected) > 0, 'the bot to see its client')
        yield Session(bot, client, media=media, run=run)
    finally:
        await media.stop()
        if not run.done():
            await bot.worker.cancel()
        _ = await asyncio.wait_for(asyncio.gather(run, return_exceptions=True), seconds(10))
        client.close()
        await connection.disconnect()
    await tasks_ended()


async def tasks_ended() -> None:
    """Waits for every task but this one to end, and fails naming those that don't."""
    current = asyncio.current_task()

    def left() -> list[asyncio.Task[object]]:
        return [task for task in asyncio.all_tasks() if task is not current and not task.done()]

    with contextlib.suppress(TimeoutError):
        await wait_until(lambda: left() == [], 'the tasks to end', timeout=seconds(5))
    assert left() == []


async def no_tasks_left(running: Session) -> None:
    """Stops the client's media, and checks that the bot, ended, left no task behind."""
    await running.media.stop()
    await tasks_ended()


@pytest.fixture
def problems() -> Generator[list[str], None, None]:
    """The warnings and errors logged during the test."""
    logged: list[str] = []

    def record(message: object) -> None:
        logged.append(str(message))

    sink = logger.add(record, level='WARNING')
    yield logged
    logger.remove(sink)


@pytest.mark.asyncio
async def test_audio_comes_back(problems: list[str]) -> None:
    async with session() as running:
        listener = running.media.listen(running.client.microphone)
        await listener.wait_for_tone(440)

        audio = running.recorder.audio
        assert {(frame.sample_rate, frame.num_channels, len(frame.audio)) for frame in audio} == {
            (BOT_SAMPLE_RATE, 1, BOT_SAMPLE_RATE // 50 * 2)
        }
        assert running.recorder.connected == 1
        assert running.bot.connected == [running.connection]

    assert problems == []


@pytest.mark.asyncio
async def test_app_messages_go_both_ways(problems: list[str]) -> None:
    async with session() as running:
        await running.client.wait_channel_open()

        running.client.send({'type': 'hello', 'n': 1})
        await wait_until(lambda: {'echo': {'type': 'hello', 'n': 1}} in running.client.messages, 'the echo')

        assert running.recorder.messages == [{'type': 'hello', 'n': 1}]
        assert running.bot.app_messages == [({'type': 'hello', 'n': 1}, running.connection.pc_id)]

    assert problems == []


def assert_solid(image: UserImageRawFrame, size: tuple[int, int], color: str) -> None:
    width, height = size
    assert image.size == size
    assert image.format == 'RGB'
    assert len(image.image) == width * height * 3

    center = (height // 2 * width + width // 2) * 3
    red, green, blue = image.image[center : center + 3]
    strongest = {'red': red, 'blue': blue}[color]
    assert strongest > 150
    assert green < 100


@pytest.mark.asyncio
async def test_camera_and_screen_reach_the_pipeline_as_rgb(problems: list[str]) -> None:
    async with session() as running:
        recorder = running.recorder
        await wait_until(lambda: len(recorder.images_of('camera')) >= 3, 'camera images')
        await wait_until(lambda: len(recorder.images_of('screenVideo')) >= 3, 'screen images')

        assert_solid(recorder.images_of('camera')[-1], CAMERA_SIZE, 'red')
        assert_solid(recorder.images_of('screenVideo')[-1], SCREEN_SIZE, 'blue')
        assert {image.user_id for image in recorder.images} == {running.connection.pc_id}

    assert problems == []


@pytest.mark.asyncio
async def test_a_turned_camera_reaches_the_pipeline_turned(problems: list[str]) -> None:
    async with session() as running:
        camera = running.client.camera
        assert camera is not None
        # a phone held upright sends its pixels unturned, and the turn with them
        await running.media.send_video(camera, CAMERA_SIZE, RED_YUV, rotation=90)
        width, height = CAMERA_SIZE

        def turned() -> list[UserImageRawFrame]:
            return [image for image in running.recorder.images_of('camera') if image.size == (height, width)]

        await wait_until(turned, 'turned camera images')
        assert_solid(turned()[-1], (height, width), 'red')

    assert problems == []


@pytest.mark.asyncio
async def test_a_source_is_read_only_while_captured(problems: list[str]) -> None:
    params = TransportParams(audio_in_enabled=True, video_in_enabled=True)
    async with session(params) as running:
        recorder = running.recorder
        await asyncio.sleep(FEW_FRAMES_SECS)
        assert recorder.images == []

        await running.bot.transport.capture_participant_video(running.connection.pc_id, None, 'screenVideo')
        await wait_until(lambda: len(recorder.images_of('screenVideo')) >= 3, 'screen images')

        assert recorder.images_of('camera') == []

    assert problems == []


@pytest.mark.asyncio
async def test_image_requests_ride_on_the_next_frame(problems: list[str]) -> None:
    params = TransportParams(
        audio_in_enabled=True,
        video_in_enabled=True,
        video_in_sources={'camera': VideoInSourceParams(on_request_only=True)},
    )
    async with session(params) as running:
        recorder = running.recorder
        await asyncio.sleep(FEW_FRAMES_SECS)
        assert recorder.images == []

        requests = [UserImageRequestFrame(user_id='a', text='describe'), UserImageRequestFrame(user_id='b')]
        for request in requests:
            await running.bot.transport.input().queue_frame(request)
        await wait_until(lambda: len(recorder.images) >= 2, 'the answers')
        await asyncio.sleep(FEW_FRAMES_SECS)

        assert [image.request for image in recorder.images] == requests
        assert recorder.images[0].text == 'describe'

    assert problems == []


def track_status(receiver_index: int, *, enabled: bool) -> dict[str, object]:
    message = {'type': 'trackStatus', 'receiver_index': receiver_index, 'enabled': enabled}
    return {'type': SIGNALLING_TYPE, 'message': message}


@pytest.mark.asyncio
async def test_a_source_turned_off_sends_no_images(problems: list[str]) -> None:
    async with session() as running:
        recorder = running.recorder
        await running.client.wait_channel_open()
        await wait_until(lambda: len(recorder.images_of('camera')) > 0, 'camera images')

        answers: list[object] = []

        async def answered(result: object) -> None:  # ruff: ignore[unused-async]
            answers.append(result)

        running.client.send(track_status(1, enabled=False))
        await asyncio.sleep(FEW_FRAMES_SECS)
        request = UserImageRequestFrame(user_id='a', video_source='camera', result_callback=answered)
        await running.bot.transport.input().queue_frame(request)
        off = len(recorder.images_of('camera'))
        screen = len(recorder.images_of('screenVideo'))
        await asyncio.sleep(FEW_FRAMES_SECS)

        assert len(recorder.images_of('camera')) == off
        assert len(recorder.images_of('screenVideo')) > screen
        assert answers == [{'error': "The client isn't sending camera video."}]

        running.client.send(track_status(1, enabled=True))
        await wait_until(lambda: len(recorder.images_of('camera')) > off, 'camera images again')

    # the answer to the request is logged
    assert len(problems) == 1
    assert "The client isn't sending camera video." in problems[0]


async def center_of_next_frame(track: webrtc.MediaStreamTrack, size: tuple[int, int]) -> tuple[int, int, int]:
    """The RGB of the center pixel of the next frame of a track, which must be of the size."""
    options = webrtc.VideoFrameCopyToOptions(format='RGBX')
    reader = reader_of(track)
    try:
        frame = (await asyncio.wait_for(reader.read(), seconds(10))).value
        assert isinstance(frame, webrtc.VideoFrame)
        with frame:
            assert (frame.coded_width, frame.coded_height) == size
            rgbx = bytearray(frame.allocation_size(options))
            _ = await frame.copy_to(rgbx, options)
    finally:
        _ = reader.cancel()

    center = (size[1] // 2 * size[0] + size[0] // 2) * 4
    red, green, blue, _ = rgbx[center : center + 4]
    return red, green, blue


@pytest.mark.asyncio
async def test_bot_video_reaches_the_client(problems: list[str]) -> None:
    params = TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_is_live=True,
        video_out_width=CAMERA_SIZE[0],
        video_out_height=CAMERA_SIZE[1],
    )
    async with session(params) as running:
        assert running.client.camera is not None
        red, green, blue = await center_of_next_frame(running.client.camera.receiver.track, CAMERA_SIZE)

        assert green > 150
        assert max(red, blue) < 100

    assert problems == []


@pytest.mark.asyncio
async def test_a_client_renegotiation_keeps_the_media(problems: list[str]) -> None:
    async with session() as running:
        listener = running.media.listen(running.client.microphone)
        await listener.wait_for_tone(440)

        await offer_to(running.connection, running.client)
        images = len(running.recorder.images)
        listener.samples.clear()

        await listener.wait_for_tone(440)
        await wait_until(lambda: len(running.recorder.images) > images, 'images after renegotiating')
        assert running.bot.connected == [running.connection]

    assert problems == []


@pytest.mark.asyncio
async def test_the_bot_asks_for_a_renegotiation(problems: list[str]) -> None:
    async with session() as running:
        await running.client.wait_channel_open()

        running.connection.ask_to_renegotiate()
        renegotiate = {'type': SIGNALLING_TYPE, 'message': {'type': 'renegotiate'}}
        await wait_until(lambda: renegotiate in running.client.messages, 'the request to renegotiate')
        await offer_to(running.connection, running.client)

        listener = running.media.listen(running.client.microphone)
        await listener.wait_for_tone(440)

    assert problems == []


@pytest.mark.asyncio
async def test_a_restart_resumes_the_media(problems: list[str]) -> None:
    async with session() as running:
        old_pc_id = running.connection.pc_id
        restarted = await start_client(running.media, tone=660)
        try:
            # the browser client offers on its new connection first, then closes the old one
            await offer_to(running.connection, restarted, restart_pc=True)
            await add_candidates(running.connection, restarted)
            running.client.close()
            await restarted.wait_connected()

            listener = running.media.listen(restarted.microphone)
            await listener.wait_for_tone(660)
            images = len(running.recorder.images_of('screenVideo'))
            await wait_until(lambda: len(running.recorder.images_of('screenVideo')) > images, 'screen images')

            assert running.connection.pc_id != old_pc_id
            assert running.bot.connected == [running.connection, running.connection]
            assert running.recorder.connected == 2
            assert running.bot.disconnected == []
        finally:
            restarted.close()

    assert problems == []


@pytest.mark.asyncio
async def test_an_ended_source_parks_its_reader(problems: list[str]) -> None:
    async with session() as running:
        recorder = running.recorder
        await wait_until(lambda: len(recorder.images_of('screenVideo')) > 0, 'screen images')
        assert running.client.screen is not None

        screen_track = running.connection.screen_video_input_track()
        assert screen_track is not None

        running.client.screen.stop()
        await offer_to(running.connection, running.client)
        await wait_until(lambda: screen_track.ready_state == 'ended', 'the screen track ending')
        screen = len(recorder.images_of('screenVideo'))
        camera = len(recorder.images_of('camera'))
        await asyncio.sleep(FEW_FRAMES_SECS)

        assert len(recorder.images_of('screenVideo')) == screen
        assert len(recorder.images_of('camera')) > camera
        reader = running.bot.transport.input()._receive_video_tasks['screenVideo']
        assert not reader.done()

    assert problems == []


@pytest.mark.asyncio
async def test_the_client_leaving_ends_the_pipeline(problems: list[str]) -> None:
    async with session() as running:
        await running.client.wait_channel_open()

        running.client.close()
        await running.wait_ended()

        assert running.bot.disconnected == [running.connection]
        await no_tasks_left(running)

    assert problems == []


@pytest.mark.asyncio
async def test_ending_the_pipeline_tells_the_client(problems: list[str]) -> None:
    params = TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_end_silence_secs=0)
    async with session(params) as running:
        await running.client.wait_channel_open()

        await running.bot.worker.queue_frame(EndFrame())
        await running.wait_ended()

        peer_left = {'type': SIGNALLING_TYPE, 'message': {'type': 'peerLeft'}}
        await wait_until(lambda: peer_left in running.client.messages, 'the bot leaving')
        assert running.bot.disconnected == []
        assert running.connection.pc.connection_state == 'closed'
        await no_tasks_left(running)

    assert problems == []


@pytest.mark.asyncio
async def test_the_processors_take_their_names() -> None:
    connection = SmallWebRTCConnection()
    transport = SmallWebRTCTransport(
        webrtc_connection=connection, params=TransportParams(), input_name='in', output_name='out'
    )

    assert transport.input().name == 'in'
    assert transport.output().name == 'out'
    await connection.disconnect()


async def ping_every_second(client: BrowserClient) -> None:
    """Pings over the data channel, as the framework's JavaScript client does."""
    while True:
        client.ping()
        await asyncio.sleep(1)


@contextlib.asynccontextmanager
async def pinging(running: Session, *, pings: bool) -> AsyncGenerator[None, None]:
    """Pings from the client during the block, once the bot got a first ping; nothing without ``pings``."""
    if not pings:
        yield
        return

    await running.client.wait_channel_open()
    task = asyncio.ensure_future(ping_every_second(running.client))
    try:
        await wait_until(lambda: running.connection._last_ping is not None, 'the first ping')
        yield
    finally:
        _ = task.cancel()
        _ = await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('client', ['silent', 'pinging'])
async def test_a_connection_that_recovers_keeps_the_client(problems: list[str], client: str) -> None:
    relay = UdpRelay()
    try:
        async with session(relay=relay) as running, pinging(running, pings=client == 'pinging'):
            listener = running.media.listen(running.client.microphone)
            await listener.wait_for_tone(440)
            pc = running.connection.pc
            loop = asyncio.get_running_loop()

            # the engine notices after some seconds without answers to its checks
            relay.paused = True
            await wait_until(lambda: pc.connection_state == 'disconnected', 'the drop', timeout=seconds(20))
            dropped = loop.time()
            relay.paused = False
            await wait_until(lambda: pc.connection_state == 'connected', 'the recovery', timeout=seconds(20))

            listener.samples.clear()
            images = len(running.recorder.images)
            await listener.wait_for_tone(440)
            await wait_until(lambda: len(running.recorder.images) > images, 'images after recovering')
            # past the time a disconnected client that pings may stay silent
            await asyncio.sleep(max(dropped + _DISCONNECTED_CLIENT_SECS + 0.5 - loop.time(), 0))
            assert running.bot.disconnected == []
            assert running.bot.connected == [running.connection]
            assert running.recorder.connected == 1
    finally:
        relay.close()

    assert problems == []


@pytest.mark.asyncio
async def test_a_pinging_client_that_vanishes_leaves_before_the_connection_fails(problems: list[str]) -> None:
    relay = UdpRelay()
    try:
        async with session(relay=relay) as running, pinging(running, pings=True):
            pc = running.connection.pc
            loop = asyncio.get_running_loop()

            # the client's process dies: nothing comes from it anymore, and nothing closes
            relay.paused = True
            await wait_until(lambda: pc.connection_state == 'disconnected', 'the drop', timeout=seconds(20))
            dropped = loop.time()
            await wait_until(
                lambda: running.bot.disconnected == [running.connection],
                'the client to leave',
                timeout=seconds(_DISCONNECTED_CLIENT_SECS + 2),
            )

            # the connection itself fails about 10 s after the drop
            assert loop.time() - dropped < seconds(_DISCONNECTED_CLIENT_SECS + 1.5)
            assert pc.connection_state == 'closed'
    finally:
        relay.close()

    assert problems == []


@pytest.mark.asyncio
async def test_a_pinging_client_that_restarts_after_its_disconnect_keeps_the_bot(problems: list[str]) -> None:
    relay = UdpRelay()
    try:
        async with session(relay=relay) as running, pinging(running, pings=True):
            pc = running.connection.pc
            relay.paused = True
            await wait_until(lambda: pc.connection_state == 'disconnected', 'the drop', timeout=seconds(20))

            # the framework's JavaScript client offers a new connection 5 s after its own disconnect
            await asyncio.sleep(5)
            restarted = await start_client(running.media, tone=660)
            try:
                await offer_to(running.connection, restarted, restart_pc=True)
                await add_candidates(running.connection, restarted)
                running.client.close()
                await restarted.wait_connected()

                listener = running.media.listen(restarted.microphone)
                await listener.wait_for_tone(660)
                assert running.bot.disconnected == []
                assert running.bot.connected == [running.connection, running.connection]
            finally:
                restarted.close()
    finally:
        relay.close()

    assert problems == []


@pytest.mark.asyncio
async def test_an_interruption_reaches_the_pacer(problems: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    interrupted: list[AudioPacer] = []

    def interrupt(pacer: AudioPacer) -> None:
        interrupted.append(pacer)

    monkeypatch.setattr(AudioPacer, 'interrupt', interrupt)
    async with session() as running:
        await running.bot.worker.queue_frame(InterruptionFrame())

        await wait_until(lambda: len(interrupted) == 1, 'the interruption')

    assert problems == []


async def run_bot(bot: Bot) -> None:
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(bot.worker)
    await asyncio.wait_for(runner.run(), seconds(10))


@pytest.mark.asyncio
async def test_a_client_gone_before_the_transport_ends_the_bot(problems: list[str]) -> None:
    connection = SmallWebRTCConnection()
    client = BrowserClient()
    try:
        await connect_client(connection, client)
        client.close()
        await wait_until(lambda: connection.pc.connection_state == 'closed', 'the client to leave')

        bot = Bot(connection, default_params())
        await run_bot(bot)

        assert bot.disconnected == [connection]
        assert bot.connected == []
    finally:
        client.close()
        await connection.disconnect()
    await tasks_ended()

    assert problems == []


@pytest.mark.asyncio
async def test_a_client_leaving_while_the_bot_connects_only_disconnects(
    problems: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    params = TransportParams(audio_in_enabled=True, audio_out_enabled=True, video_out_enabled=True)
    media = Media()
    client = await start_client(media)
    connection = SmallWebRTCConnection()
    bot = Bot(connection, params)
    replace_audio_track = connection.replace_audio_track

    async def leave_after(track: webrtc.MediaStreamTrack | None) -> None:
        # the client leaves between the bot's audio and video
        await replace_audio_track(track)
        client.close()
        await wait_until(lambda: connection.pc.connection_state == 'closed', 'the client to leave')

    monkeypatch.setattr(connection, 'replace_audio_track', leave_after)
    try:
        offer = await client.offer()
        await connection.initialize(sdp=offer['sdp'], type=offer['type'])
        await client.accept(connection.get_answer())
        await add_candidates(connection, client)
        await run_bot(bot)

        assert bot.disconnected == [connection]
        assert bot.connected == []
    finally:
        await media.stop()
        client.close()
        await connection.disconnect()
    await tasks_ended()

    assert problems == []
