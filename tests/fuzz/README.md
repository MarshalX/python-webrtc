# Fuzzing

Coverage-guided fuzz targets for [Atheris](https://github.com/google/atheris) (libFuzzer for Python). The extension
is built with libFuzzer coverage, ASan and UBSan; libwebrtc isn't instrumented, but its `RTC_CHECK` aborts and
crashes are caught.

| Target | What it fuzzes |
| --- | --- |
| `video_frame` | `VideoFrame` from buffers, `copy_to` with rects, layouts and RGB conversions, frames of frames |
| `audio_data` | `AudioData` and `copy_to` with every format and layout conversion |
| `native_buffers` | The native `wrtc.VideoFrameBuffer` and `wrtc.copyAudioSamples` directly, without the Python checks |
| `generator` | `AudioData` and `VideoFrame` written to generators sent over a connection, read back by processors |
| `sframe` | The native SFrame of RFC 9605: headers, key derivation, decryption of arbitrary or tampered ciphertexts, round trips of every suite |
| `sframe_stream` | `SFrameEncryptorStream` and `SFrameDecryptorStream` with keys added, removed and rotated between chunks, checked against a model of the keys |
| `encoded_frame` | Script transforms of a connection rewriting, dropping, copying and reordering encoded frames, and SFrame transforms set and keyed mid-stream |

Linux only (Apple Clang has no libFuzzer), in the manylinux image; the build is kept in `build/fuzz`:

```sh
make fuzz T=video_frame O=-max_total_time=600
make fuzz T=audio_data O=tests/fuzz/crashes/audio_data-crash-...   # replays a crash
```

Only the documented exceptions are expected, and a few oracles check results (a frame or samples copied out as they
are give the same bytes, SFrame decrypts what it encrypted and nothing tampered). A crash becomes a regression test in
`tests/`.
