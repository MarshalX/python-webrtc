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
    for track in stream.getTracks():
        print(repr(track), get_dir(track))

        sender = pc.addTrack(track, stream)
        # TODO should be raised
        # Sender already exists for track 88db8c42-7e4e-... (INVALID_PARAMETER)
        # sender2 = pc.addTrack(track, [stream])
        print(repr(sender), get_dir(sender))

        print(sender.track)
        track.enabled = False

    # length = int(48000 * 16 / 8 / 100 * 1)  # 960
    # data = b'\0' * length
    # frame = wrtc.RTCOnDataEvent(data, length)

    source = webrtc.RTCAudioSource()
    track = source.createTrack()
    track.enabled = False

    # pc.addTrack(track, None)
    # source.onData(frame)

    # local_sdp = await toAsync(pc.createOffer)
    # print('Local SDP with track', local_sdp)
    # print(local_sdp.sdp)

    stream = webrtc.get_user_media()
    tracks1 = stream.get_tracks()
    tracks2 = stream.get_tracks()
    tracks3 = stream.get_audio_tracks()
    tracks4 = stream.get_audio_tracks()

    assert tracks1[0]._native_obj == tracks2[0]._native_obj

    sender = pc.add_track(tracks1[0], stream)
    print(sender.track)
    tracks1[0].enabled = False

    track = stream.get_track_by_id(tracks1[0].id)
    print(track)

    assert sender.track._native_obj == track._native_obj

    t1 = track.clone()
    t2 = track.clone()
    assert t1._native_obj != t2._native_obj
    s1 = stream.clone()
    s2 = stream.clone()
    assert s1._native_obj != s2._native_obj

    local_sdp = await pc.create_offer()
    # print(local_sdp.sdp)
    # pc.close()
    await pc.set_local_description(local_sdp)

    pc.close()
    pc.close()

    try:
        # invalid sdp
        webrtc.RTCSessionDescription(webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.answer, 'sdp'))

        # invalid pc state
        pc.close()

        # sender already created
        pc.add_track(tracks1[0], stream)
    # except webrtc.PythonWebRTCExceptionBase as e:
    # except webrtc.PythonWebRTCException as e:
    except webrtc.RTCException as e:
        # except webrtc.SdpParseException as e:
        print('exception', str(e))
    # idle()


if __name__ == '__main__':
    asyncio.run(main())
