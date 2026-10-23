#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""AudioData of WebCodecs: construction, copies and sample conversions."""

from __future__ import annotations

import array
import gc
import struct
from typing import TYPE_CHECKING, NamedTuple

import pytest

import webrtc
from tests.helpers import mistyped
from webrtc import AudioSampleFormat

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Buffer


#: Bytes per sample of the sample types narrower than 4 bytes
SAMPLE_SIZES = {'u8': 1, 's16': 2}


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
    if data is None:
        sample_type = format.split('-', maxsplit=1)[0]
        data = bytes(channels * frames * SAMPLE_SIZES.get(sample_type, 4))
    init = webrtc.AudioDataInit(
        format=format,
        sample_rate=8000,
        number_of_frames=frames,
        number_of_channels=channels,
        timestamp=1234,
        data=data,
        transfer=transfer if transfer is not None else [],
    )
    return webrtc.AudioData(init)


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
    options = webrtc.AudioDataCopyToOptions.from_json({'planeIndex': 0, 'frameCount': 2})

    assert audio.timestamp == -10
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


def drop_unclosed_data() -> None:
    audio_data()
    gc.collect()


def test_unclosed_data_warns() -> None:
    """A data garbage collected without being closed warns."""
    gc.collect()
    with pytest.warns(ResourceWarning, match='AudioData'):
        drop_unclosed_data()


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


class Samples(NamedTuple):
    """The minimum, maximum, half and silence of a sample type, and its array typecode."""

    values: list[float]
    typecode: str


#: The samples of each type, as the WPT test of conversions takes them
VALUES = {
    'u8': Samples([0, 255, 191, 128], 'B'),
    's16': Samples([-(2**15), 2**15 - 1, (2**15 - 1) // 2, 0], 'h'),
    's32': Samples([-(2**31), 2**31 - 1, (2**31 - 1) // 2, 0], 'i'),
    'f32': Samples([-1.0, 1.0, 0.5, 0.0], 'f'),
}

#: How far a converted sample may be off: a coarser source can't reach the extremes of a finer destination exactly
TOLERANCES = {'u8': 1, 's16': 256, 's32': 2**24, 'f32': 1 / 64}


@pytest.mark.parametrize('source', VALUES)
@pytest.mark.parametrize('destination', VALUES)
def test_sample_conversions(source: webrtc.AudioSampleFormatValue, destination: webrtc.AudioSampleFormatValue) -> None:
    """Samples convert between types, scaled to their range."""
    values, typecode = VALUES[source]
    audio = audio_data(format=source, channels=1, frames=4, data=array.array(typecode, values).tobytes())
    expected, destination_typecode = VALUES[destination]
    out = array.array(destination_typecode, [0] * 4)
    options = webrtc.AudioDataCopyToOptions(plane_index=0, format=destination)

    audio.copy_to(memoryview(out).cast('B'), options)

    for got, want in zip(out.tolist(), expected):
        assert abs(got - want) <= TOLERANCES[destination]
    audio.close()


@pytest.mark.parametrize('destination', ['u8', 's16', 's32'])
def test_non_finite_f32_samples_convert(destination: webrtc.AudioSampleFormatValue) -> None:
    """NaN is silence and infinities are the extremes; converting NaN was undefined behavior (found by fuzzing)."""
    values = [float('nan'), float('inf'), float('-inf')]
    audio = audio_data(format='f32', channels=1, frames=3, data=array.array('f', values).tobytes())
    (minimum, maximum, _half, silence), typecode = VALUES[destination]
    out = array.array(typecode, [1] * 3)
    options = webrtc.AudioDataCopyToOptions(plane_index=0, format=destination)

    audio.copy_to(memoryview(out).cast('B'), options)

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


def test_transfer_is_a_sequence_of_buffers() -> None:
    """A single buffer as transfer is a TypeError."""
    data = bytearray(8)
    with pytest.raises(TypeError, match='transfer is a sequence of buffers'):
        audio_data(format='f32', channels=1, frames=2, data=data, transfer=mistyped(data))


@pytest.mark.parametrize(
    ('members', 'error'),
    [
        ({'number_of_frames': -1}, 'number_of_frames must be a non-negative integer'),
        ({'timestamp': 1.5}, 'timestamp is an integer'),
        ({'data': 7}, 'data must be a bytes-like buffer'),
    ],
    ids=['negative frames', 'float timestamp', 'data not a buffer'],
)
def test_invalid_init_member(members: dict[str, object], error: str) -> None:
    """Each invalid member of an init is a TypeError naming it."""
    init = webrtc.AudioDataInit(
        format='u8', sample_rate=8000, number_of_frames=1, number_of_channels=1, timestamp=0, data=bytes(1)
    )
    for name, value in members.items():
        setattr(init, name, value)

    with pytest.raises(TypeError, match=error):
        webrtc.AudioData(init)


def test_negative_copy_option() -> None:
    """A negative frame offset is a TypeError."""
    audio = audio_data()
    options = webrtc.AudioDataCopyToOptions(plane_index=0, frame_offset=-1)

    with pytest.raises(TypeError, match='frame_offset must be a non-negative integer, not -1'):
        audio.allocation_size(options)

    audio.close()


def test_closed_data_repr_duration_and_clone() -> None:
    """A closed data has no duration and can't be cloned."""
    audio = audio_data(frames=80)
    assert repr(audio) == '<webrtc.AudioData f32-planar 2ch 80 frames 8000 Hz timestamp=1234>'

    audio.close()

    assert repr(audio) == '<webrtc.AudioData closed>'
    assert audio.duration == 0
    with pytest.raises(webrtc.InvalidStateError, match='closed'):
        audio.clone()
