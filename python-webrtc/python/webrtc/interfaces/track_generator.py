#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Tracks of media the application writes: VideoTrackGenerator, and MediaStreamTrackGenerator of Chrome."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from webrtc import AudioData, AudioSampleFormat, MediaStreamTrack, MediaType, VideoFrame, wrtc
from webrtc.exceptions import NotSupportedError
from webrtc.models.audio_data import AudioDataCopyToOptions
from webrtc.models.dictionary import Dictionary
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
        audio = data._take()
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
        finally:
            audio.close()

    def close(self) -> None:
        # ends the tracks of the generator
        self._native.close()

    def abort(self, _reason: object) -> None:
        self._native.close()


class VideoTrackGenerator:
    """A video track of the frames written to a stream.

    See https://developer.mozilla.org/en-US/docs/Web/API/VideoTrackGenerator.

    Each frame written is sent on :attr:`track` and closed. Closing or aborting :attr:`writable` ends the track.

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
        """:obj:`webrtc.MediaStreamTrack`: The track of the frames."""
        return self._track

    @property
    def writable(self) -> WritableStream:
        """:obj:`webrtc.WritableStream`: Where to write :obj:`webrtc.VideoFrame` objects."""
        return self._writable

    @property
    def muted(self) -> bool:
        """:obj:`bool`: Whether frames written are dropped, the track being muted meanwhile."""
        return self._native.muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._native.muted = bool(value)


@dataclass
class MediaStreamTrackGeneratorInit(Dictionary):
    """How to create a :obj:`MediaStreamTrackGenerator`.

    Args:
        kind (:obj:`webrtc.MediaType`): ``audio`` or ``video``.
    """

    kind: MediaType | MediaTypeValue


class MediaStreamTrackGenerator(MediaStreamTrack):
    """A track of the media written to a stream, :obj:`webrtc.VideoFrame` or :obj:`webrtc.AudioData` objects.

    It's Chrome's API (https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackGenerator), the only one for
    audio: for video, :obj:`VideoTrackGenerator` is the standard one.

    Audio is sent in 10 ms frames: samples short of one wait for the next ones written.

    Args:
        kind (:obj:`webrtc.MediaType`, :obj:`str` or :obj:`MediaStreamTrackGeneratorInit`): ``'audio'`` or ``'video'``,
            or the init with it.

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
        """:obj:`webrtc.WritableStream`: Where to write the media."""
        return self._writable
