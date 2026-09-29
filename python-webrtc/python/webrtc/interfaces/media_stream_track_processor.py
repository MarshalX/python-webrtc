#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

from webrtc import AudioData, MediaStreamTrack, MediaType, VideoFrame, WebRTCObject, wrtc
from webrtc.streams import ReadableStream
from webrtc.utils.events import EventTarget
from webrtc.utils.names import alias

#: How many frames of video are queued for reads, as the specification says
DEFAULT_VIDEO_BUFFER_SIZE = 1
#: How many 10 ms chunks of audio are queued for reads, as Chrome does
DEFAULT_AUDIO_BUFFER_SIZE = 10


@dataclass
class MediaStreamTrackProcessorInit:
    """How to create a :obj:`MediaStreamTrackProcessor`.

    Args:
        track (:obj:`webrtc.MediaStreamTrack`): The track to read.
        max_buffer_size (:obj:`int`, optional): How many frames are queued for reads before the oldest one is dropped.
    """

    track: MediaStreamTrack
    max_buffer_size: Optional[int] = None

    #: Alias for :attr:`max_buffer_size`
    maxBufferSize = alias('max_buffer_size')


def _parse_init(
    track: Any, max_buffer_size: Optional[int], options: Dict[str, Any]
) -> Tuple[MediaStreamTrack, Optional[int]]:
    """The track and the buffer size, from the init, its dict form, or the arguments"""
    if isinstance(track, MediaStreamTrackProcessorInit):
        track, max_buffer_size = track.track, track.max_buffer_size
    elif isinstance(track, dict):
        init = dict(track)
        track = init.pop('track', None)
        max_buffer_size = init.pop('max_buffer_size', init.pop('maxBufferSize', max_buffer_size))
        if init:
            raise TypeError(f'MediaStreamTrackProcessorInit has no member {next(iter(init))!r}')
    if 'maxBufferSize' in options:
        max_buffer_size = options.pop('maxBufferSize')
    if options:
        raise TypeError(f'Unexpected arguments: {", ".join(options)}')
    if not isinstance(track, MediaStreamTrack):
        raise TypeError(f'track must be a MediaStreamTrack, not {type(track).__name__}')
    return track, max_buffer_size


class _TrackSource:
    """The underlying source of :attr:`MediaStreamTrackProcessor.readable`: takes media from the native queue only
    for pending reads, so the native queue drops the oldest items when full"""

    def __init__(self, processor: 'MediaStreamTrackProcessor'):
        self._processor = processor
        self._controller = None

    def start(self, controller):
        self._controller = controller

    def pull(self, controller):
        native = self._processor._native_obj
        created_outside_loop = native._listeners is None
        # the native events go to the loop reading
        self._processor._attach()
        if created_outside_loop:
            # the wakeup sent before was dropped
            native._ackWakeup()
        self.deliver()

    def cancel(self, reason):
        self._processor._native_obj.cancel()

    def deliver(self):
        """Fulfills the pending reads with the media queued, and closes the stream once the track ended"""
        native = self._processor._native_obj
        stream = self._processor._readable
        controller = self._controller
        while stream._state == 'readable' and stream._reader is not None and stream._reader._read_requests:
            item = native.read()
            if item is None:
                break
            controller.enqueue(self._processor._wrap_media(item))
        if native.ended and stream._state == 'readable' and not controller._close_requested:
            controller.close()


class MediaStreamTrackProcessor(WebRTCObject, EventTarget):
    """Reads the media of a track as a stream: :obj:`webrtc.VideoFrame` objects for a video track,
    :obj:`webrtc.AudioData` ones (10 ms each) for an audio track, as Chrome does
    (https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackProcessor).

    Media is queued as it arrives, up to ``max_buffer_size`` items: when the queue is full, the oldest item is
    dropped (and counted in :attr:`discarded_frames`), so a slow reader never makes memory grow. The stream closes
    when the track ends. Frames read are to be closed once used.

    Args:
        track (:obj:`webrtc.MediaStreamTrack` or :obj:`MediaStreamTrackProcessorInit`): The track to read, or the
            init with it. A dictionary of the init's members is taken too.
        max_buffer_size (:obj:`int`, optional): How many items are queued: 1 frame of video by default, 10 chunks
            of audio.

    Raises:
        :obj:`TypeError`: If the track isn't a :obj:`webrtc.MediaStreamTrack`, or the size isn't from 0 to 65535.

    Example::

        processor = webrtc.MediaStreamTrackProcessor(track)
        async for frame in processor.readable:
            ...
            frame.close()
    """

    _class = wrtc.MediaStreamTrackProcessor

    def __init__(
        self,
        track: Union[MediaStreamTrack, MediaStreamTrackProcessorInit, Dict[str, Any], None] = None,
        max_buffer_size: Optional[int] = None,
        **options,
    ):
        track, max_buffer_size = _parse_init(track, max_buffer_size, options)
        video = track.kind == MediaType.video
        if max_buffer_size is None:
            max_buffer_size = DEFAULT_VIDEO_BUFFER_SIZE if video else DEFAULT_AUDIO_BUFFER_SIZE
        if isinstance(max_buffer_size, bool) or not isinstance(max_buffer_size, int):
            raise TypeError(f'max_buffer_size must be an integer, not {max_buffer_size!r}')
        if not 0 <= max_buffer_size <= 65535:
            raise TypeError(f'max_buffer_size must be from 0 to 65535, not {max_buffer_size}')

        super().__init__(self._class(track._native_obj, max(1, max_buffer_size)))
        self._video = video
        self._source = _TrackSource(self)
        self._readable = ReadableStream(self._source, high_water_mark=0)
        self._attach()

    def _on_event(self, name: str, *args):
        if name == '_ready':
            self._native_obj._ackWakeup()
            self._source.deliver()

    def _wrap_media(self, item: tuple) -> Union[VideoFrame, AudioData]:
        if self._video:
            buffer, timestamp, rotation, rtp_timestamp = item
            return VideoFrame._from_native(buffer, timestamp, rotation, rtp_timestamp or None)
        data, bits_per_sample, sample_rate, channels, frames, timestamp = item
        return AudioData._from_native(data, bits_per_sample, sample_rate, channels, frames, timestamp)

    @property
    def readable(self) -> ReadableStream:
        """:obj:`webrtc.ReadableStream`: The media of the track."""
        return self._readable

    @property
    def total_frames(self) -> int:
        """:obj:`int`: How many frames (or chunks of audio) the track delivered."""
        return self._native_obj.totalFrames

    @property
    def discarded_frames(self) -> int:
        """:obj:`int`: How many of them were dropped because the queue was full."""
        return self._native_obj.discardedFrames

    #: Alias for :attr:`total_frames`
    totalFrames = total_frames
    #: Alias for :attr:`discarded_frames`
    discardedFrames = discarded_frames
