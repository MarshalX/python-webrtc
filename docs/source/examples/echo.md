# Echo peer

Sends back the video it receives, in grayscale: a processor piped through a transform stream into a generator, as in
a browser. Two connections in one process stand for the two peers.

```{literalinclude} ../../../examples/echo.py
:language: python
:caption: examples/echo.py
```
