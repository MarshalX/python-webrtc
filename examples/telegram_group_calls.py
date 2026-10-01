#!/usr/bin/env python3
#
#  Copyright 2022 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""Plays a raw audio file to a Telegram group call, with MediaStreamTrackGenerator.

The file is 48 kHz stereo 16-bit PCM. Pyrogram reads its session from the SESSION_NAME, API_ID and API_HASH
environment variables.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import time
from typing import TYPE_CHECKING, BinaryIO, TypedDict

# pip install pytgcalls[pyrogram]==3.0.0.dev21
import pyrogram
from pytgcalls.mtproto.data import GroupCallWrapper
from pytgcalls.mtproto.data.update import UpdateGroupCallWrapper
from pytgcalls.mtproto.pyrogram_bridge import PyrogramBridge

import webrtc

if TYPE_CHECKING:
    from pytgcalls.mtproto.data.update import UpdateGroupCallParticipantsWrapper


class Fingerprint(TypedDict):
    """A DTLS fingerprint of the Telegram server."""

    fingerprint: str


class Candidate(TypedDict):
    """An ICE candidate of the Telegram server."""

    foundation: str
    component: str
    protocol: str
    priority: str
    ip: str
    port: str
    type: str
    generation: str


class Transport(TypedDict):
    """The transport of the Telegram server."""

    ufrag: str
    pwd: str
    fingerprints: list[Fingerprint]
    candidates: list[Candidate]


class CallParams(TypedDict):
    """The parameters of a joined call."""

    transport: Transport


def sdp_attributes(sdp: str) -> dict[str, str]:
    """The first value of each attribute (``a=name:value``) of an SDP."""
    attributes: dict[str, str] = {}
    for line in sdp.split('\r\n'):
        if line.startswith('a='):
            name, _, value = line[2:].partition(':')
            attributes.setdefault(name, value)
    return attributes


def join_params(offer: str) -> dict[str, object]:
    """The transport of the offer, as Telegram takes it to join a call."""
    attributes = sdp_attributes(offer)
    hash_, fingerprint = attributes['fingerprint'].split(' ')
    return {
        'fingerprints': [{'fingerprint': fingerprint, 'hash': hash_, 'setup': 'active'}],
        'pwd': attributes['ice-pwd'],
        'ssrc': int(attributes['ssrc'].split(' ')[0]),
        'ssrc-groups': [],
        'ufrag': attributes['ice-ufrag'],
    }


def build_answer(params: CallParams) -> str:
    """The SDP answer of the Telegram server."""
    transport = params['transport']
    candidates = '\n'.join(
        f'a=candidate:{c["foundation"]} {c["component"]} {c["protocol"]} {c["priority"]} {c["ip"]} {c["port"]} '
        f'typ {c["type"]} generation {c["generation"]}'
        for c in transport['candidates']
    )
    return f"""v=0
o=- {time.time()} 2 IN IP4 0.0.0.0
s=-
t=0 0
a=group:BUNDLE 0
a=ice-lite
m=audio 1 RTP/SAVPF 111 126
c=IN IP4 0.0.0.0
a=mid:0
a=ice-ufrag:{transport['ufrag']}
a=ice-pwd:{transport['pwd']}
a=fingerprint:sha-256 {transport['fingerprints'][0]['fingerprint']}
a=setup:passive
{candidates}
a=rtpmap:111 opus/48000/2
a=rtpmap:126 telephone-event/8000
a=fmtp:111 minptime=10; useinbandfec=1; usedtx=1
a=rtcp:1 IN IP4 0.0.0.0
a=rtcp-mux
a=rtcp-fb:111 transport-cc
a=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level
a=recvonly
"""


async def send_audio_data(generator: webrtc.MediaStreamTrackGenerator, file: BinaryIO) -> None:
    """Writes raw 48 kHz stereo 16-bit audio to the track, 10 ms at a time, at the pace of real time."""
    writer = generator.writable.get_writer()
    loop = asyncio.get_running_loop()
    start = loop.time()
    chunks = 0

    while (data := file.read(480 * 4)) != b'':  # 480 frames of 2 channels of 16 bits
        frames = len(data) // 4
        await writer.write(
            webrtc.AudioData(
                webrtc.AudioDataInit(
                    format='s16',
                    sample_rate=48000,
                    number_of_frames=frames,
                    number_of_channels=2,
                    timestamp=chunks * 10_000,
                    data=data[: frames * 4],
                )
            )
        )
        chunks += 1
        await asyncio.sleep(max(0.0, start + chunks / 100 - loop.time()))


async def main(input_peer: str, audio: BinaryIO) -> None:
    """Joins the group call of the peer and plays the audio to it."""
    client = pyrogram.Client(
        os.environ.get('SESSION_NAME'), api_hash=os.environ.get('API_HASH'), api_id=os.environ.get('API_ID')
    )
    await client.start()
    pc = webrtc.RTCPeerConnection()

    generator = webrtc.MediaStreamTrackGenerator('audio')
    pc.add_track(generator)

    offer = await pc.create_offer()
    await pc.set_local_description(offer)
    answered = asyncio.Event()

    async def on_update(update: UpdateGroupCallWrapper | UpdateGroupCallParticipantsWrapper) -> None:
        # only the parameters of the joined call matter, the first time they come
        if answered.is_set() or not isinstance(update, UpdateGroupCallWrapper):
            return
        if isinstance(update.call, GroupCallWrapper):
            answered.set()
            params: CallParams = json.loads(update.call.params.data)
            answer = build_answer(params)
            await pc.set_remote_description(
                webrtc.RTCSessionDescription(webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.answer, answer))
            )

    app = PyrogramBridge(client)
    app.register_group_call_native_callback(on_update, on_update)
    await app.get_and_set_group_call(input_peer)
    await app.resolve_and_set_join_as(None)

    def pre_update_processing() -> None:
        pass

    params = json.dumps(join_params(offer.sdp))
    await app.join_group_call(
        None, params, muted=False, video_stopped=False, pre_update_processing=pre_update_processing
    )
    await asyncio.wait_for(answered.wait(), 30)

    sending = asyncio.ensure_future(send_audio_data(generator, audio))

    await pyrogram.idle()
    sending.cancel()
    await client.stop()


if __name__ == '__main__':
    peer = input('Input peer:')
    filename = input('Input filename to play:')

    with pathlib.Path(filename).open('rb') as file:
        asyncio.run(main(peer, file))
