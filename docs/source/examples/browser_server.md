---
description: "A Python WebRTC server for a browser page: your camera comes back in grayscale, and Python answers a chat over a data channel."
---

# Browser and Python server

A browser page sends your camera to Python, which sends it back in grayscale, and Python answers a chat over a data
channel. Open the printed address and allow the camera:

```bash
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/browser_server.py
```

Python reads the video with a {obj}`~webrtc.MediaStreamTrackProcessor`, pipes it through a
{obj}`~webrtc.TransformStream` and writes it to a {obj}`~webrtc.VideoTrackGenerator`. Browsers allow the camera only on
localhost or over HTTPS, so the server listens on localhost. Behind a strict NAT, pass your own TURN server with
`--turn`.

```{literalinclude} ../../../examples/browser_server.py
:language: python
:caption: examples/browser_server.py
```
