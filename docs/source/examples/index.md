---
description: "Complete Python WebRTC programs: a server for a browser page, voice agents, WHIP and WHEP, live streams in the terminal and more."
---

# Examples

Complete programs from the [examples](https://github.com/MarshalX/python-webrtc/tree/main/examples) directory of the
repository. They are dedicated to the public domain under CC0: use them as the base of your own code.

The ones with dependencies declare them inline, so [uv](https://docs.astral.sh/uv/) runs them with nothing to
install.

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} {octicon}`sync;1em;sd-mr-1` Echo peer
:link: echo
:link-type: doc

Sends the received video back in grayscale.
:::

:::{grid-item-card} {octicon}`file-media;1em;sd-mr-1` Recorder
:link: recorder
:link-type: doc

Writes received video and audio to raw files.
:::

:::{grid-item-card} {octicon}`browser;1em;sd-mr-1` Browser and Python server
:link: browser_server
:link-type: doc

Sends your camera back from Python in grayscale, with a chat over a data channel.
:::

:::{grid-item-card} {octicon}`unmute;1em;sd-mr-1` Voice chat with OpenAI GPT-Live
:link: openai_live
:link-type: doc

Talks to the model through your microphone and speakers.
:::

:::{grid-item-card} {octicon}`comment-discussion;1em;sd-mr-1` Voice agent with Gemini Live
:link: gemini_live
:link-type: doc

Talks to Gemini from a browser page, through a Python server that keeps the API key.
:::

:::{grid-item-card} {octicon}`hubot;1em;sd-mr-1` Pipecat voice bot
:link: pipecat_bot
:link-type: doc

A Pipecat bot on the development runner: a voice pipeline, or an echo with no keys.
:::

:::{grid-item-card} {octicon}`broadcast;1em;sd-mr-1` Live stream in the terminal
:link: janus_streaming
:link-type: doc

Watches a public stream, with the video as colored characters and the audio on your speakers.
:::

:::{grid-item-card} {octicon}`broadcast;1em;sd-mr-1` WHIP and WHEP
:link: whip_whep
:link-type: doc

Plays a WHEP stream in the terminal, or publishes one over WHIP.
:::

::::

```{toctree}
:hidden:

echo
recorder
browser_server
openai_live
gemini_live
pipecat_bot
janus_streaming
whip_whep
```
