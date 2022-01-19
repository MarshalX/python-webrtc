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

import os
import json
import time
import asyncio
import threading

from test import Event, toAsync
import webrtc

# pip install pytgcalls[pyrogram]==3.0.0.dev21
import pyrogram
from pytgcalls.mtproto.pyrogram_bridge import PyrogramBridge


REMOTE_ANSWER_EVENT = None
remote_sdp = None


def parse_sdp(sdp):
    lines = sdp.split('\r\n')

    def lookup(prefix):
        for line in lines:
            if line.startswith(prefix):
                return line[len(prefix):]

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
        'fingerprints': [
            {
                'fingerprint': info['fingerprint'],
                'hash': info['hash'],
                'setup': 'active'
            }
        ],
        'pwd': info['pwd'],
        'ssrc': info['source'],
        'ssrc-groups': [],
        'ufrag': info['ufrag']
    }


def build_answer(sdp):
    def add_candidates():
        candidates_sdp = []
        for cand in sdp['transport']['candidates']:
            candidates_sdp.append(f"a=candidate:{cand['foundation']} {cand['component']} {cand['protocol']} "
                                  f"{cand['priority']} {cand['ip']} {cand['port']} typ {cand['type']} "
                                  f"generation {cand['generation']}")

        return '\n'.join(candidates_sdp)

    return f"""v=0
o=- {time.time()} 2 IN IP4 0.0.0.0
s=-
t=0 0   
a=group:BUNDLE audio
a=ice-lite
m=audio 1 RTP/SAVPF 111 126
c=IN IP4 0.0.0.0
a=mid:audio
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

    REMOTE_ANSWER_EVENT.set()


def send_audio_data(audio_source):
    def get_ms_time():
        return round(time.time() * 1000)

    last_read_ms = 0

    length = int(480 * 16 / 8 * 2)  # 2 channels with 16 bits per sample in 48khz

    f = open('test.raw', 'rb')

    while True:
        start_time = get_ms_time()

        if last_read_ms == 0 or start_time - last_read_ms >= 10:
            data = f.read(length)
            if not data:   # eof
                f.close()
                break

            event_data = webrtc.RTCOnDataEvent(data, length // 4)   # 2 channels
            event_data.channelCount = 2
            audio_source.onData(event_data)

            last_read_ms = start_time

        delta_time = get_ms_time() - start_time
        if delta_time < 10:
            time.sleep((10 - delta_time) / 1000)


async def main(client, input_peer):
    global REMOTE_ANSWER_EVENT
    REMOTE_ANSWER_EVENT = Event()

    pc = webrtc.RTCPeerConnection()

    # stream = webrtc.getUserMedia()
    # for track in stream.getTracks():
    #     pc.addTrack(track, stream)

    audio_source = webrtc.RTCAudioSource()
    track = audio_source.createTrack()
    pc.addTrack(track, None)

    local_sdp = await toAsync(pc.createOffer)
    await toAsync(pc.setLocalDescription)(local_sdp)

    app = PyrogramBridge(client)
    app.register_group_call_native_callback(
        group_call_participants_update_callback, group_call_update_callback
    )
    await app.get_and_set_group_call(input_peer)
    await app.resolve_and_set_join_as(None)

    def pre_update_processing():
        pass

    parsed_sdp = parse_sdp(local_sdp.sdp)
    payload = get_params_from_parsed_sdp(parsed_sdp)

    await app.join_group_call(None, json.dumps(payload), False, False, pre_update_processing)

    await asyncio.wait_for(REMOTE_ANSWER_EVENT.wait(), 30)

    answer_sdp_init = webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.answer, remote_sdp)
    answer_sdp = webrtc.RTCSessionDescription(answer_sdp_init)
    # TODO allow to pass RTCSessionDescriptionInit
    await toAsync(pc.setRemoteDescription)(answer_sdp)

    thread = threading.Thread(target=send_audio_data, args=(audio_source,))
    thread.daemon = True
    thread.start()

    await pyrogram.idle()


if __name__ == '__main__':
    pyro_client = pyrogram.Client(
        os.environ.get('SESSION_NAME'), api_hash=os.environ.get('API_HASH'), api_id=os.environ.get('API_ID')
    )
    pyro_client.start()

    peer = os.environ.get('PEER')

    asyncio.get_event_loop().run_until_complete(main(pyro_client, peer))
