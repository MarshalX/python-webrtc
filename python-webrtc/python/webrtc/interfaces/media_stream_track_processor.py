#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""MediaStreamTrackProcessor, which reads the media of a track as a readable stream."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from typing_extensions import Never, override

import wrtc
from webrtc.base import WebRTCObject
from webrtc.enums import MediaType
from webrtc.models.audio_data import AudioData
from webrtc.models.dictionary import Dictionary
from webrtc.models.video_frame import VideoFrame
from webrtc.streams import QueuingStrategy, ReadableStream
from webrtc.utils.events import EventTarget
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from webrtc.interfaces.media_stream_track import MediaStreamTrack
    from webrtc.streams import ReadableStreamDefaultController

#: How many video frames are queued for reads by default, as set by the specification
DEFAULT_VIDEO_BUFFER_SIZE = 1
#: How many 10 ms chunks of audio are queued for reads by default, which makes 100 ms in all
DEFAULT_AUDIO_BUFFER_SIZE = 10
_MAX_BUFFER_SIZE = 65535
# the members of a native item of video: the buffer, timestamp, rotation and RTP timestamp (6 for audio)
_VIDEO_ITEM_SIZE = 4


@dataclass
class MediaStreamTrackProcessorInit(Dictionary):
    """The options of a :obj:`MediaStreamTrackProcessor`.

    Args:
        track (:obj:`webrtc.MediaStreamTrack`): The track to read.
        max_buffer_size (:obj:`int`, optional): How many items are queued before the oldest one is dropped. It
            ranges from 0 to 65535, and 0 is treated as 1. If unset, it's :data:`DEFAULT_VIDEO_BUFFER_SIZE` or
            :data:`DEFAULT_AUDIO_BUFFER_SIZE`.
    """

    track: MediaStreamTrack
    max_buffer_size: int | None = None

    #: Alias for :attr:`max_buffer_size`
    maxBufferSize: ClassVar[Alias[int | None]] = alias('max_buffer_size')


class _TrackSource:
    """The underlying source of :attr:`MediaStreamTrackProcessor.readable`.

    It takes media from the native queue only for pending reads, so the native queue drops the oldest items when full.
    """

    def __init__(self, processor: MediaStreamTrackProcessor) -> None:
        self._processor = processor
        self._controller: ReadableStreamDefaultController[VideoFrame | AudioData] | None = None

    def start(self, controller: ReadableStreamDefaultController[VideoFrame | AudioData]) -> None:
        self._controller = controller

    def pull(self, _controller: ReadableStreamDefaultController[VideoFrame | AudioData]) -> None:
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
        controller = self._controller
        if controller is None:
            msg = 'the stream of the processor has not started'
            raise RuntimeError(msg)
        while controller._has_pending_reads():
            item = native.read()
            if item is None:
                break
            controller.enqueue(self._processor._wrap_media(item))
        if native.ended and controller._can_close_or_enqueue():
            controller.close()


class MediaStreamTrackProcessor(WebRTCObject[wrtc.MediaStreamTrackProcessor], EventTarget[Never]):
    """Reads the media of a track as a stream.

    :attr:`readable` gives :obj:`webrtc.VideoFrame` objects for a video track and :obj:`webrtc.AudioData` objects
    of 10 ms each for an audio track. Media is queued as it arrives, up to ``max_buffer_size`` items. When the
    queue is full, the oldest item is dropped and counted in :attr:`discarded_frames`, so a slow reader never makes
    memory grow. The stream closes when the track ends. Close each frame you read once you're done with it.

    See :mdn:`MediaStreamTrackProcessor`.

    Args:
        init (:obj:`MediaStreamTrackProcessorInit`): The track to read and how many items are queued. By
            default that's 1 frame of video or 10 chunks of audio.

    Raises:
        TypeError: If the size isn't an integer from 0 to 65535.

    Example::

        processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
        async for frame in processor.readable:
            ...
            frame.close()
    """

    _class = wrtc.MediaStreamTrackProcessor

    def __init__(self, init: MediaStreamTrackProcessorInit) -> None:
        track, max_buffer_size = init.track, init.max_buffer_size
        video = track.kind == MediaType.video
        if max_buffer_size is None:
            max_buffer_size = DEFAULT_VIDEO_BUFFER_SIZE if video else DEFAULT_AUDIO_BUFFER_SIZE
        if isinstance(max_buffer_size, bool) or not isinstance(max_buffer_size, int):
            msg = f'max_buffer_size must be an integer, not {max_buffer_size!r}'
            raise TypeError(msg)
        if not 0 <= max_buffer_size <= _MAX_BUFFER_SIZE:
            msg = f'max_buffer_size must be from 0 to {_MAX_BUFFER_SIZE}, not {max_buffer_size}'
            raise TypeError(msg)

        super().__init__(wrtc.MediaStreamTrackProcessor(track._native_obj, max(1, max_buffer_size)))
        # the native processor doesn't keep the track, Python does
        self._track = track
        self._source = _TrackSource(self)
        self._readable: ReadableStream[VideoFrame | AudioData] = ReadableStream(
            self._source, QueuingStrategy(high_water_mark=0)
        )
        self._attach()
        if self._native_obj._listeners is not None:
            # media comes as soon as the sink is attached: a wakeup sent before the listeners were set was dropped
            self._native_obj._ackWakeup()

    @override
    def _on_event(self, name: str, *_args: object) -> None:
        if name == '_ready':
            self._native_obj._ackWakeup()
            self._source.deliver()

    @staticmethod
    def _wrap_media(
        item: tuple[wrtc.VideoFrameBuffer, int, int, int] | tuple[bytes, int, int, int, int, int],
    ) -> VideoFrame | AudioData:
        if len(item) == _VIDEO_ITEM_SIZE:
            return VideoFrame._from_native(item)
        return AudioData._from_native(item)

    @property
    def readable(self) -> ReadableStream[VideoFrame | AudioData]:
        """:obj:`webrtc.ReadableStream`: The media of the track. It closes once the track ends.

        Canceling it makes the processor stop reading the track.

        See :mdn:`MediaStreamTrackProcessor/readable`.
        """
        return self._readable

    @property
    def total_frames(self) -> int:
        """:obj:`int`: How many frames or chunks of audio the track delivered to the processor, read or not.

        See :mdn:`MediaStreamTrackProcessor/totalFrames`.
        """
        return self._native_obj.totalFrames

    @property
    def discarded_frames(self) -> int:
        """:obj:`int`: How many of :attr:`total_frames` were dropped unread because the queue was full.

        See :mdn:`MediaStreamTrackProcessor/discardedFrames`.
        """
        return self._native_obj.discardedFrames

    #: Alias for :attr:`total_frames`
    totalFrames = total_frames
    #: Alias for :attr:`discarded_frames`
    discardedFrames = discarded_frames
