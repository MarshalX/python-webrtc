#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["wrtc>=0.0.1", "aiohttp>=3.9"]
# ///
#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""Talks to Gemini Live from a browser, through a Python server that keeps the API key.

    browser  <-- WebRTC -->  this server  <-- WebSocket -->  Gemini Live API

    export GEMINI_API_KEY=...
    uv run gemini_live.py
    uv run gemini_live.py --voice Kore --instructions "You are a pirate. Keep answers short."

Open http://localhost:8080 and press Talk. Anyone who can open the page talks on your key, so the server listens on
localhost. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from array import array
from dataclasses import dataclass, field
from typing import TypedDict

import aiohttp
from aiohttp import web

import webrtc

GEMINI_URL = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'
STUN = 'stun:stun.l.google.com:19302'
INPUT_RATE = 16000  # Gemini hears 16 kHz
OUTPUT_RATE = 24000  # and speaks at 24 kHz
INPUT_CHUNK = 0.04  # seconds of the microphone per message, Google advises 20 to 40 ms
OUTPUT_CHUNK = 0.02  # seconds of the answer written to the track at a time
EVENTS_CHANNEL = 0  # the id of the negotiated channel of the transcripts
SETUP_LIMIT = 10  # seconds for Gemini to accept a session
CONNECT_LIMIT = 15  # seconds for the page to connect once answered
# gathering completes only once every STUN request is answered or times out, which can take tens of seconds
GATHERING_PAUSE = 0.4  # seconds without a new ICE candidate after which gathering counts as done
GATHERING_LIMIT = 3  # seconds to wait for ICE candidates at most


class Call:
    """A page connected to a Gemini session: its microphone goes to Gemini, Gemini's voice and transcripts to it."""

    def __init__(self, name: str, gemini: Gemini, ice_servers: list[webrtc.RTCIceServer]) -> None:
        self.name = name
        self.gemini = gemini
        self.pc = webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=ice_servers))
        self.generator = webrtc.MediaStreamTrackGenerator('audio')
        self.playback = Playback(self.generator)
        negotiated = webrtc.RTCDataChannelInit(negotiated=True, id=EVENTS_CHANNEL)
        self.events = self.pc.create_data_channel('events', negotiated)
        self.tasks: list[asyncio.Future[None]] = []
        self._ended = asyncio.Event()

    async def answer(self, offer: webrtc.RTCSessionDescriptionInit) -> webrtc.RTCSessionDescription:
        """Answers the offer of the page, then starts passing the audio both ways."""
        self.pc.on('track', self._on_track)
        self.pc.on('connectionstatechange', self._on_connection_state)
        self.events.on('close', self._on_events_close)

        await self.pc.set_remote_description(offer)
        # the offered transceiver has no track to send yet, so it takes this one
        self.pc.add_track(self.generator)
        await self.pc.set_local_description()
        answer = await gathered(self.pc)

        self.tasks.append(asyncio.ensure_future(self.playback.run()))
        self.tasks.append(asyncio.ensure_future(self._listen()))
        asyncio.get_running_loop().call_later(CONNECT_LIMIT, self._hang_up_unless_connected)
        return answer

    def hang_up(self) -> None:
        """Ends the call: run() then closes everything. Ending an ended call does nothing."""
        self._ended.set()

    async def run(self) -> None:
        """Waits for the call to end, then closes the connection and the session."""
        await self._ended.wait()
        for task in self.tasks:
            task.cancel()
        results = await asyncio.gather(*self.tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                print(f'{self.name}: {result!r}')

        self.pc.close()
        self.generator.stop()
        await self.gemini.close()
        print(f'{self.name}: ended')

    def _on_track(self, event: webrtc.RTCTrackEvent) -> None:
        self.tasks.append(asyncio.ensure_future(self._send_microphone(event.track)))

    def _on_connection_state(self, _event: webrtc.Event) -> None:
        state = self.pc.connection_state
        print(f'{self.name}: {state}')
        if state in {'failed', 'closed'}:
            self.hang_up()

    def _on_events_close(self, _event: webrtc.Event) -> None:
        print(f'{self.name}: the page hung up')
        self.hang_up()

    def _hang_up_unless_connected(self) -> None:
        if self.pc.connection_state in {'new', 'connecting'}:
            print(f'{self.name}: the page did not connect in {CONNECT_LIMIT} s')
            self.hang_up()

    async def _send_microphone(self, track: webrtc.MediaStreamTrack) -> None:
        """Streams the microphone of the page to Gemini in chunks of INPUT_CHUNK seconds, until it ends."""
        processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
        pending = array('h')
        try:
            async for media in processor.readable:
                with audio_data(media) as data:
                    samples = mono_samples(data)
                    rate = int(data.sample_rate)

                sent_rate = gemini_rate(rate)
                pending += downsample(samples, rate // sent_rate)
                if len(pending) >= sent_rate * INPUT_CHUNK:
                    await self.gemini.send_audio(pending.tobytes(), sent_rate)
                    pending = array('h')
        finally:
            self.hang_up()

    async def _listen(self) -> None:
        """Plays Gemini's voice and passes its transcripts to the page, until the session ends."""
        try:
            while True:
                message = await self.gemini.receive()
                self._on_gemini_message(message)
        except GeminiError as e:
            print(f'{self.name}: {e}')
            self._send_to_page({'type': 'note', 'text': str(e)})
        finally:
            self.hang_up()

    def _on_gemini_message(self, message: ServerMessage) -> None:
        content = message.get('serverContent')
        if content is not None:
            self._on_content(content)

        go_away = message.get('goAway')
        if go_away is not None:
            text = f'Gemini will end the session in {go_away.get("timeLeft", "a moment")}'
            self._send_to_page({'type': 'note', 'text': text})

    def _on_content(self, content: ServerContent) -> None:
        if content.get('interrupted', False):
            self.playback.clear()
            self._send_to_page({'type': 'turn'})

        for part in content.get('modelTurn', {}).get('parts', []):
            blob = part.get('inlineData')
            if blob is not None:
                self.playback.add(base64.b64decode(blob.get('data', '')))

        heard = content.get('inputTranscription', {}).get('text', '')
        if heard != '':
            self._send_to_page({'type': 'transcript', 'speaker': 'user', 'text': heard})

        said = content.get('outputTranscription', {}).get('text', '')
        if said != '':
            self._send_to_page({'type': 'transcript', 'speaker': 'gemini', 'text': said})

        if content.get('turnComplete', False):
            self._send_to_page({'type': 'turn'})

    def _send_to_page(self, message: dict[str, str]) -> None:
        """Sends a transcript fragment, the end of a turn or a note to the page, if it's still there."""
        if self.events.ready_state == 'open':
            self.events.send(json.dumps(message))


class Blob(TypedDict, total=False):
    """Base64 media of a message of Gemini."""

    data: str
    mimeType: str


class Part(TypedDict, total=False):
    """A part of a turn of Gemini: the fields used here."""

    inlineData: Blob


class Content(TypedDict, total=False):
    """A turn of Gemini."""

    parts: list[Part]


class Transcription(TypedDict, total=False):
    """A fragment of a transcript."""

    text: str


class ServerContent(TypedDict, total=False):
    """What Gemini says: audio, transcripts and the state of its turn."""

    modelTurn: Content
    interrupted: bool
    turnComplete: bool
    inputTranscription: Transcription
    outputTranscription: Transcription


class GoAway(TypedDict, total=False):
    """The notice that Gemini will close the connection soon."""

    timeLeft: str


class ServerMessage(TypedDict, total=False):
    """A message of Gemini: the fields used here."""

    setupComplete: dict[str, object]
    serverContent: ServerContent
    goAway: GoAway


class GeminiError(Exception):
    """Gemini refused the session or closed it."""


class Gemini:
    """A session of the Live API, over a WebSocket."""

    def __init__(self, http: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse[bool]) -> None:
        self.http = http
        self.ws = ws

    @classmethod
    async def connect(cls, args: argparse.Namespace) -> Gemini:
        """Opens a session, which Gemini has to accept in SETUP_LIMIT seconds."""
        http = aiohttp.ClientSession()
        try:
            return await asyncio.wait_for(cls._open(http, args), SETUP_LIMIT)
        except asyncio.TimeoutError:
            await http.close()
            msg = f'Gemini did not accept the session in {SETUP_LIMIT} s'
            raise GeminiError(msg) from None
        except BaseException:
            await http.close()
            raise

    @classmethod
    async def _open(cls, http: aiohttp.ClientSession, args: argparse.Namespace) -> Gemini:
        try:
            ws = await http.ws_connect(args.endpoint, headers={'x-goog-api-key': args.api_key})
        except aiohttp.ClientError as e:
            msg = f'Could not connect to Gemini: {e}'
            raise GeminiError(msg) from None

        session = cls(http, ws)
        await ws.send_json({'setup': setup_message(args)})
        message = await session.receive()
        if 'setupComplete' not in message:
            msg = f'Gemini sent {message} instead of accepting the session'
            raise GeminiError(msg)
        return session

    async def receive(self) -> ServerMessage:
        """The next message of Gemini, which sends JSON in text or binary frames."""
        frame = await self.ws.receive()
        if frame.type in {aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY}:
            message: ServerMessage = json.loads(frame.data)
            return message

        reason = frame.extra if frame.type == aiohttp.WSMsgType.CLOSE else frame.type.name
        msg = f'Gemini closed the session ({self.ws.close_code}): {reason}'
        raise GeminiError(msg)

    async def send_audio(self, pcm: bytes, sample_rate: int) -> None:
        """Sends 16-bit mono samples, unless the session has ended."""
        if self.ws.closed:
            return
        audio = {'data': base64.b64encode(pcm).decode(), 'mimeType': f'audio/pcm;rate={sample_rate}'}
        await self.ws.send_json({'realtimeInput': {'audio': audio}})

    async def close(self) -> None:
        """Closes the WebSocket."""
        await self.ws.close()
        await self.http.close()


def setup_message(args: argparse.Namespace) -> dict[str, object]:
    """The first message of a session: the model, its voice and instructions, and the transcripts to send."""
    generation: dict[str, object] = {'responseModalities': ['AUDIO']}
    if args.voice:
        generation['speechConfig'] = {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': args.voice}}}

    setup: dict[str, object] = {
        'model': f'models/{args.model}',
        'generationConfig': generation,
        'inputAudioTranscription': {},
        'outputAudioTranscription': {},
    }
    if args.instructions:
        setup['systemInstruction'] = {'parts': [{'text': args.instructions}]}
    return setup


class Playback:
    """Writes Gemini's voice to a track in real time, so an interruption can drop what's left."""

    def __init__(self, generator: webrtc.MediaStreamTrackGenerator) -> None:
        self.writer = generator.writable.get_writer()
        self.queued = bytearray()

    def add(self, pcm: bytes) -> None:
        """Queues 24 kHz 16-bit mono samples."""
        self.queued += pcm

    def clear(self) -> None:
        """Drops the samples not played yet."""
        self.queued.clear()

    async def run(self) -> None:
        """Writes a chunk every OUTPUT_CHUNK seconds, silence when nothing is queued."""
        loop = asyncio.get_running_loop()
        frames = int(OUTPUT_RATE * OUTPUT_CHUNK)
        size = frames * 2
        timestamp = 0
        next_write = loop.time()
        while True:
            chunk = bytes(self.queued[:size]).ljust(size, b'\0')
            del self.queued[:size]

            init = webrtc.AudioDataInit(
                format='s16',
                sample_rate=OUTPUT_RATE,
                number_of_frames=frames,
                number_of_channels=1,
                timestamp=timestamp,
                data=chunk,
            )
            await self.writer.write(webrtc.AudioData(init))

            timestamp += int(OUTPUT_CHUNK * 1_000_000)
            next_write += OUTPUT_CHUNK
            await asyncio.sleep(max(0, next_write - loop.time()))


def audio_data(media: object) -> webrtc.AudioData:
    """The media a processor of an audio track reads, as audio data."""
    if not isinstance(media, webrtc.AudioData):
        msg = f'expected audio data, not {media!r}'
        raise TypeError(msg)
    return media


def mono_samples(data: webrtc.AudioData) -> array[int]:
    """The 16-bit samples of the first channel."""
    options = webrtc.AudioDataCopyToOptions(plane_index=0, format='s16-planar')
    buffer = bytearray(data.allocation_size(options))
    data.copy_to(buffer, options)
    return array('h', buffer)


def gemini_rate(rate: int) -> int:
    """The rate to send audio at: 16 kHz when the rate divides evenly, else the rate itself, which Gemini resamples."""
    return INPUT_RATE if rate % INPUT_RATE == 0 else rate


def downsample(samples: array[int], factor: int) -> array[int]:
    """Averages every `factor` samples into one: a rough low-pass, enough for speech."""
    averages = (sum(samples[start : start + factor]) // factor for start in range(0, len(samples), factor))
    return array('h', averages)


async def gathered(pc: webrtc.RTCPeerConnection) -> webrtc.RTCSessionDescription:
    """Waits for the ICE candidates until they pause, GATHERING_LIMIT seconds at most, then returns the description."""
    progress = asyncio.Event()

    def on_progress(_event: object) -> None:
        progress.set()

    pc.on('icecandidate', on_progress)
    pc.on('icegatheringstatechange', on_progress)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + GATHERING_LIMIT
    try:
        while pc.ice_gathering_state != 'complete' and loop.time() < deadline:
            progress.clear()
            try:
                await asyncio.wait_for(progress.wait(), min(GATHERING_PAUSE, deadline - loop.time()))
            except asyncio.TimeoutError:
                break
    finally:
        pc.off('icecandidate', on_progress)
        pc.off('icegatheringstatechange', on_progress)

    if pc.local_description is None:
        msg = 'no local description'
        raise RuntimeError(msg)
    return pc.local_description


@dataclass
class Server:
    """Serves the page, and connects each page that calls to a Gemini session of its own."""

    args: argparse.Namespace
    ice_servers: list[webrtc.RTCIceServer]
    calls: dict[Call, asyncio.Future[None]] = field(default_factory=dict)
    count: int = 0

    async def page(self, _request: web.Request) -> web.Response:
        """The page, with the ICE servers and the id of the transcripts channel filled in."""
        config = {'iceServers': [server.to_json() for server in self.ice_servers], 'eventsChannel': EVENTS_CHANNEL}
        # escaped, so a URL in the config can't end the script element
        script_config = json.dumps(config).replace('<', '\\u003c')
        return web.Response(text=PAGE.replace('/*CONFIG*/', script_config), content_type='text/html')

    async def offer(self, request: web.Request) -> web.Response:
        """Opens a Gemini session, then answers the offer of the page, which has its ICE candidates."""
        # other sites can only post JSON after a CORS preflight, which this server doesn't allow
        if request.content_type != 'application/json':
            raise web.HTTPUnsupportedMediaType

        offer = webrtc.RTCSessionDescriptionInit.from_json(await request.json())
        self.count += 1
        name = f'Call {self.count}'
        print(f'{name}: connecting to Gemini')
        try:
            gemini = await Gemini.connect(self.args)
        except GeminiError as e:
            print(f'{name}: {e}')
            return web.Response(status=502, text=str(e))

        call = Call(name, gemini, self.ice_servers)
        self.calls[call] = asyncio.ensure_future(self._serve(call))
        try:
            answer = await call.answer(offer)
        except Exception:
            call.hang_up()
            raise
        return web.json_response(answer.to_json())

    async def _serve(self, call: Call) -> None:
        """Runs a call until it ends, then forgets it."""
        try:
            await call.run()
        finally:
            del self.calls[call]

    async def close(self, _app: web.Application) -> None:
        """Ends the calls when the server stops."""
        for call in self.calls:
            call.hang_up()
        await asyncio.gather(*self.calls.values(), return_exceptions=True)


def parse_args() -> argparse.Namespace:
    """The options of the command line."""
    parser = argparse.ArgumentParser(
        description='Voice chat with Gemini Live from a browser, through WebRTC and this server.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--api-key', default=os.environ.get('GEMINI_API_KEY'), help='default: $GEMINI_API_KEY')
    parser.add_argument('--model', default='gemini-3.8-live', help='the Live model')
    parser.add_argument('--voice', help='Kore, Puck, Charon, ..., default: the one of the model')
    parser.add_argument('--instructions', help='the system prompt')
    parser.add_argument('--host', default='localhost', help='the address to listen on: whoever reaches it uses the key')
    parser.add_argument('--port', type=int, default=8080, help='the port to listen on')
    parser.add_argument('--endpoint', default=GEMINI_URL, help='the WebSocket URL of the Live API')
    return parser.parse_args()


def main() -> None:
    """Serves the page until Ctrl+C."""
    args = parse_args()
    if not args.api_key:
        print('No API key: set GEMINI_API_KEY or pass --api-key')
        sys.exit(1)

    server = Server(args, [webrtc.RTCIceServer(urls=STUN)])
    app = web.Application()
    app.router.add_get('/', server.page)
    app.router.add_post('/offer', server.offer)
    app.on_shutdown.append(server.close)

    print(f'Open http://{args.host}:{args.port} and press Talk. Press Ctrl+C to stop.')
    # handles Ctrl+C on every platform, then runs the shutdown handlers
    web.run_app(app, host=args.host, port=args.port, access_log=None, print=None)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gemini Live over WebRTC</title>
<style>
  body { font: 16px/1.5 system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }
  button { font-size: 1.1rem; padding: 0.5rem 1.5rem; }
  #state { margin-left: 1rem; color: #666; }
  #transcript p { margin: 0.5rem 0; }
  .user { color: #0b62d6; }
  .gemini { color: #8a2be2; }
  .note { color: #666; font-style: italic; }
</style>
</head>
<body>
<h1>Gemini Live</h1>
<p>Your microphone goes to the Python server over WebRTC, the server talks to Gemini.</p>
<button id="talk">Talk</button><span id="state">Not connected</span>
<div id="transcript"></div>
<audio id="speaker" autoplay></audio>
<script>
const CONFIG = /*CONFIG*/;
const GATHERING_PAUSE = 400;
const GATHERING_LIMIT = 3000;

const talk = document.getElementById('talk');
const state = document.getElementById('state');
const transcript = document.getElementById('transcript');
const speaker = document.getElementById('speaker');

let pc = null;
let microphone = null;
let line = null;
let lineSpeaker = null;

// like gathered() on the server: waits for the ICE candidates until they pause, at most GATHERING_LIMIT
function gathered(connection) {
  return new Promise((resolve) => {
    const listening = new AbortController();
    const limit = setTimeout(done, GATHERING_LIMIT);
    let pause = null;

    function done() {
      clearTimeout(limit);
      clearTimeout(pause);
      listening.abort();
      resolve();
    }

    function check() {
      if (connection.iceGatheringState === 'complete') {
        done();
      } else {
        clearTimeout(pause);
        pause = setTimeout(done, GATHERING_PAUSE);
      }
    }

    connection.addEventListener('icecandidate', check, {signal: listening.signal});
    connection.addEventListener('icegatheringstatechange', check, {signal: listening.signal});
    check();
  });
}

async function call() {
  talk.disabled = true;
  state.textContent = 'Asking for the microphone...';
  microphone = await navigator.mediaDevices.getUserMedia({audio: true});

  const connection = new RTCPeerConnection({iceServers: CONFIG.iceServers});
  pc = connection;
  connection.addTrack(microphone.getAudioTracks()[0], microphone);
  connection.addEventListener('track', (event) => {
    speaker.srcObject = new MediaStream([event.track]);
  });
  connection.addEventListener('connectionstatechange', () => {
    if (pc !== connection) {
      return;
    }
    if (connection.connectionState === 'failed') {
      hangUp('Connection failed');
    } else {
      state.textContent = connection.connectionState;
    }
  });

  const events = connection.createDataChannel('events', {negotiated: true, id: CONFIG.eventsChannel});
  events.addEventListener('message', (event) => onServerMessage(JSON.parse(event.data)));
  events.addEventListener('close', () => {
    if (pc === connection) {
      hangUp();
    }
  });

  await connection.setLocalDescription();
  await gathered(connection);
  state.textContent = 'Connecting to Gemini...';
  const response = await fetch('/offer', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(connection.localDescription),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  await connection.setRemoteDescription(await response.json());
  talk.textContent = 'Hang up';
  talk.disabled = false;
}

function hangUp(message = 'Not connected') {
  if (pc) {
    pc.close();
    pc = null;
  }
  if (microphone) {
    for (const track of microphone.getTracks()) {
      track.stop();
    }
    microphone = null;
  }
  talk.textContent = 'Talk';
  talk.disabled = false;
  state.textContent = message;
  line = null;
}

function onServerMessage(message) {
  if (message.type === 'transcript') {
    addTranscript(message.speaker, message.text);
  } else if (message.type === 'turn') {
    line = null;
  } else if (message.type === 'note') {
    addNote(message.text);
  }
}

function addTranscript(who, text) {
  if (!line || lineSpeaker !== who) {
    line = document.createElement('p');
    line.className = who;
    line.textContent = who === 'user' ? 'You: ' : 'Gemini: ';
    lineSpeaker = who;
    transcript.append(line);
  }
  line.textContent += text;
}

function addNote(text) {
  const note = document.createElement('p');
  note.className = 'note';
  note.textContent = text;
  transcript.append(note);
  line = null;
}

talk.addEventListener('click', () => {
  if (pc) {
    hangUp();
  } else {
    call().catch((error) => hangUp(error.message));
  }
});
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
