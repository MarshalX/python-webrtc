#!/usr/bin/env python3
#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""Records the media a peer receives to raw files, with MediaStreamTrackProcessor.

Two connections in this process stand for the two peers: one sends the synthetic camera and microphone of
get_user_media, the other writes what it receives to video.i420 (I420 frames) and audio.pcm (16-bit samples),
which play with:

    ffplay -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 video.i420
    ffplay -f s16le -ar 48000 -ch_layout mono audio.pcm
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import BinaryIO

import webrtc

SECONDS = 5


async def record(track: webrtc.MediaStreamTrack, file: BinaryIO) -> None:
    """Writes the frames of a track to a file until the track ends."""
    frames = 0
    with file:
        async for media in webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=30)
        ).readable:
            # audio data for an audio track, video frames for a video one
            if isinstance(media, webrtc.AudioData):
                options = webrtc.AudioDataCopyToOptions(plane_index=0)
                data = bytearray(media.allocation_size(options))
                media.copy_to(data, options)
            elif isinstance(media, webrtc.VideoFrame):
                data = bytearray(media.allocation_size())
                await media.copy_to(data)
            else:
                msg = f'unexpected media: {media!r}'
                raise TypeError(msg)
            media.close()
            file.write(data)
            frames += 1
    print(f'{file.name}: {frames} {track.kind} frames')


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
    """Records the camera and the microphone for a few seconds."""
    sender, receiver = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    trickle(sender, receiver)
    stream = webrtc.get_user_media(audio=True, video=True)
    for track in stream.get_tracks():
        sender.add_track(track, stream)

    recordings: list[asyncio.Future[None]] = []

    @receiver.on('track')
    def on_track(event: webrtc.RTCTrackEvent) -> None:
        path = pathlib.Path('audio.pcm' if event.track.kind == 'audio' else 'video.i420')
        recordings.append(asyncio.ensure_future(record(event.track, path.open('wb'))))

    await negotiate(sender, receiver)
    await asyncio.sleep(SECONDS)
    # closing the connection ends its remote tracks, which ends the recordings
    receiver.close()
    sender.close()
    await asyncio.gather(*recordings)
    for track in stream.get_tracks():
        track.stop()


if __name__ == '__main__':
    asyncio.run(main())
