# Quickstart

## Installation

```bash
pip install wrtc
```

The package is `wrtc` on PyPI, and `webrtc` in Python. Wheels are pre-built for the
[supported platforms](index.md#supported-platforms). Elsewhere pip builds it from sources, which needs CMake 3.26+
and a C++20 compiler (Clang on Linux, Apple Clang on macOS, MSVC on Windows). The prebuilt libwebrtc is downloaded
once and cached, so nothing else has to be installed.

To build from sources on a supported platform too:

```bash
pip install wrtc --no-binary wrtc
```

## Two peers and a data channel

A connection needs two ends. Here both live in one process, so passing the offer, the answer and the ICE candidates
between them is a function call. In a real application they travel over a signalling channel of your own: a
WebSocket, an HTTP request, anything.

```python
import asyncio

import webrtc


async def main():
    caller = webrtc.RTCPeerConnection()
    callee = webrtc.RTCPeerConnection()

    @caller.on('icecandidate')
    async def on_caller_candidate(event):
        if event.candidate is not None:
            await callee.add_ice_candidate(event.candidate)

    @callee.on('icecandidate')
    async def on_callee_candidate(event):
        if event.candidate is not None:
            await caller.add_ice_candidate(event.candidate)

    received = asyncio.get_running_loop().create_future()

    @callee.on('datachannel')
    def on_datachannel(event):
        event.channel.on('message', lambda message: received.set_result(message.data))

    channel = caller.create_data_channel('chat')
    channel.on('open', lambda _: channel.send('Hello from Python!'))

    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    await caller.set_remote_description(answer)

    print(await received)

    caller.close()
    callee.close()


if __name__ == '__main__':
    asyncio.run(main())
```

```text
Hello from Python!
```

What happens:

1. The caller creates a data channel, so its offer has a data section.
2. Each side applies its own description with `set_local_description` and the other side's with
   `set_remote_description`.
3. ICE candidates arrive in the `icecandidate` event as they are gathered. Each one is passed to the other side.
4. Once connected, the channel opens on both ends: the callee gets it in the `datachannel` event.

Everything is asynchronous and runs on the event loop: handlers are called there, and can be coroutines.

## Next steps

- [Connections](guides/connections.md): configuration, STUN and TURN servers, states.
- [Data channels](guides/data-channels.md): options, binary messages, back pressure.
- [Events](guides/events.md): registering and removing handlers.
- [Media](guides/media.md): sending and receiving audio and video.
- [Examples](examples/index.md): complete programs, from an echo peer to a voice chat.
