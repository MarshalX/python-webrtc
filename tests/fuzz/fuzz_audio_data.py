#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Fuzzes AudioData: creation, and copy_to with every conversion of format and layout."""

import sys

import atheris

with atheris.instrument_imports():
    from _input import Input

    import webrtc

FORMATS = list(webrtc.AudioSampleFormat)
EXPECTED = (TypeError, ValueError, BufferError, webrtc.NotSupportedError, webrtc.InvalidStateError)
SAMPLE_BYTES = {'u8': 1, 's16': 2, 's32': 4, 'f32': 4}


def check_identity(audio: webrtc.AudioData, data: bytes) -> None:
    """Interleaved samples copied out in their own format are the same bytes"""
    if audio.format.value.endswith('-planar'):
        return
    out = bytearray(audio.allocation_size({'plane_index': 0}))
    audio.copy_to(out, {'plane_index': 0})
    assert bytes(out) == data[: len(out)], f'{audio!r} copied out differently'


def test_one_input(data: bytes) -> None:
    inp = Input(data)
    format = inp.choice(FORMATS)
    frames, channels = inp.integer(512), inp.integer(8)
    sample_rate = inp.number(96000) if inp.flag() else 48000
    size = inp.small(1 << 14)
    if isinstance(frames, int) and isinstance(channels, int) and inp.flag():
        # exactly enough samples, when it's not too many
        exact = frames * channels * SAMPLE_BYTES[format.value.split('-')[0]]
        size = exact if 0 <= exact < 1 << 16 else size
    source = inp.buffer(size)
    try:
        audio = webrtc.AudioData(
            format=format,
            sample_rate=sample_rate,
            number_of_frames=frames,
            number_of_channels=channels,
            timestamp=inp.integer(),
            data=source,
        )
    except EXPECTED:
        return
    check_identity(audio, bytes(source))
    for _ in range(inp.small(4)):
        options = {'plane_index': inp.integer(8)}
        if inp.flag():
            options['frame_offset'] = inp.integer(512)
        if inp.flag():
            options['frame_count'] = inp.integer(512)
        if inp.flag():
            options['format'] = inp.choice(FORMATS)
        try:
            size = audio.allocation_size(options)
            audio.copy_to(inp.destination(min(size, 1 << 20)), options)
        except EXPECTED:
            pass
        if inp.small(8) == 0:
            audio = audio.clone()


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
