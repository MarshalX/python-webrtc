# Live stream in the terminal

Plays a stream of the public [Janus](https://janus.conf.meetecho.com/) demo server. The video is drawn with colored
characters and the audio plays on your speakers. It needs no account or key:

```bash
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/janus_streaming.py
```

```{literalinclude} ../../../examples/janus_streaming.py
:language: python
:caption: examples/janus_streaming.py
```
