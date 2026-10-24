# WHIP and WHEP

Plays a live stream over [WHEP](https://www.rfc-editor.org/rfc/rfc9725) in the terminal, or publishes one over WHIP.
With no URL it plays the public demo stream of [Dolby OptiView](https://optiview.dolby.com/), with no account or key:

```bash
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/whip_whep.py
```

The demo stream is H.264. Where the OS has no H.264 codec, as on Linux and Windows, the example downloads Cisco's
OpenH264 binary once, and `--no-openh264` skips it. See [H.264](../guides/h264.md).

OpenH264 Video Codec provided by Cisco Systems, Inc.

To publish with `--whip` and play it back, a local [MediaMTX](https://github.com/bluenviron/mediamtx) server works:

```bash
docker run -d --rm --name wrtc-mediamtx -p 8889:8889 -p 8189:8189/udp bluenviron/mediamtx:latest
uv run whip_whep.py --whip http://localhost:8889/wrtc/whip
uv run whip_whep.py http://localhost:8889/wrtc/whep
docker stop wrtc-mediamtx
```

```{literalinclude} ../../../examples/whip_whep.py
:language: python
:caption: examples/whip_whep.py
```
