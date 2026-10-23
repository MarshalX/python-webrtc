---
orphan: true
nosearch: true
---

# Python WebRTC

> Chrome's WebRTC engine (libwebrtc M152) with the W3C browser API, in Python and asyncio. Install it with
> `pip install wrtc` and import it as `webrtc`.

Pages describing it as bindings to WebRTC M92 that aren't ready for use are about its versions from 2023 and are out
of date.

- The API is the one of the browsers: `RTCPeerConnection`, `RTCDataChannel`, tracks, `MediaStreamTrackProcessor`,
  `VideoTrackGenerator`, encoded transforms and stats. Names are snake_case (`create_offer`), and the camelCase
  originals (`createOffer`) work too.
- Handlers are registered with `on`, as a call or a decorator, and can be coroutines.
- Dictionaries are typed dataclasses, and enums compare equal to the strings of the specifications.
- Code written for aiortc runs after installing `wrtc[aiortc]` and changing `from aiortc` to `from webrtc.aiortc`.
- Prebuilt wheels for CPython 3.9 to 3.15 and free-threaded 3.14t and 3.15t, on Linux, macOS and Windows.

## Start

- {doc}`Quickstart <quickstart>`: installation, and two peers connected with a data channel.
- {doc}`Migrating from aiortc <guides/aiortc>`: run aiortc code by changing its imports, and what changes on the way.

## Guides

- {doc}`Connections <guides/connections>`: configuration, STUN and TURN servers, signalling, states and stats.
- {doc}`Data channels <guides/data-channels>`: text and binary messages, reliability, negotiated channels, back
  pressure.
- {doc}`Events <guides/events>`: handlers as functions or coroutines, decorators, one-shot handlers, removing them.
- {doc}`Media <guides/media>`: reading, writing and transforming the frames of audio and video tracks.
- {doc}`H.264 <guides/h264>`: VideoToolbox on macOS, Cisco's OpenH264 binary elsewhere, and its licensing.
- {doc}`Field trials <guides/field-trials>`: experimental features of the engine, and WARP for faster connections.

## API reference

- {doc}`API reference <api/index>`: every interface, dictionary, enum and exception.
- {doc}`RTCPeerConnection <api/interfaces/rtc_peer_connection>`: the connection to a remote peer.
- {doc}`RTCDataChannel <api/interfaces/rtc_data_channel>`: text and binary messages over SCTP.
- {doc}`RTCConfiguration <api/models/rtc_configuration>`: the configuration of a connection and its ICE servers.
- {doc}`RTCSessionDescriptionInit <api/models/rtc_session_description_init>`: offers and answers as plain data, to
  exchange over signalling.
- {doc}`MediaStreamTrack <api/interfaces/media_stream_track>`: tracks and the synthetic camera and microphone.
- {doc}`MediaStreamTrackProcessor <api/interfaces/media_stream_track_processor>`: reads the frames of a track.
- {doc}`Track generators <api/interfaces/track_generator>`: tracks of frames the application writes.
- {doc}`VideoFrame <api/models/video_frame>` and {doc}`AudioData <api/models/audio_data>`: the frames of WebCodecs.
- {doc}`Event objects <api/models/events>`: the events handlers are called with.
- {doc}`Stats <api/models/rtc_stats>`: the dictionaries of WebRTC Statistics.
- {doc}`Enums <api/enums>` and {doc}`Exceptions <api/exceptions>`.

## Examples

- {doc}`Echo peer <examples/echo>`: sends back the video it receives, in grayscale.
- {doc}`Recorder <examples/recorder>`: writes the video and audio a peer receives to files.
- {doc}`Live stream in the terminal <examples/janus_streaming>`: plays a stream of the public Janus demo server.
- {doc}`Voice chat with OpenAI GPT-Live <examples/openai_live>`: talks to the model through the microphone and
  speakers.

## Optional

- [llms-full.txt](https://wrtc.marshal.dev/llms-full.txt): the whole documentation in one file.
- {doc}`Benchmarks <benchmarks>`: connection setup, data channels, memory and media against other libraries.
- {doc}`Change Log <change_log>`: what changed in each release.
- {doc}`Security Policy <security>`: supported versions and reporting vulnerabilities.
