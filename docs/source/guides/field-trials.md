# Field trials

The native WebRTC engine ships some features turned off, behind field trials. A trial has a name, like
`WebRTC-Sctp-Snap`, and a group, usually `Enabled`. Browsers set them with a command-line flag. In python-webrtc,
`webrtc.field_trials` sets them: a mapping of names to groups that works like {data}`os.environ`.

```python
import webrtc

webrtc.field_trials['WebRTC-Sctp-Snap'] = 'Enabled'
webrtc.field_trials.update({'WebRTC-IceHandshakeDtls': 'Enabled'})

pc = webrtc.RTCPeerConnection()
```

The `WRTC_FIELD_TRIALS` environment variable sets them without changing the code. It takes the format of the browsers'
flag, each name and group followed by a `/`:

```bash
WRTC_FIELD_TRIALS='WebRTC-Sctp-Snap/Enabled/WebRTC-IceHandshakeDtls/Enabled/' python app.py
```

It's read when `webrtc` is imported, and a malformed value fails the import. Code can then add trials or change
them. `str(webrtc.field_trials)` gives the same format back.

## Before the first connection

The engine reads the trials once, when it starts: on the first {class}`~webrtc.RTCPeerConnection` or
{class}`~webrtc.RTCIceTransport`. From then on they're fixed for the life of the process, and changing them raises
{class}`~webrtc.InvalidStateError`, even after every connection is closed. To try other trials, start a new process.

Trial names change between releases of the engine, which is libwebrtc M152 in this release. An unknown name is
accepted and does nothing, as it does in the browsers, so check the spelling.

## WARP

[WARP](https://datatracker.ietf.org/doc/draft-uberti-tsvwg-warp/) connects faster by saving round trips. It's made of four parts, and each of them works on its own: a peer that
lacks one falls back to the usual handshake for it.

| Part | Saves | How |
| --- | --- | --- |
| [DTLS 1.3](https://datatracker.ietf.org/doc/html/rfc9147) | 1 round trip of the DTLS handshake | On by default |
| [SNAP](https://datatracker.ietf.org/doc/draft-hancke-tsvwg-snap/) | up to 2 round trips: the SCTP handshake goes in the SDP (`a=sctp-init`) | `WebRTC-Sctp-Snap` |
| [SPED](https://datatracker.ietf.org/doc/draft-hancke-webrtc-sped/) | 1 round trip: the DTLS handshake rides on the ICE checks | `WebRTC-IceHandshakeDtls` |
| A negotiated data channel | the channel opens without asking the remote peer | `negotiated=True` and an `id` |

```python
webrtc.field_trials.update({'WebRTC-Sctp-Snap': 'Enabled', 'WebRTC-IceHandshakeDtls': 'Enabled'})

pc = webrtc.RTCPeerConnection()
events = pc.create_data_channel('events', webrtc.RTCDataChannelInit(negotiated=True, id=4))
```

The server has to know the `id` of the channel, so the signalling sends it along with the offer, as
[OpenAI's WARP guide](https://developers.openai.com/api/docs/guides/realtime-webrtc-warp) describes. The
[GPT-Live example](../examples/openai_live.md) connects this way.

With both trials, a data channel between two python-webrtc peers opens 50% sooner, and a GPT-Live session starts 62%
sooner once the API has answered.
