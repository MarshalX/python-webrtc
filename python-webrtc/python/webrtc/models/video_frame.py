#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The WebCodecs :obj:`VideoFrame`, its rectangles, color space and the dictionaries that create and copy it."""

from __future__ import annotations

import asyncio
import copy
import math
import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, NamedTuple, TypeVar, cast, overload

from webrtc import (
    AlphaOption,
    AlphaOptionValue,
    DataCloneError,
    InvalidStateError,
    NotSupportedError,
    PredefinedColorSpace,
    PredefinedColorSpaceValue,
    RTCException,
    VideoColorPrimaries,
    VideoColorPrimariesValue,
    VideoMatrixCoefficients,
    VideoMatrixCoefficientsValue,
    VideoPixelFormat,
    VideoPixelFormatValue,
    VideoTransferCharacteristics,
    VideoTransferCharacteristicsValue,
    wrtc,
)
from webrtc.models.closable import Closable
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias
from webrtc.utils.transfer import Transfer

if TYPE_CHECKING:
    from typing_extensions import Buffer, TypeGuard

_EnumT = TypeVar('_EnumT', bound=Enum)

_MAX_UNSIGNED_LONG = 2**32 - 1
_RGB_FORMATS = (VideoPixelFormat.RGBA, VideoPixelFormat.RGBX, VideoPixelFormat.BGRA, VideoPixelFormat.BGRX)


@dataclass(frozen=True)
class DOMRectReadOnly:
    """An immutable rectangle, like the coded or visible part of a frame.

    The width and height may be negative. The edges are then measured from :attr:`x` and :attr:`y` backwards.

    See :mdn:`DOMRectReadOnly`.

    Args:
        x (:obj:`float`, optional): The horizontal origin, 0 by default.
        y (:obj:`float`, optional): The vertical origin, 0 by default.
        width (:obj:`float`, optional): The width, 0 by default.
        height (:obj:`float`, optional): The height, 0 by default.
    """

    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0

    @property
    def top(self) -> float:
        """:obj:`float`: The smaller of :attr:`y` and :attr:`y` plus :attr:`height`.

        See :mdn:`DOMRectReadOnly/top`.
        """
        return min(self.y, self.y + self.height)

    @property
    def right(self) -> float:
        """:obj:`float`: The larger of :attr:`x` and :attr:`x` plus :attr:`width`.

        See :mdn:`DOMRectReadOnly/right`.
        """
        return max(self.x, self.x + self.width)

    @property
    def bottom(self) -> float:
        """:obj:`float`: The larger of :attr:`y` and :attr:`y` plus :attr:`height`.

        See :mdn:`DOMRectReadOnly/bottom`.
        """
        return max(self.y, self.y + self.height)

    @property
    def left(self) -> float:
        """:obj:`float`: The smaller of :attr:`x` and :attr:`x` plus :attr:`width`.

        See :mdn:`DOMRectReadOnly/left`.
        """
        return min(self.x, self.x + self.width)

    @classmethod
    def from_rect(cls, other: DOMRectInit | DOMRectReadOnly | None = None) -> DOMRectReadOnly:
        """Creates a rectangle with the origin and size of another one.

        See :mdn:`DOMRectReadOnly/fromRect_static`.

        Args:
            other (:obj:`DOMRectInit` or :obj:`DOMRectReadOnly`, optional): The rectangle to copy. When left
                out, the result is an empty rectangle at the origin.

        Returns:
            :obj:`DOMRectReadOnly`: The new rectangle.
        """
        if other is None:
            return cls()
        return cls(other.x, other.y, other.width, other.height)

    def to_json(self) -> dict[str, float]:
        """Serializes the rectangle, including its edges.

        See :mdn:`DOMRectReadOnly/toJSON`.

        Returns:
            :obj:`dict`: The ``x``, ``y``, ``width``, ``height``, ``top``, ``right``, ``bottom`` and ``left`` values.
        """
        return {
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'top': self.top,
            'right': self.right,
            'bottom': self.bottom,
            'left': self.left,
        }

    #: Alias for :meth:`from_rect`
    fromRect: ClassVar = from_rect
    #: Alias for :meth:`to_json`
    toJSON: ClassVar = to_json


@dataclass
class DOMRectInit(Dictionary):
    """A rectangle passed as an option, like the visible part of a new frame.

    Wherever one is accepted, a :obj:`DOMRectReadOnly` is accepted too.

    See :mdn:`DOMRectReadOnly/fromRect_static`.

    Args:
        x (:obj:`float`, optional): The horizontal origin, 0 by default.
        y (:obj:`float`, optional): The vertical origin, 0 by default.
        width (:obj:`float`, optional): The width, 0 by default.
        height (:obj:`float`, optional): The height, 0 by default.
    """

    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0


@dataclass
class PlaneLayout(Dictionary):
    """The position of one plane of pixels in a buffer.

    See :mdn:`VideoFrame/copyTo`.

    Args:
        offset (:obj:`int`): The index of the plane's first byte in the buffer.
        stride (:obj:`int`): The number of bytes from the start of one row to the start of the next, padding included.
    """

    offset: int
    stride: int


@dataclass
class VideoColorSpace:
    """The color space of a frame, read from :attr:`VideoFrame.color_space`. A member is :obj:`None` when unknown.

    Frames received from a track carry no color space of their own and report BT.601 (``smpte170m``) with a
    limited range. That's the default of the software decoders.

    See :mdn:`VideoColorSpace`.

    Args:
        primaries (:obj:`webrtc.VideoColorPrimaries`, optional): The color primaries.
        transfer (:obj:`webrtc.VideoTransferCharacteristics`, optional): The transfer characteristics.
        matrix (:obj:`webrtc.VideoMatrixCoefficients`, optional): The matrix that converts between RGB and YUV.
        full_range (:obj:`bool`, optional): Whether samples span the full range of their bits. If not, they
            use the limited (studio) range.
    """

    primaries: VideoColorPrimaries | VideoColorPrimariesValue | None = None
    transfer: VideoTransferCharacteristics | VideoTransferCharacteristicsValue | None = None
    matrix: VideoMatrixCoefficients | VideoMatrixCoefficientsValue | None = None
    full_range: bool | None = None

    def to_json(self) -> dict[str, str | bool | None]:
        """Serializes the color space.

        See :mdn:`VideoColorSpace/toJSON`.

        Returns:
            :obj:`dict`: The ``primaries``, ``transfer``, ``matrix`` and ``fullRange`` values.
        """
        return {
            'primaries': self.primaries,
            'transfer': self.transfer,
            'matrix': self.matrix,
            'fullRange': self.full_range,
        }

    #: Alias for :attr:`full_range`
    fullRange: ClassVar[Alias[bool | None]] = alias('full_range')
    #: Alias for :meth:`to_json`
    toJSON: ClassVar = to_json


@dataclass
class VideoColorSpaceInit(Dictionary):
    """A color space passed to a new frame. A :obj:`VideoColorSpace` is accepted too.

    See :mdn:`VideoColorSpace/VideoColorSpace`.

    Args:
        primaries (:obj:`webrtc.VideoColorPrimaries`, optional): The color primaries.
        transfer (:obj:`webrtc.VideoTransferCharacteristics`, optional): The transfer characteristics.
        matrix (:obj:`webrtc.VideoMatrixCoefficients`, optional): The matrix that converts between RGB and YUV.
        full_range (:obj:`bool`, optional): Whether samples span the full range of their bits. If not, they
            use the limited (studio) range.
    """

    primaries: VideoColorPrimaries | VideoColorPrimariesValue | None = None
    transfer: VideoTransferCharacteristics | VideoTransferCharacteristicsValue | None = None
    matrix: VideoMatrixCoefficients | VideoMatrixCoefficientsValue | None = None
    full_range: bool | None = None

    #: Alias for :attr:`full_range`
    fullRange: ClassVar[Alias[bool | None]] = alias('full_range')


_REC709 = VideoColorSpace(
    VideoColorPrimaries.bt709, VideoTransferCharacteristics.bt709, VideoMatrixCoefficients.bt709, full_range=False
)
_SRGB = VideoColorSpace(
    VideoColorPrimaries.bt709, VideoTransferCharacteristics.iec61966_2_1, VideoMatrixCoefficients.rgb, full_range=True
)
# libwebrtc frames carry no color space: its software codecs (VP8, VP9, AV1) use BT.601 unless told otherwise
_REC601 = VideoColorSpace(
    VideoColorPrimaries.smpte170m,
    VideoTransferCharacteristics.smpte170m,
    VideoMatrixCoefficients.smpte170m,
    full_range=False,
)


@dataclass
class VideoFrameMetadata(Dictionary):
    """Extra facts about a frame, returned by :meth:`VideoFrame.metadata`.

    See :mdn:`VideoFrame/metadata`.

    Args:
        rtp_timestamp (:obj:`int`, optional): The RTP timestamp of a frame received from a remote peer, or
            :obj:`None` for local frames.
    """

    rtp_timestamp: int | None = None

    #: Alias for :attr:`rtp_timestamp`
    rtpTimestamp: ClassVar[Alias[int | None]] = alias('rtp_timestamp')


@dataclass
class VideoFrameBufferInit(Dictionary):
    """Options to create a :obj:`VideoFrame` from a buffer of pixels.

    Only the pixels of the visible rectangle are kept. They become the whole frame, so its coded size is the size
    of ``visible_rect``.

    See :mdn:`VideoFrame/VideoFrame`.

    Args:
        format (:obj:`webrtc.VideoPixelFormat`): The pixel format of the buffer.
        coded_width (:obj:`int`): The width of the pixels in the buffer, which must be positive.
        coded_height (:obj:`int`): The height of the pixels in the buffer, which must be positive.
        timestamp (:obj:`int`): The presentation time in microseconds.
        duration (:obj:`int`, optional): The duration in microseconds.
        layout (:obj:`list` of :obj:`PlaneLayout`, optional): The offset and stride of each plane in the buffer.
            By default, the planes are tightly packed one after another.
        visible_rect (:obj:`DOMRectInit`, optional): The part of the pixels to keep. Its coordinates are integers
            aligned to the chroma subsampling. All the pixels are kept by default.
        rotation (:obj:`float`, optional): The clockwise rotation to apply when showing the frame, rounded to the
            nearest multiple of 90.
        flip (:obj:`bool`, optional): Whether to mirror the frame horizontally when showing it, before rotating.
        display_width (:obj:`int`, optional): The width to show the frame at, given together with
            ``display_height``. By default, the display size is the visible size after rotation.
        display_height (:obj:`int`, optional): The height to show the frame at, given together with
            ``display_width``.
        color_space (:obj:`VideoColorSpaceInit`, optional): The color space. By default, it's sRGB for RGB formats
            and BT.709 with a limited range for the others.
        metadata (:obj:`VideoFrameMetadata`, optional): Extra facts about the frame, deep-copied.
        transfer (:obj:`list` of bytes-like buffers, optional): Buffers to give up to the frame. The pixels are
            copied regardless. Transferred :obj:`memoryview` objects are released, but other buffers stay usable.
    """

    _dictionaries: ClassVar = {
        'layout': PlaneLayout,
        'visible_rect': DOMRectInit,
        'color_space': VideoColorSpaceInit,
        'metadata': VideoFrameMetadata,
    }

    format: VideoPixelFormat | VideoPixelFormatValue
    coded_width: int
    coded_height: int
    timestamp: int
    duration: int | None = None
    layout: list[PlaneLayout] | None = None
    visible_rect: DOMRectInit | DOMRectReadOnly | None = None
    rotation: float = 0
    flip: bool = False
    display_width: int | None = None
    display_height: int | None = None
    color_space: VideoColorSpaceInit | VideoColorSpace | None = None
    metadata: VideoFrameMetadata | None = None
    transfer: list[Buffer] = field(default_factory=list)

    #: Alias for :attr:`coded_width`
    codedWidth: ClassVar[Alias[int]] = alias('coded_width')
    #: Alias for :attr:`coded_height`
    codedHeight: ClassVar[Alias[int]] = alias('coded_height')
    #: Alias for :attr:`visible_rect`
    visibleRect: ClassVar[Alias[DOMRectInit | DOMRectReadOnly | None]] = alias('visible_rect')
    #: Alias for :attr:`display_width`
    displayWidth: ClassVar[Alias[int | None]] = alias('display_width')
    #: Alias for :attr:`display_height`
    displayHeight: ClassVar[Alias[int | None]] = alias('display_height')
    #: Alias for :attr:`color_space`
    colorSpace: ClassVar[Alias[VideoColorSpaceInit | VideoColorSpace | None]] = alias('color_space')


@dataclass
class VideoFrameInit(Dictionary):
    """Options to create a :obj:`VideoFrame` from another one. Anything left out is taken from the source frame.

    The new frame shares the pixels of the source and always keeps its color space.

    See :mdn:`VideoFrame/VideoFrame`.

    Args:
        timestamp (:obj:`int`, optional): The presentation time in microseconds.
        duration (:obj:`int`, optional): The duration in microseconds.
        alpha (:obj:`webrtc.AlphaOption`, optional): Whether to keep the alpha channel. With ``discard``, the frame
            switches to the matching format without alpha.
        visible_rect (:obj:`DOMRectInit`, optional): The part of the source's coded pixels to show. Its coordinates
            are integers aligned to the chroma subsampling. Unless the display size is given, it's scaled to match.
        rotation (:obj:`float`, optional): A clockwise rotation added to the source's, rounded to the nearest
            multiple of 90.
        flip (:obj:`bool`, optional): Whether to mirror the frame horizontally. It toggles the source's flip.
        display_width (:obj:`int`, optional): The width to show the frame at, given together with
            ``display_height``.
        display_height (:obj:`int`, optional): The height to show the frame at, given together with
            ``display_width``.
        metadata (:obj:`VideoFrameMetadata`, optional): Extra facts that replace the source's, deep-copied.
    """

    _dictionaries: ClassVar = {'visible_rect': DOMRectInit, 'metadata': VideoFrameMetadata}

    timestamp: int | None = None
    duration: int | None = None
    alpha: AlphaOption | AlphaOptionValue = AlphaOption.keep
    visible_rect: DOMRectInit | DOMRectReadOnly | None = None
    rotation: float = 0
    flip: bool = False
    display_width: int | None = None
    display_height: int | None = None
    metadata: VideoFrameMetadata | None = None

    #: Alias for :attr:`visible_rect`
    visibleRect: ClassVar[Alias[DOMRectInit | DOMRectReadOnly | None]] = alias('visible_rect')
    #: Alias for :attr:`display_width`
    displayWidth: ClassVar[Alias[int | None]] = alias('display_width')
    #: Alias for :attr:`display_height`
    displayHeight: ClassVar[Alias[int | None]] = alias('display_height')


@dataclass
class VideoFrameCopyToOptions(Dictionary):
    """Options for :meth:`VideoFrame.copy_to` and :meth:`VideoFrame.allocation_size`.

    See :mdn:`VideoFrame/copyTo`.

    Args:
        rect (:obj:`DOMRectInit`, optional): The part of the coded pixels to copy. Its coordinates are integers
            aligned to the chroma subsampling. By default, the visible rectangle is copied.
        layout (:obj:`list` of :obj:`PlaneLayout`, optional): Where to write each plane in the destination.
            By default, the planes are tightly packed one after another.
        format (:obj:`webrtc.VideoPixelFormat`, optional): The format to write. It's either the frame's own
            format, or one of ``RGBA``, ``RGBX``, ``BGRA`` and ``BGRX`` to convert to RGB.
        color_space (:obj:`webrtc.PredefinedColorSpace`, optional): The color space of an RGB conversion. Only
            ``srgb`` is supported, and it's the default.
    """

    _dictionaries: ClassVar = {'rect': DOMRectInit, 'layout': PlaneLayout}

    rect: DOMRectInit | DOMRectReadOnly | None = None
    layout: list[PlaneLayout] | None = None
    format: VideoPixelFormat | VideoPixelFormatValue | None = None
    color_space: PredefinedColorSpace | PredefinedColorSpaceValue | None = None

    #: Alias for :attr:`color_space`
    colorSpace: ClassVar[Alias[PredefinedColorSpace | PredefinedColorSpaceValue | None]] = alias('color_space')


class _Plane(NamedTuple):
    sample_bytes: int
    subsampling_x: int
    subsampling_y: int

    def rows(self, rect: DOMRectReadOnly) -> tuple[int, int]:
        """The first row of the rect in the plane and the number of rows."""
        top = int(rect.y) // self.subsampling_y
        return top, -(-int(rect.y + rect.height) // self.subsampling_y) - top

    def columns(self, rect: DOMRectReadOnly) -> tuple[int, int]:
        """The first byte of the rect in a row of the plane and the number of bytes."""
        left = int(rect.x) // self.subsampling_x
        width = -(-int(rect.x + rect.width) // self.subsampling_x) - left
        return left * self.sample_bytes, width * self.sample_bytes


def _planes(format: VideoPixelFormat) -> list[_Plane]:
    if format in _RGB_FORMATS:
        return [_Plane(4, 1, 1)]
    if format == VideoPixelFormat.NV12:
        return [_Plane(1, 1, 1), _Plane(2, 2, 2)]
    name = format.value
    sample_bytes = 2 if name.endswith(('P10', 'P12')) else 1
    x, y = {'I420': (2, 2), 'I422': (2, 1), 'I444': (1, 1)}[name[:4]]
    planes = [_Plane(sample_bytes, 1, 1), _Plane(sample_bytes, x, y), _Plane(sample_bytes, x, y)]
    if name[4:5] == 'A':
        planes.append(_Plane(sample_bytes, 1, 1))
    return planes


def _has_alpha(format: VideoPixelFormat) -> bool:
    return format in {VideoPixelFormat.RGBA, VideoPixelFormat.BGRA} or format.value[4:5] == 'A'


def _without_alpha(format: VideoPixelFormat) -> VideoPixelFormat:
    if format in {VideoPixelFormat.RGBA, VideoPixelFormat.BGRA}:
        return VideoPixelFormat(format.value[:3] + 'X')
    return VideoPixelFormat(format.value[:4] + format.value[5:])


def _enum(cls: type[_EnumT], value: object) -> _EnumT:
    try:
        return cls(value)
    except ValueError:
        msg = f'{value!r} is not a {cls.__name__}'
        raise TypeError(msg) from None


def _optional_enum(cls: type[_EnumT], value: object) -> _EnumT | None:
    return None if value is None else _enum(cls, value)


def _is_buffer(value: object) -> TypeGuard[Buffer]:
    try:
        # the buffer protocol has no runtime check of its own before Python 3.12: memoryview() is the check
        _ = memoryview(cast('Buffer', value))
    except TypeError:
        return False
    return True


def _buffer_size(data: Buffer) -> int:
    return memoryview(data).nbytes


def _dimension(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_UNSIGNED_LONG:
        msg = f'{name} must be an unsigned 32-bit integer, not {value!r}'
        raise TypeError(msg)
    return value


def _display_size(init: VideoFrameBufferInit | VideoFrameInit) -> tuple[int, int] | None:
    """The display size of an init, if given."""
    if (init.display_width is None) != (init.display_height is None):
        msg = 'display_width and display_height go together'
        raise TypeError(msg)
    if init.display_width is None:
        return None
    width, height = _dimension(init.display_width, 'display_width'), _dimension(init.display_height, 'display_height')
    if width == 0 or height == 0:
        msg = 'The display size must be positive'
        raise TypeError(msg)
    return width, height


def _is_sideways(rotation: int) -> bool:
    return rotation in {90, 270}


def _oriented(width: int, height: int, rotation: int) -> tuple[int, int]:
    """The size as shown after the rotation."""
    return (height, width) if _is_sideways(rotation) else (width, height)


def _rect(value: DOMRectInit | DOMRectReadOnly | None) -> DOMRectReadOnly | None:
    if value is None or isinstance(value, DOMRectReadOnly):
        return value
    return DOMRectReadOnly(value.x, value.y, value.width, value.height)


def _layout(value: list[PlaneLayout] | None) -> list[PlaneLayout] | None:
    if value is None:
        return None
    return [PlaneLayout(_dimension(plane.offset, 'offset'), _dimension(plane.stride, 'stride')) for plane in value]


def _rotation(value: float) -> int:
    """The nearest multiple of 90, ties rounded up, from 0 to 270."""
    if not math.isfinite(value):
        msg = f'The rotation must be finite, not {value!r}'
        raise TypeError(msg)
    return math.floor(value / 90 + 0.5) * 90 % 360


def _checked_rect(rect: DOMRectReadOnly, coded_size: tuple[int, int]) -> DOMRectReadOnly:
    """A rect given for a frame, with integer coordinates."""
    if min(rect.width, rect.height) <= 0 or min(rect.x, rect.y) < 0:
        msg = 'The rect must have a positive size and offset'
        raise TypeError(msg)
    coded_width, coded_height = coded_size
    if rect.x + rect.width > coded_width or rect.y + rect.height > coded_height:
        msg = 'The rect must be inside of the coded size'
        raise TypeError(msg)
    if any(not float(v).is_integer() for v in (rect.x, rect.y, rect.width, rect.height)):
        msg = 'The rect must have integer coordinates'
        raise TypeError(msg)
    return DOMRectReadOnly(int(rect.x), int(rect.y), int(rect.width), int(rect.height))


def _parse_visible_rect(
    default: DOMRectReadOnly,
    override: DOMRectReadOnly | None,
    *,
    coded_size: tuple[int, int],
    format: VideoPixelFormat,
) -> DOMRectReadOnly:
    rect = default if override is None else _checked_rect(override, coded_size)
    for plane in _planes(format):
        if rect.x % plane.subsampling_x != 0 or rect.y % plane.subsampling_y != 0:
            msg = f'The rect must be aligned to the subsampling of {format.value}'
            raise TypeError(msg)
    return rect


class _PlaneCopy(NamedTuple):
    left_bytes: int
    top: int
    width_bytes: int
    height: int
    offset: int
    stride: int

    @property
    def end(self) -> int:
        """The byte after the plane in the buffer."""
        return self.offset + self.stride * self.height


class _CopyPlan(NamedTuple):
    resource: wrtc.VideoFrameBuffer
    format: VideoPixelFormat
    rect: DOMRectReadOnly
    size: int
    planes: list[_PlaneCopy]


def _compute_layout(
    rect: DOMRectReadOnly, format: VideoPixelFormat, layout: list[PlaneLayout] | None
) -> tuple[int, list[_PlaneCopy]]:
    """Compute Layout and Allocation Size: the size of the buffer and where each plane goes in it."""
    planes = _planes(format)
    if layout is not None and len(layout) != len(planes):
        msg = f'The layout must have {len(planes)} planes for {format.value}'
        raise TypeError(msg)
    allocation_size = 0
    copies: list[_PlaneCopy] = []
    for index, plane in enumerate(planes):
        copy = _plane_copy(plane, rect, index, layout=layout, next_offset=allocation_size)
        if copy.end > _MAX_UNSIGNED_LONG:
            msg = 'The planes are too large'
            raise TypeError(msg)
        for earlier, other in enumerate(copies):
            if other.offset < copy.end and copy.offset < other.end:
                msg = f'Planes {earlier} and {index} overlap'
                raise TypeError(msg)
        allocation_size = max(allocation_size, copy.end)
        copies.append(copy)
    return allocation_size, copies


def _plane_copy(
    plane: _Plane, rect: DOMRectReadOnly, index: int, *, layout: list[PlaneLayout] | None, next_offset: int
) -> _PlaneCopy:
    """Where a plane of a rect goes in a buffer: as the layout says, or packed at the next offset."""
    top, height = plane.rows(rect)
    left_bytes, width_bytes = plane.columns(rect)
    if layout is None:
        return _PlaneCopy(left_bytes, top, width_bytes, height, next_offset, width_bytes)
    if layout[index].stride < width_bytes:
        msg = f'The stride of plane {index} is smaller than its rows'
        raise TypeError(msg)
    return _PlaneCopy(left_bytes, top, width_bytes, height, layout[index].offset, layout[index].stride)


def _color_space(value: VideoColorSpaceInit | VideoColorSpace | None) -> VideoColorSpace | None:
    if value is None:
        return None
    return VideoColorSpace(
        _optional_enum(VideoColorPrimaries, value.primaries),
        _optional_enum(VideoTransferCharacteristics, value.transfer),
        _optional_enum(VideoMatrixCoefficients, value.matrix),
        None if value.full_range is None else bool(value.full_range),
    )


def _copy_metadata(metadata: VideoFrameMetadata | None) -> VideoFrameMetadata:
    """Copy VideoFrame metadata: a deep copy, as structured cloning makes."""
    if metadata is None:
        return VideoFrameMetadata()
    if not isinstance(metadata, VideoFrameMetadata):
        msg = f'metadata is a VideoFrameMetadata, not {type(metadata).__name__}'
        raise TypeError(msg)
    try:
        return copy.deepcopy(metadata)
    except (TypeError, copy.Error) as e:
        raise DataCloneError(str(e)) from None


def _coded_size(init: VideoFrameBufferInit) -> tuple[int, int]:
    size = _dimension(init.coded_width, 'coded_width'), _dimension(init.coded_height, 'coded_height')
    if 0 in size:
        msg = 'The coded size must be positive'
        raise TypeError(msg)
    return size


def _visible_resource(
    data: Buffer, init: VideoFrameBufferInit, format: VideoPixelFormat, *, coded_size: tuple[int, int]
) -> tuple[wrtc.VideoFrameBuffer, tuple[int, int]]:
    """The pixels of the visible rect of a buffer, which becomes the whole frame, and their size."""
    coded = DOMRectReadOnly(0, 0, *coded_size)
    rect = _parse_visible_rect(coded, _rect(init.visible_rect), coded_size=coded_size, format=format)
    allocation_size, copies = _compute_layout(coded, format, _layout(init.layout))
    if _buffer_size(data) < allocation_size:
        msg = f'The data must be at least {allocation_size} bytes for this format and size'
        raise TypeError(msg)
    layout = [
        (copy.offset + plane.rows(rect)[0] * copy.stride + plane.columns(rect)[0], copy.stride)
        for copy, plane in zip(copies, _planes(format))
    ]
    size = int(rect.width), int(rect.height)
    return wrtc.VideoFrameBuffer.fromData(format.value, *size, data, layout), size


class _Geometry(NamedTuple):
    """How the pixels of a frame are shown."""

    visible_rect: DOMRectReadOnly
    display: tuple[int, int]
    rotation: int
    flip: bool


class _FrameInfo(NamedTuple):
    timestamp: int
    duration: int | None
    color_space: VideoColorSpace
    metadata: VideoFrameMetadata


class VideoFrame(Closable):
    """One frame of video. It holds the pixels along with how and when to show them.

    A frame holds its pixels until :meth:`close` is called or a ``with`` block around it ends. Close every frame
    once done with it, including frames read from a track. A frame that is garbage collected while open emits a
    :obj:`ResourceWarning`.

    See :mdn:`VideoFrame`.

    Args:
        source: A bytes-like buffer of pixels, which is copied into the frame. It can also be another
            :obj:`VideoFrame`, whose pixels are shared without copying.
        init (:obj:`VideoFrameBufferInit` or :obj:`VideoFrameInit`, optional): The options. A
            buffer requires a :obj:`VideoFrameBufferInit`, and a frame takes an optional :obj:`VideoFrameInit`.

    Raises:
        TypeError: If the source or the options are invalid, or the buffer is too small for them.
        webrtc.InvalidStateError: If the source frame is closed.

    Example::

        frame = webrtc.VideoFrame(
            i420, webrtc.VideoFrameBufferInit(format='I420', coded_width=640, coded_height=480, timestamp=0)
        )
    """

    _resource: wrtc.VideoFrameBuffer | None
    _format: VideoPixelFormat
    _visible_rect: DOMRectReadOnly
    _display: tuple[int, int]
    _rotation: int
    _flip: bool
    _timestamp: int
    _duration: int | None
    _color_space: VideoColorSpace
    _metadata: VideoFrameMetadata

    @overload
    def __init__(self, image: VideoFrame, /, init: VideoFrameInit | None = None) -> None: ...

    @overload
    def __init__(self, data: Buffer, /, init: VideoFrameBufferInit) -> None: ...

    def __init__(
        self,
        source: Buffer | VideoFrame,
        /,
        init: VideoFrameBufferInit | VideoFrameInit | None = None,
    ) -> None:
        self._resource = None
        if isinstance(source, VideoFrame):
            if isinstance(init, VideoFrameBufferInit):
                msg = 'A VideoFrame of a VideoFrame takes a VideoFrameInit'
                raise TypeError(msg)
            self._init_from_frame(source, init if init is not None else VideoFrameInit())
        elif _is_buffer(source):
            if not isinstance(init, VideoFrameBufferInit):
                msg = 'A VideoFrame of a buffer needs a VideoFrameBufferInit'
                raise TypeError(msg)
            self._init_from_buffer(source, init)
        else:
            msg = f'A VideoFrame is created from a buffer or a VideoFrame, not {type(source).__name__}'
            raise TypeError(msg)

    def _init_from_buffer(self, data: Buffer, init: VideoFrameBufferInit) -> None:
        format = _enum(VideoPixelFormat, init.format)
        coded_size = _coded_size(init)
        display = _display_size(init)
        if not isinstance(init.timestamp, int) or isinstance(init.timestamp, bool):
            msg = 'The timestamp is an integer of microseconds'
            raise TypeError(msg)

        transfer = Transfer(init.transfer)
        resource, (width, height) = _visible_resource(data, init, format, coded_size=coded_size)
        rotation = _rotation(init.rotation)
        color_space = _color_space(init.color_space)
        if color_space is None:
            color_space = _SRGB if format in _RGB_FORMATS else _REC709
        transfer.detach()
        self._set(
            resource,
            format,
            geometry=_Geometry(
                DOMRectReadOnly(0, 0, width, height),
                display if display is not None else _oriented(width, height, rotation),
                rotation,
                flip=bool(init.flip),
            ),
            info=_FrameInfo(init.timestamp, init.duration, color_space, _copy_metadata(init.metadata)),
        )

    def _init_from_frame(self, other: VideoFrame, init: VideoFrameInit) -> None:
        if other._resource is None:
            msg = 'The frame is closed'
            raise InvalidStateError(msg)
        display = _display_size(init)
        resource, format = other._resource, other._format
        if AlphaOption(init.alpha) == AlphaOption.discard and _has_alpha(format):
            resource, format = resource.withoutAlpha(), _without_alpha(format)
        override = _rect(init.visible_rect)
        coded_size = (other.coded_width, other.coded_height)
        rect = _parse_visible_rect(other._visible_rect, override, coded_size=coded_size, format=format)

        applied = _rotation(init.rotation)
        rotation = (other._rotation + (360 - applied if other._flip else applied)) % 360
        if display is None:
            display = other._display_for(rect, rotation, scaled=override is not None)
        self._set(
            resource,
            format,
            geometry=_Geometry(rect, display, rotation, flip=other._flip != bool(init.flip)),
            info=_FrameInfo(
                init.timestamp if init.timestamp is not None else other._timestamp,
                init.duration if init.duration is not None else other._duration,
                other._color_space,
                other._metadata if init.metadata is None else _copy_metadata(init.metadata),
            ),
        )

    def _display_for(self, rect: DOMRectReadOnly, rotation: int, *, scaled: bool) -> tuple[int, int]:
        """The display size of a frame of these pixels with another visible rect and rotation."""
        if scaled:
            # keep the scale of the visible rect to the display size
            shown_width, shown_height = _oriented(*self._display, self._rotation)
            width = round(rect.width * (shown_width / self._visible_rect.width))
            height = round(rect.height * (shown_height / self._visible_rect.height))
            if width == 0 or height == 0:
                msg = 'The display size would be zero'
                raise TypeError(msg)
            return _oriented(width, height, rotation)
        if _is_sideways(rotation) != _is_sideways(self._rotation):
            return self._display[1], self._display[0]
        return self._display

    def _set(
        self, resource: wrtc.VideoFrameBuffer, format: VideoPixelFormat, *, geometry: _Geometry, info: _FrameInfo
    ) -> None:
        self._resource = resource
        self._format = format
        self._visible_rect, self._display, self._rotation, self._flip = geometry
        self._timestamp, self._duration, self._color_space, self._metadata = info

    @classmethod
    def _from_native(cls, native: tuple[wrtc.VideoFrameBuffer, int, int, int]) -> VideoFrame:
        """A frame of a track: the pixels, timestamp, rotation and RTP timestamp (0 if unknown)."""
        resource, timestamp, rotation, rtp_timestamp = native
        frame = cls.__new__(cls)
        width, height = resource.width, resource.height
        frame._set(
            resource,
            VideoPixelFormat(resource.format),
            geometry=_Geometry(
                DOMRectReadOnly(0, 0, width, height), _oriented(width, height, rotation), rotation, flip=False
            ),
            info=_FrameInfo(
                timestamp, None, _REC601, VideoFrameMetadata(rtp_timestamp if rtp_timestamp != 0 else None)
            ),
        )
        return frame

    def _take_resource(self) -> wrtc.VideoFrameBuffer:
        """The visible pixels, for a generator, which closes the frame."""
        resource = self._resource
        if resource is None:
            msg = 'The frame is closed'
            raise InvalidStateError(msg)
        rect = self._visible_rect
        if (rect.x, rect.y, rect.width, rect.height) != (0, 0, resource.width, resource.height):
            pixels = bytearray(self.allocation_size())
            layout = self._copy_to(pixels, None)
            planes = [(plane.offset, plane.stride) for plane in layout]
            resource = wrtc.VideoFrameBuffer.fromData(
                self._format.value, int(rect.width), int(rect.height), pixels, planes
            )
        self._resource = None
        return resource

    def __del__(self) -> None:
        if getattr(self, '_resource', None) is not None:
            warnings.warn('A VideoFrame was garbage collected without being closed', ResourceWarning, stacklevel=2)

    @property
    def format(self) -> VideoPixelFormat | None:
        """:obj:`webrtc.VideoPixelFormat`, optional: The pixel format, or :obj:`None` once closed.

        See :mdn:`VideoFrame/format`.
        """
        return self._format if self._resource is not None else None

    @property
    def coded_width(self) -> int:
        """:obj:`int`: The width of the stored pixels, or 0 once closed.

        See :mdn:`VideoFrame/codedWidth`.
        """
        return self._resource.width if self._resource is not None else 0

    @property
    def coded_height(self) -> int:
        """:obj:`int`: The height of the stored pixels, or 0 once closed.

        See :mdn:`VideoFrame/codedHeight`.
        """
        return self._resource.height if self._resource is not None else 0

    @property
    def coded_rect(self) -> DOMRectReadOnly | None:
        """:obj:`DOMRectReadOnly`, optional: A rectangle covering all the stored pixels, or :obj:`None` once closed.

        See :mdn:`VideoFrame/codedRect`.
        """
        if self._resource is None:
            return None
        return DOMRectReadOnly(0, 0, self._resource.width, self._resource.height)

    @property
    def visible_rect(self) -> DOMRectReadOnly | None:
        """:obj:`DOMRectReadOnly`, optional: The part of the stored pixels to show, or :obj:`None` once closed.

        See :mdn:`VideoFrame/visibleRect`.
        """
        return self._visible_rect if self._resource is not None else None

    @property
    def rotation(self) -> int:
        """:obj:`int`: The clockwise rotation to apply when showing the frame, which is 0, 90, 180 or 270.

        Frames from a track carry the rotation that the sender signalled. The pixels themselves are not rotated.

        See :mdn:`VideoFrame/rotation`.
        """
        return self._rotation

    @property
    def flip(self) -> bool:
        """:obj:`bool`: Whether to mirror the frame horizontally when showing it, before :attr:`rotation`.

        See :mdn:`VideoFrame/flip`.
        """
        return self._flip

    @property
    def display_width(self) -> int:
        """:obj:`int`: The width to show the frame at after rotation, or 0 once closed.

        See :mdn:`VideoFrame/displayWidth`.
        """
        return self._display[0] if self._resource is not None else 0

    @property
    def display_height(self) -> int:
        """:obj:`int`: The height to show the frame at after rotation, or 0 once closed.

        See :mdn:`VideoFrame/displayHeight`.
        """
        return self._display[1] if self._resource is not None else 0

    @property
    def timestamp(self) -> int:
        """:obj:`int`: The presentation time in microseconds, kept after closing.

        See :mdn:`VideoFrame/timestamp`.
        """
        return self._timestamp

    @property
    def duration(self) -> int | None:
        """:obj:`int`, optional: The duration in microseconds, or :obj:`None` if unknown, as for frames from a track.

        See :mdn:`VideoFrame/duration`.
        """
        return self._duration

    @property
    def color_space(self) -> VideoColorSpace:
        """:obj:`VideoColorSpace`: The color space of the pixels, kept after closing.

        See :mdn:`VideoFrame/colorSpace`.
        """
        return self._color_space

    def metadata(self) -> VideoFrameMetadata:
        """Returns a copy of the frame's extra facts, like the RTP timestamp of a frame received from a peer.

        See :mdn:`VideoFrame/metadata`.

        Returns:
            :obj:`VideoFrameMetadata`: A deep copy, so changing it leaves the frame untouched.

        Raises:
            webrtc.InvalidStateError: If the frame is closed.
        """
        if self._resource is None:
            msg = 'The frame is closed'
            raise InvalidStateError(msg)
        return _copy_metadata(self._metadata)

    def _plan_copy(self, options: VideoFrameCopyToOptions | None) -> _CopyPlan:
        resource = self._resource
        if resource is None:
            msg = 'The frame is closed'
            raise InvalidStateError(msg)
        if options is None:
            options = VideoFrameCopyToOptions()
        format = self._format
        if options.format is not None:
            format = _enum(VideoPixelFormat, options.format)
            if format != self._format and format not in _RGB_FORMATS:
                msg = f'Frames are converted to RGB formats only, not {format.value}'
                raise NotSupportedError(msg)
        if options.color_space is not None:
            color_space = _enum(PredefinedColorSpace, options.color_space)
            # libyuv keeps the primaries and transfer of the frame, which is sRGB as far as it can tell
            if options.format is not None and format in _RGB_FORMATS and color_space != PredefinedColorSpace.srgb:
                msg = f'Frames are converted to RGB in srgb only, not {color_space.value}'
                raise NotSupportedError(msg)
        coded_size = (self.coded_width, self.coded_height)
        rect = _parse_visible_rect(self._visible_rect, _rect(options.rect), coded_size=coded_size, format=self._format)
        size, planes = _compute_layout(rect, format, _layout(options.layout))
        return _CopyPlan(resource, format, rect, size, planes)

    def allocation_size(self, options: VideoFrameCopyToOptions | None = None) -> int:
        """Computes the minimum destination size for :meth:`copy_to` with the same options.

        See :mdn:`VideoFrame/allocationSize`.

        Args:
            options (:obj:`VideoFrameCopyToOptions`, optional): What to copy and how.

        Returns:
            :obj:`int`: The number of bytes.

        Raises:
            webrtc.InvalidStateError: If the frame is closed.
            TypeError: If the options are invalid, like a rectangle outside the frame or overlapping planes.
            webrtc.NotSupportedError: If the format or color space can't be converted to.
        """
        return self._plan_copy(options).size

    def copy_to(
        self, destination: bytearray | memoryview, options: VideoFrameCopyToOptions | None = None
    ) -> asyncio.Future[list[PlaneLayout]]:
        """Copies the pixels into a buffer, converting them to RGB if asked.

        The copy happens before this returns, so the future is already done. Call it from a running event loop.
        Errors are set on the future and not raised. RGB conversion uses the frame's matrix and range.

        See :mdn:`VideoFrame/copyTo`.

        Args:
            destination (:obj:`bytearray` or writable :obj:`memoryview`): The buffer to write to, at least
                :meth:`allocation_size` bytes long.
            options (:obj:`VideoFrameCopyToOptions`, optional): What to copy and how.

        Returns:
            :obj:`asyncio.Future`: Resolves to a :obj:`list` of :obj:`PlaneLayout` that says where each plane was
            written. It fails with the errors of :meth:`allocation_size`, or :obj:`TypeError` if the buffer is too
            small.
        """
        future = asyncio.get_running_loop().create_future()
        try:
            future.set_result(self._copy_to(destination, options))
        except (TypeError, ValueError, LookupError, RuntimeError, RTCException) as e:
            future.set_exception(e)
        return future

    def _copy_to(
        self, destination: bytearray | memoryview, options: VideoFrameCopyToOptions | None
    ) -> list[PlaneLayout]:
        plan = self._plan_copy(options)
        if _buffer_size(destination) < plan.size:
            msg = f'The destination must be at least {plan.size} bytes'
            raise TypeError(msg)
        if plan.format == self._format:
            plan.resource.copyPlanes(destination, [tuple(plane) for plane in plan.planes])
        else:
            (plane,) = plan.planes
            rect, matrix = plan.rect, self._color_space.matrix
            plan.resource.convertTo(
                destination,
                plan.format.value,
                int(rect.x),
                int(rect.y),
                int(rect.width),
                int(rect.height),
                plane.offset,
                plane.stride,
                str(matrix) if matrix is not None else '',
                bool(self._color_space.full_range),
            )
        return [PlaneLayout(plane.offset, plane.stride) for plane in plan.planes]

    def clone(self) -> VideoFrame:
        """Creates another frame that shares these pixels without copying them. Each frame must be closed separately.

        See :mdn:`VideoFrame/clone`.

        Returns:
            :obj:`VideoFrame`: The new frame.

        Raises:
            webrtc.InvalidStateError: If the frame is closed.
        """
        if self._resource is None:
            msg = 'The frame is closed'
            raise InvalidStateError(msg)
        frame = VideoFrame.__new__(VideoFrame)
        frame.__dict__.update(self.__dict__)
        return frame

    def close(self) -> None:
        """Releases this frame's hold on the pixels. Closing a closed frame does nothing.

        After that, the size and rectangle attributes read as empty, and most methods raise
        :obj:`webrtc.InvalidStateError`.

        See :mdn:`VideoFrame/close`.
        """
        self._resource = None

    def __repr__(self) -> str:
        if self._resource is None:
            return '<webrtc.VideoFrame closed>'
        return (
            f'<webrtc.VideoFrame {self._format.value} {self.coded_width}x{self.coded_height} '
            f'timestamp={self._timestamp}>'
        )

    #: Alias for :attr:`coded_width`
    codedWidth = coded_width
    #: Alias for :attr:`coded_height`
    codedHeight = coded_height
    #: Alias for :attr:`coded_rect`
    codedRect = coded_rect
    #: Alias for :attr:`visible_rect`
    visibleRect = visible_rect
    #: Alias for :attr:`display_width`
    displayWidth = display_width
    #: Alias for :attr:`display_height`
    displayHeight = display_height
    #: Alias for :attr:`color_space`
    colorSpace = color_space
    #: Alias for :meth:`allocation_size`
    allocationSize = allocation_size
    #: Alias for :meth:`copy_to`
    copyTo = copy_to
