---
description: "Run aiortc code on Chrome's WebRTC engine: install wrtc[aiortc], change the imports to webrtc.aiortc, and the rest stays as it is."
---

# Migrating from aiortc

`webrtc.aiortc` runs code written for aiortc 1.15 on Python WebRTC's engine. Install the extra, change the imports,
and the rest of the code stays as it is:

```bash
pip install "wrtc[aiortc]"
```

```python
# before
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRecorder

# after
from webrtc.aiortc import RTCPeerConnection, RTCSessionDescription
from webrtc.aiortc.contrib.media import MediaPlayer, MediaRecorder
```

The layer follows aiortc's API: its names, argument orders, dataclasses, events and errors. These pages don't document
it again, so read [aiortc's documentation](https://aiortc.readthedocs.io) for the API. Every other module path changes
the same way: `aiortc.sdp` becomes `webrtc.aiortc.sdp`, `aiortc.contrib.signaling` becomes
`webrtc.aiortc.contrib.signaling`.

Everything built on `RTCPeerConnection` works, `contrib.media` and `contrib.signaling` included, except what
[What differs](#what-differs) lists. All 7 of aiortc's examples run with only the imports changed, also against an
aiortc peer. H.264 works through VideoToolbox on macOS. Elsewhere, call `await webrtc.openh264.install()` once at
startup, see [H.264](h264.md).

Python WebRTC isn't affiliated with or endorsed by aiortc.

## Libraries that import aiortc

A library that imports `aiortc` itself runs on the layer unchanged. Call `webrtc.aiortc.install_alias()` before
importing it:

```python
import webrtc.aiortc

webrtc.aiortc.install_alias()

import some_library  # its aiortc imports now get webrtc.aiortc
```

`aiortc.x` then gives `webrtc.aiortc.x`, and a module the layer lacks raises `ModuleNotFoundError`. Call it first,
in each process: it raises `RuntimeError` if `aiortc` is imported already.

The library's aiortc dependency stays installed but unused. Keep it if the library imports aiortc's dependencies, such
as `aioice` or `cryptography`, directly.

## What differs

Not supported:

- **ORTC below ICE.** Standalone `RTCIceGatherer`, `RTCIceTransport`, `RTCDtlsTransport`, `RTCSctpTransport`,
  `RTCRtpSender` and `RTCRtpReceiver`, and `RTCDataChannel` on anything but `pc.sctp`, raise `NotImplementedError`.
  Transports come from `RTCPeerConnection`.
- **Certificate import.** `RTCCertificate(key, cert)` raises `NotImplementedError`. Generated certificates are ECDSA,
  with one SHA-256 fingerprint.
- **Internal modules.** `rtp`, `jitterbuffer`, `clock` and `utils` are aiortc's code, but the engine's packets never
  pass through them, so a jitter buffer given to a receiver does nothing. Setting `rtcsctptransport.USERDATA_MAX_LENGTH`
  or `rtcdtlstransport.X509_DIGEST_ALGORITHMS` does nothing either. `rate` isn't there, and `codecs` has only the
  bitrate constants: no encoder and decoder classes, no `CODECS` or `HEADER_EXTENSIONS` table. `MAX_FRAME_RATE` exists
  but isn't applied, as in aiortc.
- **An explicit `id` on a non-negotiated data channel.** It's ignored, as the specification says.
- **Encoded passthrough.** `MediaPlayer(decode=False)` works, but its packets are decoded and encoded again: the same
  output, more CPU.

Behaves differently:

- **ICE gathering.** `setLocalDescription` waits for gathering at most 5 s, as aiortc does. A STUN server never
  answers through some network interfaces, such as a VPN's or a virtual machine's, and then both wait the full 5 s.
  ICE checks start while gathering runs, so the ICE state can be ahead of where aiortc would be. Every configured STUN
  and TURN server is used, where aiortc uses the first of each.
- **SDP.** Descriptions are the engine's: other codecs and payload types, more attributes, and stricter validation of
  munged SDP. `getCapabilities` lists more codecs, so code that picks a codec by position can get another one. A
  format parameter you add to your own description changes what the peer sends you, not what you send.
- **Opus.** It negotiates as with the native API: mono at 32 kbps unless the peer asks for stereo, then stereo at
  64 kbps. aiortc offers stereo and sends it at 96 kbps. `recv()` still returns 48 kHz stereo frames, with a mono
  stream in both channels. To receive stereo, add `stereo=1` to the Opus format parameters of your description before
  `setLocalDescription`, as the [Janus streaming example](../examples/janus_streaming.md) does.
- **Video bitrate and resolution.** The engine adapts the bitrate to the network instead of aiortc's fixed range,
  unless you change the `codecs` constants. It also starts video at a low resolution and raises it as the bandwidth
  estimate grows, as browsers do, so the peer can receive frames smaller than the ones you send. aiortc always sends
  the full frame.
- **Transports before negotiation.** `sender.transport` and `receiver.transport` are `None` until
  `setLocalDescription`.
- **Data channels.** Messages are limited to 256 KiB between Python WebRTC peers and to 64 KiB with an aiortc peer;
  a larger one raises `TypeError`. A `maxPacketLifeTime` of 0 makes the channel unreliable.
- **Remote media.** `recv()` buffers about 1 s (30 video frames, 100 audio chunks) and drops the oldest after that,
  where aiortc queues without limit. Remote video can arrive as `yuv420p10le` or `nv12`, besides `yuv420p`.
- **Track end.** Remote tracks end when the peer closes the connection or you call `close()`. A remote
  `transceiver.stop()` alone doesn't end them.
- **Stats.** The ids are the engine's. `remote-inbound-rtp` and `remote-outbound-rtp` follow the engine's RTCP interval,
  so they arrive later than in aiortc.

## Performance

Python WebRTC opens connections 7–8x faster than aiortc, moves 7.7–14.6x more data through a data channel and spends
less CPU on audio. See the [benchmarks](../benchmarks.md).

The layer gives up some of that for compatibility: it costs up to 8% more than the same code on the native API. Each
received video frame is copied into a PyAV frame, and importing PyAV adds about 24 MB at startup. The native API has
neither cost, see [Moving to the native API](#moving-to-the-native-api).

## Moving to the native API

The layer is a way in. The native API has more to offer:

- **The browser API.** W3C names in snake_case (camelCase works too), so MDN's guides apply as they are. See
  {mdn}`RTCPeerConnection`.
- **Trickle ICE.** Send each candidate as it's found, in the `icecandidate` event, instead of waiting for gathering.
  Connections set up sooner. See [Connections](connections.md#signalling).
- **Frames without conversion.** {obj}`~webrtc.MediaStreamTrackProcessor` gives {obj}`~webrtc.VideoFrame` and
  {obj}`~webrtc.AudioData`, and you copy only what you read. No PyAV import. See [Media](media.md).
- **More features.** Bitrate caps for any sender, simulcast, {obj}`~webrtc.RTCRtpScriptTransform` for encoded frames,
  end-to-end encryption with SFrame, DTMF, typed dataclasses and full type stubs.

Common calls:

| aiortc | Python WebRTC |
|--------|---------------|
| `RTCPeerConnection()` | `webrtc.RTCPeerConnection()`. No STUN server by default: pass {obj}`~webrtc.RTCConfiguration` with `ice_servers`. |
| `RTCSessionDescription(sdp=sdp, type='offer')` | `webrtc.RTCSessionDescriptionInit(type='offer', sdp=sdp)` |
| `await pc.setLocalDescription(offer)`, then send `pc.localDescription` | `await pc.set_local_description(offer)`, send it, then send each candidate of `icecandidate` to `add_ice_candidate` |
| `@pc.on('track')`, called with the track | `@pc.on('track')`, called with an event: `event.track` |
| `@channel.on('message')`, called with the message | `@channel.on('message')`, called with an event: `event.data` |
| `await track.recv()` | `async for frame in webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable` |
| A `VideoStreamTrack` subclass with `recv()` | {obj}`~webrtc.VideoTrackGenerator`, with frames written to its `writable` |
| An `AudioStreamTrack` subclass with `recv()` | `webrtc.MediaStreamTrackGenerator('audio')`, with chunks written to its `writable` |
| `MediaRelay().subscribe(track)` | `track.clone()` |
| `vpx.MAX_BITRATE = 1_000_000` | `encodings[0].max_bitrate` with `sender.get_parameters()` and `await sender.set_parameters(...)` |

What catches code ported this way:

- **Handlers get one event argument.** A handler written for aiortc, with no argument, raises `TypeError` that goes
  to the event loop's exception handler, so it looks like the event never fires. Register handlers from a running
  event loop. See [Events](events.md).
- **`ice_connection_state` reaches `connected`.** aiortc reports `completed` instead.
- **A peer's hang-up isn't seen at once.** `connection_state` becomes `disconnected` several seconds after the peer
  closes. Send a bye message through your signalling, or watch the DTLS transport's `statechange` for `closed`.
- **`close()` is not a coroutine and fires no events**, so don't wait for a final `closed` state change.
- **`replace_track` is a coroutine.** Without `await`, it does nothing.
