---
description: "A Gemini Live voice agent in the browser with live transcripts, through a Python WebRTC server that keeps the API key."
---

# Voice agent with Gemini Live

Talks to Gemini from a browser page, with live transcripts, through a Python server in the middle:

```text
browser  <-- WebRTC -->  Python server  <-- WebSocket -->  Gemini Live API
```

The server reads the microphone with a {obj}`~webrtc.MediaStreamTrackProcessor`, streams it to Gemini as 16 kHz PCM,
and writes Gemini's 24 kHz answer to a {obj}`~webrtc.MediaStreamTrackGenerator`. When you talk over Gemini, it drops
the rest of the answer.

## Why a server in the middle

Google's [Live API overview](https://ai.google.dev/gemini-api/docs/live-api) describes two ways to connect. A page can
connect to Gemini directly, with short-lived tokens in production, or go through your server. This example takes the
second way, with WebRTC to the browser, as the WebRTC partner integrations on that page do:

- The API key stays on the server, which sees every message and can add tools, logging or limits.
- The browser gets WebRTC's echo cancellation, jitter buffer and NAT traversal.
- Gemini gets the WebSocket it's specified with.

## Running it

Get a key in [Google AI Studio](https://aistudio.google.com/apikey). The free tier works, but Google uses what you send
on it to improve its products. See [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).

```bash
GEMINI_API_KEY=... uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/gemini_live.py
```

Open <http://localhost:8080> and press Talk. Anyone who can open the page talks on your key, so the server listens on
localhost.

```{literalinclude} ../../../examples/gemini_live.py
:language: python
:caption: examples/gemini_live.py
```
