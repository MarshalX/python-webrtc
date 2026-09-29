#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""AudioData of WebCodecs (https://developer.mozilla.org/en-US/docs/Web/API/AudioData) and its dictionaries."""

import math
import warnings
from dataclasses import dataclass
from typing import Any, NamedTuple, Optional, Union

from webrtc import AudioSampleFormat, InvalidRangeError, InvalidStateError, NotSupportedError, wrtc
from webrtc.utils.names import alias, snake_case

_SAMPLE_BYTES = {'u8': 1, 's16': 2, 's32': 4, 'f32': 4}


def _sample_format(value: Any) -> AudioSampleFormat:
    try:
        return AudioSampleFormat(value)
    except ValueError:
        raise TypeError(f'{value!r} is not an AudioSampleFormat') from None


def _sample_bytes(format: AudioSampleFormat) -> int:
    return _SAMPLE_BYTES[format.value.split('-')[0]]


def _is_planar(format: AudioSampleFormat) -> bool:
    return format.value.endswith('-planar')


@dataclass
class AudioDataInit:
    """How to create an :obj:`AudioData`.

    Args:
        format (:obj:`webrtc.AudioSampleFormat`): The type and layout of the samples.
        sample_rate (:obj:`float`): The number of frames per second.
        number_of_frames (:obj:`int`): The number of frames (samples per channel).
        number_of_channels (:obj:`int`): The number of channels.
        timestamp (:obj:`int`): The presentation time in microseconds.
        data: A bytes-like buffer of the samples, which is copied.
    """

    format: AudioSampleFormat
    sample_rate: float
    number_of_frames: int
    number_of_channels: int
    timestamp: int
    data: Any

    #: Alias for :attr:`sample_rate`
    sampleRate = alias('sample_rate')
    #: Alias for :attr:`number_of_frames`
    numberOfFrames = alias('number_of_frames')
    #: Alias for :attr:`number_of_channels`
    numberOfChannels = alias('number_of_channels')


@dataclass
class AudioDataCopyToOptions:
    """What :meth:`AudioData.copy_to` copies.

    Args:
        plane_index (:obj:`int`): The channel to copy for a planar format, 0 for an interleaved one.
        frame_offset (:obj:`int`, optional): The first frame to copy.
        frame_count (:obj:`int`, optional): How many frames to copy, up to the last one by default.
        format (:obj:`webrtc.AudioSampleFormat`, optional): The format to convert to, the data's own one by default.
    """

    plane_index: int
    frame_offset: int = 0
    frame_count: Optional[int] = None
    format: Optional[AudioSampleFormat] = None

    #: Alias for :attr:`plane_index`
    planeIndex = alias('plane_index')
    #: Alias for :attr:`frame_offset`
    frameOffset = alias('frame_offset')
    #: Alias for :attr:`frame_count`
    frameCount = alias('frame_count')


def _copy_options(value: Any) -> AudioDataCopyToOptions:
    if isinstance(value, AudioDataCopyToOptions):
        return value
    if isinstance(value, dict):
        kwargs = {snake_case(k): v for k, v in value.items() if v is not None}
        if 'plane_index' not in kwargs:
            raise TypeError('plane_index is required')
        try:
            return AudioDataCopyToOptions(**kwargs)
        except TypeError as e:
            raise TypeError(f'Invalid AudioDataCopyToOptions: {e}') from None
    raise TypeError(f'{value!r} is not an AudioDataCopyToOptions')


def _unsigned(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f'{name} must be a non-negative integer, not {value!r}')
    return value


class _CopyPlan(NamedTuple):
    format: AudioSampleFormat
    plane_index: int
    frame_offset: int
    frame_count: int
    size: int


class AudioData:
    """Audio samples and their metadata (https://developer.mozilla.org/en-US/docs/Web/API/AudioData).

    Samples read from a track hold memory until :meth:`close`, like a :obj:`webrtc.VideoFrame`.

    Args:
        init (:obj:`AudioDataInit`, optional): The samples and their format. A dictionary of its members, or keyword
            arguments, can be passed instead.

    Raises:
        :obj:`TypeError`: If the init isn't valid, or the data is too small for it.

    Example::

        data = webrtc.AudioData(format='s16', sample_rate=48000, number_of_frames=480, number_of_channels=1,
                                timestamp=0, data=bytes(960))
    """

    def __init__(self, init: Any = None, **options):
        if init is None:
            init = options
        elif options:
            raise TypeError('Pass either an init or keyword arguments')
        if isinstance(init, dict):
            kwargs = {snake_case(k): v for k, v in init.items() if k != 'transfer'}
            try:
                init = AudioDataInit(**kwargs)
            except TypeError as e:
                raise TypeError(f'Invalid AudioDataInit: {e}') from None
        if not isinstance(init, AudioDataInit):
            raise TypeError(f'{init!r} is not an AudioDataInit')

        format = _sample_format(init.format)
        sample_rate = init.sample_rate
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, float)) or not 0 < sample_rate < math.inf:
            raise TypeError('sample_rate must be positive and finite')
        frames = _unsigned(init.number_of_frames, 'number_of_frames')
        channels = _unsigned(init.number_of_channels, 'number_of_channels')
        if frames == 0 or channels == 0:
            raise TypeError('number_of_frames and number_of_channels must be positive')
        if isinstance(init.timestamp, bool) or not isinstance(init.timestamp, int):
            raise TypeError('The timestamp is an integer of microseconds')
        try:
            view = memoryview(init.data).cast('B')
        except TypeError:
            raise TypeError('data must be a bytes-like buffer') from None
        size = frames * channels * _sample_bytes(format)
        if view.nbytes < size:
            raise TypeError(f'data must be at least {size} bytes for this format and size')
        self._set(bytes(view[:size]), format, float(sample_rate), frames, channels, init.timestamp)

    def _set(
        self, data: bytes, format: AudioSampleFormat, sample_rate: float, frames: int, channels: int, timestamp: int
    ) -> None:
        self._data: Optional[bytes] = data
        self._format = format
        self._sample_rate = sample_rate
        self._frames = frames
        self._channels = channels
        self._timestamp = timestamp

    @classmethod
    def _from_native(
        cls, data: bytes, bits_per_sample: int, sample_rate: int, channels: int, frames: int, timestamp: int
    ) -> 'AudioData':
        """Samples of a track, interleaved"""
        audio = cls.__new__(cls)
        format = {8: AudioSampleFormat.u8, 16: AudioSampleFormat.s16, 32: AudioSampleFormat.s32}[bits_per_sample]
        audio._set(data, format, float(sample_rate), frames, channels, timestamp)
        audio._warn_unclosed = True
        return audio

    def _take(self) -> 'AudioData':
        """The samples, for a generator, which closes the data"""
        if self._data is None:
            raise InvalidStateError('The data is closed')
        copy = self.clone()
        self.close()
        return copy

    def __del__(self):
        if getattr(self, '_data', None) is not None and getattr(self, '_warn_unclosed', False):
            warnings.warn('An AudioData was garbage collected without being closed', ResourceWarning, stacklevel=2)

    @property
    def format(self) -> Optional[AudioSampleFormat]:
        """:obj:`webrtc.AudioSampleFormat`, optional: The type and layout of the samples, :obj:`None` once closed."""
        return self._format if self._data is not None else None

    @property
    def sample_rate(self) -> float:
        """:obj:`float`: The number of frames per second, 0 once closed."""
        return self._sample_rate if self._data is not None else 0

    @property
    def number_of_frames(self) -> int:
        """:obj:`int`: The number of frames, 0 once closed."""
        return self._frames if self._data is not None else 0

    @property
    def number_of_channels(self) -> int:
        """:obj:`int`: The number of channels, 0 once closed."""
        return self._channels if self._data is not None else 0

    @property
    def duration(self) -> int:
        """:obj:`int`: The duration in microseconds, 0 once closed."""
        if self._data is None:
            return 0
        return int(self._frames / self._sample_rate * 1_000_000)

    @property
    def timestamp(self) -> int:
        """:obj:`int`: The presentation time in microseconds."""
        return self._timestamp

    def _plan_copy(self, options: Any) -> _CopyPlan:
        if self._data is None:
            raise InvalidStateError('The data is closed')
        options = _copy_options(options)
        plane_index = _unsigned(options.plane_index, 'plane_index')
        frame_offset = _unsigned(options.frame_offset, 'frame_offset')
        destination = self._format if options.format is None else _sample_format(options.format)
        if _is_planar(destination):
            if plane_index >= self._channels:
                raise InvalidRangeError(f'plane_index must be less than the {self._channels} channels')
        elif plane_index > 0:
            raise InvalidRangeError('plane_index must be 0 for an interleaved format')
        if frame_offset >= self._frames:
            raise InvalidRangeError(f'frame_offset must be less than the {self._frames} frames')
        remaining = self._frames - frame_offset
        frame_count = remaining
        if options.frame_count is not None:
            frame_count = _unsigned(options.frame_count, 'frame_count')
            if frame_count > remaining:
                raise InvalidRangeError(f'frame_count must be at most the {remaining} frames from frame_offset')
        elements = frame_count if _is_planar(destination) else frame_count * self._channels
        return _CopyPlan(destination, plane_index, frame_offset, frame_count, elements * _sample_bytes(destination))

    def allocation_size(self, options: Any) -> int:
        """Returns how many bytes :meth:`copy_to` needs.

        Args:
            options (:obj:`AudioDataCopyToOptions`): What is copied.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the data is closed.
            :obj:`TypeError`: If the options aren't valid.
            :obj:`webrtc.InvalidRangeError`: If the plane or the frames don't exist.
        """
        return self._plan_copy(options).size

    def copy_to(self, destination: Union[bytearray, memoryview], options: Any) -> None:
        """Copies samples into a buffer, converting them to another format if asked.

        Args:
            destination (:obj:`bytearray` or writable :obj:`memoryview`): The buffer.
            options (:obj:`AudioDataCopyToOptions`): What is copied.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the data is closed.
            :obj:`webrtc.InvalidRangeError`: If the plane or the frames don't exist, or the buffer is too small.
            :obj:`webrtc.NotSupportedError`: If the samples can't be converted to the format.
        """
        plan = self._plan_copy(options)
        if memoryview(destination).nbytes < plan.size:
            raise InvalidRangeError(f'The destination must be at least {plan.size} bytes')
        try:
            wrtc.copyAudioSamples(
                self._data,
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

    def clone(self) -> 'AudioData':
        """Returns another data of the same samples, which is closed separately.

        Raises:
            :obj:`webrtc.InvalidStateError`: If the data is closed.
        """
        if self._data is None:
            raise InvalidStateError('The data is closed')
        audio = AudioData.__new__(AudioData)
        audio.__dict__.update(self.__dict__)
        return audio

    def close(self) -> None:
        """Releases the samples. Closing a closed data does nothing."""
        self._data = None

    def __enter__(self) -> 'AudioData':
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __repr__(self):
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
