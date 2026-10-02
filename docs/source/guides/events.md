# Events

Connections, channels, tracks and transports fire the events of the specification. Every one of them is an
{obj}`~webrtc.utils.events.EventTarget`.

## Handlers

{meth}`~webrtc.utils.events.UniformEventTarget.on` registers a handler, called with the event object. It can be a
plain function or a coroutine function, and `on` works as a decorator too:

```python
@pc.on('track')
def on_track(event):
    print('new track:', event.track.kind)


@pc.on('icecandidate')
async def on_candidate(event):
    await signaling.send(event.candidate)


channel.on('message', lambda event: print(event.data))
```

The names are the ones of the specification, without the `on` prefix. A name the object doesn't fire raises
{obj}`ValueError`, which lists the names it does.

Handlers run on the event loop they were registered from, so they have to be registered from a running loop. The
events of libwebrtc threads are only scheduled there: a slow handler delays the next events, not the media.

## One-shot handlers

{meth}`~webrtc.utils.events.UniformEventTarget.once` registers a handler that is removed after its first call. To
wait for an event inline, resolve a future from it:

```python
opened = asyncio.get_running_loop().create_future()
channel.once('open', lambda event: opened.set_result(event))
await opened
```

## Removing handlers

```python
pc.remove_listener('track', on_track)  # one handler
pc.remove_all_listeners('track')  # every handler of an event
pc.off()  # every handler of every event
```

{meth}`~webrtc.utils.events.EventTarget.listeners` returns the handlers of an event, and
{meth}`~webrtc.utils.events.EventTarget.event_names` the events that have some. A handler is registered once:
registering it again does nothing.

## Errors

An exception in a handler doesn't stop the other handlers: it goes to the exception handler of the loop, which logs
it by default. Use {meth}`asyncio.loop.set_exception_handler` to handle them yourself.
