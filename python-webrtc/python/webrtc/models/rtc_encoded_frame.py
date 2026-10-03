#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The encoded frames an :obj:`webrtc.RTCRtpScriptTransformer` reads and writes, and their metadata."""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Generic, TypeVar

from typing_extensions import override

from webrtc.enums import EncodedVideoChunkType
from webrtc.exceptions import DataCloneError
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from typing_extensions import Buffer, Self

    import wrtc


@dataclass
class RTCEncodedFrameMetadata(Dictionary):
    """The metadata of an encoded frame. Members a frame doesn't have are :obj:`None`.

    Args:
        synchronization_source (:obj:`int`, optional): The SSRC of the RTP stream of the frame.
        payload_type (:obj:`int`, optional): The RTP payload type of the frame.
        contributing_sources (:obj:`list` of :obj:`int`, optional): The CSRCs of the frame.
        rtp_timestamp (:obj:`int`, optional): The RTP timestamp of the frame.
        receive_time (:obj:`float`, optional): When the first packet of a received frame arrived, in milliseconds
            since the Unix epoch.
        capture_time (:obj:`float`, optional): When the frame was captured, in milliseconds since the Unix epoch
            (of the remote clock, for a received frame).
        sender_capture_time_offset (:obj:`float`, optional): The offset of the clock of the capturer from the clock
            of the sender, in milliseconds, for a received frame.
        mime_type (:obj:`str`, optional): The codec of the frame, like ``'video/VP8'``.
    """

    synchronization_source: int | None = None
    payload_type: int | None = None
    contributing_sources: list[int] | None = None
    rtp_timestamp: int | None = None
    receive_time: float | None = None
    capture_time: float | None = None
    sender_capture_time_offset: float | None = None
    mime_type: str | None = None

    #: Alias for :attr:`synchronization_source`
    synchronizationSource: ClassVar[Alias[int | None]] = alias('synchronization_source')
    #: Alias for :attr:`payload_type`
    payloadType: ClassVar[Alias[int | None]] = alias('payload_type')
    #: Alias for :attr:`contributing_sources`
    contributingSources: ClassVar[Alias[list[int] | None]] = alias('contributing_sources')
    #: Alias for :attr:`rtp_timestamp`
    rtpTimestamp: ClassVar[Alias[int | None]] = alias('rtp_timestamp')
    #: Alias for :attr:`receive_time`
    receiveTime: ClassVar[Alias[float | None]] = alias('receive_time')
    #: Alias for :attr:`capture_time`
    captureTime: ClassVar[Alias[float | None]] = alias('capture_time')
    #: Alias for :attr:`sender_capture_time_offset`
    senderCaptureTimeOffset: ClassVar[Alias[float | None]] = alias('sender_capture_time_offset')
    #: Alias for :attr:`mime_type`
    mimeType: ClassVar[Alias[str | None]] = alias('mime_type')


@dataclass
class RTCEncodedVideoFrameMetadata(RTCEncodedFrameMetadata):
    """The metadata of an :obj:`RTCEncodedVideoFrame`. See :obj:`RTCEncodedFrameMetadata` for the common members.

    Args:
        frame_id (:obj:`int`, optional): The identifier of the frame, which dependencies refer to.
        dependencies (:obj:`list` of :obj:`int`, optional): The identifiers of the frames this one depends on.
        width (:obj:`int`, optional): The width of the frame, in pixels.
        height (:obj:`int`, optional): The height of the frame, in pixels.
        spatial_index (:obj:`int`, optional): The spatial layer of the frame.
        temporal_index (:obj:`int`, optional): The temporal layer of the frame.
        timestamp (:obj:`int`, optional): The presentation timestamp of the frame, in microseconds.
    """

    frame_id: int | None = None
    dependencies: list[int] | None = None
    width: int | None = None
    height: int | None = None
    spatial_index: int | None = None
    temporal_index: int | None = None
    timestamp: int | None = None

    #: Alias for :attr:`frame_id`
    frameId: ClassVar[Alias[int | None]] = alias('frame_id')
    #: Alias for :attr:`spatial_index`
    spatialIndex: ClassVar[Alias[int | None]] = alias('spatial_index')
    #: Alias for :attr:`temporal_index`
    temporalIndex: ClassVar[Alias[int | None]] = alias('temporal_index')


@dataclass
class RTCEncodedAudioFrameMetadata(RTCEncodedFrameMetadata):
    """The metadata of an :obj:`RTCEncodedAudioFrame`. See :obj:`RTCEncodedFrameMetadata` for the common members.

    Args:
        sequence_number (:obj:`int`, optional): The RTP sequence number of a received frame.
        audio_level (:obj:`float`, optional): The audio level of the frame, from 0 (silence) to 1 (0 dBov).
    """

    sequence_number: int | None = None
    audio_level: float | None = None

    #: Alias for :attr:`sequence_number`
    sequenceNumber: ClassVar[Alias[int | None]] = alias('sequence_number')
    #: Alias for :attr:`audio_level`
    audioLevel: ClassVar[Alias[float | None]] = alias('audio_level')


@dataclass
class RTCEncodedVideoFrameOptions(Dictionary):
    """The options of the copy constructor of :obj:`RTCEncodedVideoFrame`.

    Args:
        metadata (:obj:`RTCEncodedVideoFrameMetadata`, optional): Members replacing those of the original frame,
            the ones that aren't :obj:`None`.
    """

    metadata: RTCEncodedVideoFrameMetadata | None = None

    _dictionaries: ClassVar = {'metadata': RTCEncodedVideoFrameMetadata}


@dataclass
class RTCEncodedAudioFrameOptions(Dictionary):
    """The options of the copy constructor of :obj:`RTCEncodedAudioFrame`.

    Args:
        metadata (:obj:`RTCEncodedAudioFrameMetadata`, optional): Members replacing those of the original frame,
            the ones that aren't :obj:`None`.
    """

    metadata: RTCEncodedAudioFrameMetadata | None = None

    _dictionaries: ClassVar = {'metadata': RTCEncodedAudioFrameMetadata}


_MetadataT = TypeVar('_MetadataT', bound=RTCEncodedFrameMetadata)


class _RTCEncodedFrame(Generic[_MetadataT]):
    _metadata_class: type[_MetadataT]

    _native: wrtc.RTCEncodedFrame | None
    _payload: bytearray | None
    _metadata: _MetadataT
    # the sender or receiver the frame came from (see RTCRtpScriptTransformer), 0 for a constructed frame
    _owner: int
    _counter: int
    # given up to libwebrtc by a write, like a transferred ArrayBuffer
    _detached: bool

    def _init_copy(self, original_frame: _RTCEncodedFrame[_MetadataT], metadata: _MetadataT | None) -> None:
        if not isinstance(original_frame, type(self)):
            msg = f'original_frame must be an {type(self).__name__}, not {type(original_frame).__name__}'
            raise TypeError(msg)
        if original_frame._detached:
            msg = 'The data of the original frame was written to its sender or receiver'
            raise DataCloneError(msg)
        merged = copy.deepcopy(original_frame._metadata)
        if metadata is not None:
            for field in dataclasses.fields(metadata):
                value: object = getattr(metadata, field.name)
                if value is not None:
                    setattr(merged, field.name, copy.deepcopy(value))
        self._native = None
        self._payload = bytearray(original_frame.data)
        self._metadata = merged
        self._owner = 0
        self._counter = 0
        self._detached = False

    @classmethod
    def _from_native(cls, native: wrtc.RTCEncodedFrame, owner: int, counter: int) -> Self:
        frame = cls.__new__(cls)
        values = native.getMetadata()
        frame._native = native
        frame._payload = None
        frame._metadata = cls._metadata_class.from_json(values)
        frame._owner = owner
        frame._counter = counter
        frame._detached = False
        frame._init_native(values)
        return frame

    def _init_native(self, values: dict[str, object]) -> None:
        """Takes what the metadata dataclass doesn't have from the native metadata."""

    def _detach(self) -> tuple[wrtc.RTCEncodedFrame | None, bytearray | None]:
        native, payload = self._native, self._payload
        self._native = None
        self._payload = None
        self._detached = True
        return native, payload

    @property
    def data(self) -> bytearray:
        """:obj:`bytearray`: The encoded payload, which can be changed in place or replaced.

        A :obj:`bytearray` set is used as it is, other buffers are copied. Empty once the frame is written.

        Raises:
            TypeError: If the value set isn't a contiguous buffer.
        """
        if self._payload is None:
            self._payload = bytearray(self._native.getData()) if self._native is not None else bytearray()
        return self._payload

    @data.setter
    def data(self, value: Buffer) -> None:
        if isinstance(value, bytearray):
            self._payload = value
            return
        try:
            view = memoryview(value)
        except TypeError:
            msg = f'data must be a buffer, not {type(value).__name__}'
            raise TypeError(msg) from None
        if not view.contiguous:
            msg = 'data must be a contiguous buffer'
            raise TypeError(msg)
        self._payload = bytearray(view.cast('B') if view.ndim == 1 else view.tobytes())

    def _copied_metadata(self) -> _MetadataT:
        return copy.deepcopy(self._metadata)

    def __repr__(self) -> str:
        return f'<webrtc.{type(self).__name__} object at {hex(id(self))}>'


class RTCEncodedVideoFrame(_RTCEncodedFrame[RTCEncodedVideoFrameMetadata]):
    """An encoded video frame an :obj:`webrtc.RTCRtpScriptTransformer` reads, and writes back changed or not.

    Args:
        original_frame (:obj:`RTCEncodedVideoFrame`): The frame to copy, its payload and metadata.
        options (:obj:`RTCEncodedVideoFrameOptions`, optional): Metadata replacing that of the original.

    A copy is a frame of no sender or receiver: writing it to a transformer drops it.

    Raises:
        TypeError: If ``original_frame`` isn't an :obj:`RTCEncodedVideoFrame`.
        webrtc.DataCloneError: If ``original_frame`` was written.
    """

    _metadata_class = RTCEncodedVideoFrameMetadata

    def __init__(
        self, original_frame: RTCEncodedVideoFrame, options: RTCEncodedVideoFrameOptions | None = None
    ) -> None:
        self._init_copy(original_frame, options.metadata if options is not None else None)
        self._type = original_frame._type

    @override
    def _init_native(self, values: dict[str, object]) -> None:
        self._type = EncodedVideoChunkType.key if values.get('keyFrame') is True else EncodedVideoChunkType.delta
        rid = values.get('rid')
        self._rid = rid if isinstance(rid, str) else None

    _type: EncodedVideoChunkType
    _rid: str | None = None

    @property
    def type(self) -> EncodedVideoChunkType:
        """:obj:`webrtc.EncodedVideoChunkType`: Whether it's a key frame or a delta frame."""
        return self._type

    def get_metadata(self) -> RTCEncodedVideoFrameMetadata:
        """Returns the metadata of the frame.

        Returns:
            :obj:`RTCEncodedVideoFrameMetadata`: A copy, which changing doesn't change the frame.
        """
        return self._copied_metadata()

    #: Alias for :meth:`get_metadata`
    getMetadata = get_metadata


class RTCEncodedAudioFrame(_RTCEncodedFrame[RTCEncodedAudioFrameMetadata]):
    """An encoded audio frame an :obj:`webrtc.RTCRtpScriptTransformer` reads, and writes back changed or not.

    Args:
        original_frame (:obj:`RTCEncodedAudioFrame`): The frame to copy, its payload and metadata.
        options (:obj:`RTCEncodedAudioFrameOptions`, optional): Metadata replacing that of the original.

    A copy is a frame of no sender or receiver: writing it to a transformer drops it.

    Raises:
        TypeError: If ``original_frame`` isn't an :obj:`RTCEncodedAudioFrame`.
        webrtc.DataCloneError: If ``original_frame`` was written.
    """

    _metadata_class = RTCEncodedAudioFrameMetadata

    def __init__(
        self, original_frame: RTCEncodedAudioFrame, options: RTCEncodedAudioFrameOptions | None = None
    ) -> None:
        self._init_copy(original_frame, options.metadata if options is not None else None)

    def get_metadata(self) -> RTCEncodedAudioFrameMetadata:
        """Returns the metadata of the frame.

        Returns:
            :obj:`RTCEncodedAudioFrameMetadata`: A copy, which changing doesn't change the frame.
        """
        return self._copied_metadata()

    #: Alias for :meth:`get_metadata`
    getMetadata = get_metadata
