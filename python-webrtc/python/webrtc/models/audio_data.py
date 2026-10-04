#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The WebCodecs :obj:`AudioData` and the dictionaries that create and copy it."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, NamedTuple, cast

from webrtc import (
    AudioSampleFormat,
    AudioSampleFormatValue,
    InvalidRangeError,
    InvalidStateError,
    NotSupportedError,
    wrtc,
)
from webrtc.models.closable import Closable
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias
from webrtc.utils.transfer import Transfer

if TYPE_CHECKING:
    from typing_extensions import Buffer, TypeGuard

_SAMPLE_BYTES = {'u8': 1, 's16': 2, 's32': 4, 'f32': 4}


def _sample_format(value: object) -> AudioSampleFormat:
    try:
        return AudioSampleFormat(value)
    except ValueError:
        msg = f'{value!r} is not an AudioSampleFormat'
        raise TypeError(msg) from None


def _sample_bytes(format: AudioSampleFormat) -> int:
    return _SAMPLE_BYTES[format.value.split('-')[0]]


def _is_planar(format: AudioSampleFormat) -> bool:
    return format.value.endswith('-planar')


@dataclass
class AudioDataInit(Dictionary):
    """Options to create an :obj:`AudioData`.

    See :mdn:`AudioData/AudioData`.

    Args:
        format (:obj:`webrtc.AudioSampleFormat`): The sample type and whether channels are interleaved or planar.
        sample_rate (:obj:`float`): The number of frames per second. It must be positive and finite.
        number_of_frames (:obj:`int`): The number of frames (samples per channel), which must be positive.
        number_of_channels (:obj:`int`): The number of channels, which must be positive.
        timestamp (:obj:`int`): The presentation time in microseconds.
        data: A bytes-like buffer that holds at least the samples described above. Extra bytes are ignored. The
            buffer is copied unless it is transferred.
        transfer (:obj:`list` of bytes-like buffers, optional): Buffers to give up. When ``data`` is among them its
            memory is kept without copying, so it must not be modified afterwards. Transferred :obj:`memoryview`
            objects are released, but other buffers stay usable.
    """

    format: AudioSampleFormat | AudioSampleFormatValue
    sample_rate: float
    number_of_frames: int
    number_of_channels: int
    timestamp: int
    data: Buffer
    transfer: list[Buffer] = field(default_factory=list)

    #: Alias for :attr:`sample_rate`
    sampleRate: ClassVar[Alias[float]] = alias('sample_rate')
    #: Alias for :attr:`number_of_frames`
    numberOfFrames: ClassVar[Alias[int]] = alias('number_of_frames')
    #: Alias for :attr:`number_of_channels`
    numberOfChannels: ClassVar[Alias[int]] = alias('number_of_channels')


@dataclass
class AudioDataCopyToOptions(Dictionary):
    """Options for :meth:`AudioData.copy_to` and :meth:`AudioData.allocation_size`.

    See :mdn:`AudioData/copyTo`.

    Args:
        plane_index (:obj:`int`): The channel to copy when the destination format is planar. It must be 0 for an
            interleaved format, which copies all channels.
        frame_offset (:obj:`int`, optional): The index of the first frame to copy, 0 by default.
        frame_count (:obj:`int`, optional): How many frames to copy. By default, all frames from ``frame_offset`` on.
        format (:obj:`webrtc.AudioSampleFormat`, optional): The format to convert the samples to. By default, the
            data's own format.
    """

    plane_index: int
    frame_offset: int = 0
    frame_count: int | None = None
    format: AudioSampleFormat | AudioSampleFormatValue | None = None

    #: Alias for :attr:`plane_index`
    planeIndex: ClassVar[Alias[int]] = alias('plane_index')
    #: Alias for :attr:`frame_offset`
    frameOffset: ClassVar[Alias[int]] = alias('frame_offset')
    #: Alias for :attr:`frame_count`
    frameCount: ClassVar[Alias[int | None]] = alias('frame_count')


def _unsigned(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f'{name} must be a non-negative integer, not {value!r}'
        raise TypeError(msg)
    return value


def _sample_rate(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < math.inf:
        msg = 'sample_rate must be positive and finite'
        raise TypeError(msg)
    return float(value)


def _is_buffer(data: object) -> TypeGuard[Buffer]:
    try:
        _ = memoryview(cast('Buffer', data))
    except TypeError:
        return False
    return True


def _buffer(data: object, size: int, *, keep: bool) -> bytes | memoryview:
    """The first bytes of a bytes-like buffer, copied or a read-only view of them."""
    try:
        # memoryview() is the check of the buffer protocol
        view = memoryview(cast('Buffer', data)).cast('B')
    except TypeError:
        msg = 'data must be a bytes-like buffer'
        raise TypeError(msg) from None
    if view.nbytes < size:
        msg = f'data must be at least {size} bytes for this format and size'
        raise TypeError(msg)
    return view[:size].toreadonly() if keep else bytes(view[:size])


class _Layout(NamedTuple):
    format: AudioSampleFormat
    sample_rate: float
    frames: int
    channels: int


class _CopyPlan(NamedTuple):
    data: bytes | memoryview
    format: AudioSampleFormat
    plane_index: int
    frame_offset: int
    frame_count: int
    size: int


class AudioData(Closable):
    """A block of audio samples with their format and presentation time.

    The samples are held until :meth:`close` is called or a ``with`` block around the data ends. Data read from a
    track is interleaved ``u8``, ``s16`` or ``s32``. It emits a :obj:`ResourceWarning` if it is garbage collected
    while open.

    See :mdn:`AudioData`.

    Args:
        init (:obj:`AudioDataInit`): The samples and their format.

    Raises:
        TypeError: If the options are invalid, or the data is too small for them.

    Example::

        data = webrtc.AudioData(
            webrtc.AudioDataInit(
                format='s16',
                sample_rate=48000,
                number_of_frames=480,
                number_of_channels=1,
                timestamp=0,
                data=bytes(960),
            )
        )
    """

    _data: bytes | memoryview | None
    _format: AudioSampleFormat
    _sample_rate: float
    _frames: int
    _channels: int
    _timestamp: int
    #: Whether a data read from a track warns if garbage collected without being closed
    _warn_unclosed: bool = False

    def __init__(self, init: AudioDataInit) -> None:
        format = _sample_format(init.format)
        sample_rate = _sample_rate(init.sample_rate)
        frames = _unsigned(init.number_of_frames, 'number_of_frames')
        channels = _unsigned(init.number_of_channels, 'number_of_channels')
        if frames == 0 or channels == 0:
            msg = 'number_of_frames and number_of_channels must be positive'
            raise TypeError(msg)
        if isinstance(init.timestamp, bool) or not isinstance(init.timestamp, int):
            msg = 'The timestamp is an integer of microseconds'
            raise TypeError(msg)
        transfer = Transfer(init.transfer)
        size = frames * channels * _sample_bytes(format)
        data = _buffer(init.data, size, keep=_is_buffer(init.data) and transfer.has(init.data))
        transfer.detach()
        self._set(data, _Layout(format, sample_rate, frames, channels), init.timestamp)

    def _set(self, data: bytes | memoryview, layout: _Layout, timestamp: int) -> None:
        self._data = data
        self._format, self._sample_rate, self._frames, self._channels = layout
        self._timestamp = timestamp

    @classmethod
    def _from_native(cls, native: tuple[bytes, int, int, int, int, int]) -> AudioData:
        """Samples of a track, interleaved: the data, bits per sample, sample rate, channels, frames and timestamp."""
        data, bits_per_sample, sample_rate, channels, frames, timestamp = native
        audio = cls.__new__(cls)
        format = {8: AudioSampleFormat.u8, 16: AudioSampleFormat.s16, 32: AudioSampleFormat.s32}[bits_per_sample]
        audio._set(data, _Layout(format, float(sample_rate), frames, channels), timestamp)
        audio._warn_unclosed = True
        return audio

    def _take(self) -> AudioData:
        """The samples, for a generator, which closes the data."""
        if self._data is None:
            msg = 'The data is closed'
            raise InvalidStateError(msg)
        copy = self.clone()
        self.close()
        return copy

    def __del__(self) -> None:
        if getattr(self, '_data', None) is not None and getattr(self, '_warn_unclosed', False):
            warnings.warn('An AudioData was garbage collected without being closed', ResourceWarning, stacklevel=2)

    @property
    def format(self) -> AudioSampleFormat | None:
        """:obj:`webrtc.AudioSampleFormat`, optional: The sample type and layout, or :obj:`None` once closed.

        See :mdn:`AudioData/format`.
        """
        return self._format if self._data is not None else None

    @property
    def sample_rate(self) -> float:
        """:obj:`float`: The number of frames per second, or 0 once closed.

        See :mdn:`AudioData/sampleRate`.
        """
        return self._sample_rate if self._data is not None else 0

    @property
    def number_of_frames(self) -> int:
        """:obj:`int`: The number of frames (samples per channel), or 0 once closed.

        See :mdn:`AudioData/numberOfFrames`.
        """
        return self._frames if self._data is not None else 0

    @property
    def number_of_channels(self) -> int:
        """:obj:`int`: The number of channels, or 0 once closed.

        See :mdn:`AudioData/numberOfChannels`.
        """
        return self._channels if self._data is not None else 0

    @property
    def duration(self) -> int:
        """:obj:`int`: The duration in microseconds, rounded down, or 0 once closed.

        See :mdn:`AudioData/duration`.
        """
        if self._data is None:
            return 0
        return int(self._frames / self._sample_rate * 1_000_000)

    @property
    def timestamp(self) -> int:
        """:obj:`int`: The presentation time in microseconds, kept after closing.

        See :mdn:`AudioData/timestamp`.
        """
        return self._timestamp

    def _plan_copy(self, options: AudioDataCopyToOptions) -> _CopyPlan:
        data = self._data
        if data is None:
            msg = 'The data is closed'
            raise InvalidStateError(msg)
        plane_index = _unsigned(options.plane_index, 'plane_index')
        frame_offset = _unsigned(options.frame_offset, 'frame_offset')
        destination = self._format if options.format is None else _sample_format(options.format)
        if _is_planar(destination):
            if plane_index >= self._channels:
                msg = f'plane_index must be less than the {self._channels} channels'
                raise InvalidRangeError(msg)
        elif plane_index > 0:
            msg = 'plane_index must be 0 for an interleaved format'
            raise InvalidRangeError(msg)
        if frame_offset >= self._frames:
            msg = f'frame_offset must be less than the {self._frames} frames'
            raise InvalidRangeError(msg)
        remaining = self._frames - frame_offset
        frame_count = remaining
        if options.frame_count is not None:
            frame_count = _unsigned(options.frame_count, 'frame_count')
            if frame_count > remaining:
                msg = f'frame_count must be at most the {remaining} frames from frame_offset'
                raise InvalidRangeError(msg)
        elements = frame_count if _is_planar(destination) else frame_count * self._channels
        return _CopyPlan(
            data, destination, plane_index, frame_offset, frame_count, elements * _sample_bytes(destination)
        )

    def allocation_size(self, options: AudioDataCopyToOptions) -> int:
        """Computes the minimum destination size for :meth:`copy_to` with the same options.

        See :mdn:`AudioData/allocationSize`.

        Args:
            options (:obj:`AudioDataCopyToOptions`): What to copy.

        Returns:
            :obj:`int`: The number of bytes.

        Raises:
            webrtc.InvalidStateError: If the data is closed.
            TypeError: If an option has the wrong type or a negative value.
            webrtc.InvalidRangeError: If the plane or the frames are out of range.
        """
        return self._plan_copy(options).size

    def copy_to(self, destination: bytearray | memoryview, options: AudioDataCopyToOptions) -> None:
        """Copies samples into a buffer, converting them to another format if asked.

        Float samples converted to an integer format are clamped to the range from -1 to 1 first.

        See :mdn:`AudioData/copyTo`.

        Args:
            destination (:obj:`bytearray` or writable :obj:`memoryview`): The buffer to write to, at least
                :meth:`allocation_size` bytes long.
            options (:obj:`AudioDataCopyToOptions`): What to copy.

        Raises:
            webrtc.InvalidStateError: If the data is closed.
            TypeError: If an option has the wrong type or a negative value.
            webrtc.InvalidRangeError: If the plane or the frames are out of range, or the buffer is too small.
            webrtc.NotSupportedError: If the samples can't be converted to the format.
        """
        plan = self._plan_copy(options)
        if memoryview(destination).nbytes < plan.size:
            msg = f'The destination must be at least {plan.size} bytes'
            raise InvalidRangeError(msg)
        try:
            wrtc.copyAudioSamples(
                plan.data,
                self._format.value,
                self._channels,
                self._frames,
                destination,
                plan.format.value,
                plan.plane_index,
                plan.frame_offset,
                plan.frame_count,
            )
        except ValueError as e:
            raise NotSupportedError(str(e)) from None

    def clone(self) -> AudioData:
        """Creates another data that shares these samples without copying them. Each must be closed separately.

        See :mdn:`AudioData/clone`.

        Returns:
            :obj:`AudioData`: The new data.

        Raises:
            webrtc.InvalidStateError: If the data is closed.
        """
        if self._data is None:
            msg = 'The data is closed'
            raise InvalidStateError(msg)
        audio = AudioData.__new__(AudioData)
        audio.__dict__.update(self.__dict__)
        return audio

    def close(self) -> None:
        """Releases this data's hold on the samples. Closing a closed data does nothing.

        After that, the format and size attributes read as empty, and the methods raise
        :obj:`webrtc.InvalidStateError`.

        See :mdn:`AudioData/close`.
        """
        self._data = None

    def __repr__(self) -> str:
        if self._data is None:
            return '<webrtc.AudioData closed>'
        return (
            f'<webrtc.AudioData {self._format.value} {self._channels}ch {self._frames} frames '
            f'{self._sample_rate:g} Hz timestamp={self._timestamp}>'
        )

    #: Alias for :attr:`sample_rate`
    sampleRate = sample_rate
    #: Alias for :attr:`number_of_frames`
    numberOfFrames = number_of_frames
    #: Alias for :attr:`number_of_channels`
    numberOfChannels = number_of_channels
    #: Alias for :meth:`allocation_size`
    allocationSize = allocation_size
    #: Alias for :meth:`copy_to`
    copyTo = copy_to
