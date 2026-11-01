#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["wrtc[pipecat]>=0.2.0", "pipecat-ai[runner,webrtc,deepgram,openai,cartesia,silero]>=1.15,<2"]
# ///
#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""A Pipecat voice bot on Python WebRTC, served by Pipecat's development runner.

    export DEEPGRAM_API_KEY=... OPENAI_API_KEY=... CARTESIA_API_KEY=...
    uv run pipecat_bot.py
    uv run pipecat_bot.py --echo

Open http://localhost:7860 and press Connect. With the three keys, the bot listens with Deepgram, answers with OpenAI
and speaks with Cartesia, and stops talking when you talk over it. With --echo, or without the keys, it sends your
voice back. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import Frame, InputAudioRawFrame, LLMRunFrame, OutputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.workers.runner import WorkerRunner

import webrtc.pipecat

if TYPE_CHECKING:
    from pipecat.runner.types import SmallWebRTCRunnerArguments

KEYS = ('DEEPGRAM_API_KEY', 'OPENAI_API_KEY', 'CARTESIA_API_KEY')
INSTRUCTIONS = (
    'You are a helpful assistant in a voice conversation. Your answers are spoken aloud, so use no emojis, lists or '
    'other formatting. Answer briefly.'
)
VOICE = '86e30c1d-714b-4074-a1f2-1cb6b552fb49'  # a voice of Cartesia's library


class Echo(FrameProcessor):
    """Sends the user's audio back as the bot's."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Echoes audio frames and passes the rest on."""
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame):
            await self.push_frame(OutputAudioRawFrame(frame.audio, frame.sample_rate, frame.num_channels))
        else:
            await self.push_frame(frame, direction)


def echo_pipeline(transport: webrtc.pipecat.SmallWebRTCTransport) -> Pipeline:
    """The pipeline that sends the client's microphone back to its speakers."""
    return Pipeline([transport.input(), Echo(), transport.output()])


class VoiceBot:
    """Speech to text, the model, and text to speech; the user's speech interrupts the bot."""

    def __init__(self) -> None:
        self.context = LLMContext()
        self.stt = DeepgramSTTService(api_key=os.environ['DEEPGRAM_API_KEY'])
        self.llm = OpenAILLMService(
            api_key=os.environ['OPENAI_API_KEY'], settings=OpenAILLMService.Settings(system_instruction=INSTRUCTIONS)
        )
        self.tts = CartesiaTTSService(
            api_key=os.environ['CARTESIA_API_KEY'], settings=CartesiaTTSService.Settings(voice=VOICE)
        )

    def pipeline(self, transport: webrtc.pipecat.SmallWebRTCTransport) -> Pipeline:
        """The pipeline between the client's microphone and its speakers."""
        user, assistant = LLMContextAggregatorPair(
            self.context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
        )
        return Pipeline([transport.input(), self.stt, user, self.llm, self.tts, transport.output(), assistant])

    async def greet(self, worker: PipelineWorker) -> None:
        """Asks the model to start the conversation."""
        self.context.add_message({'role': 'developer', 'content': 'Introduce yourself to the user.'})
        await worker.queue_frames([LLMRunFrame()])


def voice_bot(args: argparse.Namespace) -> VoiceBot | None:
    """The voice bot, or :obj:`None` to echo: with ``--echo``, or when a key is missing."""
    if args.echo:
        return None

    missing = [key for key in KEYS if key not in os.environ]
    if len(missing) > 0:
        logger.warning(f'{", ".join(missing)} not set: echoing your voice back')
        return None

    return VoiceBot()


async def bot(runner_args: SmallWebRTCRunnerArguments) -> None:
    """Runs a pipeline for one client until it leaves; the runner calls it for each new connection."""
    transport = webrtc.pipecat.SmallWebRTCTransport(
        webrtc_connection=runner_args.webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )

    voice = voice_bot(runner_args.cli_args)
    pipeline = echo_pipeline(transport) if voice is None else voice.pipeline(transport)

    worker = PipelineWorker(pipeline, params=PipelineParams(), idle_timeout_secs=runner_args.pipeline_idle_timeout_secs)
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    async def on_client_connected(_transport: object, _connection: object) -> None:
        logger.info('Client connected')
        if voice is not None:
            await voice.greet(worker)

    async def on_client_disconnected(_transport: object, _connection: object) -> None:
        logger.info('Client disconnected')
        await runner.cancel()

    transport.add_event_handler('on_client_connected', on_client_connected)
    transport.add_event_handler('on_client_disconnected', on_client_disconnected)
    await runner.run()


def main() -> None:
    """Serves the runner's page and its routes, and starts :func:`bot` for each client that connects."""
    # before the runner's import, which pulls in Pipecat's own transport
    webrtc.pipecat.install_alias()
    from pipecat.runner.run import main as run  # ruff: ignore[import-outside-top-level]

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--echo', action='store_true', help='send your voice back, with no keys needed')
    run(parser)


if __name__ == '__main__':
    main()
