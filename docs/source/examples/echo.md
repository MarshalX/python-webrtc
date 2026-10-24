---
description: "A Python WebRTC peer that sends back the video it receives in grayscale, through a transform stream, as in a browser."
---

# Echo peer

Sends back the video it receives, in grayscale. A processor is piped through a transform stream into a generator,
as in a browser. Two connections in one process stand for the two peers.

```{literalinclude} ../../../examples/echo.py
:language: python
:caption: examples/echo.py
```
