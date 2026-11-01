#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The transport of a pipeline over the peer connection to one client.

See https://wrtc.marshal.dev/guides/pipecat/.
"""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from loguru import logger
from pipecat.frames.frames import (
    ClientConnectedFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    UserImageRawFrame,
    UserImageRequestFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport

# private, pinned by the names test: the sampling stays the same as other transports'
from pipecat.transports.video_in_sampler import (
    _capture_framerate,  # ruff: ignore[import-private-name]
    _VideoInSamplers,  # ruff: ignore[import-private-name]
)
from pipecat.utils.shared import acquires, releases

import webrtc
from webrtc.pipecat._media import AudioPacer, AudioReader, VideoWriter, read_track, video_image
from webrtc.pipecat.connection import (
    AUDIO_TRANSCEIVER_INDEX,
    SCREEN_VIDEO_TRANSCEIVER_INDEX,
    VIDEO_TRANSCEIVER_INDEX,
    SmallWebRTCConnection,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pipecat.frames.frames import (
        CancelFrame,
        EndFrame,
        Frame,
        InputAudioRawFrame,
        OutputAudioRawFrame,
        OutputImageRawFrame,
        OutputTransportMessageFrame,
        OutputTransportMessageUrgentFrame,
        SpriteFrame,
        StartFrame,
    )
    from pipecat.processors.frame_processor import FrameProcessorSetup
    from pipecat.transports.base_transport import TransportParams

CAM_VIDEO_SOURCE = 'camera'
SCREEN_VIDEO_SOURCE = 'screenVideo'
MIC_AUDIO_SOURCE = 'microphone'

# the samplers are keyed by participant, and there's one
_PEER_ID = 'peer'
_SOURCES_BY_RECEIVER = {
    AUDIO_TRANSCEIVER_INDEX: MIC_AUDIO_SOURCE,
    VIDEO_TRANSCEIVER_INDEX: CAM_VIDEO_SOURCE,
    SCREEN_VIDEO_TRANSCEIVER_INDEX: SCREEN_VIDEO_SOURCE,
}
_VIDEO_SOURCES = (CAM_VIDEO_SOURCE, SCREEN_VIDEO_SOURCE)


@dataclass
class _Callbacks:
    on_client_connected: Callable[[SmallWebRTCConnection], Awaitable[None]]
    on_client_disconnected: Callable[[SmallWebRTCConnection], Awaitable[None]]
    on_app_message: Callable[[object, str], Awaitable[None]]
    on_track_status: Callable[[str, bool], Awaitable[None]]


class _Client:
    """The client behind a connection, shared by the input and the output."""

    def __init__(self, connection: SmallWebRTCConnection, callbacks: _Callbacks) -> None:
        self.connection = connection
        self._callbacks = callbacks
        self._params: TransportParams | None = None
        self.audio_in_sample_rate = 0
        self.audio_out_sample_rate = 0

        # a restart replaces it, and the tracks with it
        self._pc: webrtc.RTCPeerConnection | None = None
        self._closing = False
        self._tracks: dict[str, webrtc.MediaStreamTrack | None] = dict.fromkeys(_SOURCES_BY_RECEIVER.values())
        self._enabled = dict.fromkeys(_SOURCES_BY_RECEIVER.values(), True)
        self._tracks_changed = asyncio.Event()
        self._audio_out: AudioPacer | None = None
        self._video_out: VideoWriter | None = None
        # app messages wait for on_client_connected
        self._connecting = asyncio.Lock()
        # closed fired before this was made, so the bot learns it once it connects
        self._left_before = connection.closed

        connection.add_event_handler('connected', self._on_connected)
        connection.add_event_handler('closed', self._on_closed)
        connection.add_event_handler('track-started', self._on_track_started)
        connection.add_event_handler('track-status', self._on_track_status)
        connection.add_event_handler('app-message', self._on_app_message)

    async def setup(self, params: TransportParams, setup: FrameProcessorSetup) -> None:
        self._params = params
        self.audio_in_sample_rate = params.audio_in_sample_rate or setup.audio_in_sample_rate
        self.audio_out_sample_rate = params.audio_out_sample_rate or setup.audio_out_sample_rate

    # both the input and the output call these; the first connects, the last disconnects
    @acquires('connection')
    async def connect(self) -> None:
        logger.info('Connecting to the client of {}', self.connection.pc_id)
        await self.connection.connect()
        if self._left_before:
            self._left_before = False
            await self._on_closed(self.connection)

    @releases('connection')
    async def disconnect(self) -> None:
        if not self._closing:
            logger.info('Disconnecting from the client of {}', self.connection.pc_id)
            self._closing = True
            await self.connection.disconnect()
        await self._close_outputs()

    def can_send(self) -> bool:
        return self.connection.is_connected() and not self._closing

    def is_enabled(self, source: str) -> bool:
        """Whether the client offered a source and hasn't turned it off."""
        return self._tracks[source] is not None and self._enabled[source]

    async def live_track(self, source: str, *, ended: webrtc.MediaStreamTrack | None = None) -> webrtc.MediaStreamTrack:
        """Waits for a live track of a source other than ``ended``, whose state may not say ended yet."""
        while True:
            changed = self._tracks_changed
            track = self._tracks[source]
            if track is not None and track is not ended and track.ready_state == webrtc.MediaStreamTrackState.live:
                return track
            _ = await changed.wait()

    async def write_audio(self, frame: OutputAudioRawFrame) -> bool:
        pacer = self._audio_out
        if pacer is None or not self.can_send():
            return False
        return await pacer.write(frame.audio, frame.num_channels)

    def interrupt_audio(self) -> None:
        if self._audio_out is not None:
            self._audio_out.interrupt()

    async def write_video(self, frame: OutputImageRawFrame) -> bool:
        writer = self._video_out
        if writer is None or not self.can_send():
            return False
        return await writer.write(frame)

    def send_message(self, frame: OutputTransportMessageFrame | OutputTransportMessageUrgentFrame) -> None:
        if self._closing:
            logger.debug('Disconnecting, dropping a message to the client: {}', frame.message)
            return
        self.connection.send_app_message(frame.message)

    async def _on_connected(self, connection: SmallWebRTCConnection) -> None:
        pc = connection.pc
        # the same peer connection recovered, and the client stayed
        if self._params is None or self._closing or pc is self._pc:
            return

        async with self._connecting:
            logger.debug('The client of {} connected', connection.pc_id)
            self._pc = pc
            # the client announces the new connection's tracks again
            self._enabled = dict.fromkeys(self._enabled, True)
            self._take_tracks(self._params)
            await self._send_outputs(self._params)
            # the client may have left, or the bot disconnected, meanwhile
            if self._pc is pc and not self._closing and not connection.closed:
                await self._callbacks.on_client_connected(connection)

    async def _on_track_started(self, connection: SmallWebRTCConnection, _track: webrtc.MediaStreamTrack) -> None:
        # a renegotiation that added a source
        if self._params is not None and connection.pc is self._pc and not self._closing:
            self._take_tracks(self._params)

    async def _on_closed(self, connection: SmallWebRTCConnection) -> None:
        logger.debug('The connection {} closed', connection.pc_id)
        self._pc = None
        self._set_tracks(dict.fromkeys(self._tracks))
        await self._close_outputs()
        if not self._closing:
            await self._callbacks.on_client_disconnected(connection)

    async def _on_track_status(self, _connection: SmallWebRTCConnection, receiver_index: int, enabled: bool) -> None:
        source = _SOURCES_BY_RECEIVER.get(receiver_index)
        if source is None:
            return
        self._enabled[source] = enabled
        await self._callbacks.on_track_status(source, enabled)

    async def _on_app_message(self, connection: SmallWebRTCConnection, message: object) -> None:
        async with self._connecting:
            await self._callbacks.on_app_message(message, connection.pc_id)

    def _take_tracks(self, params: TransportParams) -> None:
        """Takes the current peer connection's tracks of the sources the bot reads."""
        tracks: dict[str, webrtc.MediaStreamTrack | None] = dict.fromkeys(self._tracks)
        if params.audio_in_enabled:
            tracks[MIC_AUDIO_SOURCE] = self.connection.audio_input_track()
        if params.video_in_enabled:
            tracks[CAM_VIDEO_SOURCE] = self.connection.video_input_track()
            tracks[SCREEN_VIDEO_SOURCE] = self.connection.screen_video_input_track()
        self._set_tracks(tracks)

    def _set_tracks(self, tracks: dict[str, webrtc.MediaStreamTrack | None]) -> None:
        self._tracks = tracks
        changed, self._tracks_changed = self._tracks_changed, asyncio.Event()
        changed.set()

    async def _send_outputs(self, params: TransportParams) -> None:
        """Sends the bot's audio and video on the current peer connection."""
        # created before the first wait, so a close during it closes both
        if params.audio_out_enabled and self._audio_out is None:
            self._audio_out = AudioPacer(self.audio_out_sample_rate, auto_silence=params.audio_out_auto_silence)
        if params.video_out_enabled and self._video_out is None:
            self._video_out = VideoWriter()

        audio_out, video_out = self._audio_out, self._video_out
        if audio_out is not None:
            await self.connection.replace_audio_track(audio_out.track)
        if video_out is not None:
            await self.connection.replace_video_track(video_out.track)

    async def _close_outputs(self) -> None:
        audio_out, self._audio_out = self._audio_out, None
        video_out, self._video_out = self._video_out, None
        if audio_out is not None:
            await audio_out.close()
        if video_out is not None:
            video_out.close()


class SmallWebRTCInputTransport(BaseInputTransport):
    """The client's microphone, camera, screen share and app messages; video is read only while captured.

    Args:
        client: Shared with the output.
        params: The transport's parameters.
        **kwargs: Passed to the base class, like ``name``.
    """

    def __init__(self, client: _Client, params: TransportParams, **kwargs: object) -> None:
        super().__init__(params, **kwargs)
        self._client = client
        self._params = params
        self._receive_audio_task: asyncio.Task[None] | None = None
        self._receive_video_tasks: dict[str, asyncio.Task[None]] = {}
        self._video_samplers = _VideoInSamplers()

    def _supports_video_in_source(self, video_source: str) -> bool:  # ruff: ignore[no-self-use]
        return video_source in _VIDEO_SOURCES

    async def setup(self, setup: FrameProcessorSetup) -> None:
        """Connects to the client.

        Args:
            setup: The pipeline's setup.
        """
        await super().setup(setup)
        await self._client.setup(self._params, setup)
        await self._client.connect()

    async def cleanup(self) -> None:
        """Stops reading and disconnects, if it hasn't yet."""
        await super().cleanup()
        await self._teardown()

    async def start(self, frame: StartFrame) -> None:
        """Starts reading the microphone.

        Args:
            frame: The start frame.
        """
        await super().start(frame)
        if self._params.audio_in_enabled:
            self._start_audio()
        await self.set_transport_ready(frame)

    async def stop(self, frame: EndFrame) -> None:
        """Stops reading and disconnects.

        Args:
            frame: The end frame.
        """
        await super().stop(frame)
        await self._teardown()

    async def cancel(self, frame: CancelFrame) -> None:
        """Stops reading and disconnects right away.

        Args:
            frame: The cancel frame.
        """
        await super().cancel(frame)
        await self._teardown()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Processes a frame, answering image requests.

        Args:
            frame: The frame.
            direction: Its direction.
        """
        await super().process_frame(frame, direction)
        if isinstance(frame, UserImageRequestFrame):
            await self.request_participant_image(frame)

    async def push_app_message(self, message: object) -> None:
        """Pushes a client message into the pipeline, both ways.

        Args:
            message: The message.
        """
        logger.trace('An app message of the client: {}', message)
        await self.broadcast_frame(InputTransportMessageFrame, message=message)

    async def request_participant_image(self, frame: UserImageRequestFrame) -> None:
        """Answers an image request with the next frame of its source, the camera by default.

        Args:
            frame: The request.
        """
        logger.debug('An image of the client is requested by {}', frame.user_id)
        if frame.video_source is None:
            frame.video_source = CAM_VIDEO_SOURCE

        if not self._client.is_enabled(frame.video_source):
            await self._answer_image_requests([frame], f"The client isn't sending {frame.video_source} video.")
            return

        if not self._video_samplers.is_capturing(_PEER_ID, frame.video_source):
            self._video_samplers.capture(_PEER_ID, frame.video_source, None)
        _ = self._video_samplers.add_request(_PEER_ID, frame.video_source, frame)
        self._start_video(frame.video_source)

    async def capture_participant_media(self, source: str = CAM_VIDEO_SOURCE, framerate: int | None = None) -> None:
        """Captures a source of the client.

        Args:
            source: ``'camera'``, ``'screenVideo'`` or ``'microphone'``.
            framerate: For video: ``0`` only answers image requests, :obj:`None` passes on every frame.
        """
        if source == MIC_AUDIO_SOURCE:
            if self._params.audio_in_enabled:
                self._start_audio()
            return
        if source in _VIDEO_SOURCES:
            self._video_samplers.capture(_PEER_ID, source, framerate)
            self._start_video(source)

    async def stop_video(self, video_source: str) -> None:
        """Answers the image requests waiting on a source the client turned off.

        Args:
            video_source: ``'camera'`` or ``'screenVideo'``.
        """
        requests = self._video_samplers.take_requests(_PEER_ID, video_source)
        await self._answer_image_requests(requests, f'The client turned off its {video_source} video.')

    async def remove_all_video(self) -> None:
        """Stops capturing video, answering the image requests waiting on it."""
        await self._stop_video_tasks()
        requests = self._video_samplers.clear()
        await self._answer_image_requests(requests, 'The client disconnected.')

    def _start_audio(self) -> None:
        if self._receive_audio_task is None:
            self._receive_audio_task = self.create_task(self._receive_audio())

    def _start_video(self, source: str) -> None:
        if self._params.video_in_enabled and source not in self._receive_video_tasks:
            task: asyncio.Task[None] = self.create_task(self._receive_video(source), f'receive_{source}')
            self._receive_video_tasks[source] = task

    async def _receive_audio(self) -> None:
        reader = AudioReader(self._client.audio_in_sample_rate, self._params.audio_in_channels)
        push = cast('Callable[[InputAudioRawFrame], Awaitable[None]]', self.push_audio_frame)
        track: webrtc.MediaStreamTrack | None = None
        try:
            while True:
                # a restart brings a new track
                track = await self._client.live_track(MIC_AUDIO_SOURCE, ended=track)
                await reader.read(track, push)
        except Exception:  # ruff: ignore[blind-except]
            logger.exception('{} stopped reading the audio of the client', self)

    async def _receive_video(self, source: str) -> None:
        handle = functools.partial(self._handle_video_frame, source)
        track: webrtc.MediaStreamTrack | None = None
        try:
            while True:
                track = await self._client.live_track(source, ended=track)
                await read_track(track, handle, max_buffer_size=1)
        except Exception:  # ruff: ignore[blind-except]
            logger.exception('{} stopped reading the {} video of the client', self, source)

    async def _handle_video_frame(self, source: str, frame: webrtc.AudioData | webrtc.VideoFrame) -> None:
        if not isinstance(frame, webrtc.VideoFrame) or not self._client.is_enabled(source):
            return
        due, request = self._video_samplers.sample(_PEER_ID, source)
        if not due:
            return

        image = video_image(frame)
        image_frame = UserImageRawFrame(
            user_id=self._client.connection.pc_id, image=image.pixels, size=image.size, format='RGB'
        )
        image_frame.transport_source = source
        if request is not None:
            image_frame.text = request.text
            image_frame.append_to_context = request.append_to_context
            image_frame.request = request
        await self.push_video_frame(image_frame)

    async def _stop_video_tasks(self) -> None:
        tasks = list(self._receive_video_tasks.values())
        self._receive_video_tasks.clear()
        for task in tasks:
            await self.cancel_task(task)

    async def _teardown(self) -> None:
        """Stops reading and releases the client."""
        if self._receive_audio_task is not None:
            await self.cancel_task(self._receive_audio_task)
            self._receive_audio_task = None
        await self._stop_video_tasks()
        await self._client.disconnect()


class SmallWebRTCOutputTransport(BaseOutputTransport):
    """The bot's audio, video and app messages; writing audio takes as long as playing it.

    Args:
        client: Shared with the input.
        params: The transport's parameters.
        **kwargs: Passed to the base class, like ``name``.
    """

    def __init__(self, client: _Client, params: TransportParams, **kwargs: object) -> None:
        super().__init__(params, **kwargs)
        self._client = client
        self._params = params

    async def setup(self, setup: FrameProcessorSetup) -> None:
        """Connects to the client.

        Args:
            setup: The pipeline's setup.
        """
        await super().setup(setup)
        await self._client.setup(self._params, setup)
        await self._client.connect()

    async def cleanup(self) -> None:
        """Disconnects, if it hasn't yet."""
        await super().cleanup()
        await self._client.disconnect()

    async def start(self, frame: StartFrame) -> None:
        """Starts the output.

        Args:
            frame: The start frame.
        """
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def stop(self, frame: EndFrame) -> None:
        """Sends what's left and disconnects.

        Args:
            frame: The end frame.
        """
        await super().stop(frame)
        await self._client.disconnect()

    async def cancel(self, frame: CancelFrame) -> None:
        """Disconnects right away.

        Args:
            frame: The cancel frame.
        """
        await super().cancel(frame)
        await self._client.disconnect()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Processes a frame; an interruption also stops audio catching up on a stall.

        Args:
            frame: The frame.
            direction: Its direction.
        """
        if isinstance(frame, InterruptionFrame):
            self._client.interrupt_audio()
        await super().process_frame(frame, direction)

    async def send_message(self, frame: OutputTransportMessageFrame | OutputTransportMessageUrgentFrame) -> None:
        """Sends a message over the data channel, held until it opens.

        Args:
            frame: The message.
        """
        self._client.send_message(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        """Sends audio, returning once it's sent.

        Args:
            frame: The audio, at the output's rate.

        Returns:
            Whether it was sent: not while the client isn't connected.
        """
        return await self._client.write_audio(frame)

    async def write_video_frame(self, frame: OutputImageRawFrame) -> bool:
        """Sends an image.

        Args:
            frame: The image, ``RGB`` or ``RGBA``.

        Returns:
            Whether it was sent: not while the client isn't connected, or for another format.
        """
        return await self._client.write_video(frame)


class SmallWebRTCTransport(BaseTransport):
    """A transport over the peer connection to one client, for its audio, video and app messages.

    Events: ``on_client_connected(transport, connection)``, again after a restart;
    ``on_client_disconnected(transport, connection)``, when the client leaves, not the bot;
    ``on_app_message(transport, message, sender)``, where ``sender`` is the ``pc_id``.

    Args:
        webrtc_connection: The connection to the client.
        params: The transport's parameters.
        input_name: The input processor's name.
        output_name: The output processor's name.

    Example::

        transport = SmallWebRTCTransport(webrtc_connection=connection, params=TransportParams(audio_in_enabled=True))


        @transport.event_handler('on_client_connected')
        async def on_client_connected(transport, connection): ...
    """

    def __init__(
        self,
        webrtc_connection: SmallWebRTCConnection,
        params: TransportParams,
        input_name: str | None = None,
        output_name: str | None = None,
    ) -> None:
        super().__init__(input_name=input_name, output_name=output_name)
        self._params = params
        callbacks = _Callbacks(
            on_client_connected=self._on_client_connected,
            on_client_disconnected=self._on_client_disconnected,
            on_app_message=self._on_app_message,
            on_track_status=self._on_track_status,
        )
        self._client = _Client(webrtc_connection, callbacks)
        self._input: SmallWebRTCInputTransport | None = None
        self._output: SmallWebRTCOutputTransport | None = None

        self._register_event_handler('on_app_message')
        self._register_event_handler('on_client_connected')
        self._register_event_handler('on_client_disconnected')

    def get_client_id(self, client: SmallWebRTCConnection) -> str:  # ruff: ignore[no-self-use]
        """The id of a client: its ``pc_id``.

        Args:
            client: The connection to the client.

        Returns:
            The id.
        """
        return client.pc_id

    def input(self) -> SmallWebRTCInputTransport:
        """The input processor, created on the first call.

        Returns:
            The input.
        """
        if self._input is None:
            self._input = SmallWebRTCInputTransport(
                self._client, self._params, name=cast('str | None', self._input_name)
            )
        return self._input

    def output(self) -> SmallWebRTCOutputTransport:
        """The output processor, created on the first call.

        Returns:
            The output.
        """
        if self._output is None:
            self._output = SmallWebRTCOutputTransport(
                self._client, self._params, name=cast('str | None', self._output_name)
            )
        return self._output

    async def send_image(self, frame: OutputImageRawFrame | SpriteFrame) -> None:
        """Queues an image to the output.

        Args:
            frame: The image.
        """
        if self._output is not None:
            await self._output.queue_frame(frame, FrameDirection.DOWNSTREAM)

    async def send_audio(self, frame: OutputAudioRawFrame) -> None:
        """Queues audio to the output.

        Args:
            frame: The audio.
        """
        if self._output is not None:
            await self._output.queue_frame(frame, FrameDirection.DOWNSTREAM)

    async def capture_participant_video(
        self,
        participant_id: str,  # ruff: ignore[unused-method-argument]
        framerate: int | None = 30,
        video_source: str = CAM_VIDEO_SOURCE,
        *,
        on_request_only: bool = False,
    ) -> None:
        """Captures the client's camera or screen share, overriding ``video_in_sources`` for it.

        Args:
            participant_id: Unused: there's one client.
            framerate: Frames per second, or :obj:`None` for every frame.
            video_source: ``'camera'`` or ``'screenVideo'``.
            on_request_only: Whether to pass on only the frames that answer image requests.
        """
        rate = _capture_framerate(framerate, on_request_only, 'SmallWebRTCTransport.capture_participant_video')
        if self._input is not None:
            await self._input.capture_participant_media(source=video_source, framerate=rate)

    async def capture_participant_audio(self, audio_source: str = MIC_AUDIO_SOURCE) -> None:
        """Captures the client's microphone, if the input doesn't read it yet.

        Args:
            audio_source: ``'microphone'``.
        """
        if self._input is not None:
            await self._input.capture_participant_media(source=audio_source)

    async def _on_app_message(self, message: object, sender: str) -> None:
        if self._input is not None:
            await self._input.push_app_message(message)
        await self._call_event_handler('on_app_message', message, sender)

    async def _on_client_connected(self, connection: SmallWebRTCConnection) -> None:
        # before the handlers, so a handler capturing a source itself wins
        if self._input is not None:
            for video_source, source_params in self._params.video_in_sources.items():
                if self._input._supports_video_in_source(video_source):
                    framerate = 0 if source_params.on_request_only else source_params.framerate
                    await self._input.capture_participant_media(source=video_source, framerate=framerate)

        await self._call_event_handler('on_client_connected', connection)
        if self._input is not None:
            await self._input.push_frame(ClientConnectedFrame())

    async def _on_client_disconnected(self, connection: SmallWebRTCConnection) -> None:
        if self._input is not None:
            await self._input.remove_all_video()
        await self._call_event_handler('on_client_disconnected', connection)

    async def _on_track_status(self, source: str, enabled: bool) -> None:
        if self._input is not None and source != MIC_AUDIO_SOURCE and not enabled:
            await self._input.stop_video(source)
