"""An echo peer: it sends back the video it receives, in grayscale, with a processor piped through a transform
stream into a generator, as in a browser.

Two connections in this process stand for the two peers: the caller sends its synthetic camera, the echo peer
sends the frames back, and the caller checks that they have no color.
"""

import asyncio

import webrtc

SECONDS = 3


class Grayscale:
    """A transformer of I420 frames: U and V at 128 leave only the luma"""

    async def transform(self, frame, controller):
        data = bytearray(frame.allocation_size({'format': 'I420'}))
        await frame.copy_to(data, {'format': 'I420'})
        luma = frame.coded_width * frame.coded_height
        data[luma:] = b'\x80' * (len(data) - luma)
        controller.enqueue(
            webrtc.VideoFrame(
                data,
                format='I420',
                coded_width=frame.coded_width,
                coded_height=frame.coded_height,
                timestamp=frame.timestamp,
            )
        )
        frame.close()


async def watch(track):
    """Reads the echoed frames for a while, then prints whether the last one is gray"""
    reader = webrtc.MediaStreamTrackProcessor(track).readable.get_reader()
    loop = asyncio.get_running_loop()
    end = loop.time() + SECONDS
    frames = 0
    while loop.time() < end:
        frame = (await reader.read()).value
        rgba = bytearray(frame.allocation_size({'format': 'RGBA'}))
        await frame.copy_to(rgba, {'format': 'RGBA'})
        frame.close()
        frames += 1
    red, green, blue = rgba[0:3]
    print(f'{frames} frames echoed, the last one is gray: {red == green == blue} ({red}, {green}, {blue})')


def trickle(caller, callee):
    """Passes the ICE candidates of each connection to the other one"""
    for pc, other in ((caller, callee), (callee, caller)):

        async def on_candidate(event, other=other):
            if event.candidate:
                await other.add_ice_candidate(event.candidate)

        pc.on('icecandidate', on_candidate)


async def negotiate(caller, callee):
    """Exchanges an offer and an answer"""
    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    await caller.set_remote_description(answer)


async def main():
    caller, echo = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    trickle(caller, echo)
    camera = webrtc.get_user_media(audio=False, video=True).get_video_tracks()[0]
    caller.add_track(camera)
    generator = webrtc.VideoTrackGenerator()
    echoed = asyncio.get_running_loop().create_future()
    pipes = []

    @echo.on('track')
    def on_echo_track(event):
        readable = webrtc.MediaStreamTrackProcessor(event.track).readable
        pipe = readable.pipe_through(webrtc.TransformStream(Grayscale())).pipe_to(generator.writable)
        pipes.append(asyncio.ensure_future(pipe))

    @caller.on('track')
    def on_caller_track(event):
        echoed.set_result(event.track)

    await negotiate(caller, echo)
    # the echo goes back on the transceiver of the camera, which the echo peer offers to send on
    echo.add_track(generator.track)
    await negotiate(echo, caller)
    await watch(await asyncio.wait_for(echoed, 10))

    caller.close()
    echo.close()
    camera.stop()
    # the camera track ended, which closes the pipe and the generator
    await asyncio.wait_for(asyncio.gather(*pipes, return_exceptions=True), 10)


if __name__ == '__main__':
    asyncio.run(main())
