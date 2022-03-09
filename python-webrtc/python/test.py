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
        wrtc.RTCIceComponent,
        wrtc.RTCIceRole,
        wrtc.RTCIceTransportState,
        wrtc.CricketIceGatheringState,
        wrtc.DtlsTransportState,
        wrtc.SctpTransportState,
        wrtc.MediaType,
    ]
    for enum in enums:
        print(f'{enum!r} = {enum.__members__}')

    pc = webrtc.RTCPeerConnection()

    stream = webrtc.getUserMedia()
    # print(repr(stream), get_dir(stream))
    # for track in stream.getTracks():
    #     print(repr(track), get_dir(track))
    #     sender = pc.add_track(track, stream)

    # local_sdp = await pc.create_offer()
    # await pc.set_local_description(local_sdp)
    #
    # transport = sender.transport
    # transceivers = pc.get_transceivers()

    params = webrtc.RtpEncodingParameters(
        max_bitrate=1234, max_framerate=20, rid="lolkek", scale_resolution_down_by=2.0
    )
    init = webrtc.RtpTransceiverInit(
        direction=webrtc.TransceiverDirection.recvonly, send_encodings=[params], streams=[stream]
    )

    transceiver = pc.add_transceiver(webrtc.MediaType.audio)
    transceiver_with_params = pc.add_transceiver(webrtc.MediaType.audio, init)

    transceiver_by_track = pc.add_transceiver(stream.get_tracks()[0])
    transceiver_by_track_with_params = pc.add_transceiver(stream.get_tracks()[0], init)

    local_sdp = await pc.create_offer()
    await pc.set_local_description(local_sdp)

    transceivers = pc.get_transceivers()

    idle()


if __name__ == '__main__':
    asyncio.run(main())
