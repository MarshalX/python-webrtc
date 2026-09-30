#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes VideoFrame: creation from a buffer, copy_to with conversions and layouts, and frames of frames."""

from __future__ import annotations

import asyncio
import sys

import atheris

with atheris.instrument_imports():
    from inputs import Buffer, Input

    import webrtc

FORMATS = list(webrtc.VideoPixelFormat)
# what the specification lets these raise, and BufferError for read-only buffers; anything else is a bug
EXPECTED = (TypeError, ValueError, BufferError, webrtc.NotSupportedError, webrtc.InvalidStateError)

loop = asyncio.new_event_loop()


async def _copy_to(frame: webrtc.VideoFrame, destination: Buffer, options: dict[str, object] | None) -> None:
    await frame.copy_to(destination, options)


def copy_to(frame: webrtc.VideoFrame, destination: Buffer, options: dict[str, object] | None) -> None:
    loop.run_until_complete(_copy_to(frame, destination, options))


def rect(inp: Input) -> dict[str, float]:
    return {'x': inp.number(), 'y': inp.number(), 'width': inp.number(), 'height': inp.number()}


def layout(inp: Input) -> list[dict[str, object]]:
    return [{'offset': inp.integer(4096), 'stride': inp.integer(256)} for _ in range(inp.small(4))]


def copy_options(inp: Input) -> dict[str, object]:
    options: dict[str, object] = {}
    if inp.flag():
        options['rect'] = rect(inp)
    if inp.flag():
        options['layout'] = layout(inp)
    if inp.flag():
        options['format'] = inp.choice(FORMATS)
    return options


def frame_of_frame(inp: Input, frame: webrtc.VideoFrame) -> webrtc.VideoFrame:
    init: dict[str, object] = {'visible_rect': rect(inp)} if inp.flag() else {}
    if inp.flag():
        init['alpha'] = inp.choice(['keep', 'discard'])
    if inp.flag():
        init['rotation'] = inp.number(360)
        init['flip'] = inp.flag()
    if inp.flag():
        init['display_width'], init['display_height'] = inp.integer(), inp.integer()
    return webrtc.VideoFrame(frame, init)


def exercise(inp: Input, frame: webrtc.VideoFrame) -> None:
    for _ in range(inp.small(4)):
        action = inp.small(5)
        if action == 0:
            options = copy_options(inp)
            size = frame.allocation_size(options)
            copy_to(frame, inp.destination(min(size, 1 << 20)), options)
        elif action == 1:
            frame = frame_of_frame(inp, frame)
        elif action == 2:
            frame = frame.clone()
        elif action == 3:
            frame.close()
        else:
            frame.metadata()


def check_identity(format: webrtc.VideoPixelFormat, size: tuple[int, int], data: Buffer) -> None:
    """A packed frame copied out as it is gives the same bytes."""
    width, height = size
    init = {'format': format, 'coded_width': width, 'coded_height': height, 'timestamp': 0}
    size = webrtc.VideoFrame(bytes(1 << 16), init).allocation_size() if width * height <= 1024 else 0
    if not size:
        return
    packed = bytes(data)[:size] + bytes(max(0, size - len(data)))
    with webrtc.VideoFrame(packed, init) as frame:
        out = bytearray(size)
        copy_to(frame, out, None)
        assert bytes(out) == packed, f'{format} {width}x{height} copied out differently'


def test_one_input(data: bytes) -> None:
    inp = Input(data)
    format = inp.choice(FORMATS)
    if inp.flag():
        width, height = inp.small(32) + 1, inp.small(32) + 1
        check_identity(format, (width, height), inp.buffer(width * height * 8))
        return
    width, height = inp.integer(), inp.integer()
    init: dict[str, object] = {
        'format': format,
        'coded_width': width,
        'coded_height': height,
        'timestamp': inp.integer(),
    }
    if inp.flag():
        init['layout'] = layout(inp)
    if inp.flag():
        init['visible_rect'] = rect(inp)
    if inp.flag():
        init['rotation'] = inp.number(360)
    if inp.flag():
        init['display_width'], init['display_height'] = inp.integer(), inp.integer()
    try:
        frame = webrtc.VideoFrame(inp.buffer(inp.small(1 << 15)), init)
        exercise(inp, frame)
    except EXPECTED:
        pass


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
