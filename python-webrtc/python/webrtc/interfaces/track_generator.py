#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Tracks of media the application writes: VideoTrackGenerator, and MediaStreamTrackGenerator of Chrome."""

from dataclasses import dataclass
from typing import Any, Union

from webrtc import AudioData, AudioSampleFormat, MediaStreamTrack, MediaType, VideoFrame, wrtc
from webrtc.exceptions import NotSupportedError
from webrtc.streams import WritableStream


class _TrackSink:
    """The underlying sink of a generator's writable stream: sends each chunk on the track, closing it"""

    def __init__(self, native: 'wrtc.TrackGenerator'):
        self._native = native

    def write(self, chunk: Any, controller) -> None:
        if self._native.kind == 'video':
            self._write_video(chunk)
        else:
            self._write_audio(chunk)

    def _write_video(self, frame: Any) -> None:
        if not isinstance(frame, VideoFrame):
            raise TypeError(f'A video generator takes VideoFrame, not {type(frame).__name__}')
        if frame._resource is None:
            raise TypeError('The frame is closed')
        timestamp, rotation = frame.timestamp, frame.rotation
        self._native.writeVideo(frame._take_resource(), timestamp, rotation)

    def _write_audio(self, data: Any) -> None:
        if not isinstance(data, AudioData):
            raise TypeError(f'An audio generator takes AudioData, not {type(data).__name__}')
        if data._data is None:
            raise TypeError('The data is closed')
        audio = data._take()
        if audio.format == AudioSampleFormat.s16:
            samples = audio._data
        else:
            samples = bytearray(audio.number_of_frames * audio.number_of_channels * 2)
            audio.copy_to(samples, {'plane_index': 0, 'format': AudioSampleFormat.s16})
            samples = bytes(samples)
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

    def abort(self, reason: Any) -> None:
        self._native.close()


class VideoTrackGenerator:
    """A video track of the frames written to a stream
    (https://developer.mozilla.org/en-US/docs/Web/API/VideoTrackGenerator).

    Each frame written is sent on :attr:`track` and closed. Closing or aborting :attr:`writable` ends the track.

    Example::

        generator = webrtc.VideoTrackGenerator()
        pc.add_track(generator.track)
        writer = generator.writable.get_writer()
        await writer.write(webrtc.VideoFrame(i420, format='I420', coded_width=640, coded_height=480, timestamp=0))
    """

    def __init__(self):
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
    def muted(self, value: bool):
        self._native.muted = bool(value)


@dataclass
class MediaStreamTrackGeneratorInit:
    """How to create a :obj:`MediaStreamTrackGenerator`.

    Args:
        kind (:obj:`webrtc.MediaType`): ``audio`` or ``video``.
    """

    kind: MediaType


class MediaStreamTrackGenerator(MediaStreamTrack):
    """A track of the media written to a stream, :obj:`webrtc.VideoFrame` or :obj:`webrtc.AudioData` objects. It's
    Chrome's API (https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackGenerator), the only one for
    audio: for video, :obj:`VideoTrackGenerator` is the standard one.

    Audio is sent in 10 ms frames: samples short of one wait for the next ones written.

    Args:
        kind (:obj:`webrtc.MediaType`, :obj:`str` or :obj:`MediaStreamTrackGeneratorInit`): ``'audio'`` or ``'video'``,
            or the init with it. A dictionary of the init's members is taken too.

    Raises:
        :obj:`TypeError`: If the kind isn't audio or video.
    """

    def __init__(self, kind: Union[str, MediaType, MediaStreamTrackGeneratorInit, dict]):
        if isinstance(kind, MediaStreamTrackGeneratorInit):
            kind = kind.kind
        elif isinstance(kind, dict):
            kind = kind.get('kind')
        if kind not in ('audio', 'video'):
            raise TypeError(f"The kind must be 'audio' or 'video', not {kind!r}")
        self._generator = wrtc.TrackGenerator(MediaType(kind).value)
        super().__init__(self._generator.track)
        self._attach()
        self._writable = WritableStream(_TrackSink(self._generator))

    @property
    def writable(self) -> WritableStream:
        """:obj:`webrtc.WritableStream`: Where to write the media."""
        return self._writable
