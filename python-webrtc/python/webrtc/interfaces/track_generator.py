#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Tracks of media the application writes, with VideoTrackGenerator and the non-standard MediaStreamTrackGenerator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import wrtc
from webrtc.enums import AudioSampleFormat, MediaType
from webrtc.exceptions import NotSupportedError
from webrtc.interfaces.media_stream_track import MediaStreamTrack
from webrtc.models.audio_data import AudioData, AudioDataCopyToOptions
from webrtc.models.dictionary import Dictionary
from webrtc.models.video_frame import VideoFrame
from webrtc.streams import WritableStream

if TYPE_CHECKING:
    from webrtc.enums import MediaTypeValue
    from webrtc.streams import WritableStreamDefaultController


class _TrackSink:
    """The underlying sink of a generator's writable stream: sends each chunk on the track, closing it."""

    def __init__(self, native: wrtc.TrackGenerator) -> None:
        self._native = native

    def write(self, chunk: object, _controller: WritableStreamDefaultController) -> None:
        if self._native.kind == 'video':
            self._write_video(chunk)
        else:
            self._write_audio(chunk)

    def _write_video(self, frame: object) -> None:
        if not isinstance(frame, VideoFrame):
            msg = f'A video generator takes VideoFrame, not {type(frame).__name__}'
            raise TypeError(msg)
        if frame._resource is None:
            msg = 'The frame is closed'
            raise TypeError(msg)
        timestamp, rotation = frame.timestamp, frame.rotation
        self._native.writeVideo(frame._take_resource(), timestamp, rotation)

    def _write_audio(self, data: object) -> None:
        if not isinstance(data, AudioData):
            msg = f'An audio generator takes AudioData, not {type(data).__name__}'
            raise TypeError(msg)
        if data._data is None:
            msg = 'The data is closed'
            raise TypeError(msg)
        with data._take() as audio:
            self._send_audio(audio)

    def _send_audio(self, audio: AudioData) -> None:
        data_bytes = audio._data
        if audio.format == AudioSampleFormat.s16 and data_bytes is not None:
            samples = bytes(data_bytes)
        else:
            # closed, copy_to() raises
            buffer = bytearray(audio.number_of_frames * audio.number_of_channels * 2)
            audio.copy_to(buffer, AudioDataCopyToOptions(plane_index=0, format=AudioSampleFormat.s16))
            samples = bytes(buffer)
        # rates beyond an int are unsupported too: the native check rejects them
        rate = min(int(audio.sample_rate), 2**31 - 1)
        try:
            self._native.writeAudio(samples, rate, audio.number_of_channels, audio.number_of_frames)
        except ValueError as e:
            raise NotSupportedError(str(e)) from None

    def close(self) -> None:
        # ends the tracks of the generator
        self._native.close()

    def abort(self, _reason: object) -> None:
        self._native.close()


class VideoTrackGenerator:
    """A video track of the frames the application writes to a stream.

    The visible rect of each :obj:`webrtc.VideoFrame` written is sent on :attr:`track`, and the frame is closed.
    Writing anything else or a closed frame errors :attr:`writable`. Closing or aborting :attr:`writable` ends the
    track.

    See :mdn:`VideoTrackGenerator`.

    Example::

        generator = webrtc.VideoTrackGenerator()
        pc.add_track(generator.track)
        writer = generator.writable.get_writer()
        init = webrtc.VideoFrameBufferInit(format='I420', coded_width=640, coded_height=480, timestamp=0)
        await writer.write(webrtc.VideoFrame(i420, init))
    """

    def __init__(self) -> None:
        self._native = wrtc.TrackGenerator('video')
        # the native generator doesn't keep the track, Python does
        self._track = MediaStreamTrack._wrap(self._native.track)
        self._writable = WritableStream(_TrackSink(self._native))

    @property
    def track(self) -> MediaStreamTrack:
        """:obj:`webrtc.MediaStreamTrack`: The video track carrying the frames written.

        See :mdn:`VideoTrackGenerator/track`.
        """
        return self._track

    @property
    def writable(self) -> WritableStream:
        """:obj:`webrtc.WritableStream`: The stream to write :obj:`webrtc.VideoFrame` objects to.

        See :mdn:`VideoTrackGenerator/writable`.
        """
        return self._writable

    @property
    def muted(self) -> bool:
        """:obj:`bool`: Whether written frames are dropped. :attr:`track` stays muted while it's :obj:`True`.

        It starts as :obj:`False`.

        See :mdn:`VideoTrackGenerator/muted`.
        """
        return self._native.muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._native.muted = bool(value)


@dataclass
class MediaStreamTrackGeneratorInit(Dictionary):
    """The options of a :obj:`MediaStreamTrackGenerator`.

    Args:
        kind (:obj:`webrtc.MediaType`): The kind of the track, ``'audio'`` or ``'video'``.
    """

    kind: MediaType | MediaTypeValue


class MediaStreamTrackGenerator(MediaStreamTrack):
    """A track of the :obj:`webrtc.VideoFrame` or :obj:`webrtc.AudioData` objects the application writes to a stream.

    It's non-standard, but it's the only way to generate audio. For video, :obj:`VideoTrackGenerator` is the standard
    choice. Unlike :obj:`VideoTrackGenerator`, this generator is the track itself.

    Each object written is sent and closed. Audio is converted to 16-bit samples and sent in 10 ms frames. Samples
    that don't fill a frame wait for the next write. Writing the wrong kind of object or a closed one errors
    :attr:`writable`. So does a sample rate the library can't send, with :obj:`webrtc.NotSupportedError`. Closing or
    aborting :attr:`writable` ends the track.

    See :mdn:`MediaStreamTrackGenerator`.

    Args:
        kind (:obj:`webrtc.MediaType`, :obj:`str` or :obj:`MediaStreamTrackGeneratorInit`): ``'audio'`` or ``'video'``,
            or an init that holds it.

    Raises:
        TypeError: If the kind isn't audio or video.
    """

    def __init__(self, kind: MediaType | MediaTypeValue | MediaStreamTrackGeneratorInit) -> None:
        if isinstance(kind, MediaStreamTrackGeneratorInit):
            kind = kind.kind
        if kind not in {'audio', 'video'}:
            msg = f"The kind must be 'audio' or 'video', not {kind!r}"
            raise TypeError(msg)
        self._generator = wrtc.TrackGenerator(MediaType(kind).value)
        super().__init__(self._generator.track)
        self._attach()
        self._writable = WritableStream(_TrackSink(self._generator))

    @property
    def writable(self) -> WritableStream:
        """:obj:`webrtc.WritableStream`: The stream to write :obj:`webrtc.VideoFrame` or :obj:`webrtc.AudioData` to.

        See :mdn:`MediaStreamTrackGenerator/writable`.
        """
        return self._writable
