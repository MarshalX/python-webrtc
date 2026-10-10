# Change Log

## Version 0.0.1

**XX.XX.2026**

**🔌 The whole WebRTC API is bound. Every interface, every method, every dictionary: all 154 binding issues of the [tracker](https://github.com/users/MarshalX/projects/1/views/1) are done, and the API goes beyond them**

**🎞 Media processing that not every browser ships yet: `MediaStreamTrackProcessor`, `VideoTrackGenerator` and `MediaStreamTrackGenerator`, with the `VideoFrame` and `AudioData` of WebCodecs**

**🔐 WebRTC Encoded Transform: the encoded frames of senders and receivers in Python with `RTCRtpScriptTransform`, and end-to-end encryption with SFrame**

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
* Support free-threaded Python: the extension runs without the GIL, with `cp314t` and `cp315t` wheels by [@MarshalX](https://github.com/MarshalX)
* Implement WebRTC spec APIs and event ordering for WPT by [@MarshalX](https://github.com/MarshalX) in [#195](https://github.com/MarshalX/python-webrtc/pull/195)
* Add MediaStreamTrackProcessor, track generators and WebCodecs frames by [@MarshalX](https://github.com/MarshalX) in [#197](https://github.com/MarshalX/python-webrtc/pull/197)
* Align WebIDL dictionaries with the spec as typed models by [@MarshalX](https://github.com/MarshalX) in [#212](https://github.com/MarshalX/python-webrtc/pull/212)
* Align the public API with the WPT WebIDL by [@MarshalX](https://github.com/MarshalX) in [#214](https://github.com/MarshalX/python-webrtc/pull/214)
* Type event handlers per event, add listener management methods by [@MarshalX](https://github.com/MarshalX) in [#215](https://github.com/MarshalX/python-webrtc/pull/215)
* Replace `to_async` with `call_native`, drop its timeout by [@MarshalX](https://github.com/MarshalX) in [#206](https://github.com/MarshalX/python-webrtc/pull/206)
* Add the OpenAI GPT-Live voice chat example by [@MarshalX](https://github.com/MarshalX) in [#198](https://github.com/MarshalX/python-webrtc/pull/198)
* Add field trials, connect the GPT-Live example with WARP, skip loopback candidates by [@MarshalX](https://github.com/MarshalX)
* Add the Janus streaming example by [@MarshalX](https://github.com/MarshalX) in [#205](https://github.com/MarshalX/python-webrtc/pull/205)
* Run original web-platform-tests through a PythonMonkey shim by [@MarshalX](https://github.com/MarshalX) in [#193](https://github.com/MarshalX/python-webrtc/pull/193)
* Sync tests with web-platform-tests by [@MarshalX](https://github.com/MarshalX) in [#192](https://github.com/MarshalX/python-webrtc/pull/192)
* Compare the public API with the WPT WebIDL by [@MarshalX](https://github.com/MarshalX) in [#211](https://github.com/MarshalX/python-webrtc/pull/211)
* Add Atheris fuzz targets, fix findings by [@MarshalX](https://github.com/MarshalX) in [#204](https://github.com/MarshalX/python-webrtc/pull/204)
* Add strict clang-format and clang-tidy, fix all findings by [@MarshalX](https://github.com/MarshalX) in [#203](https://github.com/MarshalX/python-webrtc/pull/203)
* Enable all ruff rules, fix findings by [@MarshalX](https://github.com/MarshalX) in [#210](https://github.com/MarshalX/python-webrtc/pull/210)
* Type check with Pyrefly at full strictness, fix findings by [@MarshalX](https://github.com/MarshalX) in [#213](https://github.com/MarshalX/python-webrtc/pull/213)
* Run tests on GitHub Actions by [@MarshalX](https://github.com/MarshalX) in [#187](https://github.com/MarshalX/python-webrtc/pull/187)
* Fix wrapper ownership: shared_ptr lifetimes, no factory leaks or dangling observers by [@MarshalX](https://github.com/MarshalX) in [#194](https://github.com/MarshalX/python-webrtc/pull/194)
* Fix the GC deadlock by releasing wrappers off libwebrtc threads by [@MarshalX](https://github.com/MarshalX) in [#199](https://github.com/MarshalX/python-webrtc/pull/199)
* Fix deadlocks, leaks and crashes found by sanitizers and chaos tests by [@MarshalX](https://github.com/MarshalX) in [#200](https://github.com/MarshalX/python-webrtc/pull/200)
* Fix `set_parameters` hanging when libwebrtc drops the callback by [@MarshalX](https://github.com/MarshalX) in [#208](https://github.com/MarshalX/python-webrtc/pull/208)
* Fix sender and receiver leaks by releasing handlers of ended tracks by [@MarshalX](https://github.com/MarshalX) in [#216](https://github.com/MarshalX/python-webrtc/pull/216)
* Keep unreferenced connections, channels and live tracks alive while they have handlers or pending work, until they close or their event loop closes by [@MarshalX](https://github.com/MarshalX)
* Fire `ended` on the remote tracks of a connection when it's closed, and keep a failed `RTCIceTransport` alive for an ICE restart by [@MarshalX](https://github.com/MarshalX)
* Deliver events and the results of native calls through a mailbox per event loop, so native threads never run Python; a native object has one wrapper, which takes no attributes, by [@MarshalX](https://github.com/MarshalX)
* Fix a cancelled operation of a connection breaking the operations queued before and after it by [@MarshalX](https://github.com/MarshalX)
* Fix the docs build with the current `sphinx-favicon` by [@MarshalX](https://github.com/MarshalX), closes [#186](https://github.com/MarshalX/python-webrtc/issues/186)
