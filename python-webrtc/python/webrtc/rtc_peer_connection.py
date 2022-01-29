import wrtc

from .utils.callback_to_async import to_async


class RTCPeerConnection:

    def __init__(self):
        self.__pc = wrtc.RTCPeerConnection()

    async def set_local_description(self, sdp):
        return await to_async(self.__pc.setLocalDescription)(sdp)

    async def set_remote_description(self, sdp):
        return await to_async(self.__pc.setRemoteDescription)(sdp)

    async def create_offer(self):
        return await to_async(self.__pc.createOffer)

    async def add_track(self, track, stream=None):
        return self.__pc.addTrack(track, stream)

    setLocalDescription = set_local_description
    setRemoteDescription = set_remote_description
    createOffer = create_offer
    addTrack = add_track
