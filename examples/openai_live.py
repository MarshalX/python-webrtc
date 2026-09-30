#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["wrtc>=0.0.0.dev10", "sounddevice", "httpx"]
# ///
#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""Talk to OpenAI GPT-Live from the terminal: your microphone goes to the model, its voice to your speakers.

No server needed: the script posts its SDP offer to the OpenAI API with your key, as the guide
https://developers.openai.com/api/docs/guides/voice-webrtc?api=live describes for a backend.

    export OPENAI_API_KEY=sk-...
    uv run openai_live.py
    uv run openai_live.py --voice gleam --instructions "You are a pirate. Keep answers short."
    uv run openai_live.py --list-devices

uv installs the dependencies declared above. Without a download, straight from GitHub:

    uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/openai_live.py

Or with pip: pip install wrtc sounddevice httpx, then python openai_live.py.

Press Ctrl+C to hang up. Without headphones the microphone is muted while the assistant speaks, so it doesn't
hear itself; with headphones pass --barge-in to be able to interrupt it.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import signal
import sys
import threading
import time
from array import array
from typing import Any, ClassVar

import httpx
import sounddevice

import webrtc

API_URL = 'https://api.openai.com/v1/live/sessions'
SAMPLE_RATE = 48000
FRAME = SAMPLE_RATE // 100  # 10 ms of samples, as WebRTC sends them
VOICE_LEVEL = 0.02  # the peak level above which audio counts as speech
ECHO_TAIL = 0.6  # seconds the microphone stays muted after the assistant stops
MAX_PLAYBACK = 0.5  # seconds of assistant audio buffered before the oldest is dropped
SILENT_MIC_WARNING = 10  # seconds of silence before the microphone is suspected


class Console:
    """Human-readable output: timestamped status lines and live transcripts that share the terminal."""

    COLORS: ClassVar[dict[str, str]] = {
        'dim': '2',
        'red': '31',
        'green': '32',
        'yellow': '33',
        'blue': '34',
        'magenta': '35',
        'cyan': '36',
    }

    def __init__(self, *, verbose: bool) -> None:
        self.verbose = verbose
        self.color = sys.stdout.isatty() and not os.environ.get('NO_COLOR')
        self.speaker: str | None = None  # who the open transcript line belongs to

    def paint(self, text: str, color: str) -> str:
        """The text in a color, if the terminal shows colors."""
        return f'\033[{self.COLORS[color]}m{text}\033[0m' if self.color else text

    def _end_transcript(self) -> None:
        if self.speaker:
            print(flush=True)
            self.speaker = None

    def log(self, icon: str, text: str, color: str | None = None) -> None:
        """Prints a timestamped status line."""
        self._end_transcript()
        line = f'{self.paint(time.strftime("%H:%M:%S"), "dim")}  {icon}  {text}'
        print(self.paint(line, color) if color else line, flush=True)

    def info(self, text: str) -> None:
        """Prints a status line."""
        self.log('•', text)

    def ok(self, text: str) -> None:
        """Prints a line of a success."""
        self.log('✓', text, 'green')

    def warn(self, text: str) -> None:
        """Prints a line of a problem."""
        self.log('!', text, 'yellow')

    def error(self, text: str) -> None:
        """Prints a line of a failure."""
        self.log('✗', text, 'red')

    def debug(self, text: str) -> None:
        """Prints a line in verbose mode only."""
        if self.verbose:
            self.log('·', text, 'dim')

    def transcript(self, speaker: str, delta: str) -> None:
        """Appends a fragment to the speaker's line; fragments have no end marker, so a new speaker starts a line."""
        if speaker != self.speaker:
            self._end_transcript()
            label, color = ('You', 'cyan') if speaker == 'user' else ('Assistant', 'magenta')
            print(self.paint(f'\n{label}: ', color), end='')
            self.speaker = speaker
        print(delta, end='', flush=True)


def peak(samples: bytes) -> float:
    """The peak level of 16-bit samples, from 0 to 1."""
    values = array('h', samples)
    return max(*values, -min(values)) / 32768 if values else 0


class Microphone:
    """Captures 10 ms chunks of 16-bit mono audio from a device into an asyncio queue."""

    def __init__(self, device: str | int | None, loop: asyncio.AbstractEventLoop) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self._loop = loop
        self._stream = sounddevice.RawInputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=FRAME, device=device, callback=self._on_audio
        )
        self.name = sounddevice.query_devices(self._stream.device)['name']

    def _on_audio(self, data: memoryview, *_: object) -> None:
        self._loop.call_soon_threadsafe(self._put, bytes(data))

    def _put(self, chunk: bytes) -> None:
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(chunk)

    def start(self) -> None:
        """Starts capturing."""
        self._stream.start()

    def close(self) -> None:
        """Stops capturing and releases the device."""
        self._stream.stop()
        self._stream.close()


class Speakers:
    """Plays 16-bit audio on a device from a small buffer, opened on the first chunk to match its format."""

    def __init__(self, device: str | int | None) -> None:
        self.device = device
        self.name = sounddevice.query_devices(device, 'output')['name']
        self._stream: sounddevice.RawOutputStream | None = None
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._limit = 0

    def play(self, samples: bytes, sample_rate: int, channels: int) -> None:
        """Queues samples, opening the device on the first ones."""
        if self._stream is None:
            self._limit = int(sample_rate * MAX_PLAYBACK) * channels * 2
            self._stream = sounddevice.RawOutputStream(
                samplerate=sample_rate, channels=channels, dtype='int16', device=self.device, callback=self._on_need
            )
            self._stream.start()
        with self._lock:
            self._buffer += samples
            if len(self._buffer) > self._limit:
                del self._buffer[: len(self._buffer) - self._limit]

    def _on_need(self, out: memoryview, *_: object) -> None:
        size = len(out)
        with self._lock:
            chunk = self._buffer[:size]
            del self._buffer[:size]
        out[: len(chunk)] = chunk
        out[len(chunk) :] = bytes(size - len(chunk))

    def close(self) -> None:
        """Releases the device."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()


class LiveCall:
    """A call with the model: the microphone and the speakers, the connection and its event channel."""

    def __init__(self, args: argparse.Namespace, console: Console) -> None:
        self.args = args
        self.console = console
        self.pc: webrtc.RTCPeerConnection | None = None
        self.events: webrtc.RTCDataChannel | None = None
        self.microphone: Microphone | None = None
        self.speakers: Speakers | None = None
        self.tasks: list[asyncio.Future[None]] = []
        self.session_closed = asyncio.Event()
        self.assistant_spoke_at = 0.0  # when the assistant's audio was last above the speech level

    async def run(self, hang_up: asyncio.Event) -> None:
        """Connects, then talks until hung up."""
        console, args = self.console, self.args
        loop = asyncio.get_running_loop()

        self.microphone = Microphone(args.input_device, loop)
        self.speakers = Speakers(args.output_device)
        console.info(f'Microphone: {self.microphone.name}')
        console.info(f'Speakers:   {self.speakers.name}')
        if not args.barge_in:
            console.info('Echo guard on: the mic is muted while the assistant speaks (--barge-in turns it off)')

        self.pc = webrtc.RTCPeerConnection()
        self.pc.on('connectionstatechange', self._on_connection_state)
        self.pc.on('track', self._on_track)

        generator = webrtc.MediaStreamTrackGenerator('audio')
        self.pc.add_track(generator)
        # created before the offer, so the offer negotiates it
        self.events = self.pc.create_data_channel('oai-events')
        self.events.on('open', lambda _event: console.ok('Event channel open'))
        self.events.on('message', self._on_message)

        offer = await self.pc.create_offer()
        await self.pc.set_local_description(offer)
        await self._gathered()

        console.info(f'Creating a {args.model} session...')
        answer = await self._create_session(self.pc.local_description.sdp)
        await self.pc.set_remote_description({'type': 'answer', 'sdp': answer})

        self.microphone.start()
        self.tasks.append(asyncio.ensure_future(self._send_microphone(generator.writable.get_writer())))
        await hang_up.wait()
        await self.close()

    async def _gathered(self) -> None:
        """Waits for the local ICE candidates, which go in the offer since there is no trickling."""
        done = asyncio.Event()
        self.pc.on('icegatheringstatechange', lambda _event: self.pc.ice_gathering_state == 'complete' and done.set())
        if self.pc.ice_gathering_state != 'complete':
            try:
                await asyncio.wait_for(done.wait(), 5)
            except asyncio.TimeoutError:
                self.console.warn('ICE gathering is slow, sending the candidates found so far')

    async def _create_session(self, sdp: str) -> str:
        session: dict[str, object] = {'model': self.args.model}
        if self.args.instructions:
            session['instructions'] = self.args.instructions
        if self.args.voice:
            session['audio'] = {'output': {'voice': self.args.voice}}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    API_URL,
                    headers={'Authorization': f'Bearer {self.args.api_key}'},
                    json={'session': session, 'transport': {'type': 'webrtc', 'sdp': sdp}},
                )
        except httpx.HTTPError as e:
            msg = f'Could not reach the OpenAI API: {e or type(e).__name__}'
            raise CallError(msg) from None
        if response.is_error:
            raise CallError(_describe_http_error(response))
        reply: dict[str, Any] = response.json()
        self.console.ok(f'Session created: {reply.get("session", {}).get("id", "?")}')
        return reply['transport']['sdp']

    def _on_connection_state(self, _event: webrtc.Event) -> None:
        state = self.pc.connection_state
        messages = {
            'connecting': ('info', 'Connecting audio...'),
            'connected': ('ok', 'Audio connected'),
            'disconnected': ('warn', 'Connection interrupted, waiting for it to recover...'),
            'failed': ('error', 'Connection failed (a firewall may block UDP)'),
        }
        if state in messages:
            level, text = messages[state]
            getattr(self.console, level)(text)

    def _on_track(self, event: webrtc.RTCTrackEvent) -> None:
        self.console.debug(f"Receiving the assistant's {event.track.kind} track")
        self.tasks.append(asyncio.ensure_future(self._play(event.track)))

    async def _send_microphone(self, writer: webrtc.WritableStreamDefaultWriter) -> None:
        """Sends the microphone to the model, silence instead while the echo guard holds it."""
        console, loop = self.console, asyncio.get_running_loop()
        silence = bytes(FRAME * 2)
        timestamp, heard, started = 0, False, loop.time()
        while True:
            chunk = await self.microphone.queue.get()
            if not heard:
                if peak(chunk) > VOICE_LEVEL:
                    heard = True
                    console.ok('Microphone is picking up sound')
                elif loop.time() - started > SILENT_MIC_WARNING:
                    heard = True
                    console.warn(
                        f'The microphone has been silent for {SILENT_MIC_WARNING} s: '
                        'check its permission and input level'
                    )
            guarded = not self.args.barge_in and time.monotonic() - self.assistant_spoke_at < ECHO_TAIL
            data = webrtc.AudioData(
                format='s16',
                sample_rate=SAMPLE_RATE,
                number_of_frames=FRAME,
                number_of_channels=1,
                timestamp=timestamp,
                data=silence if guarded else chunk,
            )
            await writer.write(data)
            timestamp += 10_000

    async def _play(self, track: webrtc.MediaStreamTrack) -> None:
        """Plays the assistant's audio."""
        heard = False
        async for data in webrtc.MediaStreamTrackProcessor(track, max_buffer_size=50).readable:
            with data:
                samples = bytearray(data.allocation_size({'plane_index': 0, 'format': 's16'}))
                data.copy_to(samples, {'plane_index': 0, 'format': 's16'})
                rate, channels = int(data.sample_rate), data.number_of_channels
            if peak(samples) > VOICE_LEVEL:
                self.assistant_spoke_at = time.monotonic()
                if not heard:
                    heard = True
                    self.console.ok(f"Receiving the assistant's voice ({rate} Hz, {channels} ch)")
            self.speakers.play(samples, rate, channels)

    def _on_message(self, event: webrtc.MessageEvent) -> None:
        console = self.console
        try:
            message: dict[str, Any] = json.loads(event.data)
        except ValueError:
            console.debug(f'Not JSON: {event.data!r}')
            return
        kind = message.get('type')
        if kind == 'session.input_transcript.delta':
            console.transcript('user', message.get('delta', ''))
        elif kind == 'session.output_transcript.delta':
            console.transcript('assistant', message.get('delta', ''))
        elif kind == 'session.started':
            console.ok('Session started, say something! (Ctrl+C to hang up)')
        elif kind == 'session.closed':
            usage = message.get('usage', {})
            reason = message.get('reason')
            console.info(f'Session closed{f" ({reason})" if reason else ""}, {usage.get("seconds", "?")} s billed')
            self.session_closed.set()
        elif kind == 'error':
            error = message.get('error', {})
            console.error(f'API error: {error.get("message") or error}')
        elif kind == 'session.usage.updated':
            usage = message.get('usage', {})
            ratio = message.get('context_window', {}).get('usage_ratio')
            context = f', context {ratio:.0%} full' if isinstance(ratio, (int, float)) else ''
            console.debug(f'Usage: {usage.get("seconds", "?")} s{context}')
        else:
            console.debug(f'Event {kind}')

    async def close(self) -> None:
        """Ends the session gracefully, then releases the audio devices."""
        console = self.console
        if self.events is not None and self.events.ready_state == 'open':
            console.info('Hanging up...')
            self.events.send(json.dumps({'type': 'session.close'}))
            try:
                await asyncio.wait_for(self.session_closed.wait(), 5)
            except asyncio.TimeoutError:
                console.warn("The session didn't confirm closing")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.pc is not None:
            self.pc.close()
        if self.microphone is not None:
            self.microphone.close()
        if self.speakers is not None:
            self.speakers.close()
        console.ok('Bye!')


class CallError(Exception):
    """The call couldn't be set up."""


def _describe_http_error(response: httpx.Response) -> str:
    try:
        message = response.json().get('error', {}).get('message')
    except ValueError:
        message = None
    hints = {
        401: 'the API key is invalid',
        403: 'the key has no access to this model',
        404: 'unknown endpoint or model',
        429: 'rate limit or quota exceeded',
    }
    summary = hints.get(response.status_code, response.reason_phrase)
    return f'OpenAI API returned {response.status_code}, {summary}' + (f': {message}' if message else '')


def parse_args() -> argparse.Namespace:
    """The options of the command line."""
    parser = argparse.ArgumentParser(
        description='Voice chat with OpenAI GPT-Live over WebRTC.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--api-key', default=os.environ.get('OPENAI_API_KEY'), help='default: $OPENAI_API_KEY')
    parser.add_argument('--model', default='gpt-live-1', help='the GPT-Live model')
    parser.add_argument('--instructions', help='the system prompt')
    parser.add_argument('--voice', help='quartz, ripple, vesper, willow, stone, gleam, meridian, bossa, tempo, ...')
    parser.add_argument('--input-device', help='microphone name or index (see --list-devices), default: the system one')
    parser.add_argument('--output-device', help='speakers name or index (see --list-devices), default: the system one')
    parser.add_argument('--barge-in', action='store_true', help='keep the mic open while the assistant speaks')
    parser.add_argument('--list-devices', action='store_true', help='list audio devices and exit')
    parser.add_argument('-v', '--verbose', action='store_true', help='log every event from the API')
    args = parser.parse_args()
    for name in ('input_device', 'output_device'):
        value = getattr(args, name)
        if value is not None and value.isdigit():
            setattr(args, name, int(value))
    return args


async def main() -> None:
    """Runs a call until Ctrl+C."""
    args = parse_args()
    if args.list_devices:
        print(sounddevice.query_devices())
        return
    console = Console(verbose=args.verbose)
    if not args.api_key:
        console.error('No API key: set OPENAI_API_KEY or pass --api-key')
        sys.exit(1)

    hang_up = asyncio.Event()
    # on Windows, Ctrl+C raises KeyboardInterrupt instead
    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, hang_up.set)

    call = LiveCall(args, console)
    try:
        await call.run(hang_up)
    except (CallError, sounddevice.PortAudioError) as e:
        console.error(str(e))
        await call.close()
        sys.exit(1)


if __name__ == '__main__':
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
