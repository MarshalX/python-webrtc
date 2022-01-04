import webrtc


if __name__ == '__main__':
    webrtc.ping()

    factory = webrtc.RTCPeerConnectionFactory.GetOrCreateDefault()
    # factory.Release()
    # factory.Dispose()

    while True:
        pass
