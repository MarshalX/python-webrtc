import asyncio

import webrtc

import wrtc


VALID_SDP = '''v=0
o=- 6373938523134045336 2 IN IP4 127.0.0.1
s=-
t=0 0
a=extmap-allow-mixed
a=msid-semantic: WMS
'''


def get_dir(o):
    return [m for m in dir(o) if not m.startswith('__')]


def idle():
    while True:
        pass


async def main():
    wrtc.ping()

    enums = [
        wrtc.RTCPeerConnectionState,
        wrtc.RTCIceConnectionState,
        wrtc.RTCIceGatheringState,
        wrtc.RTCSdpType,
        wrtc.MediaStreamTrackState,
        wrtc.MediaStreamSourceState,
        wrtc.TransceiverDirection,
    ]
    for enum in enums:
        print(f'{enum!r} = {enum.__members__}')

    pc = webrtc.RTCPeerConnection()

    stream = webrtc.getUserMedia()
    print(repr(stream), get_dir(stream))
    for track in stream.getTracks():
        print(repr(track), get_dir(track))
        pc.add_track(track, stream)

    transceivers = pc.get_transceivers()

    idle()


if __name__ == '__main__':
    asyncio.run(main())
