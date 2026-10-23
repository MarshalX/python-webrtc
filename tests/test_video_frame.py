#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""VideoFrame of WebCodecs: construction, copies, conversions and lifetime."""

from __future__ import annotations

import gc
import math
import struct
import threading

import pytest
from typing_extensions import TypedDict, Unpack

import webrtc
from tests.helpers import mistyped
from webrtc import PlaneLayout, VideoPixelFormat

# a 4x2 I420 frame: 8 samples of Y, 2 of U, 2 of V
I420_DATA = bytes(range(1, 13))
# pure red in BT.601 limited range
BT601_RED = (81, 90, 240)
BT601_LIMITED = webrtc.VideoColorSpaceInit(matrix='smpte170m', full_range=False)


class I420Init(TypedDict, total=False, closed=True):
    duration: int | None
    layout: list[PlaneLayout] | None
    visible_rect: webrtc.DOMRectInit | None
    display_width: int | None
    display_height: int | None
    metadata: webrtc.VideoFrameMetadata | None


class BufferInit(TypedDict, total=False, closed=True):
    rotation: float
    display_width: int | None
    display_height: int | None
    color_space: webrtc.VideoColorSpaceInit | None


def i420_4x2(data: bytes | bytearray = I420_DATA, *, timestamp: int = 0, **init: Unpack[I420Init]) -> webrtc.VideoFrame:
    return webrtc.VideoFrame(
        data,
        webrtc.VideoFrameBufferInit(format='I420', coded_width=4, coded_height=2, timestamp=timestamp, **init),
    )


def frame_of(
    data: bytes, format: webrtc.VideoPixelFormatValue, *, width: int, height: int, **init: Unpack[BufferInit]
) -> webrtc.VideoFrame:
    """A frame of a buffer at timestamp 0."""
    buffer_init = webrtc.VideoFrameBufferInit(
        format=format, coded_width=width, coded_height=height, timestamp=0, **init
    )
    return webrtc.VideoFrame(data, buffer_init)


def solid_i420_4x4(yuv: tuple[int, int, int], color_space: webrtc.VideoColorSpaceInit) -> webrtc.VideoFrame:
    """A 4x4 I420 frame of a single color."""
    y, u, v = yuv
    return frame_of(bytes([y] * 16 + [u] * 4 + [v] * 4), 'I420', width=4, height=4, color_space=color_space)


def rgba(pixel: bytes | bytearray, format: webrtc.VideoPixelFormatValue) -> tuple[int, int, int, int]:
    """The red, green, blue and alpha of a pixel of an RGB or BGR format."""
    if format.startswith('BGR'):
        return pixel[2], pixel[1], pixel[0], pixel[3]
    return pixel[0], pixel[1], pixel[2], pixel[3]


def assert_red(pixel: bytes | bytearray, format: webrtc.VideoPixelFormatValue) -> None:
    red, green, blue, _ = rgba(pixel, format)
    assert red > 245
    assert green < 10
    assert blue < 10


def test_construct_from_buffer() -> None:
    """A frame has the attributes of its init, and defaults for the rest."""
    frame = i420_4x2(duration=15)

    assert frame.format == VideoPixelFormat.I420
    assert (frame.coded_width, frame.coded_height) == (4, 2)
    assert frame.visible_rect == webrtc.DOMRectReadOnly(0, 0, 4, 2)
    assert frame.coded_rect == frame.visible_rect
    assert (frame.display_width, frame.display_height) == (4, 2)
    assert (frame.timestamp, frame.duration) == (0, 15)
    assert frame.color_space == webrtc.VideoColorSpace('bt709', 'bt709', 'bt709', full_range=False)
    assert frame.codedWidth == frame.coded_width
    assert frame.allocationSize() == 12
    frame.close()


def test_init_from_json() -> None:
    """An init comes from its JSON form, with camelCase names and nested dictionaries."""
    init = webrtc.VideoFrameBufferInit.from_json({
        'format': 'I420',
        'codedWidth': 4,
        'codedHeight': 2,
        'timestamp': 7,
        'visibleRect': {'x': 2, 'width': 2, 'height': 2},
        'layout': [{'offset': 0, 'stride': 4}, {'offset': 8, 'stride': 2}, {'offset': 10, 'stride': 2}],
        'colorSpace': {'fullRange': True},
        'unknown': 1,
    })

    assert init.visible_rect == webrtc.DOMRectInit(x=2, width=2, height=2)
    assert init.layout == [PlaneLayout(0, 4), PlaneLayout(8, 2), PlaneLayout(10, 2)]
    assert init.color_space == webrtc.VideoColorSpaceInit(full_range=True)

    with webrtc.VideoFrame(I420_DATA, init) as frame:
        assert frame.timestamp == 7
        assert frame.visible_rect == webrtc.DOMRectReadOnly(0, 0, 2, 2)
        assert frame.color_space.full_range is True

    options = webrtc.VideoFrameCopyToOptions.from_json({'rect': {'width': 4, 'height': 2}, 'format': 'RGBA'})
    assert options.rect == webrtc.DOMRectInit(width=4, height=2)


def test_buffer_needs_an_init() -> None:
    """A frame of a buffer has no defaults for its format and size."""
    # a buffer, where only a frame may come without an init
    buffer: webrtc.VideoFrame = mistyped(I420_DATA)

    with pytest.raises(TypeError, match='needs a VideoFrameBufferInit'):
        webrtc.VideoFrame(buffer)


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
def test_invalid_init(init: dict[str, object]) -> None:
    """An invalid init, or a rect that isn't aligned to the chroma planes, is a TypeError."""
    with pytest.raises(TypeError):
        webrtc.VideoFrame(I420_DATA, webrtc.VideoFrameBufferInit.from_json(init))


def test_buffer_too_small() -> None:
    """The buffer must hold the frame at its layout."""
    with pytest.raises(TypeError):
        i420_4x2(I420_DATA[:11])
    with pytest.raises(TypeError):
        # a stride smaller than a row
        i420_4x2(layout=[PlaneLayout(0, 3), PlaneLayout(8, 2), PlaneLayout(10, 2)])


@pytest.mark.asyncio
async def test_buffer_is_copied() -> None:
    """Changing the buffer later doesn't change the frame."""
    data = bytearray(I420_DATA)
    frame = i420_4x2(data)

    data[0] = 99

    out = bytearray(12)
    await frame.copy_to(out)
    assert bytes(out) == I420_DATA
    frame.close()


@pytest.mark.asyncio
async def test_copy_to_layouts() -> None:
    """CopyTo writes the planes at the layout asked for, and returns it."""
    frame = i420_4x2()
    out = bytearray(12)
    assert await frame.copy_to(out) == [PlaneLayout(0, 4), PlaneLayout(8, 2), PlaneLayout(10, 2)]
    assert bytes(out) == I420_DATA

    layout = [PlaneLayout(9, 5), PlaneLayout(1, 3), PlaneLayout(5, 3)]
    options = webrtc.VideoFrameCopyToOptions(layout=layout)
    assert frame.allocation_size(options) == 19
    out = bytearray(19)
    await frame.copy_to(out, options)
    assert list(out) == [0, 9, 10, 0, 0, 11, 12, 0, 0, 1, 2, 3, 4, 0, 5, 6, 7, 8, 0]
    frame.close()


@pytest.mark.asyncio
async def test_copy_to_rect() -> None:
    """A rect copies part of the frame, aligned to the chroma planes."""
    frame = i420_4x2()
    options = webrtc.VideoFrameCopyToOptions(rect=webrtc.DOMRectInit(x=2, y=0, width=2, height=2))
    unaligned = webrtc.VideoFrameCopyToOptions(rect=webrtc.DOMRectInit(x=1, y=0, width=2, height=2))

    out = bytearray(frame.allocation_size(options))
    await frame.copy_to(out, options)

    assert list(out) == [3, 4, 7, 8, 10, 12]
    with pytest.raises(TypeError):
        frame.allocation_size(unaligned)
    frame.close()


@pytest.mark.asyncio
async def test_copy_to_errors() -> None:
    """A small buffer and a layout of the wrong number of planes are TypeErrors, other formats aren't supported."""
    frame = i420_4x2()
    overlapping = [PlaneLayout(0, 4), PlaneLayout(0, 2), PlaneLayout(10, 2)]

    with pytest.raises(TypeError):
        await frame.copy_to(bytearray(11))
    with pytest.raises(TypeError):
        frame.allocation_size(webrtc.VideoFrameCopyToOptions(layout=[PlaneLayout(0, 4)]))
    with pytest.raises(TypeError):
        frame.allocation_size(webrtc.VideoFrameCopyToOptions(layout=overlapping))
    with pytest.raises(webrtc.NotSupportedError):
        frame.allocation_size(webrtc.VideoFrameCopyToOptions(format='NV12'))
    frame.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['RGBA', 'RGBX', 'BGRA', 'BGRX'])
async def test_convert_i420_to_rgb(format: webrtc.VideoPixelFormatValue) -> None:
    """CopyTo converts YUV to the RGB formats, with the matrix and range of the frame."""
    frame = solid_i420_4x4(BT601_RED, BT601_LIMITED)
    options = webrtc.VideoFrameCopyToOptions(format=format)

    out = bytearray(frame.allocation_size(options))
    layout = await frame.copy_to(out, options)

    assert len(out) == 64
    assert layout == [PlaneLayout(0, 16)]
    assert_red(out[:4], format)
    assert rgba(out[:4], format)[3] == 255
    frame.close()


@pytest.mark.asyncio
async def test_rgb_formats_swap_and_alpha() -> None:
    """RGBA converts to BGRA by swapping R and B, keeping alpha, and to RGBX without it."""
    frame = frame_of(bytes([1, 2, 3, 4] * 4), 'RGBA', width=2, height=2)
    out = bytearray(16)

    assert frame.color_space.matrix == 'rgb'
    assert frame.color_space.full_range is True

    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(format='BGRA'))
    assert list(out[:4]) == [3, 2, 1, 4]

    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(format='RGBX'))
    assert list(out[:4]) == [1, 2, 3, 255]
    frame.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['RGBA', 'BGRA'])
@pytest.mark.parametrize(
    ('full_range', 'yuv'),
    [(False, (74, 97, 240)), (True, (67, 92, 255))],
    ids=['limited', 'full'],
)
async def test_convert_bt2020_to_rgb(
    format: webrtc.VideoPixelFormatValue, *, full_range: bool, yuv: tuple[int, int, int]
) -> None:
    """BT.2020 frames convert with the BT.2020 matrix in their range."""
    frame = solid_i420_4x4(yuv, webrtc.VideoColorSpaceInit(matrix='bt2020-ncl', full_range=full_range))
    out = bytearray(64)

    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(format=format))

    assert_red(out[:4], format)
    frame.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['RGBA', 'BGRA'])
@pytest.mark.parametrize(
    ('full_range', 'yuv'),
    [(False, (63, 102, 240)), (True, (54, 99, 255))],
    ids=['limited', 'full'],
)
async def test_convert_bt709_to_rgb(
    format: webrtc.VideoPixelFormatValue, *, full_range: bool, yuv: tuple[int, int, int]
) -> None:
    """BT.709 frames convert with the BT.709 matrix in their range."""
    frame = solid_i420_4x4(yuv, webrtc.VideoColorSpaceInit(matrix='bt709', full_range=full_range))
    out = bytearray(64)

    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(format=format))

    assert_red(out[:4], format)
    frame.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['RGBX', 'BGRX'])
async def test_convert_nv12_to_rgb(format: webrtc.VideoPixelFormatValue) -> None:
    """The interleaved chroma is read as U then V."""
    y, u, v = BT601_RED
    frame = frame_of(bytes([y] * 8 + [u, v] * 2), 'NV12', width=4, height=2, color_space=BT601_LIMITED)
    out = bytearray(32)

    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(format=format))

    for offset in range(0, len(out), 4):
        pixel = out[offset : offset + 4]
        assert_red(pixel, format)
        assert rgba(pixel, format)[3] == 255
    frame.close()


@pytest.mark.asyncio
async def test_convert_i422a_to_rgba_keeps_the_alpha() -> None:
    """The I422A alpha plane becomes the RGBA alpha."""
    alpha = [10, 20, 30, 40, 50, 60, 70, 80]
    # 4x2 grey: Y 8, U 4, V 4, A 8
    frame = frame_of(bytes([128] * 16 + alpha), 'I422A', width=4, height=2)
    out = bytearray(32)

    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(format='RGBA'))
    assert list(out[3::4]) == alpha

    await frame.copy_to(out, webrtc.VideoFrameCopyToOptions(format='RGBX'))
    assert list(out[3::4]) == [255] * 8
    frame.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('format', 'size'),
    [
        ('I420P10', 24),
        ('I420A', 20),
        ('I422', 16),
        ('I444P12', 48),
        ('I444A', 32),
        ('NV12', 12),
    ],
)
async def test_other_formats_round_trip(format: webrtc.VideoPixelFormatValue, size: int) -> None:
    """Every planar format is kept as it is, and converts to RGBA."""
    data = bytes(i % 200 for i in range(size))
    frame = frame_of(data, format, width=4, height=2)
    out = bytearray(size)

    assert frame.allocation_size() == size
    await frame.copy_to(out)
    assert bytes(out) == data

    await frame.copy_to(bytearray(32), webrtc.VideoFrameCopyToOptions(format='RGBA'))
    frame.close()


def test_high_bit_depth_samples_are_little_endian_16_bit() -> None:
    """P10 formats have 2 bytes a sample."""
    y = struct.pack('<8H', *[1023] * 8)
    uv = struct.pack('<4H', *[512] * 4)

    frame = frame_of(y + uv, 'I420P10', width=4, height=2)

    assert frame.allocation_size() == 24
    frame.close()


def test_frame_from_frame() -> None:
    """A frame from another one shares its pixels, with a visible rect, display size, timestamp or alpha of its own."""
    frame = i420_4x2(timestamp=1234, display_width=8, display_height=2)
    right_half = webrtc.DOMRectInit(x=2, y=0, width=2, height=2)

    crop = webrtc.VideoFrame(frame, webrtc.VideoFrameInit(visible_rect=right_half))
    assert crop.visible_rect is not None
    assert (crop.coded_width, crop.visible_rect.x, crop.visible_rect.width) == (4, 2, 2)
    assert (crop.display_width, crop.display_height) == (4, 2)
    assert crop.timestamp == 1234

    later = webrtc.VideoFrame(frame, webrtc.VideoFrameInit(timestamp=5, duration=6))
    assert (later.timestamp, later.duration) == (5, 6)

    alpha = frame_of(bytes(20), 'I420A', width=4, height=2)
    assert webrtc.VideoFrame(alpha, webrtc.VideoFrameInit(alpha='discard')).format == VideoPixelFormat.I420
    assert webrtc.VideoFrame(alpha, webrtc.VideoFrameInit(alpha='keep')).format == VideoPixelFormat.I420A

    for opened in (frame, crop, later, alpha):
        opened.close()


def test_rotation_and_flip() -> None:
    """Rotations are rounded to a multiple of 90, and combine with the flip of the frame they're added to."""
    frame = frame_of(bytes(32), 'RGBX', width=4, height=2, rotation=-315)
    assert frame.rotation == 90
    assert (frame.display_width, frame.display_height) == (2, 4)

    flipped = webrtc.VideoFrame(frame, webrtc.VideoFrameInit(rotation=90, flip=True))
    assert (flipped.rotation, flipped.flip) == (180, True)

    again = webrtc.VideoFrame(flipped, webrtc.VideoFrameInit(rotation=90))
    assert (again.rotation, again.flip) == (90, True)

    for opened in (frame, flipped, again):
        opened.close()


@pytest.mark.parametrize('rotation', [math.inf, -math.inf, math.nan])
def test_rotation_must_be_finite(rotation: float) -> None:
    """A rotation is a WebIDL double: non-finite values are a TypeError, not an OverflowError (found by fuzzing)."""
    with pytest.raises(TypeError):
        frame_of(bytes(32), 'RGBX', width=4, height=2, rotation=rotation)

    frame = frame_of(bytes(32), 'RGBX', width=4, height=2)
    with frame, pytest.raises(TypeError):
        webrtc.VideoFrame(frame, webrtc.VideoFrameInit(rotation=rotation))


@pytest.mark.asyncio
async def test_close_and_clone() -> None:
    """A closed frame has no pixels, a clone is closed separately."""
    frame = i420_4x2()
    clone = frame.clone()

    frame.close()
    frame.close()

    assert frame.format is None
    assert frame.coded_width == 0
    assert frame.visible_rect is None
    assert frame.timestamp == 0
    with pytest.raises(webrtc.InvalidStateError):
        frame.allocation_size()
    with pytest.raises(webrtc.InvalidStateError):
        await frame.copy_to(bytearray(12))
    with pytest.raises(webrtc.InvalidStateError):
        frame.clone()
    with pytest.raises(webrtc.InvalidStateError):
        webrtc.VideoFrame(frame)

    clone_format = clone.format
    assert clone_format == VideoPixelFormat.I420
    with clone:
        assert clone.allocation_size() == 12
    assert clone.format is None


def drop_unclosed_frame() -> None:
    i420_4x2()
    gc.collect()


def test_unclosed_frame_warns() -> None:
    """A frame garbage collected without being closed warns."""
    with pytest.warns(ResourceWarning):
        drop_unclosed_frame()


@pytest.mark.asyncio
async def test_visible_rect_of_a_buffer_is_the_frame() -> None:
    """A frame created from a buffer keeps its visible rect only, which becomes the whole frame."""
    frame = i420_4x2(visible_rect=webrtc.DOMRectInit(x=2, y=0, width=2, height=2))

    assert (frame.coded_width, frame.coded_height) == (2, 2)
    assert frame.visible_rect == webrtc.DOMRectReadOnly(0, 0, 2, 2)

    out = bytearray(frame.allocation_size())
    await frame.copy_to(out)
    assert list(out) == [3, 4, 7, 8, 10, 12]
    frame.close()


def test_metadata_is_copied() -> None:
    """The metadata of an init is a deep copy, kept by frames of the frame unless given again."""
    metadata = webrtc.VideoFrameMetadata(rtp_timestamp=7)
    frame = i420_4x2(metadata=metadata)

    metadata.rtp_timestamp = 8

    assert frame.metadata() == webrtc.VideoFrameMetadata(rtp_timestamp=7)
    assert frame.metadata() is not frame.metadata()
    other = webrtc.VideoFrame(frame)
    assert other.metadata().rtp_timestamp == 7
    replaced = webrtc.VideoFrame(frame, webrtc.VideoFrameInit(metadata=webrtc.VideoFrameMetadata()))
    assert replaced.metadata().rtp_timestamp is None
    assert i420_4x2().metadata() == webrtc.VideoFrameMetadata()

    for opened in (frame, other, replaced):
        opened.close()
    with pytest.raises(webrtc.InvalidStateError):
        frame.metadata()


def test_init_metadata_from_json() -> None:
    """The metadata of an init comes from its JSON form too."""
    init = webrtc.VideoFrameInit.from_json({'metadata': {'rtpTimestamp': 3}})

    assert init.metadata == webrtc.VideoFrameMetadata(rtp_timestamp=3)


@pytest.mark.asyncio
async def test_transfer() -> None:
    """Transferred buffers are validated and memoryviews released; the pixels are copied all the same."""
    data = bytearray(I420_DATA)
    view = memoryview(data)

    def init(transfer: list[bytes | bytearray | memoryview]) -> webrtc.VideoFrameBufferInit:
        return webrtc.VideoFrameBufferInit(
            format='I420', coded_width=4, coded_height=2, timestamp=0, transfer=list(transfer)
        )

    with pytest.raises(webrtc.DataCloneError):
        webrtc.VideoFrame(data, init([data, view]))
    with pytest.raises(TypeError, match='transfer takes buffers'):
        webrtc.VideoFrame(data, init([mistyped(1)]))

    frame = webrtc.VideoFrame(view, init([view]))
    with pytest.raises(ValueError, match='released'):
        view.tobytes()

    data[0] = 0
    data.append(0)  # not held by the frame
    out = bytearray(12)
    await frame.copy_to(out)
    assert bytes(out) == I420_DATA
    frame.close()

    released = memoryview(b'')
    released.release()
    with pytest.raises(webrtc.DataCloneError, match='released'):
        webrtc.VideoFrame(I420_DATA, init([released]))


@pytest.mark.parametrize('format', ['RGBA', 'BGRX'])
def test_copy_to_color_space(format: webrtc.VideoPixelFormatValue) -> None:
    """Conversions to RGB are in srgb, the only color space libyuv converts to."""
    frame = i420_4x2()
    options = webrtc.VideoFrameCopyToOptions(format=format, color_space='srgb')

    assert frame.allocation_size(options) == 32
    assert webrtc.VideoFrameCopyToOptions.from_json({'colorSpace': 'srgb'}).color_space == 'srgb'
    for color_space in ('srgb-linear', 'display-p3', 'display-p3-linear'):
        with pytest.raises(webrtc.NotSupportedError, match=color_space):
            frame.allocation_size(webrtc.VideoFrameCopyToOptions(format=format, color_space=color_space))
    # copies without a conversion take no color space
    assert frame.allocation_size(webrtc.VideoFrameCopyToOptions(color_space='display-p3')) == 12
    with pytest.raises(TypeError, match='not a PredefinedColorSpace'):
        frame.allocation_size(webrtc.VideoFrameCopyToOptions(color_space=mistyped('rec2020')))
    frame.close()


def test_construct_with_positional_source() -> None:
    """The image or data of a frame is positional only, as it has another name per overload."""
    frame = i420_4x2()

    with pytest.raises(TypeError):
        webrtc.VideoFrame(source=frame)  # pyrefly: ignore[no-matching-overload]
    frame.close()


def test_dom_rect_from_rect_and_to_json() -> None:
    """fromRect() copies a rect init, toJSON() gives every attribute."""
    rect = webrtc.DOMRectReadOnly.fromRect(webrtc.DOMRectInit(x=1, y=2, width=-3, height=4))

    assert rect == webrtc.DOMRectReadOnly(1, 2, -3, 4)
    assert webrtc.DOMRectReadOnly.from_rect() == webrtc.DOMRectReadOnly()
    assert rect.toJSON() == {
        'x': 1,
        'y': 2,
        'width': -3,
        'height': 4,
        'top': 2,
        'right': 1,
        'bottom': 6,
        'left': -2,
    }


def test_color_space_to_json() -> None:
    """toJSON() gives the four members, with fullRange in camelCase."""
    color_space = webrtc.VideoColorSpace('bt709', 'iec61966-2-1', 'rgb', full_range=True)

    assert color_space.to_json() == {
        'primaries': 'bt709',
        'transfer': 'iec61966-2-1',
        'matrix': 'rgb',
        'fullRange': True,
    }
    assert webrtc.VideoColorSpace().toJSON() == {'primaries': None, 'transfer': None, 'matrix': None, 'fullRange': None}


def test_discarding_the_alpha_of_rgba() -> None:
    """Discarding the alpha of an RGB format gives its X format."""
    for format, opaque in (('RGBA', VideoPixelFormat.RGBX), ('BGRA', VideoPixelFormat.BGRX)):
        with (
            frame_of(bytes(32), format, width=4, height=2) as frame,
            webrtc.VideoFrame(frame, webrtc.VideoFrameInit(alpha='discard')) as discarded,
        ):
            assert discarded.format == opaque


def test_source_must_be_a_buffer_or_a_frame() -> None:
    """A frame is created from a buffer or a frame, each with its own init."""
    init = webrtc.VideoFrameBufferInit(format='I420', coded_width=4, coded_height=2, timestamp=0)
    number: bytes = mistyped(1)
    frame_init: webrtc.VideoFrameInit = mistyped(init)

    with pytest.raises(TypeError, match='from a buffer or a VideoFrame, not int'):
        webrtc.VideoFrame(number, init)
    with i420_4x2() as frame, pytest.raises(TypeError, match='takes a VideoFrameInit'):
        webrtc.VideoFrame(frame, frame_init)


@pytest.mark.parametrize(
    ('init', 'error'),
    [
        ({'display_width': 0, 'display_height': 0}, 'display size must be positive'),
        ({'timestamp': 1.5}, 'timestamp is an integer'),
        ({'metadata': {'rtp_timestamp': 1}}, 'metadata is a VideoFrameMetadata, not dict'),
    ],
    ids=['zero display size', 'float timestamp', 'metadata of another type'],
)
def test_invalid_buffer_init(init: dict[str, object], error: str) -> None:
    """Each invalid member of a buffer init is a TypeError naming it."""
    buffer_init = webrtc.VideoFrameBufferInit(format='I420', coded_width=4, coded_height=2, timestamp=0)
    for name, value in init.items():
        setattr(buffer_init, name, value)

    with pytest.raises(TypeError, match=error):
        webrtc.VideoFrame(I420_DATA, buffer_init)


def test_metadata_that_can_not_be_cloned() -> None:
    """Metadata that can't be structured-cloned is a DataCloneError."""
    metadata = webrtc.VideoFrameMetadata(rtp_timestamp=mistyped(threading.Lock()))

    with pytest.raises(webrtc.DataCloneError, match='lock'):
        i420_4x2(metadata=metadata)


@pytest.mark.parametrize(
    ('rect', 'error'),
    [
        (webrtc.DOMRectInit(x=2, y=0, width=4, height=2), 'inside of the coded size'),
        (webrtc.DOMRectInit(x=0, y=0, width=2.5, height=2), 'integer coordinates'),
    ],
    ids=['outside', 'fractional'],
)
def test_invalid_visible_rect_of_a_frame(rect: webrtc.DOMRectInit, error: str) -> None:
    """The visible rect is inside the coded size, with integer coordinates."""
    with i420_4x2() as frame, pytest.raises(TypeError, match=error):
        webrtc.VideoFrame(frame, webrtc.VideoFrameInit(visible_rect=rect))


def test_display_size_of_a_frame_of_a_frame() -> None:
    """A display size scaled down to nothing is a TypeError."""
    init = webrtc.VideoFrameInit(display_width=8, display_height=6)
    with i420_4x2() as frame, webrtc.VideoFrame(frame, init) as shown:
        assert (shown.display_width, shown.display_height) == (8, 6)

    one_pixel = webrtc.VideoFrameInit(visible_rect=webrtc.DOMRectInit(width=1, height=1))
    with (
        frame_of(bytes(32), 'RGBX', width=4, height=2, display_width=1, display_height=1) as small,
        pytest.raises(TypeError, match='display size would be zero'),
    ):
        webrtc.VideoFrame(small, one_pixel)


def test_planes_larger_than_an_unsigned_long() -> None:
    """Planes ending past the largest unsigned long are a TypeError."""
    layout = [PlaneLayout(2**32 - 5, 4), PlaneLayout(0, 2), PlaneLayout(4, 2)]

    with i420_4x2() as frame, pytest.raises(TypeError, match='planes are too large'):
        frame.allocation_size(webrtc.VideoFrameCopyToOptions(layout=layout))


def test_repr_and_closed_coded_rect() -> None:
    """A closed frame has no coded rect."""
    frame = i420_4x2(timestamp=42)
    assert repr(frame) == '<webrtc.VideoFrame I420 4x2 timestamp=42>'

    frame.close()

    assert repr(frame) == '<webrtc.VideoFrame closed>'
    assert frame.coded_rect is None


def test_camel_case_alias_sets_the_member() -> None:
    metadata = webrtc.VideoFrameMetadata()

    metadata.rtpTimestamp = 9

    assert metadata.rtp_timestamp == 9
