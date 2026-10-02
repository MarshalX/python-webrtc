#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["wrtc>=0.0.1", "sounddevice", "httpx"]
# ///
#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""Watches a stream of the public Janus demo server: the video in the terminal, the audio on your speakers.

    uv run janus_streaming.py
    uv run janus_streaming.py --id 1

The video is drawn with colored half blocks, so the terminal needs 24-bit color. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import shutil
import sys
import threading
import uuid
from typing import TYPE_CHECKING, TypedDict

import httpx
import sounddevice
from typing_extensions import NotRequired, Required

import webrtc

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import TracebackType

    from typing_extensions import Self

JANUS = 'https://janus.conf.meetecho.com/janus'


class Stream(TypedDict):
    """A stream of the streaming plugin."""

    id: int
    description: NotRequired[str]


class Jsep(TypedDict):
    """A session description of the Janus API."""

    type: str
    sdp: str


class PluginReply(TypedDict, total=False):
    """The data of a plugin reply: the streams of a list request."""

    list: list[Stream]


class PluginData(TypedDict, total=False):
    """The reply of a plugin."""

    data: PluginReply


class Created(TypedDict):
    """The id of a created session or handle."""

    id: int


class Error(TypedDict):
    """An error of the Janus API."""

    reason: str


class Reply(TypedDict, total=False):
    """A message of the Janus API: the fields used here."""

    janus: Required[str]
    data: Created
    error: Error
    plugindata: PluginData
    jsep: Jsep


class Janus:
    """A session with the streaming plugin of a Janus server, over its HTTP API."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=60)
        self.session = ''
        self.handle = ''

    async def __aenter__(self) -> Self:
        self.session = await self._create('', janus='create')
        self.handle = await self._create(self.session, janus='attach', plugin='janus.plugin.streaming')
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        await self._post(self.session, janus='destroy')
        await self.client.aclose()

    async def request(self, body: dict[str, object], **extra: object) -> PluginReply | None:
        """Sends a message to the plugin, returns the data of its reply."""
        reply = await self._post(self.handle, janus='message', body=body, **extra)
        return reply.get('plugindata', {}).get('data')

    async def event(self) -> Reply:
        """Waits up to 30 s for an event: requests reply right away and send their results, like offers, as events."""
        event: Reply = (await self.client.get(JANUS + self.session)).json()
        return event

    async def _post(self, path: str, **message: object) -> Reply:
        reply: Reply = (await self.client.post(JANUS + path, json={'transaction': uuid.uuid4().hex, **message})).json()
        if reply['janus'] == 'error':
            error = reply.get('error')
            raise RuntimeError(error['reason'] if error is not None else reply)
        return reply

    async def _create(self, path: str, **message: object) -> str:
        """Creates a session or a handle under the path, returns its path."""
        reply = await self._post(path, **message)
        if 'data' not in reply:
            msg = f'no id in {reply}'
            raise RuntimeError(msg)
        return f'{path}/{reply["data"]["id"]}'


class Speakers:
    """Plays 16-bit audio from a buffer that keeps half a second at most."""

    def __init__(self, rate: int, channels: int) -> None:
        self.buffer, self.lock, self.limit = bytearray(), threading.Lock(), rate * channels
        self.stream = sounddevice.RawOutputStream(rate, channels=channels, dtype='int16', callback=self._on_need)
        self.stream.start()

    def play(self, samples: bytes | bytearray) -> None:
        """Queues samples, dropping the oldest ones over the limit."""
        with self.lock:
            self.buffer += samples
            del self.buffer[: -self.limit]

    def _on_need(self, out: memoryview, *_: object) -> None:
        with self.lock:
            chunk = self.buffer[: len(out)]
            del self.buffer[: len(out)]
        out[:] = chunk.ljust(len(out), b'\0')


def draw(rgbx: bytes | bytearray, width: int, height: int, *, slot: int, slots: int) -> None:
    """Draws a frame in its slot of the screen with ▀, its foreground is the upper pixel, background the lower one."""
    total, rows = shutil.get_terminal_size()
    left = total * slot // slots
    columns = total * (slot + 1) // slots - left
    scale = max(width / columns, height / rows / 2)

    def color(x: int, y: int) -> str:
        i = (int(y * scale) * width + int(x * scale)) * 4
        return '{};{};{}'.format(*rgbx[i : i + 3])

    shown = int(width / scale)
    lines = [
        ''.join(f'\033[38;2;{color(x, 2 * y)}m\033[48;2;{color(x, 2 * y + 1)}m▀' for x in range(shown))
        for y in range(int(height / scale / 2))
    ]
    # pads with blanks rather than clearing, which would erase the other columns
    lines = [line + '\033[0m' + ' ' * (columns - shown) for line in lines]
    lines += [' ' * columns] * (rows - len(lines))
    sys.stdout.write(''.join(f'\033[{y + 1};{left + 1}H{line}' for y, line in enumerate(lines)))
    sys.stdout.flush()


@contextlib.contextmanager
def fullscreen() -> Generator[None, None, None]:
    """Switches to the alternate screen, without the cursor."""
    sys.stdout.write('\033[?1049h\033[?25l')
    try:
        yield
    finally:
        sys.stdout.write('\033[?25h\033[?1049l')


async def watch(track: webrtc.MediaStreamTrack, videos: list[webrtc.MediaStreamTrack]) -> None:
    """Draws the frames of the video track until it ends, side by side with the other videos."""
    # a buffer of one frame drops the frames the terminal is too slow for
    async for frame in webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=1)
    ).readable:
        if not isinstance(frame, webrtc.VideoFrame):
            msg = f'expected a video frame, not {frame!r}'
            raise TypeError(msg)
        with frame:
            options = webrtc.VideoFrameCopyToOptions(format='RGBX')
            rgbx = bytearray(frame.allocation_size(options))
            await frame.copy_to(rgbx, options)
            size = frame.visible_rect
        if size is None:
            msg = 'the frame has no visible rect'
            raise RuntimeError(msg)
        draw(rgbx, int(size.width), int(size.height), slot=videos.index(track), slots=len(videos))


async def listen(track: webrtc.MediaStreamTrack) -> None:
    """Plays the audio track until it ends."""
    speakers: Speakers | None = None
    try:
        async for data in webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=50)
        ).readable:
            if not isinstance(data, webrtc.AudioData):
                msg = f'expected audio data, not {data!r}'
                raise TypeError(msg)
            with data:
                options = webrtc.AudioDataCopyToOptions(plane_index=0, format='s16')
                samples = bytearray(data.allocation_size(options))
                data.copy_to(samples, options)
                rate, channels = int(data.sample_rate), data.number_of_channels
            if speakers is None:
                speakers = Speakers(rate, channels)
            speakers.play(samples)
    finally:
        if speakers is not None:
            speakers.stream.close()


async def answer(pc: webrtc.RTCPeerConnection, offer: Jsep) -> Jsep:
    """Answers with all the ICE candidates in the SDP, since there is no trickling."""
    gathered = asyncio.Event()
    pc.on('icegatheringstatechange', lambda _: pc.ice_gathering_state == 'complete' and gathered.set())
    await pc.set_remote_description(webrtc.RTCSessionDescriptionInit.from_json(offer))
    await pc.set_local_description(await pc.create_answer())
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(gathered.wait(), 5)
    if pc.local_description is None:
        msg = 'no local description'
        raise RuntimeError(msg)
    return {'type': 'answer', 'sdp': pc.local_description.sdp}


async def keep_alive(janus: Janus) -> None:
    """Polls for events, which keeps the session alive."""
    while True:
        await janus.event()


async def pick_stream(janus: Janus) -> int:
    """Lists the streams of the server, returns the first one."""
    reply = await janus.request({'request': 'list'})
    if reply is None or 'list' not in reply:
        msg = 'the server did not list its streams'
        raise RuntimeError(msg)
    streams = reply['list']
    for stream in streams:
        print(f'{stream["id"]}: {stream.get("description")}')
    return streams[0]['id']


async def main(stream_id: int | None) -> None:
    """Watches the stream until interrupted."""
    pc = webrtc.RTCPeerConnection()
    tasks: list[asyncio.Future[None]] = []
    videos: list[webrtc.MediaStreamTrack] = []

    @pc.on('track')
    def on_track(event: webrtc.RTCTrackEvent) -> None:
        if event.track.kind == 'video':
            videos.append(event.track)
            tasks.append(asyncio.ensure_future(watch(event.track, videos)))
        else:
            tasks.append(asyncio.ensure_future(listen(event.track)))

    async with Janus() as janus:
        if stream_id is None:
            stream_id = await pick_stream(janus)
        await janus.request({'request': 'watch', 'id': stream_id})
        event = await janus.event()
        while 'jsep' not in event:
            event = await janus.event()
        await janus.request({'request': 'start'}, jsep=await answer(pc, event['jsep']))

        with fullscreen():
            try:
                await keep_alive(janus)
            finally:
                pc.close()  # ends the tracks, so watch and listen return
                await asyncio.gather(*tasks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Watch a stream of the Janus demo server in the terminal.')
    parser.add_argument('--id', type=int, help='the stream to watch, default: the first one')
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(parser.parse_args().id))
