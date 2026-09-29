#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""AudioData of WebCodecs: construction, copies and sample conversions."""

import array
import struct

import pytest

import webrtc
from webrtc import AudioSampleFormat


def f32(*values):
    return array.array('f', values).tobytes()


def audio_data(format='f32-planar', channels=2, frames=5, data=None, **init):
    size = {'u8': 1, 's16': 2}.get(format.split('-')[0], 4)
    return webrtc.AudioData(
        format=format,
        sample_rate=8000,
        number_of_frames=frames,
        number_of_channels=channels,
        timestamp=1234,
        data=data if data is not None else bytes(channels * frames * size),
        **init,
    )


def test_construct():
    """AudioData has the attributes of its init"""
    audio = audio_data(frames=100)
    assert audio.format == AudioSampleFormat.f32_planar
    assert (audio.sample_rate, audio.number_of_frames, audio.number_of_channels) == (8000, 100, 2)
    assert audio.duration == 100 / 8000 * 1_000_000
    assert audio.timestamp == 1234
    assert audio.numberOfFrames == 100
    audio.close()


def test_init_as_dictionary():
    """The init is also a dictionary with camelCase names"""
    init = {
        'format': 's16',
        'sampleRate': 48000,
        'numberOfFrames': 480,
        'numberOfChannels': 1,
        'timestamp': -10,
        'data': bytes(960),
    }
    audio = webrtc.AudioData(init)
    assert audio.timestamp == -10
    audio.close()


@pytest.mark.parametrize(
    'change',
    [
        {'format': 'x32'},
        {'frames': 0},
        {'channels': 0},
        {'data': bytes(3)},
    ],
)
def test_invalid_init(change):
    """An invalid init, or data too small for it, is a TypeError"""
    with pytest.raises(TypeError):
        audio_data(**change)


def test_close_and_clone():
    """A closed data has no samples, a clone is closed separately"""
    audio = audio_data()
    clone = audio.clone()
    audio.close()
    audio.close()
    assert (audio.format, audio.sample_rate, audio.number_of_frames, audio.number_of_channels) == (None, 0, 0, 0)
    with pytest.raises(webrtc.InvalidStateError):
        audio.copy_to(bytearray(20), {'plane_index': 0})
    assert clone.number_of_frames == 5
    clone.close()


def test_copy_frames_of_a_plane():
    """copyTo copies frame_count frames from frame_offset, of one plane"""
    audio = audio_data(data=f32(1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
    out = bytearray(12)
    options = webrtc.AudioDataCopyToOptions(plane_index=1, frame_offset=1, frame_count=3)
    assert audio.allocation_size(options) == 12
    audio.copy_to(out, options)
    assert array.array('f', out).tolist() == [7, 8, 9]
    audio.close()


def test_copy_to_interleaved_and_planar():
    """Planar data copies to an interleaved format with every channel, and back one channel at a time"""
    audio = audio_data(data=f32(1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
    out = bytearray(40)
    audio.copy_to(out, {'planeIndex': 0, 'format': 'f32'})
    assert array.array('f', out).tolist() == [1, 6, 2, 7, 3, 8, 4, 9, 5, 10]
    interleaved = audio_data(format='f32', data=bytes(out))
    plane = bytearray(20)
    interleaved.copy_to(plane, {'plane_index': 1, 'format': 'f32-planar'})
    assert array.array('f', plane).tolist() == [6, 7, 8, 9, 10]
    audio.close()
    interleaved.close()


@pytest.mark.parametrize(
    'options',
    [
        {'plane_index': 2},
        {'plane_index': 1, 'format': 'f32'},
        {'plane_index': 0, 'frame_offset': 5},
        {'plane_index': 0, 'frame_offset': 1, 'frame_count': 5},
    ],
)
def test_copy_ranges(options):
    """Planes and frames that don't exist are a RangeError"""
    audio = audio_data()
    with pytest.raises(webrtc.InvalidRangeError):
        audio.copy_to(bytearray(100), options)
    audio.close()


def test_destination_too_small():
    """A destination smaller than the copy is a RangeError"""
    audio = audio_data()
    with pytest.raises(webrtc.InvalidRangeError):
        audio.copy_to(bytearray(19), {'plane_index': 0})
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
def test_sample_conversions(source, destination):
    """Samples convert between types, scaled to their range"""
    values, code = VALUES[source]
    audio = audio_data(format=source, channels=1, frames=4, data=array.array(code, values).tobytes())
    expected, destination_code = VALUES[destination]
    out = array.array(destination_code, [0] * 4)
    audio.copy_to(memoryview(out).cast('B'), {'plane_index': 0, 'format': destination})
    # a coarser source can't reach the extremes of a finer destination exactly
    tolerance = {'u8': 1, 's16': 256, 's32': 2**24, 'f32': 1 / 64}[destination]
    for got, want in zip(out.tolist(), expected):
        assert abs(got - want) <= tolerance
    audio.close()


def test_s16_bytes_are_little_endian():
    """s16 samples are little endian, scaled by 1/32768 to f32"""
    audio = audio_data(format='s16', channels=1, frames=2, data=struct.pack('<2h', 1, -1))
    out = bytearray(8)
    audio.copy_to(out, {'plane_index': 0, 'format': 'f32'})
    assert array.array('f', out).tolist() == [1 / 32768, -1 / 32768]
    audio.close()
