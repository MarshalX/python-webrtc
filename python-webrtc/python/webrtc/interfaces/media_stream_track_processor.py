#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStreamTrackProcessor of Chrome, the media of a track as a stream."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from webrtc import AudioData, MediaStreamTrack, MediaType, VideoFrame, WebRTCObject, wrtc
from webrtc.streams import ReadableStream
from webrtc.utils.events import EventTarget
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from webrtc.streams import ReadableStreamDefaultController

#: How many frames of video are queued for reads, as the specification says
DEFAULT_VIDEO_BUFFER_SIZE = 1
#: How many 10 ms chunks of audio are queued for reads, as Chrome does
DEFAULT_AUDIO_BUFFER_SIZE = 10
_MAX_BUFFER_SIZE = 65535


@dataclass
class MediaStreamTrackProcessorInit:
    """How to create a :obj:`MediaStreamTrackProcessor`.

    Args:
        track (:obj:`webrtc.MediaStreamTrack`): The track to read.
        max_buffer_size (:obj:`int`, optional): How many frames are queued for reads before the oldest one is dropped.
    """

    track: MediaStreamTrack
    max_buffer_size: int | None = None

    #: Alias for :attr:`max_buffer_size`
    maxBufferSize: ClassVar[Alias[int | None]] = alias('max_buffer_size')


def _parse_init(
    track: object, max_buffer_size: int | None, options: dict[str, object]
) -> tuple[MediaStreamTrack, int | None]:
    """The track and the buffer size, from the init, its dict form, or the arguments."""
    if isinstance(track, MediaStreamTrackProcessorInit):
        track, max_buffer_size = track.track, track.max_buffer_size
    elif isinstance(track, dict):
        init = dict(track)
        track = init.pop('track', None)
        max_buffer_size = init.pop('max_buffer_size', init.pop('maxBufferSize', max_buffer_size))
        if init:
            msg = f'MediaStreamTrackProcessorInit has no member {next(iter(init))!r}'
            raise TypeError(msg)
    if 'maxBufferSize' in options:
        max_buffer_size = options.pop('maxBufferSize')
    if options:
        msg = f'Unexpected arguments: {", ".join(options)}'
        raise TypeError(msg)
    if not isinstance(track, MediaStreamTrack):
        msg = f'track must be a MediaStreamTrack, not {type(track).__name__}'
        raise TypeError(msg)
    return track, max_buffer_size


class _TrackSource:
    """The underlying source of :attr:`MediaStreamTrackProcessor.readable`.

    It takes media from the native queue only for pending reads, so the native queue drops the oldest items when full.
    """

    def __init__(self, processor: MediaStreamTrackProcessor) -> None:
        self._processor = processor
        self._controller: ReadableStreamDefaultController | None = None

    def start(self, controller: ReadableStreamDefaultController) -> None:
        self._controller = controller

    def pull(self, _controller: ReadableStreamDefaultController) -> None:
        native = self._processor._native_obj
        created_outside_loop = native._listeners is None
        # the native events go to the loop reading
        self._processor._attach()
        if created_outside_loop:
            # the wakeup sent before was dropped
            native._ackWakeup()
        self.deliver()

    def cancel(self, _reason: object) -> None:
        self._processor._native_obj.cancel()

    def deliver(self) -> None:
        """Fulfills the pending reads with the media queued, and closes the stream once the track ended."""
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


class MediaStreamTrackProcessor(WebRTCObject[wrtc.MediaStreamTrackProcessor], EventTarget):
    """Reads the media of a track as a stream, as Chrome does.

    See https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackProcessor. It reads
    :obj:`webrtc.VideoFrame` objects for a video track, :obj:`webrtc.AudioData` ones (10 ms each) for an audio track.

    Media is queued as it arrives, up to ``max_buffer_size`` items: when the queue is full, the oldest item is
    dropped (and counted in :attr:`discarded_frames`), so a slow reader never makes memory grow. The stream closes
    when the track ends. Frames read are to be closed once used.

    Args:
        track (:obj:`webrtc.MediaStreamTrack` or :obj:`MediaStreamTrackProcessorInit`): The track to read, or the
            init with it. A dictionary of the init's members is taken too.
        max_buffer_size (:obj:`int`, optional): How many items are queued: 1 frame of video by default, 10 chunks
            of audio.

    Raises:
        TypeError: If the track isn't a :obj:`webrtc.MediaStreamTrack`, or the size isn't from 0 to 65535.

    Example::

        processor = webrtc.MediaStreamTrackProcessor(track)
        async for frame in processor.readable:
            ...
            frame.close()
    """

    _class = wrtc.MediaStreamTrackProcessor

    def __init__(
        self,
        track: MediaStreamTrack | MediaStreamTrackProcessorInit | dict[str, Any] | None = None,
        max_buffer_size: int | None = None,
        **options: object,
    ) -> None:
        track, max_buffer_size = _parse_init(track, max_buffer_size, options)
        video = track.kind == MediaType.video
        if max_buffer_size is None:
            max_buffer_size = DEFAULT_VIDEO_BUFFER_SIZE if video else DEFAULT_AUDIO_BUFFER_SIZE
        if isinstance(max_buffer_size, bool) or not isinstance(max_buffer_size, int):
            msg = f'max_buffer_size must be an integer, not {max_buffer_size!r}'
            raise TypeError(msg)
        if not 0 <= max_buffer_size <= _MAX_BUFFER_SIZE:
            msg = f'max_buffer_size must be from 0 to {_MAX_BUFFER_SIZE}, not {max_buffer_size}'
            raise TypeError(msg)

        super().__init__(self._class(track._native_obj, max(1, max_buffer_size)))
        # the native processor doesn't keep the track, Python does
        self._track = track
        self._video = video
        self._source = _TrackSource(self)
        self._readable = ReadableStream(self._source, high_water_mark=0)
        self._attach()

    def _on_event(self, name: str, *_args: object) -> None:
        if name == '_ready':
            self._native_obj._ackWakeup()
            self._source.deliver()

    def _wrap_media(self, item: tuple[Any, ...]) -> VideoFrame | AudioData:
        if self._video:
            return VideoFrame._from_native(item)
        return AudioData._from_native(item)

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
