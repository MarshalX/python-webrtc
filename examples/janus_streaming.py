#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["wrtc>=0.0.0.dev10", "sounddevice", "httpx"]
# ///
"""Watches a stream of the public Janus demo server: the video in the terminal, the audio on your speakers.

    uv run janus_streaming.py
    uv run janus_streaming.py --id 1

The video is drawn with colored half blocks, so the terminal needs 24-bit color. Press Ctrl+C to stop.
"""

import argparse
import asyncio
import contextlib
import shutil
import sys
import threading
import uuid

import httpx
import sounddevice

import webrtc

JANUS = 'https://janus.conf.meetecho.com/janus'


class Janus:
    """A session with the streaming plugin of a Janus server, over its HTTP API"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60)

    async def __aenter__(self):
        created = await self._post('', janus='create')
        self.session = f'/{created["data"]["id"]}'
        attached = await self._post(self.session, janus='attach', plugin='janus.plugin.streaming')
        self.handle = f'{self.session}/{attached["data"]["id"]}'
        return self

    async def __aexit__(self, *exc_info):
        await self._post(self.session, janus='destroy')
        await self.client.aclose()

    async def request(self, body, **extra):
        reply = await self._post(self.handle, janus='message', body=body, **extra)
        return reply.get('plugindata', {}).get('data')

    async def event(self):
        """Waits up to 30 s for an event: requests reply right away and send their results, like offers, as events"""
        return (await self.client.get(JANUS + self.session)).json()

    async def _post(self, path, **message):
        reply = (await self.client.post(JANUS + path, json={'transaction': uuid.uuid4().hex, **message})).json()
        if reply['janus'] == 'error':
            raise RuntimeError(reply['error']['reason'])
        return reply


class Speakers:
    """Plays 16-bit audio from a buffer that keeps half a second at most"""

    def __init__(self, rate, channels):
        self.buffer, self.lock, self.limit = bytearray(), threading.Lock(), rate * channels
        self.stream = sounddevice.RawOutputStream(rate, channels=channels, dtype='int16', callback=self._on_need)
        self.stream.start()

    def play(self, samples):
        with self.lock:
            self.buffer += samples
            del self.buffer[: -self.limit]

    def _on_need(self, out, *_):
        with self.lock:
            chunk = self.buffer[: len(out)]
            del self.buffer[: len(out)]
        out[:] = chunk.ljust(len(out), b'\0')


def draw(rgbx, width, height):
    """Draws a frame with ▀, whose foreground color is the upper pixel and background the lower one"""
    columns, rows = shutil.get_terminal_size()
    scale = max(width / columns, height / rows / 2)

    def color(x, y):
        i = (int(y * scale) * width + int(x * scale)) * 4
        return '{};{};{}'.format(*rgbx[i : i + 3])

    lines = (
        ''.join(f'\033[38;2;{color(x, 2 * y)}m\033[48;2;{color(x, 2 * y + 1)}m▀' for x in range(int(width / scale)))
        for y in range(int(height / scale / 2))
    )
    sys.stdout.write('\033[H' + '\033[0m\033[K\n'.join(lines) + '\033[0m\033[J')
    sys.stdout.flush()


@contextlib.contextmanager
def fullscreen():
    """Switches to the alternate screen, without the cursor"""
    sys.stdout.write('\033[?1049h\033[?25l')
    try:
        yield
    finally:
        sys.stdout.write('\033[?25h\033[?1049l')


async def watch(track):
    # a buffer of one frame drops the frames the terminal is too slow for
    async for frame in webrtc.MediaStreamTrackProcessor(track, max_buffer_size=1).readable:
        with frame:
            rgbx = bytearray(frame.allocation_size({'format': 'RGBX'}))
            await frame.copy_to(rgbx, {'format': 'RGBX'})
            size = frame.visible_rect
        draw(rgbx, int(size.width), int(size.height))


async def listen(track):
    speakers = None
    try:
        async for data in webrtc.MediaStreamTrackProcessor(track, max_buffer_size=50).readable:
            with data:
                options = {'plane_index': 0, 'format': 's16'}
                samples = bytearray(data.allocation_size(options))
                data.copy_to(samples, options)
                speakers = speakers or Speakers(int(data.sample_rate), data.number_of_channels)
            speakers.play(samples)
    finally:
        if speakers is not None:
            speakers.stream.close()


async def answer(pc, offer):
    """Answers with all the ICE candidates in the SDP, since there is no trickling"""
    gathered = asyncio.Event()
    pc.on('icegatheringstatechange', lambda _: pc.ice_gathering_state == 'complete' and gathered.set())
    await pc.set_remote_description(offer)
    await pc.set_local_description(await pc.create_answer())
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(gathered.wait(), 5)
    return {'type': 'answer', 'sdp': pc.local_description.sdp}


async def main(stream_id):
    pc, tasks = webrtc.RTCPeerConnection(), []

    @pc.on('track')
    def on_track(event):
        play = watch if event.track.kind == 'video' else listen
        tasks.append(asyncio.ensure_future(play(event.track)))

    async with Janus() as janus:
        if stream_id is None:
            streams = (await janus.request({'request': 'list'}))['list']
            for stream in streams:
                print(f'{stream["id"]}: {stream.get("description")}')
            stream_id = streams[0]['id']

        await janus.request({'request': 'watch', 'id': stream_id})
        event = {}
        while 'jsep' not in event:
            event = await janus.event()
        await janus.request({'request': 'start'}, jsep=await answer(pc, event['jsep']))

        with fullscreen():
            try:
                while True:  # polling for events keeps the session alive
                    await janus.event()
            finally:
                pc.close()  # ends the tracks, so watch and listen return
                await asyncio.gather(*tasks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Watch a stream of the Janus demo server in the terminal.')
    parser.add_argument('--id', type=int, help='the stream to watch, default: the first one')
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(parser.parse_args().id))
