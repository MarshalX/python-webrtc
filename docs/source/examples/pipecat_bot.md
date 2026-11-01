---
description: "A Pipecat voice bot on Python WebRTC, served by Pipecat's development runner: speech to text, a model and text to speech, or an echo with no keys."
---

# Pipecat voice bot

A [Pipecat](https://www.pipecat.ai) bot on [`webrtc.pipecat`](../guides/pipecat.md), served by Pipecat's development
runner. With keys of [Deepgram](https://deepgram.com), [OpenAI](https://platform.openai.com) and
[Cartesia](https://cartesia.ai), it's an interruptible voice assistant:

```bash
export DEEPGRAM_API_KEY=... OPENAI_API_KEY=... CARTESIA_API_KEY=...
uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/pipecat_bot.py
```

With `--echo`, or without the keys, it sends your voice back. Open <http://localhost:7860> and press Connect.

```{literalinclude} ../../../examples/pipecat_bot.py
:language: python
:caption: examples/pipecat_bot.py
```
