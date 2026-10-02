#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""AudioData of WebCodecs: construction, copies and sample conversions."""

from __future__ import annotations

import array
import struct
from typing import TYPE_CHECKING

import pytest

import webrtc
from tests.helpers import mistyped
from webrtc import AudioSampleFormat

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Buffer


def f32(*values: float) -> bytes:
    return array.array('f', values).tobytes()


def audio_data(
    *,
    format: webrtc.AudioSampleFormatValue = 'f32-planar',
    channels: int = 2,
    frames: int = 5,
    data: bytes | bytearray | None = None,
    transfer: list[Buffer] | None = None,
) -> webrtc.AudioData:
    size = {'u8': 1, 's16': 2}.get(format.split('-', maxsplit=1)[0], 4)
    return webrtc.AudioData(
        webrtc.AudioDataInit(
            format=format,
            sample_rate=8000,
            number_of_frames=frames,
            number_of_channels=channels,
            timestamp=1234,
            data=data if data is not None else bytes(channels * frames * size),
            transfer=transfer if transfer is not None else [],
        )
    )


def test_construct() -> None:
    """AudioData has the attributes of its init."""
    audio = audio_data(frames=100)
    assert audio.format == AudioSampleFormat.f32_planar
    assert (audio.sample_rate, audio.number_of_frames, audio.number_of_channels) == (8000, 100, 2)
    assert audio.duration == 12_500
    assert audio.timestamp == 1234
    assert audio.numberOfFrames == 100
    audio.close()


def test_init_from_json() -> None:
    """The init comes from its JSON form with camelCase names, a dictionary isn't taken itself."""
    init: dict[str, object] = {
        'format': 's16',
        'sampleRate': 48000,
        'numberOfFrames': 480,
        'numberOfChannels': 1,
        'timestamp': -10,
        'data': bytes(960),
        'transfer': [],
    }
    audio = webrtc.AudioData(webrtc.AudioDataInit.from_json(init))
    assert audio.timestamp == -10
    options = webrtc.AudioDataCopyToOptions.from_json({'planeIndex': 0, 'frameCount': 2})
    assert audio.allocation_size(options) == 4
    audio.close()


@pytest.mark.parametrize(
    'create',
    [
        lambda: audio_data(format=mistyped('x32')),
        lambda: audio_data(frames=0),
        lambda: audio_data(channels=0),
        lambda: audio_data(data=bytes(3)),
    ],
    ids=['change0', 'change1', 'change2', 'change3'],
)
def test_invalid_init(create: Callable[[], webrtc.AudioData]) -> None:
    """An invalid init, or data too small for it, is a TypeError."""
    with pytest.raises(TypeError):
        create()


def test_close_and_clone() -> None:
    """A closed data has no samples, a clone is closed separately."""
    audio = audio_data()
    clone = audio.clone()
    audio.close()
    audio.close()
    assert (audio.format, audio.sample_rate, audio.number_of_frames, audio.number_of_channels) == (None, 0, 0, 0)
    with pytest.raises(webrtc.InvalidStateError):
        audio.copy_to(bytearray(20), webrtc.AudioDataCopyToOptions(plane_index=0))
    assert clone.number_of_frames == 5
    clone.close()


def test_copy_frames_of_a_plane() -> None:
    """CopyTo copies frame_count frames from frame_offset, of one plane."""
    audio = audio_data(data=f32(1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
    out = bytearray(12)
    options = webrtc.AudioDataCopyToOptions(plane_index=1, frame_offset=1, frame_count=3)
    assert audio.allocation_size(options) == 12
    audio.copy_to(out, options)
    assert array.array('f', out).tolist() == [7, 8, 9]
    audio.close()


def test_copy_to_interleaved_and_planar() -> None:
    """Planar data copies to an interleaved format with every channel, and back one channel at a time."""
    audio = audio_data(data=f32(1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
    out = bytearray(40)
    audio.copy_to(out, webrtc.AudioDataCopyToOptions(plane_index=0, format='f32'))
    assert array.array('f', out).tolist() == [1, 6, 2, 7, 3, 8, 4, 9, 5, 10]
    interleaved = audio_data(format='f32', data=bytes(out))
    plane = bytearray(20)
    interleaved.copy_to(plane, webrtc.AudioDataCopyToOptions(plane_index=1, format='f32-planar'))
    assert array.array('f', plane).tolist() == [6, 7, 8, 9, 10]
    audio.close()
    interleaved.close()


@pytest.mark.parametrize(
    'options',
    [
        webrtc.AudioDataCopyToOptions(plane_index=2),
        webrtc.AudioDataCopyToOptions(plane_index=1, format='f32'),
        webrtc.AudioDataCopyToOptions(plane_index=0, frame_offset=5),
        webrtc.AudioDataCopyToOptions(plane_index=0, frame_offset=1, frame_count=5),
    ],
)
def test_copy_ranges(options: webrtc.AudioDataCopyToOptions) -> None:
    """Planes and frames that don't exist are a RangeError."""
    audio = audio_data()
    with pytest.raises(webrtc.InvalidRangeError):
        audio.copy_to(bytearray(100), options)
    audio.close()


def test_destination_too_small() -> None:
    """A destination smaller than the copy is a RangeError."""
    audio = audio_data()
    with pytest.raises(webrtc.InvalidRangeError):
        audio.copy_to(bytearray(19), webrtc.AudioDataCopyToOptions(plane_index=0))
    audio.close()


# minimum, maximum, half and silence of each type, as the WPT test of conversions takes them
VALUES = {
    'u8': ([0, 255, 191, 128], 'B'),
    's16': ([-(2**15), 2**15 - 1, (2**15 - 1) // 2, 0], 'h'),
    's32': ([-(2**31), 2**31 - 1, (2**31 - 1) // 2, 0], 'i'),
    'f32': ([-1.0, 1.0, 0.5, 0.0], 'f'),
}


@pytest.mark.parametrize('source', VALUES)
@pytest.mark.parametrize('destination', VALUES)
def test_sample_conversions(source: webrtc.AudioSampleFormatValue, destination: webrtc.AudioSampleFormatValue) -> None:
    """Samples convert between types, scaled to their range."""
    values, code = VALUES[source]
    audio = audio_data(format=source, channels=1, frames=4, data=array.array(code, values).tobytes())
    expected, destination_code = VALUES[destination]
    out = array.array(destination_code, [0] * 4)
    audio.copy_to(memoryview(out).cast('B'), webrtc.AudioDataCopyToOptions(plane_index=0, format=destination))
    # a coarser source can't reach the extremes of a finer destination exactly
    tolerance = {'u8': 1, 's16': 256, 's32': 2**24, 'f32': 1 / 64}[destination]
    for got, want in zip(out.tolist(), expected):
        assert abs(got - want) <= tolerance
    audio.close()


@pytest.mark.parametrize('destination', ['u8', 's16', 's32'])
def test_non_finite_f32_samples_convert(destination: webrtc.AudioSampleFormatValue) -> None:
    """NaN is silence and infinities are the extremes; converting NaN was undefined behavior (found by fuzzing)."""
    values = [float('nan'), float('inf'), float('-inf')]
    audio = audio_data(format='f32', channels=1, frames=3, data=array.array('f', values).tobytes())
    silence, maximum, minimum = VALUES[destination][0][3], VALUES[destination][0][1], VALUES[destination][0][0]
    out = array.array(VALUES[destination][1], [1] * 3)
    audio.copy_to(memoryview(out).cast('B'), webrtc.AudioDataCopyToOptions(plane_index=0, format=destination))
    assert out.tolist() == [silence, maximum, minimum]
    audio.close()


def test_s16_bytes_are_little_endian() -> None:
    """s16 samples are little endian, scaled by 1/32768 to f32."""
    audio = audio_data(format='s16', channels=1, frames=2, data=struct.pack('<2h', 1, -1))
    out = bytearray(8)
    audio.copy_to(out, webrtc.AudioDataCopyToOptions(plane_index=0, format='f32'))
    assert array.array('f', out).tolist() == [1 / 32768, -1 / 32768]
    audio.close()


def test_transfer_keeps_the_buffer() -> None:
    """Transferred data is kept without a copy, and the buffer can't be resized while kept."""
    data = bytearray(f32(1, 2))
    audio = audio_data(format='f32', channels=1, frames=2, data=data, transfer=[data])
    with pytest.raises(BufferError):
        data.append(0)
    out = bytearray(8)
    audio.copy_to(out, webrtc.AudioDataCopyToOptions(plane_index=0))
    assert bytes(out) == f32(1, 2)
    audio.close()


def test_data_is_copied_unless_transferred() -> None:
    """Data not in transfer is copied, while transferred memoryviews are released."""
    data = bytearray(f32(1, 2))
    other = bytearray(4)
    view = memoryview(other)
    audio = audio_data(format='f32', channels=1, frames=2, data=data, transfer=[view])
    data[:4] = f32(9)
    with pytest.raises(ValueError, match='released'):
        view.tobytes()
    other.append(0)
    out = bytearray(8)
    audio.copy_to(out, webrtc.AudioDataCopyToOptions(plane_index=0))
    assert bytes(out) == f32(1, 2)
    audio.close()


def test_transfer_twice() -> None:
    """A buffer transferred twice, even through a view, is a DataCloneError."""
    data = bytearray(8)
    with pytest.raises(webrtc.DataCloneError, match='more than once'):
        audio_data(format='f32', channels=1, frames=2, data=data, transfer=[data, memoryview(data)])
