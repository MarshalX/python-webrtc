## Examples

All examples are licensed under the [CC0 License](LICENSE) and are therefore fully
dedicated to the public domain. You can use them as the base for your own bots
without worrying about copyrights.

### [recorder.py](recorder.py)

**Recording received media with MediaStreamTrackProcessor.** Writes the video and audio a peer receives to raw I420 and PCM files.

### [echo.py](echo.py)

**Transforming video with a processor, a TransformStream and a VideoTrackGenerator.** Sends the received video back in grayscale.

### [browser_server.py](browser_server.py)

**A Python WebRTC server for a browser page.** Your camera comes back from Python in grayscale, and Python answers a chat over a data channel. Open the printed address and allow the camera:

```bash
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/browser_server.py
```

### [openai_live.py](openai_live.py)

**Voice chat with OpenAI GPT-Live.** Talks to the model through your microphone and speakers, with live transcripts in the terminal. No server: just an API key. Dependencies are declared inline, so [uv](https://docs.astral.sh/uv/) runs it with nothing to install:

```bash
OPENAI_API_KEY=sk-... uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/openai_live.py
```

### [gemini_live.py](gemini_live.py)

**Voice agent with Gemini Live.** A browser page talks to Gemini through a Python server that keeps the API key, over WebRTC to the page and a WebSocket to the Live API:

```bash
GEMINI_API_KEY=... uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/gemini_live.py
```

### [pipecat_bot.py](pipecat_bot.py)

**A Pipecat voice bot on Pipecat's development runner.** An interruptible voice assistant with Deepgram, OpenAI and Cartesia keys; with `--echo`, or without the keys, it echoes your voice. Needs Python 3.11+. Open http://localhost:7860 and press Connect:

```bash
export DEEPGRAM_API_KEY=... OPENAI_API_KEY=... CARTESIA_API_KEY=...
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/pipecat_bot.py
```

### [janus_streaming.py](janus_streaming.py)

**Watching a live stream in the terminal.** Plays a stream of the public [Janus](https://janus.conf.meetecho.com/) demo server: the video drawn with colored characters, the audio on your speakers, if there are any, so it runs on a server too. No account or key:

```bash
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/janus_streaming.py
```

### [whip_whep.py](whip_whep.py)

**Playing and publishing streams over WHIP and WHEP.** Plays the public demo stream of [Dolby OptiView](https://optiview.dolby.com/) in the terminal, or any WHEP endpoint, and `--whip` publishes instead. Where the OS has no H.264 codec, it downloads Cisco's OpenH264 once (OpenH264 Video Codec provided by Cisco Systems, Inc.). No account or key:

```bash
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/whip_whep.py
```
