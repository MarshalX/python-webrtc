#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""VideoFrame of WebCodecs: construction, copies, conversions and lifetime."""

import gc
import math
import struct

import pytest

import webrtc
from webrtc import PlaneLayout, VideoPixelFormat

# a 4x2 I420 frame: 8 samples of Y, 2 of U, 2 of V
I420_DATA = bytes(range(1, 13))


def i420_4x2(data=I420_DATA, **init):
    return webrtc.VideoFrame(data, **{'format': 'I420', 'coded_width': 4, 'coded_height': 2, 'timestamp': 0, **init})


def test_construct_from_buffer():
    """A frame has the attributes of its init, and defaults for the rest"""
    frame = i420_4x2(duration=15)
    assert frame.format == VideoPixelFormat.I420
    assert (frame.coded_width, frame.coded_height) == (4, 2)
    assert frame.visible_rect == webrtc.DOMRectReadOnly(0, 0, 4, 2)
    assert frame.coded_rect == frame.visible_rect
    assert (frame.display_width, frame.display_height) == (4, 2)
    assert (frame.timestamp, frame.duration) == (0, 15)
    assert frame.color_space == webrtc.VideoColorSpace('bt709', 'bt709', 'bt709', False)
    assert frame.codedWidth == frame.coded_width and frame.allocationSize() == 12
    frame.close()


def test_init_as_dataclass_or_dictionary():
    """The init is a dataclass, a dictionary with camelCase names, or keyword arguments"""
    init = webrtc.VideoFrameBufferInit(format=VideoPixelFormat.I420, coded_width=4, coded_height=2, timestamp=7)
    for frame in (
        webrtc.VideoFrame(I420_DATA, init),
        webrtc.VideoFrame(I420_DATA, {'format': 'I420', 'codedWidth': 4, 'codedHeight': 2, 'timestamp': 7}),
    ):
        assert frame.timestamp == 7
        frame.close()


@pytest.mark.parametrize(
    'init',
    [
        {'format': 'ABCD', 'coded_width': 4, 'coded_height': 2, 'timestamp': 0},
        {'format': 'I420', 'coded_width': 0, 'coded_height': 2, 'timestamp': 0},
        {'format': 'I420', 'coded_width': 2**32, 'coded_height': 2, 'timestamp': 0},
        {'format': 'I420', 'coded_width': 4, 'coded_height': 2, 'timestamp': 0, 'visible_rect': {'width': 0}},
        {'format': 'I420', 'coded_width': 4, 'coded_height': 2, 'timestamp': 0, 'display_width': 8},
        {'format': 'I420', 'coded_width': 4, 'coded_height': 2, 'timestamp': 0, 'visible_rect': {'x': 1, 'width': 2}},
        {'format': 'I420', 'coded_width': 4, 'coded_height': 2},
    ],
)
def test_invalid_init(init):
    """An invalid init, or a rect that isn't aligned to the chroma planes, is a TypeError"""
    with pytest.raises(TypeError):
        webrtc.VideoFrame(I420_DATA, **init)


def test_buffer_too_small():
    """The buffer must hold the frame at its layout"""
    with pytest.raises(TypeError):
        i420_4x2(I420_DATA[:11])
    with pytest.raises(TypeError):
        # a stride smaller than a row
        i420_4x2(layout=[PlaneLayout(0, 3), PlaneLayout(8, 2), PlaneLayout(10, 2)])


@pytest.mark.asyncio
async def test_buffer_is_copied():
    """Changing the buffer later doesn't change the frame"""
    data = bytearray(I420_DATA)
    frame = i420_4x2(data)
    data[0] = 99
    out = bytearray(12)
    await frame.copy_to(out)
    assert bytes(out) == I420_DATA
    frame.close()


@pytest.mark.asyncio
async def test_copy_to_layouts():
    """copyTo writes the planes at the layout asked for, and returns it"""
    frame = i420_4x2()
    out = bytearray(12)
    assert await frame.copy_to(out) == [PlaneLayout(0, 4), PlaneLayout(8, 2), PlaneLayout(10, 2)]
    assert bytes(out) == I420_DATA

    layout = [PlaneLayout(9, 5), PlaneLayout(1, 3), PlaneLayout(5, 3)]
    assert frame.allocation_size({'layout': layout}) == 19
    out = bytearray(19)
    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(layout=layout))
    assert list(out) == [0, 9, 10, 0, 0, 11, 12, 0, 0, 1, 2, 3, 4, 0, 5, 6, 7, 8, 0]
    frame.close()


@pytest.mark.asyncio
async def test_copy_to_rect():
    """A rect copies part of the frame, aligned to the chroma planes"""
    frame = i420_4x2()
    options = {'rect': {'x': 2, 'y': 0, 'width': 2, 'height': 2}}
    out = bytearray(frame.allocation_size(options))
    await frame.copy_to(out, options)
    assert list(out) == [3, 4, 7, 8, 10, 12]
    with pytest.raises(TypeError):
        frame.allocation_size({'rect': {'x': 1, 'y': 0, 'width': 2, 'height': 2}})
    frame.close()


@pytest.mark.asyncio
async def test_copy_to_errors():
    """A small buffer and a layout of the wrong number of planes are TypeErrors, other formats aren't supported"""
    frame = i420_4x2()
    with pytest.raises(TypeError):
        await frame.copy_to(bytearray(11))
    with pytest.raises(TypeError):
        frame.allocation_size({'layout': [PlaneLayout(0, 4)]})
    with pytest.raises(TypeError):
        # overlapping planes
        frame.allocation_size({'layout': [PlaneLayout(0, 4), PlaneLayout(0, 2), PlaneLayout(10, 2)]})
    with pytest.raises(webrtc.NotSupportedError):
        frame.allocation_size({'format': 'NV12'})
    frame.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['RGBA', 'RGBX', 'BGRA', 'BGRX'])
async def test_convert_i420_to_rgb(format):
    """copyTo converts YUV to the RGB formats, with the matrix and range of the frame"""
    # pure red in BT.601 limited range: Y 81, U 90, V 240
    data = bytes([81] * 16 + [90] * 4 + [240] * 4)
    frame = webrtc.VideoFrame(
        data,
        format='I420',
        coded_width=4,
        coded_height=4,
        timestamp=0,
        color_space={'matrix': 'smpte170m', 'full_range': False},
    )
    out = bytearray(frame.allocation_size({'format': format}))
    assert len(out) == 64
    assert await frame.copy_to(out, {'format': format}) == [PlaneLayout(0, 16)]
    r, g, b, a = out[:4] if format.startswith('RGB') else (out[2], out[1], out[0], out[3])
    assert r > 245 and g < 10 and b < 10 and a == 255
    frame.close()


@pytest.mark.asyncio
async def test_rgb_formats_swap_and_alpha():
    """RGBA converts to BGRA by swapping R and B, keeping alpha, and to RGBX without it"""
    frame = webrtc.VideoFrame(bytes([1, 2, 3, 4] * 4), format='RGBA', coded_width=2, coded_height=2, timestamp=0)
    assert frame.color_space.matrix == 'rgb' and frame.color_space.full_range
    out = bytearray(16)
    await frame.copy_to(out, {'format': 'BGRA'})
    assert list(out[:4]) == [3, 2, 1, 4]
    await frame.copy_to(out, {'format': 'RGBX'})
    assert list(out[:4]) == [1, 2, 3, 255]
    frame.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'format, size',
    [
        ('I420P10', 24),
        ('I420A', 20),
        ('I422', 16),
        ('I444P12', 48),
        ('I444A', 32),
        ('NV12', 12),
    ],
)
async def test_other_formats_round_trip(format, size):
    """Every planar format is kept as it is, and converts to RGBA"""
    data = bytes(i % 200 for i in range(size))
    frame = webrtc.VideoFrame(data, format=format, coded_width=4, coded_height=2, timestamp=0)
    assert frame.allocation_size() == size
    out = bytearray(size)
    await frame.copy_to(out)
    assert bytes(out) == data
    rgba = bytearray(32)
    await frame.copy_to(rgba, {'format': 'RGBA'})
    frame.close()


def test_high_bit_depth_samples_are_little_endian_16_bit():
    """P10 formats have 2 bytes a sample"""
    y = struct.pack('<8H', *[1023] * 8)
    uv = struct.pack('<4H', *[512] * 4)
    frame = webrtc.VideoFrame(y + uv, format='I420P10', coded_width=4, coded_height=2, timestamp=0)
    assert frame.allocation_size() == 24
    frame.close()


def test_frame_from_frame():
    """A frame from another one shares its pixels, with a visible rect, display size, timestamp or alpha of its own"""
    frame = i420_4x2(timestamp=1234, display_width=8, display_height=2)
    crop = webrtc.VideoFrame(frame, visible_rect={'x': 2, 'y': 0, 'width': 2, 'height': 2})
    assert (crop.coded_width, crop.visible_rect.x, crop.visible_rect.width) == (4, 2, 2)
    assert (crop.display_width, crop.display_height) == (4, 2)
    assert crop.timestamp == 1234

    later = webrtc.VideoFrame(frame, timestamp=5, duration=6)
    assert (later.timestamp, later.duration) == (5, 6)

    alpha = webrtc.VideoFrame(bytes(20), format='I420A', coded_width=4, coded_height=2, timestamp=0)
    assert webrtc.VideoFrame(alpha, alpha='discard').format == VideoPixelFormat.I420
    assert webrtc.VideoFrame(alpha, alpha='keep').format == VideoPixelFormat.I420A
    for f in (frame, crop, later, alpha):
        f.close()


def test_rotation_and_flip():
    """Rotations are rounded to a multiple of 90, and combine with the flip of the frame they're added to"""
    frame = webrtc.VideoFrame(bytes(32), format='RGBX', coded_width=4, coded_height=2, timestamp=0, rotation=-315)
    assert frame.rotation == 90
    assert (frame.display_width, frame.display_height) == (2, 4)
    flipped = webrtc.VideoFrame(frame, rotation=90, flip=True)
    assert (flipped.rotation, flipped.flip) == (180, True)
    again = webrtc.VideoFrame(flipped, rotation=90)
    assert (again.rotation, again.flip) == (90, True)
    for f in (frame, flipped, again):
        f.close()


@pytest.mark.parametrize('rotation', [math.inf, -math.inf, math.nan])
def test_rotation_must_be_finite(rotation):
    """A rotation is a WebIDL double: non-finite values raise TypeError, they raised OverflowError (found by fuzzing)"""
    with pytest.raises(TypeError):
        webrtc.VideoFrame(bytes(32), format='RGBX', coded_width=4, coded_height=2, timestamp=0, rotation=rotation)
    with webrtc.VideoFrame(bytes(32), format='RGBX', coded_width=4, coded_height=2, timestamp=0) as frame:
        with pytest.raises(TypeError):
            webrtc.VideoFrame(frame, rotation=rotation)


@pytest.mark.asyncio
async def test_close_and_clone():
    """A closed frame has no pixels, a clone is closed separately"""
    frame = i420_4x2()
    clone = frame.clone()
    frame.close()
    frame.close()
    assert frame.format is None and frame.coded_width == 0 and frame.visible_rect is None
    assert frame.timestamp == 0
    with pytest.raises(webrtc.InvalidStateError):
        frame.allocation_size()
    with pytest.raises(webrtc.InvalidStateError):
        await frame.copy_to(bytearray(12))
    with pytest.raises(webrtc.InvalidStateError):
        frame.clone()
    with pytest.raises(webrtc.InvalidStateError):
        webrtc.VideoFrame(frame)
    assert clone.format == VideoPixelFormat.I420
    with clone:
        assert clone.allocation_size() == 12
    assert clone.format is None


def test_unclosed_frame_warns():
    """A frame garbage collected without being closed warns"""
    with pytest.warns(ResourceWarning):
        i420_4x2()
        gc.collect()


@pytest.mark.asyncio
async def test_visible_rect_of_a_buffer_is_the_frame():
    """A frame created from a buffer keeps its visible rect only, which becomes the whole frame"""
    frame = i420_4x2(visible_rect={'x': 2, 'y': 0, 'width': 2, 'height': 2})
    assert (frame.coded_width, frame.coded_height) == (2, 2)
    assert frame.visible_rect == webrtc.DOMRectReadOnly(0, 0, 2, 2)
    out = bytearray(frame.allocation_size())
    await frame.copy_to(out)
    assert list(out) == [3, 4, 7, 8, 10, 12]
    frame.close()
