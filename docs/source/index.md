---
myst:
  html_meta:
    "description": "Python WebRTC: bindings to the native WebRTC, with the API of the browsers"
---

# Python WebRTC

Bindings to the native WebRTC M152, with the API of the browsers: peer connections, data channels, media tracks
and their frames, encoded transforms and stats, as the W3C specifications define them, in asyncio.

```python
import asyncio
import webrtc


async def main():
    pc = webrtc.RTCPeerConnection()
    channel = pc.create_data_channel('chat')

    offer = await pc.create_offer()
    await pc.set_local_description(offer)
    print(pc.local_description.sdp)


asyncio.run(main())
```

```bash
pip install wrtc
```

:::{warning}
Under development. Until the 1.0.0 release, compatibility between versions is not guaranteed.
:::

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

Names follow the specifications in snake_case (`create_offer`), and the camelCase originals (`createOffer`) work
too. Enums compare equal to the strings of the specification, and dictionaries are typed dataclasses.

## Supported platforms

Pre-built wheels for CPython 3.9 – 3.14 on:

| Linux                                       | macOS                        | Windows |
|---------------------------------------------|------------------------------|---------|
| x86_64 and aarch64 (glibc 2.27+, manylinux) | 13+, Intel and Apple Silicon | x64     |

Elsewhere, pip builds it from sources: see [Installation](quickstart.md#installation).

```{toctree}
:hidden:
:caption: 🚀 Start

quickstart
examples/index
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
