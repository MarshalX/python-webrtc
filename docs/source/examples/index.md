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

:::{grid-item-card} {octicon}`broadcast;1em;sd-mr-1` Live stream in the terminal
:link: janus_streaming
:link-type: doc

Watches a public stream, with the video as colored characters and the audio on your speakers.
:::

:::{grid-item-card} {octicon}`unmute;1em;sd-mr-1` Voice chat with OpenAI GPT-Live
:link: openai_live
:link-type: doc

Talks to the model through your microphone and speakers.
:::

:::{grid-item-card} {octicon}`people;1em;sd-mr-1` Telegram group calls
:link: telegram_group_calls
:link-type: doc

Streams audio from a raw file to a group call.
:::

::::

```{toctree}
:hidden:

echo
recorder
janus_streaming
openai_live
telegram_group_calls
```
