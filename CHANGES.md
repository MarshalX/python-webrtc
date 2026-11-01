# Change Log

## Unreleased

* Add `webrtc.pipecat`, Pipecat's SmallWebRTC transport on the native API, installed with `wrtc[pipecat]`, with `install_alias()` for Pipecat's development runner. See [Use with Pipecat](https://wrtc.marshal.dev/guides/pipecat/) by [@MarshalX](https://github.com/MarshalX)
* Add a Pipecat voice bot example by [@MarshalX](https://github.com/MarshalX)
* Add `webrtc.aiortc.install_alias()`, which makes `import aiortc` give the compat layer, for libraries that import aiortc themselves by [@MarshalX](https://github.com/MarshalX)
* Add aiortc's `rtp`, `jitterbuffer`, `utils` and `clock` modules and the ICE server helpers of `rtcicetransport` to the compat layer by [@MarshalX](https://github.com/MarshalX)
* Drop a compat layer track's buffered frames when its receiver's `_enabled` is set to `False`, and add the track's `_queue`, for libraries that skip stale frames by [@MarshalX](https://github.com/MarshalX)

## Version 0.1.0

**24.10.2026**

**🧪 The first beta: the API follows the specifications and is ready to build on, while compatibility between versions isn't guaranteed until 1.0.0**

**⚡ Data channels move 1.2–2.1 Gbps, 7.7–14.6x aiortc's throughput at 10–15% of its CPU per MB. See the [benchmarks](https://wrtc.marshal.dev/benchmarks/)**

**🚀 A data channel opens 3.5 ms after `createOffer`, 7–8x faster than aiortc, and `getStats` takes 1.7 instead of 4.2 ms**

**🎥 Simulcast for every encoder, and H.264 on macOS that recovers from encoder faults and falls back to OpenH264**

**🧭 Transceiver, ICE, SCTP and track state change with the events that report them, as in browsers**

**🧩 [Examples](https://wrtc.marshal.dev/examples/) of a server for a browser page, a Gemini Live voice agent, and WHIP/WHEP streams**

* Add simulcast for every encoder, on Windows too: each layer is sent in the negotiated codec at its scaled size, whether or not the encoder does simulcast itself. VP9 and AV1 need a `scalabilityMode` such as `L1T1` for each layer by [@MarshalX](https://github.com/MarshalX) in [#254](https://github.com/MarshalX/python-webrtc/pull/254)
* Fall back to OpenH264, once `await webrtc.openh264.install()` has run, when VideoToolbox can't encode or decode by [@MarshalX](https://github.com/MarshalX) in [#254](https://github.com/MarshalX/python-webrtc/pull/254)
* Show transceiver, ICE, SCTP and track state with the events that change them: `mid`, `currentDirection` and the selected candidate pair change when their event fires, not before by [@MarshalX](https://github.com/MarshalX) in [#259](https://github.com/MarshalX/python-webrtc/pull/259)
* Add a Python server for a browser page example: your camera comes back in grayscale, and Python answers a chat over a data channel by [@MarshalX](https://github.com/MarshalX) in [#268](https://github.com/MarshalX/python-webrtc/pull/268)
* Add a Gemini Live voice agent example, with the API key kept on the server by [@MarshalX](https://github.com/MarshalX) in [#268](https://github.com/MarshalX/python-webrtc/pull/268)
* Add a WHIP/WHEP example that plays a live stream in the terminal or publishes one by [@MarshalX](https://github.com/MarshalX) in [#268](https://github.com/MarshalX/python-webrtc/pull/268)
* Add llms.txt, Markdown versions of the docs pages and Context7 and DeepWiki configs by [@MarshalX](https://github.com/MarshalX) in [#265](https://github.com/MarshalX/python-webrtc/pull/265)
* Credit node-webrtc in the third-party licences by [@MarshalX](https://github.com/MarshalX) in [#262](https://github.com/MarshalX/python-webrtc/pull/262)
* Speed up connection setup: keep libsrtp initialized and the network list updated, start the network manager and create port allocators without waiting on the network thread by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Speed up the first connection by running libsrtp's self-tests on their own thread by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Gather a candidate pool without waits between phases, and add ICE candidates in one signaling task by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Cut thread hops from negotiation and `getStats`, and share concurrent `getStats` calls: 20 of them take 5.7 instead of 80.9 ms, renegotiation 22% less time and warm setup with trickle 18% less by [@MarshalX](https://github.com/MarshalX) in [#255](https://github.com/MarshalX/python-webrtc/pull/255)
* Cut signaling-thread waits from getters: `transceiver.mid` takes 1.0 instead of 9.8 µs, `sender.track` 38% less time, `getSelectedCandidatePair()` 46% less and renegotiation 15% less by [@MarshalX](https://github.com/MarshalX) in [#259](https://github.com/MarshalX/python-webrtc/pull/259)
* Speed up data channels on macOS and Linux with a second, connected socket for a busy peer. Set the `PythonWebRTC-ConnectedSockets` field trial to `Disabled` to turn it off by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Speed up data channel sends with one network-thread task per send, and skip the local address lookup on every UDP packet by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Convert received data channel messages once and deliver them with less Python per message by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Copy data channel messages once: 10–11% more throughput and 7–11% less CPU per MB for 1 KB messages by [@MarshalX](https://github.com/MarshalX) in [#252](https://github.com/MarshalX/python-webrtc/pull/252)
* Speed up event delivery, skip wake-ups while the event loop drains, and cache session descriptions between the events that change them by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Drop the unused audio processing and video render smoothing, which cost CPU on every received stream by [@MarshalX](https://github.com/MarshalX) in [#249](https://github.com/MarshalX/python-webrtc/pull/249)
* Send VP8 and H.264 at 720p with 6–9% less CPU per frame by [@MarshalX](https://github.com/MarshalX) in [#256](https://github.com/MarshalX/python-webrtc/pull/256)
* Wrap NV12 frames without copies, pass NV12 to VideoToolbox as it is, and pool frame buffers by [@MarshalX](https://github.com/MarshalX) in [#257](https://github.com/MarshalX/python-webrtc/pull/257)
* Copy video frame data once into pooled buffers, and convert VideoToolbox output to I420 in one pass by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Copy encoded frames less and cache RTP sources: 14% less CPU per transformed frame, `getSynchronizationSources()` in 1.3 instead of 14.8 µs. A transform now queues up to 60 unread frames instead of 120 by [@MarshalX](https://github.com/MarshalX) in [#258](https://github.com/MarshalX/python-webrtc/pull/258)
* Fix sockets raising SIGPIPE on macOS, which kills the process where its default handler is restored by [@MarshalX](https://github.com/MarshalX) in [#267](https://github.com/MarshalX/python-webrtc/pull/267)
* Fix data channel stalls under load: UDP sockets get a receive buffer of at least 8 MB, which `WebRTC-SetSocketReceiveBuffer` overrides. On Linux, raise `net.core.rmem_max` to allow it. See [Field trials](https://wrtc.marshal.dev/guides/field-trials/) by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Fix a VideoToolbox frame that fails after the encoder took it: the session restarts with a key frame by [@MarshalX](https://github.com/MarshalX) in [#254](https://github.com/MarshalX/python-webrtc/pull/254)
* Fix a connection kept alive after `close()` by the event loop it was bound to while closing by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Fix the operations of a closed event loop keeping their connections alive by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Fix the next operation starting before the code awaiting the previous one resumes, as in browsers by [@MarshalX](https://github.com/MarshalX) in [#259](https://github.com/MarshalX/python-webrtc/pull/259)
* Fix `addIceCandidate` without a remote description rejecting late; it now rejects at once by [@MarshalX](https://github.com/MarshalX) in [#261](https://github.com/MarshalX/python-webrtc/pull/261)
* Fix sends that fail as the remote end closes: they fire `error` with `data-channel-failure`, and their bytes stay in `bufferedAmount` by [@MarshalX](https://github.com/MarshalX) in [#252](https://github.com/MarshalX/python-webrtc/pull/252)
* Fix remote data channels collected before their `open` event by [@MarshalX](https://github.com/MarshalX) in [#259](https://github.com/MarshalX/python-webrtc/pull/259)
* Fix DTMF tones and gaps raised to longer minimums than the specification's by [@MarshalX](https://github.com/MarshalX) in [#253](https://github.com/MarshalX/python-webrtc/pull/253)
* Fix standalone ICE gathering waiting 1 s between phases and gathering passive TCP candidates, and gather IPv6 where the host has it by [@MarshalX](https://github.com/MarshalX) in [#253](https://github.com/MarshalX/python-webrtc/pull/253)
* Fix the end of candidates of an earlier remote description shown after an ICE restart by [@MarshalX](https://github.com/MarshalX) in [#253](https://github.com/MarshalX/python-webrtc/pull/253)
* Fix the audio capture time, so the jitter doesn't jump after a send pause by [@MarshalX](https://github.com/MarshalX) in [#253](https://github.com/MarshalX/python-webrtc/pull/253)
* Fix `VideoTrackGenerator` frames written back to back dropped as duplicates by [@MarshalX](https://github.com/MarshalX) in [#256](https://github.com/MarshalX/python-webrtc/pull/256)
* Fix relayed remote video not scaled down for its encoder at low bitrates, and a sent track's own sinks getting the encoder's smaller frames by [@MarshalX](https://github.com/MarshalX) in [#256](https://github.com/MarshalX/python-webrtc/pull/256)
* Fix encoded frames a transform drops staying in memory while the event loop is busy or closed by [@MarshalX](https://github.com/MarshalX) in [#260](https://github.com/MarshalX/python-webrtc/pull/260)
* Fix writes to a writable stream slowing down as its queue grows by [@MarshalX](https://github.com/MarshalX) in [#264](https://github.com/MarshalX/python-webrtc/pull/264)
* Fix the empty reason in the OpenAI example's connection error by [@MarshalX](https://github.com/MarshalX) in [#264](https://github.com/MarshalX/python-webrtc/pull/264)
* Fix the OpenAI example printing the API key in `--help` by [@MarshalX](https://github.com/MarshalX) in [#268](https://github.com/MarshalX/python-webrtc/pull/268)
* Fix the memory benchmark table when a run stops early at the memory limit, and benchmark charts crashing on a zero value or baseline by [@MarshalX](https://github.com/MarshalX) in [#264](https://github.com/MarshalX/python-webrtc/pull/264)
* Fix the connections guide's advice to wait for complete ICE gathering, which can take about 40 seconds with a STUN server by [@MarshalX](https://github.com/MarshalX) in [#268](https://github.com/MarshalX/python-webrtc/pull/268)

## Version 0.0.2

**15.10.2026**

**🔄 Coming from aiortc? Install `wrtc[aiortc]`, change `from aiortc` to `from webrtc.aiortc`, and your code runs on Chrome's engine. See the [migration guide](https://wrtc.marshal.dev/guides/aiortc/)**

**⚡ Data channels 14x faster (57 to 812 Mbps), 47x over 10 connections, with 88% less CPU per MB**

**🪶 80% less memory per audio connection, 27% less per data channel connection, 1450 connections instead of 200**

**📊 [Benchmarks](https://wrtc.marshal.dev/benchmarks/) against aiortc, Pion, libdatachannel and webrtc-rs: against aiortc, connections open 5–7x faster, a data channel moves 4.5–9x more data, and audio costs less CPU**

**🧪 Test coverage up to 93.4% for C++ and 99.0% for Python, with the bugs it found fixed**

* Add an aiortc compatibility layer with a migration guide by [@MarshalX](https://github.com/MarshalX) in [#245](https://github.com/MarshalX/python-webrtc/pull/245)
* Add benchmarks against four WebRTC libraries, with results and charts by [@MarshalX](https://github.com/MarshalX) in [#242](https://github.com/MarshalX/python-webrtc/pull/242)
* Add a benchmarks page to the docs, linked from the README and the docs home by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Speed up data channels: callbacks run on the network thread, every queued UDP datagram is read on a read event by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Wake event loops through the mailbox's eventfd or pipe instead of the Dispatcher thread: a native event reaches Python in 45 instead of 84 µs (p50), the Dispatcher stays for Windows by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Wait with kqueue on macOS by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Skip empty gathering phases: setup without trickle takes 5 instead of 125 ms by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Drop the RTC event log, share one receive buffer per thread, stop listening on TCP and regathering by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Cut audio CPU per stream by 41–47% by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Play Janus streams without an audio output, as on servers by [@MarshalX](https://github.com/MarshalX) in [#239](https://github.com/MarshalX/python-webrtc/pull/239)
* Fix `balanced` and `maintain-framerate` never lowering the resolution by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Fix active TCP candidates rejected as a bad port by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Fix data channel messages arriving before the channel is announced, and a channel released before its last message is sent by [@MarshalX](https://github.com/MarshalX) in [#243](https://github.com/MarshalX/python-webrtc/pull/243)
* Fix sends from the `datachannel` handler lost before the channel opens by [@MarshalX](https://github.com/MarshalX) in [#247](https://github.com/MarshalX/python-webrtc/pull/247)
* Fix SFrame video recovery, and H.264 and AV1 with raw packetization by [@MarshalX](https://github.com/MarshalX) in [#240](https://github.com/MarshalX/python-webrtc/pull/240)
* Fix descriptions lost and `iceGatheringState` reading `complete` after `close()` by [@MarshalX](https://github.com/MarshalX) in [#240](https://github.com/MarshalX/python-webrtc/pull/240)
* Fix key frame requests of a removed script transform never settling by [@MarshalX](https://github.com/MarshalX) in [#240](https://github.com/MarshalX/python-webrtc/pull/240)
* Fix the received `captureTime` counted from the NTP epoch by [@MarshalX](https://github.com/MarshalX) in [#240](https://github.com/MarshalX/python-webrtc/pull/240)
* Fix rollback allowed in the pranswer states by [@MarshalX](https://github.com/MarshalX) in [#240](https://github.com/MarshalX/python-webrtc/pull/240)
* Fix a `ValueError` in `set_parameters` for a codec without a MIME type by [@MarshalX](https://github.com/MarshalX) in [#240](https://github.com/MarshalX/python-webrtc/pull/240)
* Fix `maxMessageSize` of a dropped or closed SCTP transport by [@MarshalX](https://github.com/MarshalX) in [#240](https://github.com/MarshalX/python-webrtc/pull/240)
* Fix remote video sent on to another connection, and a local description missing the candidates gathered after the remote one was read by [@MarshalX](https://github.com/MarshalX) in [#245](https://github.com/MarshalX/python-webrtc/pull/245)
* Fix a loop closed while its drain was scheduled never being released by [@MarshalX](https://github.com/MarshalX) in [#241](https://github.com/MarshalX/python-webrtc/pull/241)
* Fix a closing connection and its channels being active but unbound, and loop release by [@MarshalX](https://github.com/MarshalX) in [#244](https://github.com/MarshalX/python-webrtc/pull/244)
* Fix a watched loop's state never released after the loop closes by [@MarshalX](https://github.com/MarshalX) in [#247](https://github.com/MarshalX/python-webrtc/pull/247)
* Fix an abort when a task queue is deleted from its own task by [@MarshalX](https://github.com/MarshalX) in [#247](https://github.com/MarshalX/python-webrtc/pull/247)
* Fix flaky waits in tests on free-threaded builds and slow cores by [@MarshalX](https://github.com/MarshalX) in [#241](https://github.com/MarshalX/python-webrtc/pull/241)
* Run tests in parallel and fix the test races it exposes by [@MarshalX](https://github.com/MarshalX) in [#247](https://github.com/MarshalX/python-webrtc/pull/247)

## Version 0.0.1

**12.10.2026**

**🔌 The whole WebRTC API is bound. Every interface, every method, every dictionary: all 154 binding issues of the [tracker](https://github.com/users/MarshalX/projects/1/views/1) are done, and the API goes beyond them**

**🎞 Media processing that not every browser ships yet: `MediaStreamTrackProcessor`, `VideoTrackGenerator` and `MediaStreamTrackGenerator`, with the `VideoFrame` and `AudioData` of WebCodecs**

**🔐 WebRTC Encoded Transform: the encoded frames of senders and receivers in Python with `RTCRtpScriptTransform`, and end-to-end encryption with SFrame**

**🎥 H.264 without bundling it: VideoToolbox on macOS, offered by default, and Cisco's OpenH264 binary on request elsewhere**

**🚀 Field trials and WARP: DTLS 1.3, SNAP and SPED cut round trips off connection setup**

**⚡ libwebrtc M152, pre-built wheels for Linux (x86_64 and aarch64), macOS and Windows, CPython 3.9 – 3.15, free-threaded 3.14t and 3.15t too**

**🧪 The public API follows the WebIDL of the specifications and runs the original web-platform-tests**

**📚 Fully reworked [docs website](https://wrtc.marshal.dev): a new theme, guides, examples and the full API reference**

What is bound, by specification:

* [WebRTC](https://w3c.github.io/webrtc-pc/): `RTCPeerConnection`, `RTCDataChannel`, `RTCRtpTransceiver`, `RTCRtpSender`, `RTCRtpReceiver`, `RTCDtlsTransport`, `RTCIceTransport`, `RTCSctpTransport`, `RTCDTMFSender`, `RTCCertificate`, `RTCIceCandidate`, `RTCSessionDescription`, with every method, attribute, event and dictionary
* [WebRTC Extensions](https://w3c.github.io/webrtc-extensions/): standalone `RTCIceTransport`, RTP header encryption, and more
* [WebRTC Statistics](https://w3c.github.io/webrtc-stats/): 19 typed stats objects in `RTCStatsReport`
* [WebRTC Encoded Transform](https://w3c.github.io/webrtc-encoded-transform/): `RTCRtpScriptTransform`, `RTCEncodedVideoFrame`, `RTCEncodedAudioFrame`, and SFrame (RFC 9605)
* [Media Capture and Streams](https://w3c.github.io/mediacapture-main/): `MediaStream`, `MediaStreamTrack` with constraints, settings and capabilities, and `MediaDevices` with a synthetic camera and microphone
* [MediaStreamTrack Insertable Media Processing](https://w3c.github.io/mediacapture-transform/): `MediaStreamTrackProcessor`, `VideoTrackGenerator`, and `MediaStreamTrackGenerator`
* [WebCodecs](https://w3c.github.io/webcodecs/): `VideoFrame` and `AudioData`
* [Streams](https://streams.spec.whatwg.org/): `ReadableStream`, `WritableStream` and `TransformStream`, with piping and async iteration

In numbers: 229 public classes, 50 enums with the string values of the specifications, 18 exceptions named after their `DOMException`, and the camelCase names of the specifications next to the snake_case ones.

* Migrate to prebuilt libwebrtc M152, scikit-build-core and single cibuildwheel CI by [@MarshalX](https://github.com/MarshalX) in [#191](https://github.com/MarshalX/python-webrtc/pull/191)
* Split wheel builds per Python version and cache libwebrtc by [@MarshalX](https://github.com/MarshalX) in [#196](https://github.com/MarshalX/python-webrtc/pull/196)
* Add Linux aarch64 wheels by [@MarshalX](https://github.com/MarshalX) in [#207](https://github.com/MarshalX/python-webrtc/pull/207)
* Support free-threaded Python with `cp314t` and `cp315t` wheels, add CPython 3.15 by [@MarshalX](https://github.com/MarshalX) in [#232](https://github.com/MarshalX/python-webrtc/pull/232)
* Implement WebRTC spec APIs and event ordering for WPT by [@MarshalX](https://github.com/MarshalX) in [#195](https://github.com/MarshalX/python-webrtc/pull/195)
* Add MediaStreamTrackProcessor, track generators and WebCodecs frames by [@MarshalX](https://github.com/MarshalX) in [#197](https://github.com/MarshalX/python-webrtc/pull/197)
* Align WebIDL dictionaries with the spec as typed models by [@MarshalX](https://github.com/MarshalX) in [#212](https://github.com/MarshalX/python-webrtc/pull/212)
* Align the public API with the WPT WebIDL by [@MarshalX](https://github.com/MarshalX) in [#214](https://github.com/MarshalX/python-webrtc/pull/214)
* Type event handlers per event, add listener management methods by [@MarshalX](https://github.com/MarshalX) in [#215](https://github.com/MarshalX/python-webrtc/pull/215)
* Add H.264 through Cisco's OpenH264 binary, downloaded on request by [@MarshalX](https://github.com/MarshalX) in [#218](https://github.com/MarshalX/python-webrtc/pull/218)
* Add H.264 on macOS through VideoToolbox, offered by default by [@MarshalX](https://github.com/MarshalX) in [#219](https://github.com/MarshalX/python-webrtc/pull/219)
* Encode H.264 with our own VideoToolbox session: AutoLevel, no rate freeze, High for Chrome by [@MarshalX](https://github.com/MarshalX) in [#233](https://github.com/MarshalX/python-webrtc/pull/233)
* Match browsers on SDP munging, connection states, `setParameters` and close by [@MarshalX](https://github.com/MarshalX) in [#227](https://github.com/MarshalX/python-webrtc/pull/227)
* Replace `to_async` with `call_native`, drop its timeout by [@MarshalX](https://github.com/MarshalX) in [#206](https://github.com/MarshalX/python-webrtc/pull/206)
* Add the OpenAI GPT-Live voice chat example by [@MarshalX](https://github.com/MarshalX) in [#198](https://github.com/MarshalX/python-webrtc/pull/198)
* Add field trials, connect the GPT-Live example with WARP, skip loopback candidates by [@MarshalX](https://github.com/MarshalX) in [#225](https://github.com/MarshalX/python-webrtc/pull/225)
* Add the Janus streaming example by [@MarshalX](https://github.com/MarshalX) in [#205](https://github.com/MarshalX/python-webrtc/pull/205)
* Play Janus streams in stereo by munging the Opus answer by [@MarshalX](https://github.com/MarshalX) in [#234](https://github.com/MarshalX/python-webrtc/pull/234)
* Rework the docs website with guides, examples and the API reference by [@MarshalX](https://github.com/MarshalX) in [#217](https://github.com/MarshalX/python-webrtc/pull/217)
* Rewrite the API docs with MDN links by [@MarshalX](https://github.com/MarshalX) in [#221](https://github.com/MarshalX/python-webrtc/pull/221)
* Run original web-platform-tests through a PythonMonkey shim by [@MarshalX](https://github.com/MarshalX) in [#193](https://github.com/MarshalX/python-webrtc/pull/193)
* Sync tests with web-platform-tests by [@MarshalX](https://github.com/MarshalX) in [#192](https://github.com/MarshalX/python-webrtc/pull/192)
* Compare the public API with the WPT WebIDL by [@MarshalX](https://github.com/MarshalX) in [#211](https://github.com/MarshalX/python-webrtc/pull/211)
* Add Atheris fuzz targets, fix findings by [@MarshalX](https://github.com/MarshalX) in [#204](https://github.com/MarshalX/python-webrtc/pull/204)
* Add strict clang-format and clang-tidy, fix all findings by [@MarshalX](https://github.com/MarshalX) in [#203](https://github.com/MarshalX/python-webrtc/pull/203)
* Enable all ruff rules, fix findings by [@MarshalX](https://github.com/MarshalX) in [#210](https://github.com/MarshalX/python-webrtc/pull/210)
* Type check with Pyrefly at full strictness, fix findings by [@MarshalX](https://github.com/MarshalX) in [#213](https://github.com/MarshalX/python-webrtc/pull/213)
* Run tests on GitHub Actions by [@MarshalX](https://github.com/MarshalX) in [#187](https://github.com/MarshalX/python-webrtc/pull/187)
* Build on Ubuntu 22.04 in CI by [@MarshalX](https://github.com/MarshalX) in [#189](https://github.com/MarshalX/python-webrtc/pull/189)
* Make CI wheel builds and PyPI publish safe to retry by [@MarshalX](https://github.com/MarshalX) in [#226](https://github.com/MarshalX/python-webrtc/pull/226)
* Retry and cache CI downloads, build the sdist in each wheel job by [@MarshalX](https://github.com/MarshalX) in [#230](https://github.com/MarshalX/python-webrtc/pull/230)
* Run isolated tests as functions instead of code strings by [@MarshalX](https://github.com/MarshalX) in [#228](https://github.com/MarshalX/python-webrtc/pull/228)
* Add an unattended bug hunt with stacks, crash triage and C++/Python coverage by [@MarshalX](https://github.com/MarshalX) in [#231](https://github.com/MarshalX/python-webrtc/pull/231)
* Update the licence holder and headers, rebuild third-party licences for M152 by [@MarshalX](https://github.com/MarshalX) in [#220](https://github.com/MarshalX/python-webrtc/pull/220)
* Fix wrapper ownership: shared_ptr lifetimes, no factory leaks or dangling observers by [@MarshalX](https://github.com/MarshalX) in [#194](https://github.com/MarshalX/python-webrtc/pull/194)
* Fix the GC deadlock by releasing wrappers off libwebrtc threads by [@MarshalX](https://github.com/MarshalX) in [#199](https://github.com/MarshalX/python-webrtc/pull/199)
* Fix deadlocks, leaks and crashes found by sanitizers and chaos tests by [@MarshalX](https://github.com/MarshalX) in [#200](https://github.com/MarshalX/python-webrtc/pull/200)
* Fix `set_parameters` hanging when libwebrtc drops the callback by [@MarshalX](https://github.com/MarshalX) in [#208](https://github.com/MarshalX/python-webrtc/pull/208)
* Fix sender and receiver leaks by releasing handlers of ended tracks by [@MarshalX](https://github.com/MarshalX) in [#216](https://github.com/MarshalX/python-webrtc/pull/216)
* Fix spec bugs found by a stricter WPT by [@MarshalX](https://github.com/MarshalX) in [#222](https://github.com/MarshalX/python-webrtc/pull/222)
* Fix callback crashes, exit hangs and thread churn in the native layer by [@MarshalX](https://github.com/MarshalX) in [#223](https://github.com/MarshalX/python-webrtc/pull/223)
* Fix stream, track and event-loop bugs, and a wrapper deadlock by [@MarshalX](https://github.com/MarshalX) in [#224](https://github.com/MarshalX/python-webrtc/pull/224)
* Release tasks stranded by a closed test loop by [@MarshalX](https://github.com/MarshalX) in [#229](https://github.com/MarshalX/python-webrtc/pull/229)
* Rebuild object lifetime: unreferenced connections, channels and live tracks stay alive while they have handlers or pending work, native threads never run Python, wrappers take no attributes by [@MarshalX](https://github.com/MarshalX) in [#232](https://github.com/MarshalX/python-webrtc/pull/232)
* Fire `ended` on remote tracks when a connection closes, keep a failed `RTCIceTransport` for an ICE restart by [@MarshalX](https://github.com/MarshalX) in [#232](https://github.com/MarshalX/python-webrtc/pull/232)
* Fix a cancelled operation of a connection breaking the operations queued before and after it by [@MarshalX](https://github.com/MarshalX) in [#217](https://github.com/MarshalX/python-webrtc/pull/217)
* Fix the docs build with the current `sphinx-favicon` by [@MarshalX](https://github.com/MarshalX) in [#217](https://github.com/MarshalX/python-webrtc/pull/217), closes [#186](https://github.com/MarshalX/python-webrtc/issues/186)

## Version 0.0.0.dev9

**03.03.2022**

* Add `RTCDtlsTransport` and `RTCPeerConnection.add_transceiver`, with `RtpEncodingParameters`, `RtpTransceiverInit` and `MediaType`
* `transport` of `RTCRtpSender` and `RTCRtpReceiver`
* `MediaStreamTrack.kind` is a `MediaType`

## Version 0.0.0.dev8

**02.03.2022**

* Add `RTCRtpTransceiver`, `RTCRtpReceiver` and `RTCIceTransport`
* `get_transceivers`, `get_senders` and `get_receivers` of `RTCPeerConnection`
* Unified Plan is the default SDP semantics

## Version 0.0.0.dev7

**26.02.2022**

* Fix a segfault of the `MediaStream` from `get_user_media`
* Compare Python wrappers by their native objects
* Add the test suite with pytest

## Version 0.0.0.dev6

**10.02.2022**

* Bind `RTCError`, `SdpParseError` and the common exceptions; failed async calls raise them
* Fix a segfault in `RTCPeerConnection.close`
* Add the security policy

## Version 0.0.0.dev5

**09.02.2022**

* Fix a segfault of `RTCSessionDescription` (double destruction)
* Publish the sdist, include third-party licences in the package

## Version 0.0.0.dev4

**06.02.2022**

* Keep one Python wrapper per native object, which fixes many segfaults and bus errors
* Fix `MediaStream` pointers and the creation of `RTCRtpSender`
* Docs: favicons, OpenGraph, keyboard navigation and mobile layout

## Version 0.0.0.dev3

**03.02.2022**

* Docs on Read the Docs, a README with the logo

## Version 0.0.0.dev2

**03.02.2022**

* `RTCPeerConnection` with `create_offer`, `create_answer`, `set_local_description`, `set_remote_description`, `add_track` and `close`
* `MediaStream`, `MediaStreamTrack` and `get_user_media`
* `RTCRtpSender`, and `RTCAudioSource` to send PCM from Python
* The pure Python `webrtc` module over the native `wrtc`, with docs
* Wheels for Linux, macOS (Intel and Apple Silicon) and Windows

## Version 0.0.0.dev1

**03.01.2022**

* The first upload: the package skeleton
