"""Records the media a peer receives to raw files, with MediaStreamTrackProcessor.

Two connections in this process stand for the two peers: one sends the synthetic camera and microphone of
get_user_media, the other writes what it receives to video.i420 (I420 frames) and audio.pcm (16-bit samples),
which play with:

    ffplay -f rawvideo -pixel_format yuv420p -video_size 640x480 -framerate 30 video.i420
    ffplay -f s16le -ar 48000 -ch_layout mono audio.pcm
"""

import asyncio

import webrtc

SECONDS = 5


async def record(track, path):
    frames = 0
    with open(path, 'wb') as file:
        async for media in webrtc.MediaStreamTrackProcessor(track, max_buffer_size=30).readable:
            if track.kind == 'audio':
                data = bytearray(media.allocation_size({'plane_index': 0}))
                media.copy_to(data, {'plane_index': 0})
            else:
                data = bytearray(media.allocation_size())
                await media.copy_to(data)
            media.close()
            file.write(data)
            frames += 1
    print(f'{path}: {frames} {track.kind} frames')


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
    sender, receiver = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    trickle(sender, receiver)
    stream = webrtc.get_user_media(audio=True, video=True)
    for track in stream.get_tracks():
        sender.add_track(track, stream)

    recordings = []

    @receiver.on('track')
    def on_track(event):
        path = 'audio.pcm' if event.track.kind == 'audio' else 'video.i420'
        recordings.append(asyncio.ensure_future(record(event.track, path)))

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
