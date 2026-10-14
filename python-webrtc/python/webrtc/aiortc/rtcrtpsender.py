#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio
import ctypes
import functools
from typing import TYPE_CHECKING, cast

import av
from av.packet import Packet

import webrtc
from webrtc.aiortc._utils import _DEFAULT_SAMPLE_RATE, _ORTC, _log_failure, _ReadOnly, _Resampler, logger
from webrtc.aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from webrtc.aiortc.rtcrtpreceiver import RemoteStreamTrack, _RtpEndpoint

if TYPE_CHECKING:
    from av.frame import Frame
    from av.stream import Stream

    from webrtc.aiortc.rtcdtlstransport import RTCDtlsTransport

_CORE_PIXEL_FORMATS = {
    'yuv420p': webrtc.VideoPixelFormat.I420,
    'nv12': webrtc.VideoPixelFormat.NV12,
    'rgba': webrtc.VideoPixelFormat.RGBA,
    'bgra': webrtc.VideoPixelFormat.BGRA,
    'rgb0': webrtc.VideoPixelFormat.RGBX,
    'bgr0': webrtc.VideoPixelFormat.BGRX,
}


_SENDABLE_CHANNELS = (1, 2)
_PYBUF_READ = 0x100
_MEMORY_VIEW = ctypes.PYFUNCTYPE(ctypes.py_object, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int)
_memory_view = _MEMORY_VIEW(('PyMemoryView_FromMemory', ctypes.pythonapi))
_MIN_SAMPLE_RATE = 8000
_MAX_SAMPLE_RATE = 384000


def _microseconds(frame: Frame) -> int:
    time = frame.time
    return round(time * 1_000_000) if time is not None else 0


def _native_video_frame(frame: av.VideoFrame) -> webrtc.VideoFrame:
    format = _CORE_PIXEL_FORMATS.get(frame.format.name)
    if format is None:
        frame = frame.reformat(format='yuv420p')
        format = webrtc.VideoPixelFormat.I420
    # a view from the first plane to the last: the core copies only the rows of the planes, never the gaps between
    addresses = [plane.buffer_ptr for plane in frame.planes]
    start = min(addresses)
    end = max(address + plane.buffer_size for address, plane in zip(addresses, frame.planes))
    init = webrtc.VideoFrameBufferInit(
        format=format,
        coded_width=frame.width,
        coded_height=frame.height,
        timestamp=_microseconds(frame),
        layout=[
            webrtc.PlaneLayout(address - start, plane.line_size) for address, plane in zip(addresses, frame.planes)
        ],
    )
    return webrtc.VideoFrame(cast('memoryview', _memory_view(start, end - start, _PYBUF_READ)), init)


def _native_audio_data(frame: av.AudioFrame) -> webrtc.AudioData:
    init = webrtc.AudioDataInit(
        format='s16',
        sample_rate=frame.sample_rate,
        number_of_frames=frame.samples,
        number_of_channels=len(frame.layout.channels),
        timestamp=_microseconds(frame),
        data=frame.planes[0],
    )
    return webrtc.AudioData(init)


def _sendable_rate(rate: int) -> bool:
    # the core sends 10 ms chunks of rate // 100 samples
    return rate % 100 == 0 and _MIN_SAMPLE_RATE <= rate <= _MAX_SAMPLE_RATE


class _NativeMedia:
    def __init__(self) -> None:
        self._resampler = _Resampler()
        self._decoder: av.AudioCodecContext | av.VideoCodecContext | None = None

    async def convert(self, media: Frame | Packet[Stream]) -> list[webrtc.VideoFrame | webrtc.AudioData]:
        loop = asyncio.get_running_loop()
        frames = await loop.run_in_executor(None, self._decode, media) if isinstance(media, Packet) else [media]
        converted: list[webrtc.VideoFrame | webrtc.AudioData] = []
        for frame in frames:
            if isinstance(frame, av.VideoFrame) and frame.format.name in _CORE_PIXEL_FORMATS:
                converted.append(_native_video_frame(frame))
            elif isinstance(frame, av.VideoFrame):
                # converting the pixels takes milliseconds at large sizes
                converted.append(await loop.run_in_executor(None, _native_video_frame, frame))
            elif isinstance(frame, av.AudioFrame):
                converted.extend(_native_audio_data(chunk) for chunk in self._audio(frame))
        return converted

    def _decode(self, packet: Packet[Stream]) -> list[Frame]:
        if self._decoder is None:
            # the stream's own decoder isn't safe to share between the threads that decode for each sender
            stream = packet.stream.codec_context
            self._decoder = cast(
                'av.AudioCodecContext | av.VideoCodecContext', av.CodecContext.create(stream.name, 'r')
            )
            self._decoder.extradata = stream.extradata
            if isinstance(stream, av.AudioCodecContext) and isinstance(self._decoder, av.AudioCodecContext):
                self._decoder.sample_rate = stream.sample_rate
                self._decoder.layout = stream.layout
        return cast('list[Frame]', self._decoder.decode(packet))

    def _audio(self, frame: av.AudioFrame) -> list[av.AudioFrame]:
        channels = len(frame.layout.channels)
        if frame.format.name == 's16' and channels in _SENDABLE_CHANNELS and _sendable_rate(frame.sample_rate):
            return [frame]
        layout = 'mono' if channels == 1 else 'stereo'
        rate = frame.sample_rate if _sendable_rate(frame.sample_rate) else _DEFAULT_SAMPLE_RATE
        return self._resampler.resample(frame, layout, rate, None)


async def _pump(
    track: MediaStreamTrack,
    writer: webrtc.WritableStreamDefaultWriter[webrtc.VideoFrame | webrtc.AudioData],
    failure: str,
) -> None:
    media = _NativeMedia()
    try:
        while True:
            for chunk in await media.convert(await track.recv()):
                await writer.write(chunk)
    except MediaStreamError:
        pass
    except Exception:
        logger.exception(failure)


def _source(
    track: MediaStreamTrack, generator: webrtc.MediaStreamTrackGenerator | None
) -> tuple[webrtc.MediaStreamTrack, webrtc.MediaStreamTrackGenerator | None]:
    if isinstance(track, RemoteStreamTrack):
        return track._native, generator
    relayed = _relayed_source(track)
    if relayed is not None:
        return relayed._generator.clone(), generator
    if generator is None:
        generator = webrtc.MediaStreamTrackGenerator(webrtc.MediaType(track.kind))
    return generator, generator


def _relayed_source(track: MediaStreamTrack | None) -> _RelayedSource | None:
    # the vendored module imports this one
    from webrtc.aiortc.contrib.media import RelayStreamTrack  # ruff: ignore[import-outside-top-level]

    if not isinstance(track, RelayStreamTrack) or track._relay is None or track._source is None:
        return None
    source = track._source
    relayed = _RELAYED.get(source)
    if relayed is None:
        relayed = _RELAYED[source] = _RelayedSource(track._relay.subscribe(source, track._buffered), source)
    return relayed


class _RelayedSource:
    # the senders of every proxy of a relayed track share one pump, through clones of one generator
    def __init__(self, input_: MediaStreamTrack, source: MediaStreamTrack) -> None:
        self._source = source
        self._input = input_
        self._generator = webrtc.MediaStreamTrackGenerator(webrtc.MediaType(source.kind))
        self._senders: set[RTCRtpSender] = set()
        self._pump: asyncio.Future[None] | None = None

    def start(self) -> None:
        if self._pump is None:
            self._pump = asyncio.ensure_future(self._run(self._generator.writable.get_writer()))

    def detach(self, sender: RTCRtpSender) -> asyncio.Future[None] | None:
        self._senders.discard(sender)
        if len(self._senders) > 0:
            return None
        pump, self._pump = self._pump, None
        if pump is not None:
            pump.cancel()
        self._end()
        return pump

    def _end(self) -> None:
        if _RELAYED.get(self._source) is self:
            del _RELAYED[self._source]
        self._input.stop()
        self._generator.stop()

    async def _run(self, writer: webrtc.WritableStreamDefaultWriter[webrtc.VideoFrame | webrtc.AudioData]) -> None:
        await _pump(self._input, writer, f'MediaRelay stopped relaying a {self._source.kind} track to its senders')
        self._pump = None
        self._end()
        for sender in list(self._senders):
            sender._source_ended()


_RELAYED: dict[MediaStreamTrack, _RelayedSource] = {}


class RTCRtpSender(_RtpEndpoint[webrtc.RTCRtpSender]):
    _native_class = webrtc.RTCRtpSender
    _track: MediaStreamTrack | None = None
    _sent: webrtc.MediaStreamTrack | None = None
    _generator: webrtc.MediaStreamTrackGenerator | None = None
    _writer: webrtc.WritableStreamDefaultWriter[webrtc.VideoFrame | webrtc.AudioData] | None = None
    _pump: asyncio.Future[None] | None = None
    _relayed: _RelayedSource | None = None
    _started = False
    kind: _ReadOnly[str] = _ReadOnly('_transceiver.kind')
    track: _ReadOnly[MediaStreamTrack | None] = _ReadOnly('_track')

    def __init__(self, trackOrKind: str | MediaStreamTrack, transport: RTCDtlsTransport) -> None:
        raise NotImplementedError(_ORTC)

    def replaceTrack(self, track: MediaStreamTrack | None) -> None:
        self._stop_pump()
        sent, generator = _source(track, self._generator) if track is not None else (None, self._generator)
        if sent != self._sent:
            task = asyncio.ensure_future(self._native.replace_track(sent))
            task.add_done_callback(functools.partial(_log_failure, 'RTCRtpSender.replaceTrack'))
        self._use(track, sent, generator)

    async def stop(self) -> None:
        pump = self._stop_pump()
        if pump is not None:
            await asyncio.gather(pump, return_exceptions=True)
        # a sender that never sent leaves its track alone
        if self._started and self._track is not None:
            self._track.stop()
            self._track = None

    def _send_keyframe(self) -> None:
        parameters = self._native.get_parameters()
        options = webrtc.RTCSetParameterOptions([
            webrtc.RTCEncodingOptions(key_frame=True) for _ in parameters.encodings
        ])
        task = asyncio.ensure_future(self._native.set_parameters(parameters, options))
        task.add_done_callback(functools.partial(_log_failure, 'RTCRtpSender._send_keyframe'))

    def _use(
        self,
        track: MediaStreamTrack | None,
        sent: webrtc.MediaStreamTrack | None,
        generator: webrtc.MediaStreamTrackGenerator | None,
    ) -> None:
        self._track = track
        self._sent = sent
        self._relayed = _relayed_source(track)
        if self._relayed is not None and track is not None:
            self._relayed._senders.add(self)
            track.on('ended', functools.partial(self._track_ended, track))
        if generator is not self._generator:
            self._generator = generator
            self._writer = None
        self._start()

    def _start(self) -> None:
        track, generator = self._track, self._generator
        if track is None or self._pump is not None or not self._transceiver._sending():
            return
        self._started = True
        if self._relayed is not None:
            self._relayed.start()
        elif generator is not None and not isinstance(track, RemoteStreamTrack):
            # streams are used from a running loop, which the track may have been added before
            if self._writer is None:
                self._writer = generator.writable.get_writer()
            self._pump = asyncio.ensure_future(self._run(track, self._writer))

    def _stop_pump(self) -> asyncio.Future[None] | None:
        relayed, self._relayed = self._relayed, None
        if relayed is not None:
            if self._sent is not None:
                self._sent.stop()
            return relayed.detach(self)
        pump, self._pump = self._pump, None
        if pump is not None:
            pump.cancel()
        return pump

    async def _run(
        self, track: MediaStreamTrack, writer: webrtc.WritableStreamDefaultWriter[webrtc.VideoFrame | webrtc.AudioData]
    ) -> None:
        await _pump(track, writer, f'RTCRtpSender({self.kind}) stopped sending its track')
        self._pump = None
        self._source_ended()

    def _source_ended(self) -> None:
        self._relayed = None
        track, self._track = self._track, None
        if track is not None:
            track.stop()

    def _track_ended(self, track: MediaStreamTrack) -> None:
        if self._track is track:
            _ = self._stop_pump()
            self._track = None


__all__ = ['RTCRtpSender']
