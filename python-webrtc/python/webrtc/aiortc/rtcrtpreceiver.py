#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio
import collections
import fractions
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Generic, TypeVar, cast

import av
from typing_extensions import override

import webrtc
from webrtc.aiortc._utils import _KINDS, _ORTC, _datetime, _ReadOnly, _Resampler
from webrtc.aiortc.mediastreams import (
    AUDIO_PTIME,
    VIDEO_CLOCK_RATE,
    VIDEO_TIME_BASE,
    MediaStreamError,
    MediaStreamTrack,
)
from webrtc.aiortc.rtcrtpparameters import (
    ParametersDict,
    RTCRtpCapabilities,
    RTCRtpCodecCapability,
    RTCRtpHeaderExtensionCapability,
)
from webrtc.aiortc.sdp import parameters_from_sdp

if TYPE_CHECKING:
    import datetime as dt

    from av.frame import Frame
    from typing_extensions import Self

    from webrtc.aiortc.rtcdtlstransport import RTCDtlsTransport
    from webrtc.aiortc.rtcrtptransceiver import RTCRtpTransceiver
    from webrtc.aiortc.stats import RTCStatsReport

# about a second of media, so a reader that falls behind for a moment loses nothing
_VIDEO_BUFFER = 30
_AUDIO_BUFFER = 100
_LATEST = 1
_NO_COPY = (0, 0, 0, 0, 0, 0)
_AV_PIXEL_FORMATS = {
    'I420': 'yuv420p',
    'I420A': 'yuva420p',
    'I422': 'yuv422p',
    'I444': 'yuv444p',
    'I420P10': 'yuv420p10le',
    'I422P10': 'yuv422p10le',
    'I444P10': 'yuv444p10le',
    'NV12': 'nv12',
    'RGBA': 'rgba',
    'RGBX': 'rgb0',
    'BGRA': 'bgra',
    'BGRX': 'bgr0',
}
_S16 = webrtc.AudioDataCopyToOptions(plane_index=0, format='s16')
_S16_BYTES = 2
_NOT_DECODED = {'red', 'cn', 'telephone-event'}
_N = TypeVar('_N', webrtc.RTCRtpSender, webrtc.RTCRtpReceiver)


@dataclass
class RTCRtpContributingSource:
    timestamp: dt.datetime
    source: int


@dataclass
class RTCRtpSynchronizationSource:
    timestamp: dt.datetime
    source: int


class _VideoFrames:
    def __init__(self) -> None:
        self._origin: int | None = None
        self._last = 0
        self._next = 0
        self._rtp = True

    def convert(self, media: webrtc.VideoFrame | webrtc.AudioData) -> list[Frame]:
        frame = cast('webrtc.VideoFrame', media)
        with frame:
            converted = _av_video_frame(frame)
            rtp_timestamp = frame.metadata().rtp_timestamp
            capture_time = frame.timestamp * VIDEO_CLOCK_RATE // 1_000_000
        if rtp_timestamp is None:
            converted.pts = self.map(capture_time, rtp=False)
        else:
            converted.pts = self.map(rtp_timestamp)
        converted.time_base = VIDEO_TIME_BASE
        return [converted]

    def map(self, timestamp: int, *, rtp: bool = True) -> int:
        if self._origin is None or rtp != self._rtp:
            # a new clock continues the pts of the old one
            self._origin = timestamp - self._next
            self._rtp = rtp
        elif timestamp < self._last:
            # the 32-bit RTP timestamp wrapped
            self._origin -= 1 << 32
        self._last = timestamp
        pts = timestamp - self._origin
        self._next = pts + 1
        return pts


def _av_video_frame(frame: webrtc.VideoFrame) -> av.VideoFrame:
    plan = frame._plan_copy(None)
    width = int(plan.rect.width)
    height = int(plan.rect.height)
    converted = av.VideoFrame(width, height, _AV_PIXEL_FORMATS[plan.format.value])
    for index, (copy, plane) in enumerate(zip(plan.planes, converted.planes)):
        # a copy of no rows is skipped, so each call fills one plane of the frame
        copies: list[tuple[int, int, int, int, int, int]] = [_NO_COPY] * len(plan.planes)
        copies[index] = (copy.left_bytes, copy.top, copy.width_bytes, copy.height, 0, plane.line_size)
        plan.resource.copyPlanes(plane, copies)
    return converted


class _AudioFrames:
    def __init__(self, layout: str, rate: int) -> None:
        self._layout = layout
        self._channels = len(av.AudioLayout(layout).channels)
        self._rate = rate
        self._frame_size = int(rate * AUDIO_PTIME)
        self._time_base = fractions.Fraction(1, rate)
        self._resampler = _Resampler()
        self._mono = memoryview(bytearray(self._frame_size * _S16_BYTES)).cast('h')
        self._pending: av.AudioFrame | None = None
        self._filled = 0
        self._samples = 0
        self._origin: int | None = None
        self._cut = False

    def convert(self, media: webrtc.VideoFrame | webrtc.AudioData) -> list[Frame]:
        data = cast('webrtc.AudioData', media)
        with data:
            self._follow_clock(data.timestamp)
            if data.sample_rate == self._rate and data.number_of_channels in {1, self._channels}:
                return self._fill(data)
            self._pending = None
            chunk = av.AudioFrame(format='s16', layout=f'{data.number_of_channels}c', samples=data.number_of_frames)
            data.copy_to(memoryview(chunk.planes[0]), _S16)
            chunk.sample_rate = int(data.sample_rate)
        resampled = self._resampler.resample(chunk, self._layout, self._rate, self._frame_size)
        return [self._stamped(frame) for frame in resampled]

    def _fill(self, data: webrtc.AudioData) -> list[Frame]:
        # the core cuts the chunks into frames of the decoders' size, with no resampling
        frames: list[Frame] = []
        offset = 0
        available = data.number_of_frames
        upmix = data.number_of_channels != self._channels
        while offset < available:
            if self._pending is None:
                self._pending = av.AudioFrame(format='s16', layout=self._layout, samples=self._frame_size)
                self._filled = 0

            count = min(available - offset, self._frame_size - self._filled)
            plane = memoryview(self._pending.planes[0])
            options = webrtc.AudioDataCopyToOptions(plane_index=0, frame_offset=offset, frame_count=count, format='s16')
            if upmix:
                # mono plays on every channel, as a stereo Opus decoder outputs it
                data.copy_to(self._mono, options)
                start = self._filled * self._channels
                end = (self._filled + count) * self._channels
                interleaved = plane.cast('h')
                for channel in range(self._channels):
                    interleaved[start + channel : end : self._channels] = self._mono[:count]
            else:
                data.copy_to(plane[self._filled * self._channels * _S16_BYTES :], options)

            offset += count
            self._filled += count
            if self._filled == self._frame_size:
                frames.append(self._stamped(self._pending))
                self._pending = None
        return frames

    def drop_partial(self) -> None:
        self._pending = None
        self._cut = True

    def _follow_clock(self, timestamp: int) -> None:
        # samples lost in a cut were never counted
        if self._origin is None:
            self._origin = timestamp
        elif self._cut:
            elapsed = round((timestamp - self._origin) * self._rate / 1_000_000)
            self._samples = max(self._samples, elapsed)
            self._resampler = _Resampler()
        self._cut = False

    def _stamped(self, frame: av.AudioFrame) -> av.AudioFrame:
        frame.pts = self._samples
        frame.sample_rate = self._rate
        frame.time_base = self._time_base
        self._samples += frame.samples
        return frame


def _audio_shape(receiver: RTCRtpReceiver | None) -> tuple[str, int]:
    # Opus comes as 48 kHz stereo, the other codecs as mono at their rate
    if receiver is None:
        return 'stereo', 48000
    codecs = receiver._native.get_parameters().codecs
    decoded = (c for c in codecs if c.mime_type.split('/')[1].lower() not in _NOT_DECODED)
    codec = next(decoded, None)
    if codec is None or codec.mime_type.lower() == 'audio/opus':
        return 'stereo', 48000
    if codec.mime_type.lower() == 'audio/g722':
        return 'mono', 16000
    return 'mono', codec.clock_rate


class RemoteStreamTrack(MediaStreamTrack):
    _native: webrtc.MediaStreamTrack
    _receiver: RTCRtpReceiver | None

    def __init__(self, kind: str, id: str | None = None) -> None:
        super().__init__()
        self.kind = kind
        if id is not None:
            self._id = id
        self._buffered = True
        self._processor: webrtc.MediaStreamTrackProcessor | None = None
        self._reader: webrtc.ReadableStreamDefaultReader[webrtc.VideoFrame | webrtc.AudioData] | None = None
        self._converter: _VideoFrames | _AudioFrames | None = None
        self._frames: collections.deque[Frame] = collections.deque()
        self._frame_queue: _FrameQueue | None = None
        self._reads = 0
        self._discarded = 0

    @classmethod
    def _of(cls, native: webrtc.MediaStreamTrack, receiver: RTCRtpReceiver | None, id: str | None = None) -> Self:
        track = cls(str(native.kind), id)
        track._native = native
        track._receiver = receiver
        return track

    def _clone(self, *, buffered: bool) -> RemoteStreamTrack:
        clone = RemoteStreamTrack._of(self._native.clone(), self._receiver)
        clone._buffered = buffered
        return clone

    def _open(self) -> webrtc.ReadableStreamDefaultReader[webrtc.VideoFrame | webrtc.AudioData]:
        video = self.kind == 'video'
        if not self._buffered:
            buffer = _LATEST
        elif video:
            buffer = _VIDEO_BUFFER
        else:
            buffer = _AUDIO_BUFFER

        init = webrtc.MediaStreamTrackProcessorInit(self._native, buffer)
        self._processor = webrtc.MediaStreamTrackProcessor(init)
        self._reader = self._processor.readable.get_reader()
        self._discarded = 0

        # a reopened reader keeps the timestamps going
        if self._converter is not None:
            return self._reader
        if video:
            self._converter = _VideoFrames()
        else:
            self._converter = _AudioFrames(*_audio_shape(self._receiver))
        return self._reader

    def _release(self) -> None:
        self._frames.clear()
        if isinstance(self._converter, _AudioFrames):
            self._converter.drop_partial()
        if self._reader is not None:
            self._reader.cancel().add_done_callback(_retrieved)
            self._reader = None
            self._processor = None

    def _ready_frames(self) -> int:
        """How many frames recv() returns without waiting."""
        processor = self._processor
        converter = self._converter
        # a waiting recv() owns the native queue
        if self._reads == 0 and processor is not None and converter is not None:
            media = processor._take()
            while media is not None:
                self._frames.extend(self._convert(converter, media))
                media = processor._take()
        return len(self._frames)

    @property
    def _queue(self) -> _FrameQueue:
        if self._frame_queue is None:
            self._frame_queue = _FrameQueue(self)
        return self._frame_queue

    @override
    async def recv(self) -> Frame:
        if self.readyState != 'live':
            raise MediaStreamError
        while len(self._frames) == 0:
            reader = self._reader if self._reader is not None else self._open()
            media = await self._read(reader)
            if media is None or self._converter is None:
                if reader is not self._reader and self.readyState == 'live':
                    # the receiver was disabled while this read waited
                    continue
                self.stop()
                raise MediaStreamError
            self._frames.extend(self._convert(self._converter, media))
        return self._frames.popleft()

    def _convert(
        self, converter: _VideoFrames | _AudioFrames, media: webrtc.VideoFrame | webrtc.AudioData
    ) -> list[Frame]:
        if isinstance(converter, _AudioFrames) and isinstance(media, webrtc.AudioData):
            discarded = media._discarded_before
            if discarded != self._discarded:
                self._discarded = discarded
                converter.drop_partial()
        return converter.convert(media)

    async def _read(
        self, reader: webrtc.ReadableStreamDefaultReader[webrtc.VideoFrame | webrtc.AudioData]
    ) -> webrtc.VideoFrame | webrtc.AudioData | None:
        read = reader.read()
        self._reads += 1
        try:
            return (await read).value
        except asyncio.CancelledError:
            self._keep_settled(read)
            raise
        finally:
            self._reads -= 1

    def _keep_settled(
        self, read: asyncio.Future[webrtc.ReadableStreamReadResult[webrtc.VideoFrame | webrtc.AudioData]]
    ) -> None:
        # cancelled after the read settled
        if not read.done() or read.cancelled() or read.exception() is not None:
            return

        media = read.result().value
        if media is not None and self._converter is not None:
            self._frames.extend(self._convert(self._converter, media))

    @override
    def stop(self) -> None:
        super().stop()
        self._release()
        self._native.stop()


class _FrameQueue(asyncio.Queue['Frame']):
    # apps drain it to skip stale frames
    def __init__(self, track: RemoteStreamTrack) -> None:
        super().__init__()
        self._track = track

    @override
    def qsize(self) -> int:
        return self._track._ready_frames()

    @override
    def empty(self) -> bool:
        return self.qsize() == 0

    @override
    def get_nowait(self) -> Frame:
        if self.empty():
            raise asyncio.QueueEmpty
        return self._track._frames.popleft()

    @override
    def task_done(self) -> None:
        pass


def _retrieved(future: asyncio.Future[None]) -> None:
    if not future.cancelled():
        _ = future.exception()


def _parameters(fmtp: str | None) -> ParametersDict:
    return parameters_from_sdp(fmtp) if fmtp is not None and fmtp != '' else {}


class _RtpEndpoint(Generic[_N]):
    _native: _N
    _native_class: ClassVar[type[webrtc.RTCRtpSender | webrtc.RTCRtpReceiver]]
    _transceiver: RTCRtpTransceiver

    @classmethod
    def _of(cls, native: _N, transceiver: RTCRtpTransceiver) -> Self:
        endpoint = cls.__new__(cls)
        endpoint._native = native
        endpoint._transceiver = transceiver
        return endpoint

    @property
    def transport(self) -> RTCDtlsTransport | None:
        native = self._native.transport
        return self._transceiver._pc._dtls_transport(native) if native is not None else None

    @classmethod
    def getCapabilities(cls, kind: str) -> RTCRtpCapabilities:
        if kind not in _KINDS:
            msg = f'cannot get capabilities for unknown media {kind}'
            raise ValueError(msg)
        native = cls._native_class.get_capabilities(webrtc.MediaType(kind))
        if native is None:
            return RTCRtpCapabilities()

        codecs = [
            RTCRtpCodecCapability(c.mime_type, c.clock_rate, c.channels, _parameters(c.sdp_fmtp_line))
            for c in native.codecs
        ]
        extensions = [RTCRtpHeaderExtensionCapability(e.uri) for e in native.header_extensions]
        return RTCRtpCapabilities(codecs=codecs, headerExtensions=extensions)

    async def getStats(self) -> RTCStatsReport:
        return self._transceiver._pc._stats(await self._native.get_stats())


class RTCRtpReceiver(_RtpEndpoint[webrtc.RTCRtpReceiver]):
    _native_class = webrtc.RTCRtpReceiver
    _track: RemoteStreamTrack | None = None
    _receiving = True
    track: _ReadOnly[RemoteStreamTrack | None] = _ReadOnly('_track')

    def __init__(self, kind: str, transport: RTCDtlsTransport) -> None:
        raise NotImplementedError(_ORTC)

    @property
    def _enabled(self) -> bool:
        return self._receiving

    @_enabled.setter
    def _enabled(self, enabled: bool) -> None:
        if not enabled and self._track is not None:
            self._track._release()
        self._receiving = enabled

    def getSynchronizationSources(self) -> list[RTCRtpSynchronizationSource]:
        sources = self._native.get_synchronization_sources()
        return [RTCRtpSynchronizationSource(_datetime(s.timestamp), s.source) for s in sources]

    async def stop(self) -> None:
        if self._track is not None:
            self._track.stop()


__all__ = ['RTCRtpContributingSource', 'RTCRtpReceiver', 'RTCRtpSynchronizationSource', 'RemoteStreamTrack']
