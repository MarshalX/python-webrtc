---
description: "Chrome's WebRTC engine with the browser API, in Python: peer connections, data channels, audio and video. Prebuilt wheels for Linux, macOS and Windows."
---

# Python WebRTC

**Chrome's WebRTC engine, with the browser API, in Python.**

Python WebRTC binds libwebrtc M152, the engine inside Chrome, and exposes it through the W3C APIs you already know
from the browser: peer connections, data channels, tracks, WebCodecs frames, encoded transforms and stats, in
asyncio. Talk to browsers, servers, SFUs and AI agents peer-to-peer, with no vendor service in between.

```bash
pip install wrtc
```

:::{tip}
Coming from aiortc? Install `wrtc[aiortc]`, change `from aiortc` to `from webrtc.aiortc`, and your code runs on Chrome's
engine. See [Migrating from aiortc](guides/aiortc.md).
:::

## If you know it in JavaScript, you know it in Python

::::{tab-set}

:::{tab-item} Python
:sync: python

```python
pc = webrtc.RTCPeerConnection()
channel = pc.create_data_channel('chat')
channel.on('open', lambda e: channel.send('Hello!'))
channel.on('message', lambda e: print(e.data))
pc.on('icecandidate', lambda e: signaling.send(e.candidate))

offer = await pc.create_offer()
await pc.set_local_description(offer)
signaling.send(pc.local_description)
```
:::

:::{tab-item} Browser
:sync: js

```js
const pc = new RTCPeerConnection();
const channel = pc.createDataChannel('chat');
channel.onopen = () => channel.send('Hello!');
channel.onmessage = (e) => console.log(e.data);
pc.onicecandidate = (e) => signaling.send(e.candidate);

const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
signaling.send(pc.localDescription);
```
:::

::::

Names follow the specifications in snake_case (`create_offer`), and the camelCase originals (`createOffer`) work
too. Enums compare equal to the strings of the specification, and dictionaries are typed dataclasses.

:::{note}
Pre-1.0: until the 1.0.0 release, compatibility between versions isn't guaranteed.
:::

## Why Python WebRTC

::::{grid} 1 2 2 3
:gutter: 3

:::{grid-item-card} {octicon}`globe;1em;sd-mr-1` The real engine
ICE, DTLS, SCTP, congestion control, jitter buffers and codecs are Chrome's own, so interop with browsers is the
browsers' interop.
:::

:::{grid-item-card} {octicon}`code;1em;sd-mr-1` The browser API
Written against the W3C specifications and tested with the web-platform-tests the browsers use.
:::

:::{grid-item-card} {octicon}`zap;1em;sd-mr-1` Native media path
Packets, decoding and encoding never touch Python. You see frames, not packets.
:::

:::{grid-item-card} {octicon}`device-camera-video;1em;sd-mr-1` Every modern codec
VP8, VP9, AV1, H.264 and Opus. Hardware H.264 through VideoToolbox on macOS. See [H.264](guides/h264.md).
:::

:::{grid-item-card} {octicon}`rocket;1em;sd-mr-1` Fast connection setup
[WARP](guides/field-trials.md#warp): DTLS 1.3, SNAP and SPED cut round trips off every new connection.
:::

:::{grid-item-card} {octicon}`package;1em;sd-mr-1` pip install and go
Prebuilt wheels for Linux, macOS and Windows, including free-threaded Python. Nothing else to install.
:::

::::

## How it compares

|                                                     | **Python WebRTC**    | aiortc         | LiveKit SDK               | GStreamer webrtcbin |
|-----------------------------------------------------|----------------------|----------------|---------------------------|---------------------|
| Engine                                              | libwebrtc (Chrome's) | own, in Python | libwebrtc                 | own, in C           |
| Connects peer-to-peer to any WebRTC endpoint        | ✅                   | ✅             | ❌ needs a LiveKit server | ✅                  |
| Browser API (`RTCPeerConnection`, `createOffer`, …) | ✅                   | similar        | ❌ rooms                  | ❌ GObject signals  |
| Media path                                          | native               | Python         | native                    | native              |
| VP9 and AV1                                         | ✅                   | ❌             | ✅                        | ✅                  |
| `pip install` on Linux, macOS and Windows           | ✅                   | ✅             | ✅                        | ❌ no Linux wheels  |

Against aiortc, it opens connections 7.3–8.3x faster, moves 7.7–14.6x more data through a data channel and spends
less CPU on audio. See the [benchmarks](benchmarks.md), which also measure Pion, libdatachannel and webrtc-rs.

The full comparison, and when another library is the better choice: [Choosing a Python WebRTC library](guides/comparison.md).

## Where to start

::::{grid} 1 2 2 3
:gutter: 3

:::{grid-item-card} {octicon}`rocket;1em;sd-mr-1` Quickstart
:link: quickstart
:link-type: doc

Install it and connect two peers with a data channel. Five minutes.
:::

:::{grid-item-card} {octicon}`book;1em;sd-mr-1` Guides
:link: guides/index
:link-type: doc

Connections, data channels, events and media, organised by what you are trying to do.
:::

:::{grid-item-card} {octicon}`code-square;1em;sd-mr-1` Examples
:link: examples/index
:link-type: doc

Every runnable example in the repository, inlined and ready to copy.
:::

:::{grid-item-card} {octicon}`device-camera-video;1em;sd-mr-1` Media
:link: guides/media
:link-type: doc

Read the frames of a track, write your own, transform them on the way.
:::

:::{grid-item-card} {octicon}`package;1em;sd-mr-1` API reference
:link: api/index
:link-type: doc

Every interface, dictionary, enum and exception of the package.
:::

:::{grid-item-card} {octicon}`history;1em;sd-mr-1` Changelog
:link: change_log
:link-type: doc

What changed in each release.
:::

::::

## What it covers

- **WebRTC**: {obj}`~webrtc.RTCPeerConnection`, data channels, transceivers, senders and receivers, DTLS, ICE and
  SCTP transports, DTMF, certificates and the stats of WebRTC Statistics.
- **Media Capture and Streams**: tracks and streams, with a synthetic camera and microphone.
- **Media processing**: {obj}`~webrtc.MediaStreamTrackProcessor`, {obj}`~webrtc.VideoTrackGenerator` and
  {obj}`~webrtc.MediaStreamTrackGenerator`, with the {obj}`~webrtc.VideoFrame` and {obj}`~webrtc.AudioData` of
  WebCodecs and WHATWG Streams.
- **WebRTC Encoded Transform**: {obj}`~webrtc.RTCRtpScriptTransform` and end-to-end encryption with SFrame.

## Supported platforms

Pre-built wheels for CPython 3.9 to 3.15, and free-threaded 3.14t and 3.15t, on:

| Linux                                       | macOS                        | Windows |
|---------------------------------------------|------------------------------|---------|
| x86_64 and aarch64 (glibc 2.27+, manylinux) | 13+, Intel and Apple Silicon | x64     |

Elsewhere, pip builds it from sources. See [Installation](quickstart.md#installation).

```{toctree}
:hidden:
:caption: 🚀 Start

quickstart
examples/index
benchmarks
```

```{toctree}
:hidden:
:caption: 📖 Guides

guides/index
guides/connections
guides/data-channels
guides/events
guides/media
guides/h264
guides/field-trials
guides/comparison
guides/aiortc
```

```{toctree}
:hidden:
:caption: 🔌 API reference

api/index
```

```{toctree}
:hidden:
:caption: 🛠 Development

change_log
security
licence
```

```{toctree}
:hidden:
:caption: 🔗 Project links

GitHub <https://github.com/MarshalX/python-webrtc>
PyPI <https://pypi.org/project/wrtc/>
Author <https://github.com/MarshalX>
```
