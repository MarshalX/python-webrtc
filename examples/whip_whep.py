#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["wrtc>=0.0.1", "sounddevice", "httpx"]
# ///
#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>.
#
#  Dedicated to the public domain under CC0, see the LICENSE file of the examples.
#

"""Plays a live stream over WHEP (RFC 9725) in the terminal, or publishes one over WHIP.

    uv run whip_whep.py
    uv run whip_whep.py https://example.com/whep/stream --token SECRET
    uv run whip_whep.py --whip http://localhost:8889/wrtc/whip

With no URL it plays the public demo stream of Dolby OptiView, which is H.264: where the OS has no H.264 codec, it
downloads Cisco's OpenH264 once, and --no-openh264 skips it. The video is drawn with colored half blocks, so the
terminal needs 24-bit color. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import shutil
import signal
import sys
import threading
from typing import TYPE_CHECKING

import httpx

import webrtc

try:
    import sounddevice
except OSError:
    PORTAUDIO = False
else:
    PORTAUDIO = True

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import TracebackType

    from typing_extensions import Self

DEMO = 'https://director.millicast.com/api/whep/k9Mwad/multiview'
# RFC 9725 asks for one transport for all the media
CONFIGURATION = webrtc.RTCConfiguration(bundle_policy='max-bundle')
DECODING_GRACE = 5  # seconds of video packets without a decoded frame before the H.264 hint

ENTER_ALTERNATE_SCREEN = '\033[?1049h'
LEAVE_ALTERNATE_SCREEN = '\033[?1049l'
HIDE_CURSOR = '\033[?25l'
SHOW_CURSOR = '\033[?25h'
RESET_COLORS = '\033[0m'


class EndpointError(Exception):
    """The endpoint couldn't be reached or refused the offer."""


class Session:
    """A WHIP or WHEP session: the resource the server creates for an offer."""

    def __init__(self, endpoint: str, token: str | None) -> None:
        # a redirect to another host drops the token, as httpx doesn't send credentials across hosts
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=True)
        self.endpoint = endpoint
        self.headers = {} if token is None else {'Authorization': f'Bearer {token}'}
        self.resource: httpx.URL | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self.resource is not None:
            # the server ends the session on its own when it times out
            with contextlib.suppress(httpx.HTTPError):
                await self.client.delete(self.resource, headers=self.headers, timeout=5)
        await self.client.aclose()

    async def post_offer(self, sdp: str) -> str:
        """Posts the offer, returns the answer."""
        headers = {**self.headers, 'Content-Type': 'application/sdp'}
        try:
            response = await self.client.post(self.endpoint, content=sdp, headers=headers)
        except httpx.HTTPError as e:
            msg = f'{self.endpoint}: {e}'
            raise EndpointError(msg) from e

        if not response.is_success:
            msg = f'{self.endpoint} returned {response.status_code} {response.reason_phrase}: {response.text[:200]}'
            raise EndpointError(msg)

        # relative to the endpoint, after any redirects
        location = response.headers.get('Location')
        if location is not None:
            self.resource = response.url.join(location)
        return response.text


async def gather_offer(pc: webrtc.RTCPeerConnection) -> str:
    """Creates the offer with all the ICE candidates in the SDP, since there is no trickling."""
    gathered = asyncio.Event()

    @pc.on('icegatheringstatechange')
    def on_gathering_state(_event: webrtc.Event) -> None:
        if pc.ice_gathering_state == 'complete':
            gathered.set()

    await pc.set_local_description()
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(gathered.wait(), 2)
    if pc.local_description is None:
        msg = 'no local description'
        raise RuntimeError(msg)
    return pc.local_description.sdp


async def connect(pc: webrtc.RTCPeerConnection, session: Session) -> None:
    """Posts the offer and applies the answer."""
    sdp = await gather_offer(pc)
    answer = await session.post_offer(sdp)
    await pc.set_remote_description(webrtc.RTCSessionDescriptionInit('answer', answer))


async def play(url: str, token: str | None, stop: asyncio.Event) -> None:
    """Plays the stream of a WHEP endpoint until stopped."""
    has_speakers = speakers_found()
    if not has_speakers:
        print('No audio output, playing the video only')

    # the notice stays on screen while OpenH264 is in use
    status = webrtc.openh264.NOTICE if webrtc.openh264.is_enabled() else ''

    pc = webrtc.RTCPeerConnection(CONFIGURATION)
    tasks: list[asyncio.Future[None]] = []
    pc.add_transceiver('video', webrtc.RTCRtpTransceiverInit(direction='recvonly'))
    pc.add_transceiver('audio', webrtc.RTCRtpTransceiverInit(direction='recvonly'))

    @pc.on('track')
    def on_track(event: webrtc.RTCTrackEvent) -> None:
        if event.track.kind == 'video':
            tasks.append(asyncio.ensure_future(watch(event.track, status)))
        elif has_speakers:
            tasks.append(asyncio.ensure_future(listen(event.track)))

    @pc.on('connectionstatechange')
    def on_connection_state(_event: webrtc.Event) -> None:
        if pc.connection_state == 'failed':
            stop.set()

    # closing inside ends the tracks before the normal screen is back, so no frame is drawn over it
    with fullscreen(status):
        try:
            async with Session(url, token) as session:
                await connect(pc, session)
                problem = await wait_for_stop(pc, stop)
        finally:
            pc.close()
            await asyncio.gather(*tasks)
    if problem is not None:
        print(problem)


async def wait_for_stop(pc: webrtc.RTCPeerConnection, stop: asyncio.Event) -> str | None:
    """Waits until stopped, returns what went wrong, if anything; a video that doesn't decode is shown right away."""
    # the answer can't tell: the demo's server answers with the offered codecs, yet sends H.264
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(stop.wait(), DECODING_GRACE)
    problem = None
    if not stop.is_set() and not h264_decodable() and await video_undecoded(pc):
        problem = 'The video arrives but none of it decodes: if it is H.264, it is off (--no-openh264) or unavailable'
        draw_status(problem)

    await stop.wait()
    if pc.connection_state == 'failed':
        return 'The connection failed: the stream ended or the network dropped it'
    return problem


async def publish(url: str, token: str | None, stop: asyncio.Event) -> None:
    """Publishes the synthetic camera and microphone to a WHIP endpoint until stopped."""
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    pc = webrtc.RTCPeerConnection(CONFIGURATION)
    for track in stream.get_tracks():
        pc.add_transceiver(track, webrtc.RTCRtpTransceiverInit(direction='sendonly', streams=[stream]))

    @pc.on('connectionstatechange')
    def on_connection_state(_event: webrtc.Event) -> None:
        print(f'Connection: {pc.connection_state}')
        if pc.connection_state == 'failed':
            stop.set()

    try:
        async with Session(url, token) as session:
            await connect(pc, session)
            print(f'Publishing to {session.resource or url}, press Ctrl+C to stop')
            await stop.wait()
    finally:
        pc.close()
        for track in stream.get_tracks():
            track.stop()


def h264_decodable() -> bool:
    """Whether receivers can decode H.264: on macOS with VideoToolbox, elsewhere once OpenH264 is installed."""
    capabilities = webrtc.RTCRtpReceiver.get_capabilities('video')
    if capabilities is None:
        return False
    return any(codec.mime_type.lower() == 'video/h264' for codec in capabilities.codecs)


async def video_undecoded(pc: webrtc.RTCPeerConnection) -> bool:
    """Whether video packets arrived but no frame was decoded."""
    report = await pc.get_stats()
    for stats in report.values():
        if isinstance(stats, webrtc.RTCInboundRtpStreamStats) and stats.kind == 'video':
            received = stats.packets_received is not None and stats.packets_received > 0
            decoded = stats.frames_decoded is not None and stats.frames_decoded > 0
            return received and not decoded
    return False


class Speakers:
    """Plays 16-bit audio from a buffer that keeps half a second at most."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.limit = 0
        self.stream: sounddevice.RawOutputStream | None = None

    def play(self, samples: bytes | bytearray, rate: int, channels: int) -> None:
        """Queues samples, dropping the oldest ones over the limit, reopens the output when their format changes."""
        if self.stream is None or (self.stream.samplerate, self.stream.channels) != (rate, channels):
            self.close()
            self.buffer = bytearray()
            # half a second of 16-bit samples
            self.limit = rate * channels
            self.stream = sounddevice.RawOutputStream(rate, channels=channels, dtype='int16', callback=self._on_need)
            self.stream.start()
        with self.lock:
            self.buffer += samples
            del self.buffer[: -self.limit]

    def _on_need(self, out: memoryview, *_: object) -> None:
        with self.lock:
            chunk = self.buffer[: len(out)]
            del self.buffer[: len(out)]
        out[:] = chunk.ljust(len(out), b'\0')

    def close(self) -> None:
        """Stops the output."""
        if self.stream is not None:
            self.stream.close()


def speakers_found() -> bool:
    """Whether audio can be played: servers often lack the PortAudio library or an output device."""
    if not PORTAUDIO:
        return False
    try:
        sounddevice.query_devices(kind='output')
    except sounddevice.PortAudioError:
        return False
    return True


def move_to(row: int) -> str:
    """The code that moves the cursor to the start of a row, counted from 1."""
    return f'\033[{row};1H'


def draw(rgbx: bytes | bytearray, width: int, height: int, *, status: str) -> None:
    """Draws a frame above the status line with ▀, its foreground is the upper pixel, background the lower one."""
    columns, rows = shutil.get_terminal_size()
    video_rows = rows - 1
    # a character is two pixels high
    scale = max(width / columns, height / video_rows / 2)
    shown_columns = int(width / scale)
    shown_rows = int(height / scale / 2)

    def color(x: int, y: int) -> str:
        """The red;green;blue of the pixel under a point of the screen."""
        i = (int(y * scale) * width + int(x * scale)) * 4
        red, green, blue = rgbx[i : i + 3]
        return f'{red};{green};{blue}'

    def line(y: int) -> str:
        """A row of the screen: two rows of pixels, padded to the width of the screen."""
        cells: list[str] = []
        for x in range(shown_columns):
            upper = color(x, 2 * y)
            lower = color(x, 2 * y + 1)
            cells.append(f'\033[38;2;{upper}m\033[48;2;{lower}m▀')
        return ''.join(cells) + RESET_COLORS + ' ' * (columns - shown_columns)

    lines = [line(y) for y in range(shown_rows)]
    lines += [' ' * columns] * (video_rows - len(lines))
    sys.stdout.write(''.join(move_to(y + 1) + text for y, text in enumerate(lines)))
    draw_status(status)


def draw_status(status: str) -> None:
    """Writes the status on the last line of the screen."""
    columns, rows = shutil.get_terminal_size()
    sys.stdout.write(move_to(rows) + status[:columns].ljust(columns))
    sys.stdout.flush()


@contextlib.contextmanager
def fullscreen(status: str) -> Generator[None, None, None]:
    """Switches to the alternate screen, without the cursor, with the status on the last line."""
    sys.stdout.write(ENTER_ALTERNATE_SCREEN + HIDE_CURSOR)
    draw_status(status)
    try:
        yield
    finally:
        sys.stdout.write(SHOW_CURSOR + LEAVE_ALTERNATE_SCREEN)


async def watch(track: webrtc.MediaStreamTrack, status: str) -> None:
    """Draws the frames of the video track until it ends, with the status under them."""
    # a buffer of one frame drops the frames the terminal is too slow for
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=1))
    options = webrtc.VideoFrameCopyToOptions(format='RGBX')
    async for frame in processor.readable:
        if not isinstance(frame, webrtc.VideoFrame):
            msg = f'expected a video frame, not {frame!r}'
            raise TypeError(msg)

        with frame:
            rgbx = bytearray(frame.allocation_size(options))
            await frame.copy_to(rgbx, options)
            size = frame.visible_rect
        if size is None:
            msg = 'the frame has no visible rect'
            raise RuntimeError(msg)

        draw(rgbx, int(size.width), int(size.height), status=status)


async def listen(track: webrtc.MediaStreamTrack) -> None:
    """Plays the audio track until it ends."""
    processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=50))
    options = webrtc.AudioDataCopyToOptions(plane_index=0, format='s16')
    speakers = Speakers()
    try:
        async for data in processor.readable:
            if not isinstance(data, webrtc.AudioData):
                msg = f'expected audio data, not {data!r}'
                raise TypeError(msg)

            with data:
                samples = bytearray(data.allocation_size(options))
                data.copy_to(samples, options)
                rate = int(data.sample_rate)
                channels = data.number_of_channels
            speakers.play(samples, rate, channels)
    finally:
        speakers.close()


async def enable_openh264() -> None:
    """Enables H.264 with Cisco's OpenH264 binary, or goes on without it when it can't be had."""
    try:
        await webrtc.openh264.install()
    except (RuntimeError, OSError) as e:
        print(f'Going on without H.264: {e}')


async def main(args: argparse.Namespace) -> None:
    """Plays or publishes until Ctrl+C."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def interrupt() -> None:
        """Stops on the first Ctrl+C; the next one raises KeyboardInterrupt."""
        stop.set()
        loop.remove_signal_handler(signal.SIGINT)

    # on Windows, Ctrl+C raises KeyboardInterrupt instead
    with contextlib.suppress(NotImplementedError):
        loop.add_signal_handler(signal.SIGINT, interrupt)

    # the codecs of a connection are fixed when it's created
    if not args.no_openh264 and not h264_decodable():
        await enable_openh264()

    try:
        if args.whip is not None:
            await publish(args.whip, args.token, stop)
        else:
            await play(args.url, args.token, stop)
    except EndpointError as e:
        sys.exit(str(e))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Play a stream over WHEP in the terminal, or publish one over WHIP.')
    parser.add_argument('url', nargs='?', default=DEMO, help='the WHEP endpoint to play, default: a public demo')
    parser.add_argument('--whip', metavar='URL', help='publish the synthetic camera and microphone to this endpoint')
    parser.add_argument('--token', help='a bearer token, if the endpoint needs one')
    parser.add_argument(
        '--no-openh264',
        action='store_true',
        help=f"don't download Cisco's OpenH264 for H.264 where the OS has none. {webrtc.openh264.NOTICE} "
        'License: https://www.openh264.org/BINARY_LICENSE.txt',
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(parser.parse_args()))
