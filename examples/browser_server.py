#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["wrtc>=0.0.1", "aiohttp"]
# ///
#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""A WebRTC server for a browser page: your camera comes back from Python with an effect, and Python answers chat.

    uv run browser_server.py
    uv run browser_server.py --effect negative
    uv run browser_server.py --turn turn:turn.example.com:3478 --turn-username user --turn-credential secret

Open the printed address and allow the camera, which browsers allow only on localhost or over HTTPS. A TURN server is
needed only behind a strict NAT, and the page gets its credentials too. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
from dataclasses import dataclass, field
from typing import Callable

from aiohttp import web

import webrtc

STUN = 'stun:stun.l.google.com:19302'
# gathering completes only once every STUN request is answered or times out, which can take tens of seconds
GATHERING_PAUSE = 0.4  # seconds without a new ICE candidate after which gathering counts as done
GATHERING_LIMIT = 3  # seconds to wait for ICE candidates at most

Effect = Callable[[bytearray, list[webrtc.PlaneLayout]], None]


def grayscale(pixels: bytearray, layout: list[webrtc.PlaneLayout]) -> None:
    """Sets the planes after the luma to 128, which leaves no color."""
    chroma = layout[1].offset
    pixels[chroma:] = b'\x80' * (len(pixels) - chroma)


INVERTED = bytes(range(255, -1, -1))


def negative(pixels: bytearray, _layout: list[webrtc.PlaneLayout]) -> None:
    """Inverts every byte, which inverts the brightness and the colors."""
    pixels[:] = pixels.translate(INVERTED)


EFFECTS: dict[str, Effect] = {'gray': grayscale, 'negative': negative}


def video_frame(media: object) -> webrtc.VideoFrame:
    """The media a processor of a video track reads, as a video frame."""
    if not isinstance(media, webrtc.VideoFrame):
        msg = f'expected a video frame, not {media!r}'
        raise TypeError(msg)
    return media


async def with_effect(frame: webrtc.VideoFrame, effect: Effect) -> webrtc.VideoFrame:
    """A copy of the visible pixels of a frame, in its own format, with the effect applied."""
    rect = frame.visible_rect
    # only for the type checker: an open frame has both
    if frame.format is None or rect is None:
        msg = 'the frame is closed'
        raise ValueError(msg)

    pixels = bytearray(frame.allocation_size())
    layout = await frame.copy_to(pixels)
    effect(pixels, layout)

    init = webrtc.VideoFrameBufferInit(
        format=frame.format,
        coded_width=int(rect.width),
        coded_height=int(rect.height),
        timestamp=frame.timestamp,
        layout=layout,
        rotation=frame.rotation,
        flip=frame.flip,
    )
    return webrtc.VideoFrame(pixels, init)


@dataclass
class EffectTransformer:
    """The transformer of a TransformStream that applies an effect to video frames."""

    effect: Effect

    async def transform(self, media: object, controller: webrtc.TransformStreamDefaultController) -> None:
        """Enqueues the frame with the effect."""
        with video_frame(media) as frame:
            controller.enqueue(await with_effect(frame, self.effect))


@dataclass
class Server:
    """Answers the offers of the page, sends the camera back with an effect and answers chat messages."""

    ice_servers: list[webrtc.RTCIceServer]
    effect_name: str
    wait_for_relay: bool
    connections: set[webrtc.RTCPeerConnection] = field(default_factory=set)
    pipes: set[asyncio.Future[None]] = field(default_factory=set)
    count: int = 0

    async def page(self, _request: web.Request) -> web.Response:
        """The page, with the ICE servers and the effect filled in."""
        config = {
            'iceServers': [server.to_json() for server in self.ice_servers],
            'waitForRelay': self.wait_for_relay,
            'effect': self.effect_name,
        }
        # escaped, so a URL in the config can't end the script element
        script_config = json.dumps(config).replace('<', '\\u003c')
        return web.Response(text=PAGE.replace('/*CONFIG*/', script_config), content_type='text/html')

    async def offer(self, request: web.Request) -> web.Response:
        """Answers an offer that has the ICE candidates of the page, with the candidates of the server."""
        # other sites can only post JSON after a CORS preflight, which this server doesn't allow
        if request.content_type != 'application/json':
            raise web.HTTPUnsupportedMediaType

        offer = webrtc.RTCSessionDescriptionInit.from_json(await request.json())
        self.count += 1
        name = f'Connection {self.count}'
        pc = webrtc.RTCPeerConnection(webrtc.RTCConfiguration(ice_servers=self.ice_servers))
        self.connections.add(pc)
        self.watch_state(pc, name)
        self.serve_chat(pc, name)

        try:
            await pc.set_remote_description(offer)
            self.send_back_with_effect(pc)
            await pc.set_local_description()
            answer = await gathered(pc, wait_for_relay=self.wait_for_relay)
        except Exception:
            self.drop(pc)
            raise
        print(f'{name}: answered')
        return web.json_response(answer.to_json())

    def send_back_with_effect(self, pc: webrtc.RTCPeerConnection) -> None:
        """Sends each received video track back through the effect, on the transceiver it came on."""
        for receiver in pc.get_receivers():
            if receiver.track.kind != 'video':
                continue

            processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(receiver.track))
            transform = webrtc.TransformStream(EffectTransformer(EFFECTS[self.effect_name]))
            generator = webrtc.VideoTrackGenerator()

            with_effect = processor.readable.pipe_through(transform)
            pipe = with_effect.pipe_to(generator.writable)
            self.pipes.add(pipe)
            pipe.add_done_callback(self.pipe_ended)

            # the offered transceiver has no track to send yet, so it takes this one
            pc.add_track(generator.track)

    def pipe_ended(self, pipe: asyncio.Future[None]) -> None:
        """Forgets a finished pipe, and prints why it failed if it did."""
        self.pipes.discard(pipe)
        if not pipe.cancelled() and pipe.exception() is not None:
            print(f'The effect stopped: {pipe.exception()!r}')

    def watch_state(self, pc: webrtc.RTCPeerConnection, name: str) -> None:
        """Prints the state of the connection, and drops it once it failed or closed."""

        @pc.on('connectionstatechange')
        def on_state(_event: webrtc.Event) -> None:
            print(f'{name}: {pc.connection_state}')
            if pc.connection_state in {'failed', 'closed'}:
                self.drop(pc)

    def serve_chat(self, pc: webrtc.RTCPeerConnection, name: str) -> None:
        """Replies to each text message on the chat channel, and drops the connection once the page closes it."""

        @pc.on('datachannel')
        def on_datachannel(event: webrtc.RTCDataChannelEvent) -> None:
            reply_to_messages(event.channel, name)

            @event.channel.on('close')
            def on_close(_event: webrtc.Event) -> None:
                print(f'{name}: the page hung up')
                self.drop(pc)

    def drop(self, pc: webrtc.RTCPeerConnection) -> None:
        """Closes a connection, which ends its tracks and so its pipes."""
        self.connections.discard(pc)
        pc.close()

    async def close(self, _app: web.Application) -> None:
        """Closes every connection and waits for the pipes to end."""
        print('Closing the connections')
        for pc in list(self.connections):
            self.drop(pc)
        await asyncio.wait_for(asyncio.gather(*self.pipes, return_exceptions=True), 10)


def reply_to_messages(channel: webrtc.RTCDataChannel, name: str) -> None:
    """Replies to each text message of a channel."""

    @channel.on('message')
    def on_message(event: webrtc.MessageEvent) -> None:
        if not isinstance(event.data, str):
            return
        print(f'{name}: the page says {event.data!r}')
        channel.send(reply(event.data))


def reply(text: str) -> str:
    """Python's reply to a chat message."""
    words = len(text.split())
    return f'{text[::-1]} ({words} word{"" if words == 1 else "s"} backwards)'


def enough_candidates(pc: webrtc.RTCPeerConnection, *, wait_for_relay: bool) -> bool:
    """Whether gathering completed, or found a relay candidate when there is a TURN server to wait for."""
    if pc.ice_gathering_state == 'complete':
        return True
    return wait_for_relay and pc.local_description is not None and ' typ relay' in pc.local_description.sdp


async def gathered(pc: webrtc.RTCPeerConnection, *, wait_for_relay: bool) -> webrtc.RTCSessionDescription:
    """Waits for enough ICE candidates, GATHERING_LIMIT seconds at most, then returns the local description."""
    progress = asyncio.Event()

    def on_progress(_event: object) -> None:
        progress.set()

    pc.on('icecandidate', on_progress)
    pc.on('icegatheringstatechange', on_progress)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + GATHERING_LIMIT
    # a relay candidate takes a few round trips, so a pause in gathering doesn't count while waiting for one
    pause = GATHERING_LIMIT if wait_for_relay else GATHERING_PAUSE
    try:
        while not enough_candidates(pc, wait_for_relay=wait_for_relay) and loop.time() < deadline:
            progress.clear()
            try:
                await asyncio.wait_for(progress.wait(), min(pause, deadline - loop.time()))
            except asyncio.TimeoutError:
                break
    finally:
        pc.off('icecandidate', on_progress)
        pc.off('icegatheringstatechange', on_progress)

    if pc.local_description is None:
        msg = 'no local description'
        raise RuntimeError(msg)
    return pc.local_description


def ice_servers(args: argparse.Namespace) -> list[webrtc.RTCIceServer]:
    """Google's STUN server, and the TURN server of the options if there is one."""
    servers = [webrtc.RTCIceServer(urls=STUN)]
    if args.turn:
        servers.append(
            webrtc.RTCIceServer(urls=args.turn, username=args.turn_username, credential=args.turn_credential)
        )
    return servers


def parse_args() -> argparse.Namespace:
    """The options of the command line."""
    parser = argparse.ArgumentParser(
        description='Send the camera of a browser page back from Python with an effect, and chat with it.'
    )
    parser.add_argument('--host', default='localhost', help='the address to listen on, default: localhost')
    parser.add_argument('--port', type=int, default=8080, help='the port to listen on, default: 8080')
    parser.add_argument('--effect', choices=sorted(EFFECTS), default='gray', help='the effect of Python, default: gray')
    parser.add_argument('--turn', default=os.environ.get('TURN_URL'), help='a TURN server URL, default: $TURN_URL')
    parser.add_argument('--turn-username', default=os.environ.get('TURN_USERNAME'), help='default: $TURN_USERNAME')
    parser.add_argument(
        '--turn-credential', default=os.environ.get('TURN_CREDENTIAL'), help='default: $TURN_CREDENTIAL'
    )
    args = parser.parse_args()

    if args.turn and not (args.turn_username and args.turn_credential):
        parser.error('a TURN server needs --turn-username and --turn-credential')
    return args


def page_url(host: str, port: int) -> str:
    """The address of the page, on localhost when the server listens on every address."""
    if is_every_address(host):
        host = 'localhost'
    return f'http://{host}:{port}'


def is_every_address(host: str) -> bool:
    """Whether the host is 0.0.0.0 or ::, which mean every address of the machine."""
    try:
        return ipaddress.ip_address(host).is_unspecified
    except ValueError:  # a host name
        return False


def main() -> None:
    """Serves the page until Ctrl+C."""
    args = parse_args()
    server = Server(ice_servers(args), args.effect, wait_for_relay=bool(args.turn))

    app = web.Application()
    app.router.add_get('/', server.page)
    app.router.add_post('/offer', server.offer)
    app.on_shutdown.append(server.close)

    print(f'Open {page_url(args.host, args.port)} and allow the camera. Press Ctrl+C to stop.')
    # handles Ctrl+C on every platform, then runs the shutdown handlers
    web.run_app(app, host=args.host, port=args.port, print=None)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Browser and Python over WebRTC</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0 auto; padding: 16px; max-width: 960px; }
  .videos { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
  figure { margin: 0; }
  video { width: 100%; aspect-ratio: 4 / 3; background: #222; border-radius: 8px; }
  #state b { font-family: ui-monospace, monospace; }
  #log { list-style: none; padding: 0; height: 160px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px; }
  #log li { padding: 4px 8px; }
  #log .python { color: #0a6; }
  form { display: flex; gap: 8px; }
  form input { flex: 1; }
</style>
</head>
<body>
<h1>Browser and Python over WebRTC</h1>
<p>
  <button id="start">Start</button>
  <button id="stop" disabled>Hang up</button>
</p>
<p id="state">
  Connection: <b id="connection">new</b>,
  ICE: <b id="ice">new</b>,
  chat: <b id="channel">closed</b>
</p>
<div class="videos">
  <figure>
    <video id="local" autoplay muted playsinline></video>
    <figcaption>Your camera</figcaption>
  </figure>
  <figure>
    <video id="remote" autoplay muted playsinline></video>
    <figcaption id="remote-caption">Back from Python</figcaption>
  </figure>
</div>
<h2>Chat with Python</h2>
<ul id="log"></ul>
<form id="chat">
  <input id="text" autocomplete="off" placeholder="Say something to Python" disabled>
  <button id="send" disabled>Send</button>
</form>
<script>
const CONFIG = /*CONFIG*/;
const GATHERING_PAUSE = 400;
const GATHERING_LIMIT = 3000;

let pc = null;
let channel = null;

const element = (id) => document.getElementById(id);

function show(id, text) {
  element(id).textContent = text;
}

function log(from, text) {
  const item = document.createElement('li');
  item.className = from;
  item.textContent = (from === 'python' ? 'Python: ' : 'You: ') + text;
  element('log').append(item);
  element('log').scrollTop = element('log').scrollHeight;
}

function enableChat(enabled) {
  element('text').disabled = !enabled;
  element('send').disabled = !enabled;
}

// like enough_candidates() on the server
function enoughCandidates() {
  if (pc.iceGatheringState === 'complete') {
    return true;
  }
  return CONFIG.waitForRelay && pc.localDescription.sdp.includes(' typ relay');
}

// like gathered() on the server: waits for enough ICE candidates, at most GATHERING_LIMIT
function gathered() {
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
      if (enoughCandidates()) {
        done();
      } else if (!CONFIG.waitForRelay) {
        clearTimeout(pause);
        pause = setTimeout(done, GATHERING_PAUSE);
      }
    }

    pc.addEventListener('icecandidate', check, {signal: listening.signal});
    pc.addEventListener('icegatheringstatechange', check, {signal: listening.signal});
    check();
  });
}

async function start() {
  element('start').disabled = true;

  const camera = await navigator.mediaDevices.getUserMedia({video: true});
  element('local').srcObject = camera;

  pc = new RTCPeerConnection({iceServers: CONFIG.iceServers});
  pc.addEventListener('connectionstatechange', () => show('connection', pc.connectionState));
  pc.addEventListener('iceconnectionstatechange', () => show('ice', pc.iceConnectionState));
  pc.addEventListener('track', (event) => {
    element('remote').srcObject = new MediaStream([event.track]);
  });
  for (const track of camera.getTracks()) {
    pc.addTrack(track, camera);
  }

  channel = pc.createDataChannel('chat');
  channel.addEventListener('open', () => {
    show('channel', 'open');
    enableChat(true);
  });
  channel.addEventListener('close', () => {
    show('channel', 'closed');
    enableChat(false);
  });
  channel.addEventListener('message', (event) => log('python', event.data));

  await pc.setLocalDescription();
  await gathered();
  const response = await fetch('/offer', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(pc.localDescription),
  });
  if (!response.ok) {
    throw new Error(`the server answered ${response.status} ${response.statusText}`);
  }
  await pc.setRemoteDescription(await response.json());
  element('stop').disabled = false;
}

function stop() {
  for (const id of ['local', 'remote']) {
    const stream = element(id).srcObject;
    if (stream) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
    }
    element(id).srcObject = null;
  }
  if (pc) {
    // close() fires no state events, so the states are set here
    pc.close();
    pc = null;
    channel = null;
  }
  show('connection', 'closed');
  show('ice', 'closed');
  show('channel', 'closed');
  enableChat(false);
  element('start').disabled = false;
  element('stop').disabled = true;
}

element('remote-caption').textContent = `Back from Python, with the ${CONFIG.effect} effect`;

element('start').addEventListener('click', () => {
  start().catch((error) => {
    stop();
    show('connection', `error: ${error.message}`);
  });
});

element('stop').addEventListener('click', stop);

element('chat').addEventListener('submit', (event) => {
  event.preventDefault();
  const text = element('text').value.trim();
  if (text === '' || !channel || channel.readyState !== 'open') {
    return;
  }
  channel.send(text);
  log('you', text);
  element('text').value = '';
});
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
