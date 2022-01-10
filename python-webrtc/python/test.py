import asyncio

import webrtc


VALID_SDP = '''v=0
o=- 6373938523134045336 2 IN IP4 127.0.0.1
s=-
t=0 0
a=extmap-allow-mixed
a=msid-semantic: WMS
'''


class Event(asyncio.Event):
    def set(self):
        self._loop.call_soon_threadsafe(super().set)


class AsyncWrapper:
    def __init__(self, func: callable):
        self.__event = Event()
        self.__func = func

        self.__args_for_run = []
        self.__kwargs_for_run = {}

        self.__result = None

    def set(self):
        self.__event.set()

    def _on_success(self, result=None):    # TODO many results mb
        self.__result = result
        self.set()

    def _on_fail(self, error):
        # TODO reraise. error should be exception created from cpp side
        pass

    async def run(self, timeout=10):
        self.__func(self._on_success, *self.__args_for_run, **self.__kwargs_for_run)  # TODO pass _on_fail
        await asyncio.wait_for(self.__event.wait(), timeout)
        return self.__result

    def __call__(self, *args, **kwargs):
        self.__args_for_run = args
        self.__kwargs_for_run = kwargs

        return self

    def __await__(self):
        return self.run().__await__()


toAsync = AsyncWrapper


def idle():
    while True:
        pass


async def test_async(peer_connection):
    async def _1():
        while True:
            sdp = await toAsync(peer_connection.createOffer)
            print('_1', sdp)
            await asyncio.sleep(0.1)

    async def _2():
        import random
        while True:
            print('_2', random.randint(0, 10**6))
            await asyncio.sleep(0.1)

    await asyncio.gather(
        _1(),
        _2(),
    )


async def main():
    webrtc.ping()

    # factory = webrtc.PeerConnectionFactory.GetOrCreateDefault()
    # factory.Release()
    # factory.Dispose()

    enums = [
        webrtc.RTCPeerConnectionState,
        webrtc.RTCIceConnectionState,
        webrtc.RTCIceGatheringState,
        webrtc.RTCSdpType,
        webrtc.MediaStreamTrackState,
    ]
    for enum in enums:
        print(f'{enum!r} = {enum.__members__}')

    # sdp string should be valid. need to bind exception on invalid
    answer_sdp = webrtc.RTCSessionDescriptionInit(webrtc.RTCSdpType.answer, VALID_SDP)
    answer = webrtc.RTCSessionDescription(answer_sdp)

    pc = webrtc.RTCPeerConnection()
    local_sdp = await toAsync(pc.createOffer)

    print('Local SDP', local_sdp)

    # after that the PC should be closed before exit from script
    await toAsync(pc.setLocalDescription)(local_sdp)

    # await toAsync(pc.setRemoteDescription)(local_sdp)
    # answer_sdp = await toAsync(pc.createAnswer)

    # print('Answer SDP', answer_sdp)

    # await test_async(pc)

    def get_dir(o):
        return [m for m in dir(o) if not m.startswith('__')]

    # TODO should be asynced?
    stream = webrtc.getUserMedia()
    print(repr(stream), get_dir(stream))
    # <webrtc.MediaStream object at 0x10623e3f0> ['active', 'addTrack', 'clone', 'getAudioTracks',
    # 'getTrackById', 'getTracks', 'getVideoTracks', 'id', 'removeTrack']
    for track in stream.getTracks():
        print(repr(track), get_dir(track))
        # <webrtc.MediaStreamTrack object at 0x10623a1f0> ['clone', 'enabled', 'id', 'kind',
        # 'muted', 'readyState', 'stop']

        # TODO
        # pc.addTrack(track, stream);

        # TODO SIGSEGV
        # track.enabled = False

    idle()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
