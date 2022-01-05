import webrtc


if __name__ == '__main__':
    webrtc.ping()

    # factory = webrtc.PeerConnectionFactory.GetOrCreateDefault()
    # factory.Release()
    # factory.Dispose()

    enums = [
        webrtc.RTCPeerConnectionState,
        webrtc.RTCIceConnectionState,
        webrtc.RTCIceGatheringState,
    ]
    for enum in enums:
        print(f'{enum!r} = {enum.__members__}')

    pc = webrtc.RTCPeerConnection()

    while True:
        pass
