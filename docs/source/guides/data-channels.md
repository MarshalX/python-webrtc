# Data channels

An {obj}`~webrtc.RTCDataChannel` sends messages between the peers, over SCTP inside the encrypted connection. See {mdn}`RTCDataChannel`.

## Opening

One side creates the channel, and the other side gets it in the `datachannel` event once the connection is up:

```python
channel = caller.create_data_channel('chat')


@callee.on('datachannel')
def on_datachannel(event):
    print('new channel:', event.channel.label)
```

The first channel adds an SCTP transport to the offer. Once the connection has it, new channels open without a new
negotiation.

## Messages

{meth}`~webrtc.RTCDataChannel.send` takes text or bytes, once the channel fired `open`. The `message` event carries
them back as `str` or `bytes`:

```python
@channel.on('open')
def on_open(_event):
    channel.send('text')
    channel.send(b'\x00\x01')


@channel.on('message')
def on_message(event):
    print(repr(event.data))
```

## Options

{obj}`~webrtc.RTCDataChannelInit` sets how messages are delivered. By default a channel is reliable and ordered.
For data that is stale when late, like positions in a game, drop retransmissions:

```python
init = webrtc.RTCDataChannelInit(ordered=False, max_retransmits=0)
channel = pc.create_data_channel('positions', init)
```

The application can also negotiate a channel itself. Both sides then create it with the same `id`, and no
`datachannel` event fires.

```python
init = webrtc.RTCDataChannelInit(negotiated=True, id=0)
channel = pc.create_data_channel('game', init)
```

The other side may be a server that picks no channel of its own: it learns the `id` from the signalling, like the
`dcid` the [GPT-Live example](../examples/openai_live.md) posts with its offer. Such a channel opens without asking the
remote peer, which saves a round trip (see [WARP](field-trials.md#warp)).

## Back pressure

`send` queues the message and returns. To send a lot without growing the queue unbounded, watch
{attr}`~webrtc.RTCDataChannel.buffered_amount` and wait for `bufferedamountlow`:

```python
channel.buffered_amount_low_threshold = 1 << 20
low = asyncio.Event()
channel.on('bufferedamountlow', lambda _: low.set())

for chunk in chunks:
    if channel.buffered_amount > 4 << 20:
        low.clear()
        await low.wait()
    channel.send(chunk)
```

## Closing

{meth}`~webrtc.RTCDataChannel.close` closes the channel on both ends. Each end fires `close`, and the remote one
fires `closing` before it. Closing the connection closes its channels. A channel with handlers or data to send stays
alive until it closes (see [Events](events.md)).
