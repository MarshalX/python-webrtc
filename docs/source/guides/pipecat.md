---
description: "Run Pipecat bots on Chrome's WebRTC engine: install wrtc[pipecat], import the transport from webrtc.pipecat, or alias it for the development runner."
---

# Use with Pipecat

`webrtc.pipecat` replaces [Pipecat](https://www.pipecat.ai)'s SmallWebRTC transport: same classes, same HTTP
signalling, same data channel messages, without aiortc, PyAV or OpenCV.

```bash
pip install "wrtc[pipecat]"
```

Tested with Pipecat 1.15.0 on Python 3.11+, and with Pipecat's JavaScript client (`@pipecat-ai/client-js` 1.16.0,
`@pipecat-ai/small-webrtc-transport` 1.11.2) unchanged. Python WebRTC isn't affiliated with Pipecat or Daily.

## Why a transport of its own

Pipecat's own transport also runs on the [aiortc layer](aiortc.md), with `webrtc.aiortc.install_alias()`. But there
every frame is converted to aiortc's and PyAV's objects and back, and Pipecat's workarounds for aiortc's limits run
although the engine doesn't need them. `webrtc.pipecat` talks to the engine directly and keeps Pipecat's classes and
protocol, so bots and clients don't change. Use the aiortc layer only for code that reaches into aiortc's objects.

## Changing the imports

```python
# before
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest, SmallWebRTCRequestHandler
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

# after
from webrtc.pipecat.connection import IceServer, SmallWebRTCConnection
from webrtc.pipecat.request_handler import SmallWebRTCRequest, SmallWebRTCRequestHandler
from webrtc.pipecat.transport import SmallWebRTCTransport
```

The rest of the bot stays as it is, except what [What differs](#what-differs) lists. `request_handler` is the only
module that needs FastAPI.

## The development runner and unchanged bots

Pipecat's runner, its WhatsApp support and bots you don't change import Pipecat's transport themselves. Call
`install_alias()` first:

```python
import webrtc.pipecat

webrtc.pipecat.install_alias()

from pipecat.runner.run import main  # its WebRTC routes now run on webrtc.pipecat
```

It raises `RuntimeError` if Pipecat's transport is imported already. Call it in every process: one started with spawn
imports everything again.

The runner shows its WebRTC routes only when aiortc is installed, though nothing imports it, so add Pipecat's
`webrtc` extra:

```bash
pip install "wrtc[pipecat]" "pipecat-ai[runner,webrtc]"
```

## A bot

```python
from fastapi import BackgroundTasks, FastAPI
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.transports.base_transport import TransportParams
from pipecat.workers.runner import WorkerRunner

from webrtc.pipecat import IceServer, SmallWebRTCConnection, SmallWebRTCTransport
from webrtc.pipecat.request_handler import SmallWebRTCPatchRequest, SmallWebRTCRequest, SmallWebRTCRequestHandler

app = FastAPI()
handler = SmallWebRTCRequestHandler(ice_servers=[IceServer(urls='stun:stun.l.google.com:19302')])


async def run_bot(connection: SmallWebRTCConnection) -> None:
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    # stt, llm, tts and the context aggregators, as in any Pipecat bot
    pipeline = Pipeline([transport.input(), stt, user, llm, tts, transport.output(), assistant])
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(PipelineWorker(pipeline))

    @transport.event_handler('on_client_disconnected')
    async def on_client_disconnected(transport, connection):
        await runner.cancel()

    await runner.run()


@app.post('/api/offer')
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    async def start(connection: SmallWebRTCConnection) -> None:
        background_tasks.add_task(run_bot, connection)

    return await handler.handle_web_request(request, start)


@app.patch('/api/offer')
async def add_candidates(request: SmallWebRTCPatchRequest) -> dict[str, str]:
    await handler.handle_patch_request(request)
    return {'status': 'success'}
```

`await handler.close()` on shutdown disconnects every client. The [Pipecat bot example](../examples/pipecat_bot.md)
is a complete bot on the runner.

## Configuration

- **ICE servers.** As in Pipecat: URLs, or `IceServer(urls=..., username=..., credential=...)`.
- **When the answer goes out.** The protocol sends the bot's candidates only in the answer, so it waits for the host
  candidates of every interface, plus a server-reflexive one with STUN and a relay one with TURN, at most
  `ice_gathering_timeout_secs` (5 s). A STUN server on the bot's own private network can't give a server-reflexive
  candidate, so there the answer waits the whole timeout.
- **Port range.** `port_range=(low, high)` keeps the bot's candidates in a range of ports. In Docker, publish the same
  range, like `-p 40000-40019:40000-40019/udp`. The runner makes its own handler, so this needs a server of your own.
- **Clients without UDP.** `tcp_listen=True` lets clients behind a firewall that blocks UDP connect over TCP, without
  TURN. With `port_range`, publish the range for `/tcp` too. See [Clients without UDP](connections.md#clients-without-udp).
- **Codecs.** The answer follows the client's offer. For H.264, see [H.264](h264.md).

## What differs

- **Tracks.** The `*_input_track()` methods return a {obj}`webrtc.MediaStreamTrack`, with no `SmallWebRTCTrack`
  around it; a source turned off comes with the `track-status` event. The `replace_*_track()` methods are coroutines.
- **Leaving.** A client that closes its connection or data channel is closed at once. A client that pings, as
  Pipecat's JavaScript client does, and stays `disconnected` for 8 s without a ping, offer or candidate is closed
  before its connection would fail. `connection_timeout_secs` counts from the answer.
- **Requests.** A `restart_pc` offer drops the old `pc_id` from the handler.
- **Not there.** `force_transceivers_to_send_recv()`, `PIPECAT_SCTP_MAX_CHUNK_SIZE`,
  `SCREEN_VIDEO_JITTER_BUFFER_CAPACITY` and the key frame renegotiation on connect: the engine doesn't need them.
  `capture_participant_video('camera')` without a participant id, deprecated in Pipecat 1.13, isn't supported.

## What it fixes

Each checked against Pipecat's transport on aiortc, with Pipecat's workaround removed where it has one:

- Large screen-share key frames, like 1080p ones, arrive whole.
- A video track the pipeline doesn't read stays flat in memory ([#3066](https://github.com/pipecat-ai/pipecat/issues/3066)).
- The data channel works on paths with a small MTU, like VPNs.
- Lost audio packets are concealed, so audio stays whole on a lossy network.
- Video adapts to a capped link instead of stalling.
- The answer goes out as soon as the candidates are enough, not after seconds of gathering ([#2426](https://github.com/pipecat-ai/pipecat/issues/2426)).
- `port_range` lets Docker publish only a range of UDP ports ([#1808](https://github.com/pipecat-ai/pipecat/issues/1808), [#1570](https://github.com/pipecat-ai/pipecat/issues/1570)).
- A bot uses less CPU per session: media stays native, with no PyAV or OpenCV conversions.
- A client that vanishes is noticed sooner ([#3140](https://github.com/pipecat-ai/pipecat/issues/3140)).
- Audio resumes right after an ICE restart.
- Clients without UDP can connect over TCP, without TURN.
- A dead first TURN server falls back to the next.
