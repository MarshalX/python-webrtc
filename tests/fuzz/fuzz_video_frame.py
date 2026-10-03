#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes VideoFrame: creation from a buffer, copy_to with conversions and layouts, and frames of frames."""

from __future__ import annotations

import asyncio
import pathlib
import sys

import atheris

with atheris.instrument_imports():
    from inputs import Buffer, Input

    import webrtc

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from tests.helpers import mistyped

FORMATS = list(webrtc.VideoPixelFormat)
# what the specification lets these raise, and BufferError for read-only buffers; anything else is a bug
EXPECTED = (TypeError, ValueError, BufferError, webrtc.NotSupportedError, webrtc.InvalidStateError)

loop = asyncio.new_event_loop()


async def _copy_to(
    frame: webrtc.VideoFrame, destination: Buffer, options: webrtc.VideoFrameCopyToOptions | None
) -> None:
    await frame.copy_to(mistyped(destination), options)


def copy_to(frame: webrtc.VideoFrame, destination: Buffer, options: webrtc.VideoFrameCopyToOptions | None) -> None:
    loop.run_until_complete(_copy_to(frame, destination, options))


def rect(inp: Input) -> webrtc.DOMRectInit:
    return webrtc.DOMRectInit(inp.number(), inp.number(), inp.number(), inp.number())


def layout(inp: Input) -> list[webrtc.PlaneLayout]:
    return [webrtc.PlaneLayout(mistyped(inp.integer(4096)), mistyped(inp.integer(256))) for _ in range(inp.small(4))]


def copy_options(inp: Input) -> webrtc.VideoFrameCopyToOptions:
    options = webrtc.VideoFrameCopyToOptions()
    if inp.flag():
        options.rect = rect(inp)
    if inp.flag():
        options.layout = layout(inp)
    if inp.flag():
        options.format = inp.choice(FORMATS)
    return options


def frame_of_frame(inp: Input, frame: webrtc.VideoFrame) -> webrtc.VideoFrame:
    init = webrtc.VideoFrameInit(visible_rect=rect(inp) if inp.flag() else None)
    if inp.flag():
        init.alpha = inp.choice([webrtc.AlphaOption.keep, webrtc.AlphaOption.discard])
    if inp.flag():
        init.rotation = inp.number(360)
        init.flip = inp.flag()
    if inp.flag():
        init.display_width, init.display_height = mistyped(inp.integer()), mistyped(inp.integer())
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
    init = webrtc.VideoFrameBufferInit(format=format, coded_width=width, coded_height=height, timestamp=0)
    allocation = webrtc.VideoFrame(bytes(1 << 16), init).allocation_size() if width * height <= 1024 else 0
    if allocation == 0:
        return
    packed = bytes(data)[:allocation] + bytes(max(0, allocation - len(data)))
    with webrtc.VideoFrame(packed, init) as frame:
        out = bytearray(allocation)
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
    init = webrtc.VideoFrameBufferInit(
        format=format, coded_width=mistyped(width), coded_height=mistyped(height), timestamp=mistyped(inp.integer())
    )
    if inp.flag():
        init.layout = layout(inp)
    if inp.flag():
        init.visible_rect = rect(inp)
    if inp.flag():
        init.rotation = inp.number(360)
    if inp.flag():
        init.display_width, init.display_height = mistyped(inp.integer()), mistyped(inp.integer())
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
