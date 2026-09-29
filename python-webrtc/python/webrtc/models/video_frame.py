#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""VideoFrame of WebCodecs (https://developer.mozilla.org/en-US/docs/Web/API/VideoFrame) and its dictionaries."""

import asyncio
import math
import warnings
from dataclasses import dataclass, fields
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

from webrtc import (
    AlphaOption,
    InvalidStateError,
    NotSupportedError,
    VideoColorPrimaries,
    VideoMatrixCoefficients,
    VideoPixelFormat,
    VideoTransferCharacteristics,
    wrtc,
)
from webrtc.utils.names import alias, snake_case

_MAX_UNSIGNED_LONG = 2**32 - 1
_RGB_FORMATS = (VideoPixelFormat.RGBA, VideoPixelFormat.RGBX, VideoPixelFormat.BGRA, VideoPixelFormat.BGRX)


@dataclass(frozen=True)
class DOMRectReadOnly:
    """A rectangle, like the visible part of a frame.

    Args:
        x (:obj:`float`, optional): The left edge.
        y (:obj:`float`, optional): The top edge.
        width (:obj:`float`, optional): The width.
        height (:obj:`float`, optional): The height.
    """

    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0

    @property
    def top(self) -> float:
        """:obj:`float`: The top edge."""
        return min(self.y, self.y + self.height)

    @property
    def right(self) -> float:
        """:obj:`float`: The right edge."""
        return max(self.x, self.x + self.width)

    @property
    def bottom(self) -> float:
        """:obj:`float`: The bottom edge."""
        return max(self.y, self.y + self.height)

    @property
    def left(self) -> float:
        """:obj:`float`: The left edge."""
        return min(self.x, self.x + self.width)


@dataclass
class PlaneLayout:
    """Where a plane is in a buffer.

    Args:
        offset (:obj:`int`): The first byte of the plane.
        stride (:obj:`int`): The number of bytes from a row to the next.
    """

    offset: int
    stride: int


@dataclass
class VideoColorSpace:
    """The color space of a frame. Members are :obj:`None` when unknown.

    Args:
        primaries (:obj:`webrtc.VideoColorPrimaries`, optional): The color primaries.
        transfer (:obj:`webrtc.VideoTransferCharacteristics`, optional): The transfer characteristics.
        matrix (:obj:`webrtc.VideoMatrixCoefficients`, optional): The matrix coefficients.
        full_range (:obj:`bool`, optional): Whether the samples use the full range of their bits.
    """

    primaries: Optional[VideoColorPrimaries] = None
    transfer: Optional[VideoTransferCharacteristics] = None
    matrix: Optional[VideoMatrixCoefficients] = None
    full_range: Optional[bool] = None

    def to_json(self) -> Dict[str, Any]:
        """Returns the members as a dictionary with the camelCase names, like ``toJSON()``."""
        return {
            'primaries': self.primaries,
            'transfer': self.transfer,
            'matrix': self.matrix,
            'fullRange': self.full_range,
        }

    #: Alias for :attr:`full_range`
    fullRange = alias('full_range')
    #: Alias for :meth:`to_json`
    toJSON = to_json


_REC709 = VideoColorSpace(
    VideoColorPrimaries.bt709, VideoTransferCharacteristics.bt709, VideoMatrixCoefficients.bt709, False
)
_SRGB = VideoColorSpace(
    VideoColorPrimaries.bt709, VideoTransferCharacteristics.iec61966_2_1, VideoMatrixCoefficients.rgb, True
)
# libwebrtc frames carry no color space: its software codecs (VP8, VP9, AV1) use BT.601 unless told otherwise
_REC601 = VideoColorSpace(
    VideoColorPrimaries.smpte170m,
    VideoTransferCharacteristics.smpte170m,
    VideoMatrixCoefficients.smpte170m,
    False,
)


@dataclass
class VideoFrameMetadata:
    """What else is known of a frame.

    Args:
        rtp_timestamp (:obj:`int`, optional): The RTP timestamp of a frame received from a remote peer.
    """

    rtp_timestamp: Optional[int] = None

    #: Alias for :attr:`rtp_timestamp`
    rtpTimestamp = alias('rtp_timestamp')


@dataclass
class VideoFrameBufferInit:
    """How to create a :obj:`VideoFrame` from a buffer of pixels.

    Args:
        format (:obj:`webrtc.VideoPixelFormat`): The layout of the pixels.
        coded_width (:obj:`int`): The width in pixels.
        coded_height (:obj:`int`): The height in pixels.
        timestamp (:obj:`int`): The presentation time in microseconds.
        duration (:obj:`int`, optional): The duration in microseconds.
        layout (:obj:`list` of :obj:`PlaneLayout`, optional): Where the planes are in the buffer, packed one after
            another by default.
        visible_rect (:obj:`DOMRectReadOnly`, optional): The part of the frame to show, all of it by default.
        rotation (:obj:`float`, optional): How the frame is rotated clockwise to be shown, rounded to a multiple of 90.
        flip (:obj:`bool`, optional): Whether the frame is mirrored horizontally to be shown, before the rotation.
        display_width (:obj:`int`, optional): The width to show the frame at, with ``display_height``.
        display_height (:obj:`int`, optional): The height to show the frame at, with ``display_width``.
        color_space (:obj:`VideoColorSpace`, optional): The color space.
    """

    format: VideoPixelFormat
    coded_width: int
    coded_height: int
    timestamp: int
    duration: Optional[int] = None
    layout: Optional[List[PlaneLayout]] = None
    visible_rect: Optional[DOMRectReadOnly] = None
    rotation: float = 0
    flip: bool = False
    display_width: Optional[int] = None
    display_height: Optional[int] = None
    color_space: Optional[VideoColorSpace] = None

    #: Alias for :attr:`coded_width`
    codedWidth = alias('coded_width')
    #: Alias for :attr:`coded_height`
    codedHeight = alias('coded_height')
    #: Alias for :attr:`visible_rect`
    visibleRect = alias('visible_rect')
    #: Alias for :attr:`display_width`
    displayWidth = alias('display_width')
    #: Alias for :attr:`display_height`
    displayHeight = alias('display_height')
    #: Alias for :attr:`color_space`
    colorSpace = alias('color_space')


@dataclass
class VideoFrameInit:
    """How to create a :obj:`VideoFrame` from another one. Members left out are the ones of that frame.

    Args:
        timestamp (:obj:`int`, optional): The presentation time in microseconds.
        duration (:obj:`int`, optional): The duration in microseconds.
        alpha (:obj:`webrtc.AlphaOption`, optional): Whether the alpha channel is kept.
        visible_rect (:obj:`DOMRectReadOnly`, optional): The part of the frame to show.
        rotation (:obj:`float`, optional): A rotation added to the one of the frame.
        flip (:obj:`bool`, optional): Whether to mirror the frame, in addition to the frame's own flip.
        display_width (:obj:`int`, optional): The width to show the frame at, with ``display_height``.
        display_height (:obj:`int`, optional): The height to show the frame at, with ``display_width``.
    """

    timestamp: Optional[int] = None
    duration: Optional[int] = None
    alpha: AlphaOption = AlphaOption.keep
    visible_rect: Optional[DOMRectReadOnly] = None
    rotation: float = 0
    flip: bool = False
    display_width: Optional[int] = None
    display_height: Optional[int] = None

    #: Alias for :attr:`visible_rect`
    visibleRect = alias('visible_rect')
    #: Alias for :attr:`display_width`
    displayWidth = alias('display_width')
    #: Alias for :attr:`display_height`
    displayHeight = alias('display_height')


@dataclass
class VideoFrameCopyToOptions:
    """How :meth:`VideoFrame.copy_to` copies a frame.

    Args:
        rect (:obj:`DOMRectReadOnly`, optional): The part to copy, the visible one by default.
        layout (:obj:`list` of :obj:`PlaneLayout`, optional): Where to put the planes, one after another by default.
        format (:obj:`webrtc.VideoPixelFormat`, optional): The format to convert to: the frame's own one, or one of
            ``RGBA``, ``RGBX``, ``BGRA`` and ``BGRX``.
    """

    rect: Optional[DOMRectReadOnly] = None
    layout: Optional[List[PlaneLayout]] = None
    format: Optional[VideoPixelFormat] = None


class _Plane(NamedTuple):
    sample_bytes: int
    subsampling_x: int
    subsampling_y: int

    def rows(self, rect: DOMRectReadOnly) -> Tuple[int, int]:
        """The first row of the rect in the plane and the number of rows"""
        top = int(rect.y) // self.subsampling_y
        return top, -(-int(rect.y + rect.height) // self.subsampling_y) - top

    def columns(self, rect: DOMRectReadOnly) -> Tuple[int, int]:
        """The first byte of the rect in a row of the plane and the number of bytes"""
        left = int(rect.x) // self.subsampling_x
        width = -(-int(rect.x + rect.width) // self.subsampling_x) - left
        return left * self.sample_bytes, width * self.sample_bytes


def _planes(format: VideoPixelFormat) -> List[_Plane]:
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
    return format in (VideoPixelFormat.RGBA, VideoPixelFormat.BGRA) or format.value[4:5] == 'A'


def _without_alpha(format: VideoPixelFormat) -> VideoPixelFormat:
    if format in (VideoPixelFormat.RGBA, VideoPixelFormat.BGRA):
        return VideoPixelFormat(format.value[:3] + 'X')
    return VideoPixelFormat(format.value[:4] + format.value[5:])


def _enum(cls: type, value: Any) -> Any:
    try:
        return cls(value)
    except ValueError:
        raise TypeError(f'{value!r} is not a {cls.__name__}') from None


def _optional_enum(cls: type, value: Any) -> Any:
    return None if value is None else _enum(cls, value)


def _is_buffer(value: Any) -> bool:
    try:
        memoryview(value)
    except TypeError:
        return False
    return True


def _buffer_size(data: Any) -> int:
    return memoryview(data).nbytes


def _dimension(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_UNSIGNED_LONG:
        raise TypeError(f'{name} must be an unsigned 32-bit integer, not {value!r}')
    return value


def _display_size(init: Any) -> Optional[Tuple[int, int]]:
    """The display size of an init, if given"""
    if (init.display_width is None) != (init.display_height is None):
        raise TypeError('display_width and display_height go together')
    if init.display_width is None:
        return None
    width, height = _dimension(init.display_width, 'display_width'), _dimension(init.display_height, 'display_height')
    if width == 0 or height == 0:
        raise TypeError('The display size must be positive')
    return width, height


def _is_sideways(rotation: int) -> bool:
    return rotation in (90, 270)


def _oriented(width: int, height: int, rotation: int) -> Tuple[int, int]:
    """The size as shown after the rotation"""
    return (height, width) if _is_sideways(rotation) else (width, height)


def _rect(value: Any) -> Optional[DOMRectReadOnly]:
    if value is None or isinstance(value, DOMRectReadOnly):
        return value
    if isinstance(value, dict):
        return DOMRectReadOnly(**{k: v for k, v in value.items() if k in ('x', 'y', 'width', 'height')})
    raise TypeError(f'{value!r} is not a DOMRectReadOnly')


def _layout(value: Any) -> Optional[List[PlaneLayout]]:
    if value is None:
        return None
    layout = []
    for plane in value:
        if isinstance(plane, dict):
            plane = PlaneLayout(plane['offset'], plane['stride'])
        layout.append(PlaneLayout(_dimension(plane.offset, 'offset'), _dimension(plane.stride, 'stride')))
    return layout


def _rotation(value: float) -> int:
    """The nearest multiple of 90, ties rounded up, from 0 to 270"""
    if not math.isfinite(value):
        raise TypeError(f'The rotation must be finite, not {value!r}')
    return int(math.floor(value / 90 + 0.5) * 90) % 360


def _parse_visible_rect(
    default: DOMRectReadOnly,
    override: Optional[DOMRectReadOnly],
    coded_width: int,
    coded_height: int,
    format: VideoPixelFormat,
) -> DOMRectReadOnly:
    rect = default
    if override is not None:
        if override.width <= 0 or override.height <= 0 or override.x < 0 or override.y < 0:
            raise TypeError('The rect must have a positive size and offset')
        if override.x + override.width > coded_width or override.y + override.height > coded_height:
            raise TypeError('The rect must be inside of the coded size')
        if any(not float(v).is_integer() for v in (override.x, override.y, override.width, override.height)):
            raise TypeError('The rect must have integer coordinates')
        rect = DOMRectReadOnly(int(override.x), int(override.y), int(override.width), int(override.height))
    for plane in _planes(format):
        if rect.x % plane.subsampling_x or rect.y % plane.subsampling_y:
            raise TypeError(f'The rect must be aligned to the subsampling of {format.value}')
    return rect


class _PlaneCopy(NamedTuple):
    left_bytes: int
    top: int
    width_bytes: int
    height: int
    offset: int
    stride: int


class _CopyPlan(NamedTuple):
    format: VideoPixelFormat
    rect: DOMRectReadOnly
    size: int
    planes: List[_PlaneCopy]


def _compute_layout(
    rect: DOMRectReadOnly, format: VideoPixelFormat, layout: Optional[List[PlaneLayout]]
) -> Tuple[int, List[_PlaneCopy]]:
    """Compute Layout and Allocation Size: the size of the buffer and where each plane goes in it"""
    planes = _planes(format)
    if layout is not None and len(layout) != len(planes):
        raise TypeError(f'The layout must have {len(planes)} planes for {format.value}')
    allocation_size = 0
    copies: List[_PlaneCopy] = []
    ends: List[int] = []
    for index, plane in enumerate(planes):
        top, height = plane.rows(rect)
        left_bytes, width_bytes = plane.columns(rect)
        if layout is not None:
            if layout[index].stride < width_bytes:
                raise TypeError(f'The stride of plane {index} is smaller than its rows')
            offset, stride = layout[index].offset, layout[index].stride
        else:
            offset, stride = allocation_size, width_bytes
        end = offset + stride * height
        if end > _MAX_UNSIGNED_LONG:
            raise TypeError('The planes are too large')
        for earlier, copy in enumerate(copies):
            if copy.offset < end and offset < ends[earlier]:
                raise TypeError(f'Planes {earlier} and {index} overlap')
        ends.append(end)
        allocation_size = max(allocation_size, end)
        copies.append(_PlaneCopy(left_bytes, top, width_bytes, height, offset, stride))
    return allocation_size, copies


def _color_space(value: Any) -> Optional[VideoColorSpace]:
    if value is None:
        return None
    if isinstance(value, dict):
        value = VideoColorSpace(
            primaries=value.get('primaries'),
            transfer=value.get('transfer'),
            matrix=value.get('matrix'),
            full_range=value.get('full_range', value.get('fullRange')),
        )
    if not isinstance(value, VideoColorSpace):
        raise TypeError(f'{value!r} is not a VideoColorSpace')
    return VideoColorSpace(
        _optional_enum(VideoColorPrimaries, value.primaries),
        _optional_enum(VideoTransferCharacteristics, value.transfer),
        _optional_enum(VideoMatrixCoefficients, value.matrix),
        None if value.full_range is None else bool(value.full_range),
    )


def _init_from(init: Any, cls: type, options: Dict[str, Any]):
    """The init of a constructor: a dataclass, a dictionary (with snake_case or camelCase names), or keywords"""
    if init is None:
        init = options
    elif options:
        raise TypeError('Pass either an init or keyword arguments')
    if isinstance(init, cls):
        return init
    if isinstance(init, dict):
        names = {f.name for f in fields(cls)}
        kwargs = {}
        for key, value in init.items():
            name = snake_case(key)
            if name not in names:
                raise TypeError(f'{cls.__name__} has no member {key!r}')
            kwargs[name] = value
        try:
            return cls(**kwargs)
        except TypeError as e:
            raise TypeError(f'Invalid {cls.__name__}: {e}') from None
    raise TypeError(f'{init!r} is not a {cls.__name__}')


class VideoFrame:
    """A frame of video: its pixels and metadata (https://developer.mozilla.org/en-US/docs/Web/API/VideoFrame).

    A frame holds its pixels until :meth:`close`, which frames read from a track should be once used: a frame
    garbage collected without being closed is released with a :obj:`ResourceWarning`.

    Args:
        source: A bytes-like buffer of pixels, or a :obj:`VideoFrame` to create another frame of the same pixels.
        init (:obj:`VideoFrameBufferInit` or :obj:`VideoFrameInit`, optional): How to create the frame, for a buffer
            (required) or a frame. A dictionary of its members, or keyword arguments, can be passed instead.

    Raises:
        :obj:`TypeError`: If the init isn't valid, or the buffer is too small for it.
        :obj:`webrtc.InvalidStateError`: If the source frame is closed.

    Example::

        frame = webrtc.VideoFrame(i420, format='I420', coded_width=640, coded_height=480, timestamp=0)
    """

    def __init__(self, source: Any, init: Any = None, **options):
        self._resource = None
        if isinstance(source, VideoFrame):
            self._init_from_frame(source, _init_from(init, VideoFrameInit, options))
        elif _is_buffer(source):
            self._init_from_buffer(source, _init_from(init, VideoFrameBufferInit, options))
        else:
            raise TypeError(f'A VideoFrame is created from a buffer or a VideoFrame, not {type(source).__name__}')

    def _init_from_buffer(self, data: Any, init: VideoFrameBufferInit) -> None:
        format = _enum(VideoPixelFormat, init.format)
        coded_width = _dimension(init.coded_width, 'coded_width')
        coded_height = _dimension(init.coded_height, 'coded_height')
        if coded_width == 0 or coded_height == 0:
            raise TypeError('The coded size must be positive')
        display = _display_size(init)
        if not isinstance(init.timestamp, int) or isinstance(init.timestamp, bool):
            raise TypeError('The timestamp is an integer of microseconds')

        coded = DOMRectReadOnly(0, 0, coded_width, coded_height)
        rect = _parse_visible_rect(coded, _rect(init.visible_rect), coded_width, coded_height, format)
        allocation_size, copies = _compute_layout(coded, format, _layout(init.layout))
        if _buffer_size(data) < allocation_size:
            raise TypeError(f'The data must be at least {allocation_size} bytes for this format and size')
        # only the visible rect is copied, which becomes the whole frame
        layout = []
        for copy, plane in zip(copies, _planes(format)):
            top, left_bytes = plane.rows(rect)[0], plane.columns(rect)[0]
            layout.append((copy.offset + top * copy.stride + left_bytes, copy.stride))
        width, height = int(rect.width), int(rect.height)
        resource = wrtc.VideoFrameBuffer.fromData(format.value, width, height, data, layout)

        rotation = _rotation(init.rotation)
        color_space = _color_space(init.color_space) or (_SRGB if format in _RGB_FORMATS else _REC709)
        self._set(
            resource,
            format,
            DOMRectReadOnly(0, 0, width, height),
            display or _oriented(width, height, rotation),
            rotation,
            bool(init.flip),
            init.timestamp,
            init.duration,
            color_space,
        )

    def _init_from_frame(self, other: 'VideoFrame', init: VideoFrameInit) -> None:
        if other._resource is None:
            raise InvalidStateError('The frame is closed')
        display = _display_size(init)
        resource, format = other._resource, other._format
        if AlphaOption(init.alpha) == AlphaOption.discard and _has_alpha(format):
            resource, format = resource.withoutAlpha(), _without_alpha(format)
        override = _rect(init.visible_rect)
        rect = _parse_visible_rect(other._visible_rect, override, other.coded_width, other.coded_height, format)

        applied = _rotation(init.rotation)
        rotation = (other._rotation + (360 - applied if other._flip else applied)) % 360
        flip = other._flip != bool(init.flip)

        if display is None and override is not None:
            # keep the scale of the source's visible rect to its display size
            shown_width, shown_height = _oriented(*other._display, other._rotation)
            width_scale = shown_width / other._visible_rect.width
            height_scale = shown_height / other._visible_rect.height
            width, height = round(rect.width * width_scale), round(rect.height * height_scale)
            if width == 0 or height == 0:
                raise TypeError('The display size would be zero')
            display = _oriented(width, height, rotation)
        elif display is None:
            display = other._display
            if _is_sideways(rotation) != _is_sideways(other._rotation):
                display = (display[1], display[0])
        self._set(
            resource,
            format,
            rect,
            display,
            rotation,
            flip,
            init.timestamp if init.timestamp is not None else other._timestamp,
            init.duration if init.duration is not None else other._duration,
            other._color_space,
            other._metadata,
        )

    def _set(
        self,
        resource: 'wrtc.VideoFrameBuffer',
        format: VideoPixelFormat,
        rect: DOMRectReadOnly,
        display: Tuple[int, int],
        rotation: int,
        flip: bool,
        timestamp: int,
        duration: Optional[int],
        color_space: VideoColorSpace,
        metadata: Optional[VideoFrameMetadata] = None,
    ) -> None:
        self._resource = resource
        self._format = format
        self._visible_rect = rect
        self._display = display
        self._rotation = rotation
        self._flip = flip
        self._timestamp = timestamp
        self._duration = duration
        self._color_space = color_space
        self._metadata = metadata or VideoFrameMetadata()

    @classmethod
    def _from_native(
        cls, resource: 'wrtc.VideoFrameBuffer', timestamp: int, rotation: int = 0, rtp_timestamp: Optional[int] = None
    ) -> 'VideoFrame':
        """A frame of a track"""
        frame = cls.__new__(cls)
        width, height = resource.width, resource.height
        frame._set(
            resource,
            VideoPixelFormat(resource.format),
            DOMRectReadOnly(0, 0, width, height),
            _oriented(width, height, rotation),
            rotation,
            False,
            timestamp,
            None,
            _REC601,
            VideoFrameMetadata(rtp_timestamp),
        )
        return frame

    def _take_resource(self) -> 'wrtc.VideoFrameBuffer':
        """The pixels, for a generator, which closes the frame"""
        if self._resource is None:
            raise InvalidStateError('The frame is closed')
        resource = self._resource
        self._resource = None
        return resource

    def __del__(self):
        if getattr(self, '_resource', None) is not None:
            warnings.warn('A VideoFrame was garbage collected without being closed', ResourceWarning, stacklevel=2)

    @property
    def format(self) -> Optional[VideoPixelFormat]:
        """:obj:`webrtc.VideoPixelFormat`, optional: The layout of the pixels, :obj:`None` once closed."""
        return self._format if self._resource is not None else None

    @property
    def coded_width(self) -> int:
        """:obj:`int`: The width of the pixels, 0 once closed."""
        return self._resource.width if self._resource is not None else 0

    @property
    def coded_height(self) -> int:
        """:obj:`int`: The height of the pixels, 0 once closed."""
        return self._resource.height if self._resource is not None else 0

    @property
    def coded_rect(self) -> Optional[DOMRectReadOnly]:
        """:obj:`DOMRectReadOnly`, optional: The rect of all the pixels, :obj:`None` once closed."""
        if self._resource is None:
            return None
        return DOMRectReadOnly(0, 0, self._resource.width, self._resource.height)

    @property
    def visible_rect(self) -> Optional[DOMRectReadOnly]:
        """:obj:`DOMRectReadOnly`, optional: The part of the pixels to show, :obj:`None` once closed."""
        return self._visible_rect if self._resource is not None else None

    @property
    def rotation(self) -> int:
        """:obj:`int`: How the frame is rotated clockwise to be shown: 0, 90, 180 or 270."""
        return self._rotation

    @property
    def flip(self) -> bool:
        """:obj:`bool`: Whether the frame is mirrored horizontally to be shown, before the rotation."""
        return self._flip

    @property
    def display_width(self) -> int:
        """:obj:`int`: The width to show the frame at, 0 once closed."""
        return self._display[0] if self._resource is not None else 0

    @property
    def display_height(self) -> int:
        """:obj:`int`: The height to show the frame at, 0 once closed."""
        return self._display[1] if self._resource is not None else 0

    @property
    def timestamp(self) -> int:
        """:obj:`int`: The presentation time in microseconds."""
        return self._timestamp

    @property
    def duration(self) -> Optional[int]:
        """:obj:`int`, optional: The duration in microseconds."""
        return self._duration

    @property
    def color_space(self) -> VideoColorSpace:
        """:obj:`VideoColorSpace`: The color space."""
        return self._color_space

    def metadata(self) -> VideoFrameMetadata:
        """Returns what else is known of the frame, like the RTP timestamp of a received frame.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the frame is closed.
        """
        if self._resource is None:
            raise InvalidStateError('The frame is closed')
        return VideoFrameMetadata(self._metadata.rtp_timestamp)

    def _plan_copy(self, options: Any) -> _CopyPlan:
        if self._resource is None:
            raise InvalidStateError('The frame is closed')
        options = _init_from(options, VideoFrameCopyToOptions, {})
        format = self._format
        if options.format is not None:
            format = _enum(VideoPixelFormat, options.format)
            if format != self._format and format not in _RGB_FORMATS:
                raise NotSupportedError(f'Frames are converted to RGB formats only, not {format.value}')
        rect = _parse_visible_rect(
            self._visible_rect, _rect(options.rect), self.coded_width, self.coded_height, self._format
        )
        size, planes = _compute_layout(rect, format, _layout(options.layout))
        return _CopyPlan(format, rect, size, planes)

    def allocation_size(self, options: Any = None) -> int:
        """Returns how many bytes :meth:`copy_to` needs.

        Args:
            options (:obj:`VideoFrameCopyToOptions`, optional): How the frame is copied.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the frame is closed.
            :obj:`TypeError`: If the options aren't valid.
            :obj:`webrtc.NotSupportedError`: If the frame can't be converted to the format.
        """
        return self._plan_copy(options).size

    def copy_to(self, destination: Union[bytearray, memoryview], options: Any = None) -> asyncio.Future:
        """Copies the pixels into a buffer.

        Args:
            destination (:obj:`bytearray` or writable :obj:`memoryview`): The buffer.
            options (:obj:`VideoFrameCopyToOptions`, optional): How the frame is copied.

        Returns:
            :obj:`asyncio.Future`: The :obj:`PlaneLayout` of each plane in the buffer, once copied.
            It fails with the errors of :meth:`allocation_size`, or :obj:`TypeError` if the buffer is too small.
        """
        future = asyncio.get_running_loop().create_future()
        try:
            future.set_result(self._copy_to(destination, options))
        except Exception as e:
            future.set_exception(e)
        return future

    def _copy_to(self, destination: Any, options: Any) -> List[PlaneLayout]:
        plan = self._plan_copy(options)
        if _buffer_size(destination) < plan.size:
            raise TypeError(f'The destination must be at least {plan.size} bytes')
        if plan.format == self._format:
            self._resource.copyPlanes(destination, [tuple(plane) for plane in plan.planes])
        else:
            (plane,) = plan.planes
            rect, matrix = plan.rect, self._color_space.matrix
            self._resource.convertTo(
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

    def clone(self) -> 'VideoFrame':
        """Returns another frame of the same pixels, which is closed separately.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the frame is closed.
        """
        if self._resource is None:
            raise InvalidStateError('The frame is closed')
        frame = VideoFrame.__new__(VideoFrame)
        frame.__dict__.update(self.__dict__)
        return frame

    def close(self) -> None:
        """Releases the pixels. Closing a closed frame does nothing."""
        self._resource = None

    def __enter__(self) -> 'VideoFrame':
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __repr__(self):
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
