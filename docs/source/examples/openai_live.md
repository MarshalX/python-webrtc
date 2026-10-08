# Voice chat with OpenAI GPT-Live

Talks to the model through your microphone and speakers, with live transcripts in the terminal. It needs no server, only an
API key.

```bash
OPENAI_API_KEY=sk-... uv run https://raw.githubusercontent.com/MarshalX/python-webrtc/main/examples/openai_live.py
```

It connects with [WARP](../guides/field-trials.md#warp), which saves round trips when the call starts. `--no-warp`
connects the usual way, and `-v` logs how long each step took after the offer.

```{literalinclude} ../../../examples/openai_live.py
:language: python
:caption: examples/openai_live.py
```
