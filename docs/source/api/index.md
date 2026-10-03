# API reference

Everything is importable from the package itself: `webrtc.RTCPeerConnection`, `webrtc.RTCConfiguration`,
`webrtc.RTCPeerConnectionState`. The pages follow the modules the objects are defined in.

::::{grid} 1 2 2 3
:gutter: 3

:::{grid-item-card} {octicon}`plug;1em;sd-mr-1` Interfaces
:link: interfaces/index
:link-type: doc

Connections, channels, tracks, transports, senders and receivers.
:::

:::{grid-item-card} {octicon}`package;1em;sd-mr-1` Models
:link: models/index
:link-type: doc

Dictionaries, frames, event objects and stats: the values the API takes and returns.
:::

:::{grid-item-card} {octicon}`list-unordered;1em;sd-mr-1` Enums
:link: enums
:link-type: doc

The string enums of the specifications.
:::

:::{grid-item-card} {octicon}`alert;1em;sd-mr-1` Exceptions
:link: exceptions
:link-type: doc

The `DOMException` names of the specifications.
:::

:::{grid-item-card} {octicon}`bell;1em;sd-mr-1` EventTarget
:link: events
:link-type: doc

Registering and removing event handlers.
:::

:::{grid-item-card} {octicon}`git-merge;1em;sd-mr-1` Streams
:link: streams
:link-type: doc

The readable, writable and transform streams of media processing.
:::

:::{grid-item-card} {octicon}`video;1em;sd-mr-1` OpenH264
:link: openh264
:link-type: doc

Enabling and disabling H.264.
:::

::::

```{toctree}
:hidden:

interfaces/index
models/index
enums
exceptions
events
streams
openh264
base
```
