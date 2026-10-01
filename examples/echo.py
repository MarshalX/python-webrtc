#!/usr/bin/env python3
#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""An echo peer: it sends back the video it receives, in grayscale.

The video goes through a processor piped through a transform stream into a generator, as in a browser.

Two connections in this process stand for the two peers: the caller sends its synthetic camera, the echo peer
sends the frames back, and the caller checks that they have no color.
"""

from __future__ import annotations

import asyncio

import webrtc

SECONDS = 3


async def grayscale(frame: webrtc.VideoFrame, controller: webrtc.TransformStreamDefaultController) -> None:
    """Transforms an I420 frame: U and V at 128 leave only the luma."""
    i420 = webrtc.VideoFrameCopyToOptions(format='I420')
    data = bytearray(frame.allocation_size(i420))
    await frame.copy_to(data, i420)
    luma = frame.coded_width * frame.coded_height
    data[luma:] = b'\x80' * (len(data) - luma)
    controller.enqueue(
        webrtc.VideoFrame(
            data,
            webrtc.VideoFrameBufferInit(
                format='I420', coded_width=frame.coded_width, coded_height=frame.coded_height, timestamp=frame.timestamp
            ),
        )
    )
    frame.close()


def video_frame(media: object) -> webrtc.VideoFrame:
    """The media a processor of a video track reads, as a video frame."""
    if not isinstance(media, webrtc.VideoFrame):
        msg = f'expected a video frame, not {media!r}'
        raise TypeError(msg)
    return media


async def watch(track: webrtc.MediaStreamTrack) -> None:
    """Reads the echoed frames for a while, then prints whether the last one is gray."""
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
    loop = asyncio.get_running_loop()
    end = loop.time() + SECONDS
    frames, rgba = 0, bytearray()
    while loop.time() < end:
        frame = video_frame((await reader.read()).value)
        options = webrtc.VideoFrameCopyToOptions(format='RGBA')
        rgba = bytearray(frame.allocation_size(options))
        await frame.copy_to(rgba, options)
        frame.close()
        frames += 1
    red, green, blue = rgba[0:3]
    print(f'{frames} frames echoed, the last one is gray: {red == green == blue} ({red}, {green}, {blue})')


def trickle(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Passes the ICE candidates of each connection to the other one."""
    for pc, other in ((caller, callee), (callee, caller)):

        async def on_candidate(
            event: webrtc.RTCPeerConnectionIceEvent, other: webrtc.RTCPeerConnection = other
        ) -> None:
            if event.candidate is not None:
                await other.add_ice_candidate(event.candidate)

        pc.on('icecandidate', on_candidate)


async def negotiate(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Exchanges an offer and an answer."""
    offer = await caller.create_offer()
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)
    answer = await callee.create_answer()
    await callee.set_local_description(answer)
    await caller.set_remote_description(answer)


async def main() -> None:
    """Echoes the camera of the caller back to it."""
    caller, echo = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    trickle(caller, echo)
    camera = webrtc.get_user_media(audio=False, video=True).get_video_tracks()[0]
    caller.add_track(camera)
    generator = webrtc.VideoTrackGenerator()
    echoed = asyncio.get_running_loop().create_future()
    pipes: list[asyncio.Future[None]] = []

    @echo.on('track')
    def on_echo_track(event: webrtc.RTCTrackEvent) -> None:
        readable = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(event.track)).readable
        pipe = readable.pipe_through(webrtc.TransformStream({'transform': grayscale})).pipe_to(generator.writable)
        pipes.append(asyncio.ensure_future(pipe))

    @caller.on('track')
    def on_caller_track(event: webrtc.RTCTrackEvent) -> None:
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
