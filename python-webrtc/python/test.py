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


def idle():
    while True:
        pass


async def main():
    wrtc.ping()

    # factory = webrtc.PeerConnectionFactory.getOrCreateDefault()
    # factory.gelease()
    # factory.dispose()

    enums = [
        wrtc.RTCPeerConnectionState,
        wrtc.RTCIceConnectionState,
        wrtc.RTCIceGatheringState,
        wrtc.RTCSdpType,
        wrtc.MediaStreamTrackState,
        wrtc.MediaStreamSourceState,
    ]
    for enum in enums:
        print(f'{enum!r} = {enum.__members__}')

    # sdp string should be valid. need to bind exception on invalid
    # answer_sdp = webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.answer, VALID_SDP)
    # answer = webrtc.RTCSessionDescription(answer_sdp)

    pc = webrtc.RTCPeerConnection()

    # local_sdp = await toAsync(pc.createOffer)
    # print('Local SDP', local_sdp)

    # after that the PC should be closed before exit from script
    # await toAsync(pc.setLocalDescription)(local_sdp)

    # await toAsync(pc.setRemoteDescription)(local_sdp)
    # answer_sdp = await toAsync(pc.createAnswer)

    # print('Answer SDP', answer_sdp)

    # await test_async(pc)

    def get_dir(o):
        return [m for m in dir(o) if not m.startswith('__')]

    stream = webrtc.getUserMedia()
    print(repr(stream), get_dir(stream))
    # <webrtc.MediaStream object at 0x10623e3f0> ['active', 'addTrack', 'clone', 'getAudioTracks',
    # 'getTrackById', 'getTracks', 'getVideoTracks', 'id', 'removeTrack']
    for track in stream.getTracks():
        print(repr(track), get_dir(track))
        # <webrtc.MediaStreamTrack object at 0x10623a1f0> ['clone', 'enabled', 'id', 'kind',
        # 'muted', 'readyState', 'stop']

        sender = pc.addTrack(track, stream)
        # TODO should be raised
        # Sender already exists for track 88db8c42-7e4e-... (INVALID_PARAMETER)
        # sender2 = pc.addTrack(track, [stream])
        print(repr(sender), get_dir(sender))

        # TODO SIGSEGV because its another instance of the track with reregistered observer. should be the same
        print(sender.track)     # should not return new instance! because it's already created by getTracks()
        track.enabled = False

    # length = int(48000 * 16 / 8 / 100 * 1)  # 960
    # data = b'\0' * length
    # frame = wrtc.RTCOnDataEvent(data, length)

    source = wrtc.RTCAudioSource()
    track = source.createTrack()
    track.enabled = False

    # pc.addTrack(track, None)
    # source.onData(frame)

    # local_sdp = await toAsync(pc.createOffer)
    # print('Local SDP with track', local_sdp)
    # print(local_sdp.sdp)

    idle()

if __name__ == '__main__':
    asyncio.run(main())
