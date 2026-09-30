## Examples

All examples are licensed under the [CC0 License](LICENSE) and are therefore fully
dedicated to the public domain. You can use them as the base for your own bots
without worrying about copyrights.

### [telegram_group_calls.py](telegram_group_calls.py)

**Sending audio with MediaStreamTrackGenerator.** The example of connection establishing with Telegram Group Calls and streaming audio from .RAW file.

### [recorder.py](recorder.py)

**Recording received media with MediaStreamTrackProcessor.** Writes the video and audio a peer receives to raw I420 and PCM files.

### [echo.py](echo.py)

**Transforming video with a processor, a TransformStream and a VideoTrackGenerator.** Sends the received video back in grayscale.

### [openai_live.py](openai_live.py)

**Voice chat with OpenAI GPT-Live.** Talks to the model through your microphone and speakers, with live transcripts in the terminal. No server: just an API key. Dependencies are declared inline, so [uv](https://docs.astral.sh/uv/) runs it with nothing to install:

```
OPENAI_API_KEY=sk-... uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/openai_live.py
```

### [janus_streaming.py](janus_streaming.py)

**Watching a live stream in the terminal.** Plays a stream of the public [Janus](https://janus.conf.meetecho.com/) demo server: the video drawn with colored characters, the audio on your speakers. No account or key:

```
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/janus_streaming.py
```
