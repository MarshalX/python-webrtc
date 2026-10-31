---
description: "Which Python WebRTC library to use: Python WebRTC (wrtc), aiortc, the LiveKit SDK and GStreamer webrtcbin compared on engine, API, codecs, platforms and performance."
---

# Choosing a Python WebRTC library

Four libraries bring WebRTC to Python: Python WebRTC (`wrtc` on PyPI), aiortc, LiveKit's Python SDK and GStreamer's
webrtcbin. This page compares them as of 24 October 2026, with a source for every fact about the others in
[Sources](#sources).

## Which one, and when

- **Python WebRTC**: you want libwebrtc, the WebRTC engine of Chrome, with the browser's API, peer-to-peer to any
  WebRTC endpoint: browsers, SFUs, media servers, AI voice APIs. Prebuilt wheels for Linux, macOS and Windows,
  free-threaded Python included.
- **aiortc**: you need ORTC objects below the peer connection, such as a standalone `RTCIceTransport`, a protocol
  stack written in Python that you can read and patch, less memory per connection than Python WebRTC, or a release line marked stable.
  Python WebRTC is a pre-1.0 beta. aiortc's own examples run on Python WebRTC with only their imports changed: see
  [Migrating from aiortc](aiortc.md).
- **LiveKit SDK**: you build on LiveKit: its rooms, LiveKit Cloud or a self-hosted LiveKit server. It connects to a
  LiveKit server only, not to other WebRTC endpoints.
- **GStreamer webrtcbin**: your media already lives in GStreamer pipelines, such as capture devices, hardware
  encoders, RTSP sources or mixing, and WebRTC is one more element in them.

## Features

| Feature                   | **Python WebRTC**          | aiortc                   | LiveKit SDK                  | GStreamer webrtcbin   |
|---------------------------|----------------------------|--------------------------|------------------------------|-----------------------|
| Engine                    | libwebrtc M152             | own, in Python           | libwebrtc M150, through Rust | own, in C             |
| Connects to               | any WebRTC endpoint        | any WebRTC endpoint      | a LiveKit server             | any WebRTC endpoint   |
| API                       | W3C, asyncio               | close to W3C, asyncio    | rooms and tracks, asyncio    | GObject signals       |
| Media path                | native                     | Python                   | native                       | native                |
| Video codecs              | VP8, VP9, AV1, H.264       | VP8, H.264               | VP8, VP9, AV1, H.264, H.265  | installed plugins     |
| Audio codecs              | Opus, G.722, G.711         | Opus, G.722, G.711       | Opus, G.711                  | installed plugins     |
| Trickle ICE               | ✅                          | half                     | ✅                            | ✅                     |
| Simulcast                 | ✅ sending                  | ❌                        | ✅                            | since 1.22            |
| Encoded transforms        | ✅                          | ❌                        | ❌                            | —                     |
| End-to-end encryption     | ✅ SFrame                   | ❌                        | ✅ AES-GCM                    | —                     |
| Free-threaded Python      | ✅ 3.14t, 3.15t             | —                        | —                            | GIL turned back on    |
| Python                    | 3.9–3.15                   | 3.10+                    | 3.9+                         | 3.10–3.14             |
| Wheels                    | Linux, macOS, Windows      | pure Python              | Linux, macOS, Windows        | macOS, Windows        |
| Tested with               | browsers' web-platform-tests | own suite, browser interop | own suite                 | own unit tests        |
| Latest release            | 0.1.0 beta, Oct 2026       | 1.15.0 stable, Jul 2026  | 1.1.21, Oct 2026             | 1.28.8, Oct 2026      |

— means the documentation doesn't say.

- **Media path.** Native means RTP, encoding and decoding run outside Python, and your code sees frames. aiortc runs
  RTP, RTCP and its jitter buffer in Python, with DTLS by OpenSSL, SRTP by libsrtp and codecs by FFmpeg.
- **H.264.** Python WebRTC uses VideoToolbox on macOS, and Cisco's OpenH264 elsewhere after one
  `openh264.install()` call: it never bundles H.264. See [H.264](h264.md). aiortc encodes with x264 from PyAV's
  wheels. LiveKit uses hardware encoders where it has them and a bundled OpenH264 otherwise.
- **LiveKit.** H.265 needs a hardware encoder: VideoToolbox on macOS, NVENC on Linux x86_64. Opus and G.711 are the
  server's default audio codecs.
- **GStreamer.** Its Windows wheels for 3.13t and 3.14t ship PyGObject 3.50, which doesn't declare free-threading
  support, so Python turns the GIL back on. It has no Linux wheels: Linux distributions package it.
- **Tests.** Python WebRTC runs the browsers' web-platform-tests unmodified, through a binding shim in
  [`tests/wpt`](https://github.com/MarshalX/python-webrtc/tree/main/tests/wpt), whose `expectations.json` lists what
  doesn't pass.

## Performance

The [benchmarks](../benchmarks.md) compare Python WebRTC with aiortc on one Apple M1. Python WebRTC opens a data
channel in 3.5 ms against 29.0 ms, moves 7.7–14.6x the data and spends 25–70% of aiortc's CPU on audio. aiortc uses
less memory per connection and less CPU per frame sending VP8 and receiving video calls; the benchmarks page explains
why. The LiveKit SDK and GStreamer aren't measured.

## Sources

The facts about the other libraries, as checked on 24 October 2026. Links to code point at the release compared.

:::{dropdown} Show the sources

**aiortc**

- The [README](https://github.com/aiortc/aiortc): the Python implementation on asyncio, ORTC, half-trickle ICE, and
  interop testing with Chrome and Firefox.
- The [codec list](https://github.com/aiortc/aiortc/blob/1.15.0/src/aiortc/codecs/__init__.py), the
  [H.264 codec](https://github.com/aiortc/aiortc/blob/1.15.0/src/aiortc/codecs/h264.py) on x264 and FFmpeg, and the
  [changelog](https://aiortc.readthedocs.io/en/latest/changelog.html): G.722 since 1.13.0, PyAV for every codec since
  1.12.0.
- The [API reference](https://aiortc.readthedocs.io/en/latest/api.html): the ORTC objects, and no send encodings,
  simulcast or encoded transforms.
- The [jitter buffer](https://github.com/aiortc/aiortc/blob/1.15.0/src/aiortc/jitterbuffer.py), and the
  [pyproject.toml](https://github.com/aiortc/aiortc/blob/1.15.0/pyproject.toml) with its dependencies on PyAV,
  pyOpenSSL and pylibsrtp.
- [PyPI](https://pypi.org/project/aiortc/): version 1.15.0 of 13 July 2026, Python 3.10+, the Production/Stable
  classifier and the single `py3-none-any` wheel.

**LiveKit SDK**

- The [README](https://github.com/livekit/python-sdks): rooms, the connection to LiveKit Cloud or a self-hosted
  server, Python 3.9+, and the table of hardware codecs by platform.
- The [Rust SDK](https://github.com/livekit/rust-sdks) it is built on, its
  [`libwebrtc` crate](https://docs.rs/crate/libwebrtc/latest), "Livekit safe bindings to libwebrtc", and, at the
  commit 1.1.21 builds on, the
  [`.gclient`](https://github.com/livekit/rust-sdks/blob/5a656c4bc4bc5c4f7fad17ab69044db3b487dfeb/webrtc-sys/libwebrtc/.gclient)
  that pins `m150_release` and the
  [session](https://github.com/livekit/rust-sdks/blob/5a656c4bc4bc5c4f7fad17ab69044db3b487dfeb/livekit/src/rtc_engine/rtc_session.rs)
  that trickles candidates over LiveKit's signalling.
- The [`TrackPublishOptions` definition](https://github.com/livekit/rust-sdks/blob/main/livekit-ffi/protocol/room.proto)
  and the [advanced media guide](https://docs.livekit.io/transport/media/advanced/): simulcast.
- The server's [default codecs](https://github.com/livekit/livekit/blob/master/pkg/config/config.go): Opus and G.711.
- The Python reference: its [modules](https://docs.livekit.io/reference/python/livekit/rtc/index.html), with no
  encoded-frame transform (`encoded_video` publishes frames encoded elsewhere), and
  [E2EE](https://docs.livekit.io/reference/python/livekit/rtc/e2ee.html), with AES-GCM. The
  [encryption guide](https://docs.livekit.io/transport/encryption/start/).
- The [tests workflow](https://github.com/livekit/python-sdks/blob/rtc-v1.1.21/.github/workflows/tests.yml).
- [PyPI](https://pypi.org/project/livekit/): version 1.1.21 of 16 October 2026 and its wheels.

**GStreamer webrtcbin**

- The [element's documentation](https://gstreamer.freedesktop.org/documentation/webrtc/index.html): its package, its
  signals (`create-offer`, `on-ice-candidate`, `add-ice-candidate` and others) and "implements the majority of the
  W3's peerconnection API".
- The [rtp plugin](https://gstreamer.freedesktop.org/documentation/rtp/index.html)'s payloaders, and the
  [AV1](https://gstreamer.freedesktop.org/documentation/rsrtp/rtpav1pay.html) one.
- The [1.22 release notes](https://gstreamer.freedesktop.org/releases/1.22/): "Initial support for sending or
  receiving simulcast streams".
- The [1.28 release notes](https://gstreamer.freedesktop.org/releases/1.28/): the wheels for macOS and Windows, and
  1.28.8 of 8 October 2026. The [Linux install guide](https://gstreamer.freedesktop.org/documentation/installing/on-linux.html):
  "included in all Linux distributions".
- The [unit tests](https://gitlab.freedesktop.org/gstreamer/gstreamer/-/blob/1.28.8/subprojects/gst-plugins-bad/tests/check/elements/webrtcbin.c)
  of webrtcbin.
- [PyPI](https://pypi.org/project/gstreamer-python/): `gstreamer-python` 1.28.8, its wheels for CPython 3.10–3.14 and
  the free-threaded ones for Windows.
- The [build recipe](https://gitlab.freedesktop.org/gstreamer/cerbero/-/blob/1.28/recipes/pygobject.recipe) of the
  wheels' PyGObject 3.50.2, its [module](https://gitlab.gnome.org/GNOME/pygobject/-/blob/3.50.2/gi/gimodule.c), and
  Python's [free-threading guide](https://docs.python.org/3/howto/free-threading-python.html): "The GIL may also
  automatically be enabled when importing a C-API extension module that is not explicitly marked as supporting free
  threading."

:::
