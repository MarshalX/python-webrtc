import webrtc


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


webrtc.ping()

# factory = webrtc.PeerConnectionFactory.GetOrCreateDefault()
# factory.Release()
# factory.Dispose()

enums = [
    webrtc.RTCPeerConnectionState,
    webrtc.RTCIceConnectionState,
    webrtc.RTCIceGatheringState,
    webrtc.RTCSdpType,
]
for enum in enums:
    print(f'{enum!r} = {enum.__members__}')

pc = webrtc.RTCPeerConnection()

# sdp string should be valid. need to bind exception on invalid
answer_sdp = webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.answer, VALID_SDP)
answer = webrtc.RTCSessionDescription(answer_sdp)

offer = None


def on_sdp(sdp: webrtc.RTCSessionDescription):
    global offer
    offer = sdp


pc.CreateOffer(on_sdp)

idle()
