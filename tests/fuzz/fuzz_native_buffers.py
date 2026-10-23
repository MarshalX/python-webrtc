#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes the native buffer functions behind VideoFrame and AudioData directly, without the checks of Python.

The native module must stay memory safe on its own: it may raise, but never read or write out of a buffer.
"""

from __future__ import annotations

import contextlib
import sys

import atheris

with atheris.instrument_imports():
    from inputs import Input

import wrtc

PIXEL_FORMATS = [
    'I420', 'I420P10', 'I420P12', 'I420A', 'I420AP10', 'I420AP12', 'I422', 'I422P10', 'I422P12', 'I422A', 'I422AP10',
    'I422AP12', 'I444', 'I444P10', 'I444P12', 'I444A', 'I444AP10', 'I444AP12', 'NV12', 'RGBA', 'RGBX', 'BGRA', 'BGRX',
    'NV21', '',
]  # fmt: skip
SAMPLE_FORMATS = ['u8', 's16', 's32', 'f32', 'u8-planar', 's16-planar', 's32-planar', 'f32-planar', 'f64', '']
MATRICES = ['', 'rgb', 'bt709', 'bt470bg', 'smpte170m', 'bt2020-ncl', 'unknown']
# pybind11 raises TypeError for arguments it can't convert (negative or too large for size_t, overflowing int)
EXPECTED = (TypeError, ValueError, RuntimeError, BufferError)


def frame(inp: Input) -> wrtc.VideoFrameBuffer:
    width = inp.unsigned(40)
    height = inp.unsigned(40)
    layout = [(inp.unsigned(1 << 12), inp.unsigned(256)) for _ in range(inp.small(4))]
    format = inp.choice(PIXEL_FORMATS)
    data = inp.buffer(inp.small(1 << 15))
    return wrtc.VideoFrameBuffer.fromData(format, width, height, data, layout)


def plane_copy(inp: Input) -> tuple[int, int, int, int, int, int]:
    return (
        inp.unsigned(256),
        inp.unsigned(256),
        inp.unsigned(256),
        inp.unsigned(256),
        inp.unsigned(256),
        inp.unsigned(256),
    )


def copy_planes(inp: Input, buffer: wrtc.VideoFrameBuffer) -> None:
    copies = [plane_copy(inp) for _ in range(inp.small(4))]
    buffer.copyPlanes(inp.destination(inp.small(1 << 15)), copies)


def convert(inp: Input, buffer: wrtc.VideoFrameBuffer) -> None:
    destination = inp.destination(inp.small(1 << 15))
    format = inp.choice(PIXEL_FORMATS)
    x = inp.unsigned(40)
    y = inp.unsigned(40)
    width = inp.unsigned(40)
    height = inp.unsigned(40)
    offset = inp.unsigned(1 << 12)
    stride = inp.unsigned(256)
    matrix = inp.choice(MATRICES)
    full_range = inp.flag()
    buffer.convertTo(destination, format, x, y, width, height, offset, stride, matrix, full_range)


def video(inp: Input) -> None:
    buffer = frame(inp)
    for _ in range(inp.small(4)):
        action = inp.small(2)
        if action == 0:
            copy_planes(inp, buffer)
        elif action == 1:
            convert(inp, buffer)
        else:
            buffer = buffer.withoutAlpha()


def audio(inp: Input) -> None:
    source = inp.buffer(inp.small(1 << 14))
    source_format = inp.choice(SAMPLE_FORMATS)
    channels = inp.unsigned(8)
    frames = inp.unsigned(1024)
    destination = inp.destination(inp.small(1 << 14))
    destination_format = inp.choice(SAMPLE_FORMATS)
    plane_index = inp.unsigned(8)
    frame_offset = inp.unsigned(1024)
    frame_count = inp.unsigned(1024)
    wrtc.copyAudioSamples(
        source,
        source_format,
        channels,
        frames,
        destination,
        destination_format,
        plane_index,
        frame_offset,
        frame_count,
    )


def test_one_input(data: bytes) -> None:
    inp = Input(data)
    with contextlib.suppress(*EXPECTED):
        if inp.flag():
            video(inp)
        else:
            audio(inp)


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
