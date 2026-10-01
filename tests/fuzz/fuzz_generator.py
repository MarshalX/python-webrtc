#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes what generators send: arbitrary AudioData and VideoFrame written to tracks of a connected peer connection.

libwebrtc checks what it's given with RTC_CHECK, which aborts the process: the generators must reject what it can't
take. The remote tracks are read by processors, so received frames go through the native path too.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import atheris

with atheris.instrument_imports():
    from inputs import Input

    import webrtc

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from tests.helpers import connect, mistyped

EXPECTED = (TypeError, ValueError, BufferError, webrtc.NotSupportedError, webrtc.InvalidStateError)
PIXEL_FORMATS = list(webrtc.VideoPixelFormat)
SAMPLE_FORMATS = list(webrtc.AudioSampleFormat)
SAMPLE_BYTES = {'u8': 1, 's16': 2, 's32': 4, 'f32': 4}
RATES = [1, 100, 1499, 1500, 3000, 7999, 8000, 11025, 16000, 22050, 44100, 48000, 96000, 192000, 384000, 384001]

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


class Session:
    """A connected pair sending a generator of each kind, whose writers are replaced once they fail."""

    caller: webrtc.RTCPeerConnection
    callee: webrtc.RTCPeerConnection
    processors: list[webrtc.MediaStreamTrackProcessor]
    senders: dict[webrtc.MediaTypeValue, webrtc.RTCRtpSender]
    writers: dict[webrtc.MediaTypeValue, webrtc.WritableStreamDefaultWriter[object]]

    async def start(self) -> None:
        self.caller, self.callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        self.processors = []
        self.callee.on(
            'track',
            lambda event: self.processors.append(
                webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(event.track))
            ),
        )
        self.senders = {}
        self.writers = {}
        for kind in ('audio', 'video'):
            generator = webrtc.MediaStreamTrackGenerator(kind)
            self.senders[kind] = self.caller.add_track(generator)
            self.writers[kind] = generator.writable.get_writer()
        await connect(self.caller, self.callee)

    async def write(self, kind: webrtc.MediaTypeValue, chunk: webrtc.AudioData | webrtc.VideoFrame) -> None:
        try:
            await self.writers[kind].write(chunk)
        except EXPECTED:
            # an errored stream fails every write after: send a new generator
            generator = webrtc.MediaStreamTrackGenerator(kind)
            await self.senders[kind].replace_track(generator)
            self.writers[kind] = generator.writable.get_writer()
        # lets the media threads and the processors run
        await asyncio.sleep(0)


def audio_data(inp: Input) -> webrtc.AudioData:
    format = inp.choice(SAMPLE_FORMATS)
    channels = inp.small(20) if inp.flag() else inp.integer(20)
    rate = inp.choice(RATES) if inp.flag() else inp.number(400000)
    frames = inp.small(8000) if inp.flag() else inp.integer(8000)
    if not (
        isinstance(channels, int)
        and not isinstance(channels, bool)
        and channels > 0
        and isinstance(frames, int)
        and not isinstance(frames, bool)
        and frames > 0
    ):
        channels, frames = 1, 480
    size = min(frames * channels * SAMPLE_BYTES[format.value.split('-')[0]], 1 << 20)
    return webrtc.AudioData(
        webrtc.AudioDataInit(
            format=format,
            sample_rate=rate,
            number_of_frames=frames,
            number_of_channels=channels,
            timestamp=mistyped(inp.integer()),
            data=bytes(size),
        )
    )


def video_frame(inp: Input) -> webrtc.VideoFrame:
    format = inp.choice(PIXEL_FORMATS)
    width = inp.small(64) + 1 if inp.flag() else inp.choice([1, 2, 3, 15, 16, 17, 639, 640, 1920, 4096])
    height = inp.small(64) + 1 if inp.flag() else inp.choice([1, 2, 3, 15, 16, 17, 479, 480, 1080, 4096])
    init = webrtc.VideoFrameBufferInit(
        format=format, coded_width=width, coded_height=height, timestamp=mistyped(inp.integer())
    )
    if inp.flag():
        init.rotation = inp.choice([0, 90, 180, 270])
    # enough for every format: 4 planes of 16-bit samples at most
    return webrtc.VideoFrame(inp.buffer(width * height * 8), init)


session = Session()
loop.run_until_complete(session.start())


def test_one_input(data: bytes) -> None:
    inp = Input(data)
    for _ in range(inp.small(3) + 1):
        kind = 'audio' if inp.flag() else 'video'
        try:
            chunk = audio_data(inp) if kind == 'audio' else video_frame(inp)
        except EXPECTED:
            continue
        loop.run_until_complete(session.write(kind, chunk))


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
