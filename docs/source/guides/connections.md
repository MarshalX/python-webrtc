# Connections

{obj}`~webrtc.RTCPeerConnection` is one end of a connection. Each end describes itself in an SDP description, and
the two exchange their descriptions and ICE candidates over a signalling channel the application provides.

## Configuration

A connection takes an {obj}`~webrtc.RTCConfiguration`. To connect across NATs, give it STUN and TURN servers:

```python
config = webrtc.RTCConfiguration(
    ice_servers=[
        webrtc.RTCIceServer(urls='stun:stun.l.google.com:19302'),
        webrtc.RTCIceServer(urls='turn:turn.example.com:3478', username='user', credential='secret'),
    ],
)
pc = webrtc.RTCPeerConnection(config)
```

Dictionaries of the specification are typed dataclasses, with the names in snake_case. Methods take them, not plain
dicts, so a misspelled member fails where it's written rather than being ignored.

## Signalling

The side that starts creates an offer, the other one answers:

```python
# the caller
offer = await pc.create_offer()
await pc.set_local_description(offer)
await signaling.send(offer)

# the callee
await pc.set_remote_description(offer)
answer = await pc.create_answer()
await pc.set_local_description(answer)
await signaling.send(answer)

# the caller again
await pc.set_remote_description(answer)
```

`signaling` stands for your own channel. Descriptions are {obj}`~webrtc.RTCSessionDescriptionInit` objects with a
`type` and an `sdp`, which is all a channel has to carry.

Candidates are gathered after `set_local_description`, and trickle in the `icecandidate` event. Send each one to the
other side, which adds it with {meth}`~webrtc.RTCPeerConnection.add_ice_candidate`. The last event has no candidate:
gathering is complete.

```python
@pc.on('icecandidate')
async def on_candidate(event):
    if event.candidate is not None:
        await signaling.send(event.candidate.to_json())
```

To skip trickling, wait for `ice_gathering_state` to be `'complete'` and send `pc.local_description`, which then has
every candidate in it.

## States

The state of a connection is in {attr}`~webrtc.RTCPeerConnection.connection_state`, and each change fires
`connectionstatechange`:

```python
@pc.on('connectionstatechange')
def on_state(_event):
    if pc.connection_state == 'failed':
        pc.restart_ice()
```

Enums are strings: `pc.connection_state == webrtc.RTCPeerConnectionState.connected` and
`pc.connection_state == 'connected'` are the same check.

## Stats

{meth}`~webrtc.RTCPeerConnection.get_stats` returns an {obj}`~webrtc.RTCStatsReport`, a mapping of ids to typed
stats objects:

```python
report = await pc.get_stats()
for stats in report.values():
    if stats.type == 'candidate-pair' and stats.nominated:
        print('round trip time:', stats.current_round_trip_time)
```

## Closing

{meth}`~webrtc.RTCPeerConnection.close` stops the transports and the media at once. A closed connection can't be
reused: create a new one.
