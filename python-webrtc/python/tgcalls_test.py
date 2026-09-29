#  tgcalls - a Python binding for C++ library by Telegram
#  pytgcalls - a library connecting the Python binding with MTProto
#  Copyright (C) 2020-2021 Il`ya (Marshal) <https://github.com/MarshalX>
#
#  This file is part of tgcalls and pytgcalls.
#
#  tgcalls and pytgcalls is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  tgcalls and pytgcalls is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License v3
#  along with tgcalls. If not, see <http://www.gnu.org/licenses/>.

import asyncio
import json
import os
import time

# pip install pytgcalls[pyrogram]==3.0.0.dev21
import pyrogram
import webrtc
from pytgcalls.mtproto.pyrogram_bridge import PyrogramBridge

remote_sdp = None


def parse_sdp(sdp):
    lines = sdp.split('\r\n')

    def lookup(prefix):
        for line in lines:
            if line.startswith(prefix):
                return line[len(prefix) :]

    info = {
        'fingerprint': lookup('a=fingerprint:').split(' ')[1],
        'hash': lookup('a=fingerprint:').split(' ')[0],
        'setup': lookup('a=setup:'),
        'pwd': lookup('a=ice-pwd:'),
        'ufrag': lookup('a=ice-ufrag:'),
    }
    ssrc = lookup('a=ssrc:')
    if ssrc:
        info['source'] = int(ssrc.split(' ')[0])

    return info


def get_params_from_parsed_sdp(info):
    return {
        'fingerprints': [{'fingerprint': info['fingerprint'], 'hash': info['hash'], 'setup': 'active'}],
        'pwd': info['pwd'],
        'ssrc': info['source'],
        'ssrc-groups': [],
        'ufrag': info['ufrag'],
    }


def build_answer(sdp):
    def add_candidates():
        candidates_sdp = []
        for cand in sdp['transport']['candidates']:
            candidates_sdp.append(
                f"a=candidate:{cand['foundation']} {cand['component']} {cand['protocol']} "
                f"{cand['priority']} {cand['ip']} {cand['port']} typ {cand['type']} "
                f"generation {cand['generation']}"
            )

        return '\n'.join(candidates_sdp)

    return f"""v=0
o=- {time.time()} 2 IN IP4 0.0.0.0
s=-
t=0 0   
a=group:BUNDLE 0
a=ice-lite
m=audio 1 RTP/SAVPF 111 126
c=IN IP4 0.0.0.0
a=mid:0
a=ice-ufrag:{sdp['transport']['ufrag']}
a=ice-pwd:{sdp['transport']['pwd']}
a=fingerprint:sha-256 {sdp['transport']['fingerprints'][0]['fingerprint']}
a=setup:passive
{add_candidates()}
a=rtpmap:111 opus/48000/2
a=rtpmap:126 telephone-event/8000
a=fmtp:111 minptime=10; useinbandfec=1; usedtx=1
a=rtcp:1 IN IP4 0.0.0.0
a=rtcp-mux
a=rtcp-fb:111 transport-cc
a=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level
a=recvonly
"""
    # a=sendrecv


async def group_call_participants_update_callback(_):
    pass


async def group_call_update_callback(update):
    global remote_sdp

    data = update.call.params.data
    remote_sdp = build_answer(json.loads(data))


async def send_audio_data(generator):
    """Writes test.raw (48 kHz stereo 16-bit) to the track, 10 ms at a time, at the pace of real time"""
    writer = generator.writable.get_writer()
    loop = asyncio.get_running_loop()
    start = loop.time()
    chunks = 0

    with open('test.raw', 'rb') as f:
        while data := f.read(480 * 4):  # 480 frames of 2 channels of 16 bits
            frames = len(data) // 4
            await writer.write(
                webrtc.AudioData(
                    format='s16',
                    sample_rate=48000,
                    number_of_frames=frames,
                    number_of_channels=2,
                    timestamp=chunks * 10_000,
                    data=data[: frames * 4],
                )
            )
            chunks += 1
            await asyncio.sleep(max(0.0, start + chunks / 100 - loop.time()))


async def main(client, input_peer):
    pc = webrtc.RTCPeerConnection()

    # stream = webrtc.get_user_media()
    # for track in stream.get_tracks():
    #     track.enabled = True
    #     pc.add_track(track, stream)

    generator = webrtc.MediaStreamTrackGenerator('audio')
    pc.add_track(generator)

    local_sdp = await pc.create_offer()
    await pc.set_local_description(local_sdp)

    app = PyrogramBridge(client)
    app.register_group_call_native_callback(group_call_participants_update_callback, group_call_update_callback)
    await app.get_and_set_group_call(input_peer)
    await app.resolve_and_set_join_as(None)

    def pre_update_processing():
        pass

    parsed_sdp = parse_sdp(local_sdp.sdp)
    payload = get_params_from_parsed_sdp(parsed_sdp)

    await app.join_group_call(None, json.dumps(payload), False, False, pre_update_processing)

    while not remote_sdp:
        await asyncio.sleep(0.1)
    # await asyncio.wait_for(REMOTE_ANSWER_EVENT.wait(), 30)

    # TODO allow to pass RTCSessionDescriptionInit
    await pc.set_remote_description(
        webrtc.RTCSessionDescription(webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.answer, remote_sdp))
    )

    sending = asyncio.ensure_future(send_audio_data(generator))

    # await asyncio.sleep(10)
    await pyrogram.idle()
    sending.cancel()


if __name__ == '__main__':
    pyro_client = pyrogram.Client(
        os.environ.get('SESSION_NAME'), api_hash=os.environ.get('API_HASH'), api_id=os.environ.get('API_ID')
    )
    pyro_client.start()

    peer = os.environ.get('PEER')

    asyncio.get_event_loop().run_until_complete(main(pyro_client, peer))
