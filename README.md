<p align="center">
    <a href="https://github.com/MarshalX/python-webrtc">
        <img src="https://github.com/MarshalX/python-webrtc/raw/main/.github/images/logo.png" alt="Python WebRTC logo">
    </a>
</p>

<h3 align="center">Chrome's WebRTC engine, with the browser API, in Python.</h3>

<p align="center">
    <a href="https://wrtc.marshal.dev/">Documentation</a>
    •
    <a href="https://wrtc.marshal.dev/quickstart/">Quickstart</a>
    •
    <a href="https://github.com/MarshalX/python-webrtc/tree/main/examples">Examples</a>
    •
    <a href="https://wrtc.marshal.dev/benchmarks/">Benchmarks</a>
    •
    <a href="https://pypi.org/project/wrtc/">PyPI</a>
</p>

---

Python WebRTC binds **libwebrtc M152**, the engine inside Chrome, and exposes it through the **W3C APIs you
already know from the browser**: `RTCPeerConnection`, data channels, tracks, WebCodecs frames, encoded transforms and
stats. Talk to browsers, servers, SFUs and AI agents peer-to-peer, with no vendor service in between.

```bash
pip install wrtc
```

## If you know it in JavaScript, you know it in Python

<table>
<tr><th>Browser</th><th>Python</th></tr>
<tr>
<td>

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

</td>
<td>

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

</td>
</tr>
</table>

Names follow the specifications in snake_case, and the camelCase originals (`createOffer`) work too. Enums compare
equal to the strings of the specification, dictionaries are typed dataclasses, and everything is asyncio.

## Highlights

- 🌐 **The real engine.** ICE, DTLS, SCTP, congestion control, jitter buffers and codecs are Chrome's own, so
  interop with browsers is the browsers' interop.
- 🧩 **The browser API.** Written against the W3C specifications and tested with the
  [web-platform-tests](https://github.com/web-platform-tests/wpt) the browsers use.
- 🎞️ **Every modern codec.** VP8, VP9, AV1, H.264 and Opus. Hardware H.264 through VideoToolbox on macOS.
- ⚡ **Native media path.** Packets, decoding and encoding never touch Python. You see frames, not packets.
- 🖼️ **Frames in, frames out.** `MediaStreamTrackProcessor`, `VideoTrackGenerator` and `MediaStreamTrackGenerator`
  with WebCodecs' `VideoFrame` and `AudioData`, piped through WHATWG Streams.
- 🔐 **Encoded transforms.** `RTCRtpScriptTransform` and end-to-end encryption with SFrame.
- 🚀 **Fast connection setup.** [WARP](https://wrtc.marshal.dev/guides/field-trials/#warp): DTLS 1.3, SNAP and
  SPED cut round trips off every new connection.
- 📦 **`pip install` and go.** Prebuilt wheels for Linux, macOS and Windows, CPython 3.9–3.15, including
  free-threaded 3.14t and 3.15t. Nothing else to install.
- 🏷️ **Typed.** Full type stubs, so your editor knows every interface, dictionary and event.

## How it compares

|                                                         | **Python WebRTC**    | aiortc            | LiveKit SDK                | GStreamer webrtcbin   |
|---------------------------------------------------------|----------------------|-------------------|----------------------------|-----------------------|
| Engine                                                  | libwebrtc (Chrome's) | own, in Python    | libwebrtc                  | own, in C             |
| Connects peer-to-peer to any WebRTC endpoint            | ✅                    | ✅                 | ❌ needs a LiveKit server   | ✅                     |
| Browser API (`RTCPeerConnection`, `createOffer`, …)     | ✅                    | similar           | ❌ rooms                    | ❌ GObject signals     |
| Media path                                              | native               | Python            | native                     | native                |
| VP9 and AV1                                             | ✅                    | ❌                 | ✅                          | ✅                     |
| `pip install` on Linux, macOS and Windows               | ✅                    | ✅                 | ✅                          | ❌ system packages     |

Against aiortc, it opens connections 5–7x faster, moves 4.5–9x more data through a data channel and spends less CPU on
audio. See the [benchmarks](https://wrtc.marshal.dev/benchmarks/), which also measure Pion, libdatachannel and
webrtc-rs.

## Codecs

|       | Linux and Windows                                                         | macOS                       |
|-------|---------------------------------------------------------------------------|-----------------------------|
| Video | VP8, VP9, AV1, H.264 with [OpenH264](https://wrtc.marshal.dev/guides/h264/) | VP8, VP9, AV1, H.264 with VideoToolbox |
| Audio | Opus, G.722, G.711                                                        | Opus, G.722, G.711          |

No H.264 implementation is built into the package. `webrtc.openh264.install()` downloads Cisco's binary on the
user's device, under Cisco's patent license.

## Platforms

Prebuilt wheels for CPython 3.9–3.15, and free-threaded 3.14t and 3.15t, on:

| Linux                                       | macOS                        | Windows |
|---------------------------------------------|------------------------------|---------|
| x86_64 and aarch64 (glibc 2.27+, manylinux) | 13+, Intel and Apple Silicon | x64     |

Elsewhere pip builds it from sources with CMake and a C++20 compiler. See [CONTRIBUTING.md](https://github.com/MarshalX/python-webrtc/blob/main/CONTRIBUTING.md#building-from-sources-sdist).

## Examples

Complete programs, ready to copy. The ones with dependencies declare them inline, so `uv run` needs nothing installed.

- 🤖 [**Voice chat with OpenAI GPT-Live**](https://github.com/MarshalX/python-webrtc/blob/main/examples/openai_live.py): talk to the model through your microphone and
  speakers. No server, just an API key.
- 📺 [**Live stream in the terminal**](https://github.com/MarshalX/python-webrtc/blob/main/examples/janus_streaming.py): watch a public Janus stream as colored
  characters, with the audio on your speakers.
- 🔁 [**Echo peer**](https://github.com/MarshalX/python-webrtc/blob/main/examples/echo.py): send the received video back in grayscale.
- 💾 [**Recorder**](https://github.com/MarshalX/python-webrtc/blob/main/examples/recorder.py): write received video and audio to files.

```bash
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/janus_streaming.py
```

## Status

Pre-1.0: the API follows the specifications, but compatibility between versions isn't guaranteed until 1.0.0. See
the [changelog](https://wrtc.marshal.dev/change_log/).

## Getting help

- 📖 [Documentation](https://wrtc.marshal.dev/): quickstart, guides and the API reference.
- 🐛 [Report a bug or request a feature](https://github.com/MarshalX/python-webrtc/issues/new).
- 💬 [Ask a question](https://github.com/MarshalX/python-webrtc/discussions/new).

## Contributing

Contributions of any size are welcome. [CONTRIBUTING.md](https://github.com/MarshalX/python-webrtc/blob/main/CONTRIBUTING.md) covers the development setup, building from
sources, releasing and updating libwebrtc.

## License

Python WebRTC is published under the [BSD 3-Clause License](https://github.com/MarshalX/python-webrtc/blob/main/LICENSE.md).
