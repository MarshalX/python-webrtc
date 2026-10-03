#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCRtpScriptTransform of WebRTC Encoded Transform: the encoded frames of a sender or receiver, in Python.

Python has no Workers: the worker of a transform is a function called on the event loop the transform was created on.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import weakref
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, NamedTuple, Union, cast

from typing_extensions import override

from webrtc import (
    DataCloneError,
    InvalidStateError,
    KeyFrameRequestEvent,
    NotAllowedError,
    NotFoundError,
    RTCEncodedAudioFrame,
    RTCEncodedVideoFrame,
    RTCRtpScriptTransformType,
    RTCTransformEvent,
    WebRTCObject,
    wrtc,
)
from webrtc.enums import EncodedVideoChunkType
from webrtc.models.dictionary import Dictionary
from webrtc.streams import QueuingStrategy, ReadableStream, WritableStream, _handled
from webrtc.utils.events import UniformEventTarget, _handler_tasks

if TYPE_CHECKING:
    from webrtc.enums import RTCRtpScriptTransformTypeValue
    from webrtc.streams import ReadableStreamDefaultController, WritableStreamDefaultController

#: The function a transform calls with its ``rtctransform`` event
Worker = Callable[[RTCTransformEvent], object]
EncodedFrame = Union[RTCEncodedVideoFrame, RTCEncodedAudioFrame]

# a rid of RFC 8851: alphanumeric, at most 255 characters
_RID = re.compile(r'[A-Za-z0-9]{1,255}')

# the transforms of the native ones: once disassociated, a native transform lets go of its transformer
_transforms: weakref.WeakValueDictionary[int, RTCRtpScriptTransform] = weakref.WeakValueDictionary()

_DISASSOCIATED = 2
_KEY_FRAME_INVALID_STATE, _KEY_FRAME_NOT_FOUND = 1, 2


@dataclass
class WorkerAndParameters(Dictionary):
    """The worker of an :obj:`RTCRtpScriptTransform` and how the transform packetizes frames.

    Args:
        worker (:obj:`callable`): The function called with the ``rtctransform`` event, a coroutine function too.
        type (:obj:`webrtc.RTCRtpScriptTransformType`, optional): ``'sframe'`` if the worker outputs SFrame-encrypted
            frames.

    Raises:
        TypeError: If the worker isn't callable.
        ValueError: If the type isn't a member of :obj:`webrtc.RTCRtpScriptTransformType`.
    """

    worker: Worker
    type: RTCRtpScriptTransformType | RTCRtpScriptTransformTypeValue | None = None

    def __post_init__(self) -> None:
        if not callable(self.worker):
            msg = f'worker must be callable, not {type(self.worker).__name__}'
            raise TypeError(msg)
        if self.type is not None:
            self.type = RTCRtpScriptTransformType(self.type)


class _KeyFrameRequest(NamedTuple):
    rid: str | None
    future: asyncio.Future[None]


class _FrameSource:
    """Takes frames from the native queue only for pending reads, so that queue drops the oldest when full."""

    def __init__(self, transformer: RTCRtpScriptTransformer) -> None:
        self._transformer = transformer
        self._controller: ReadableStreamDefaultController[EncodedFrame] | None = None

    def start(self, controller: ReadableStreamDefaultController[EncodedFrame]) -> None:
        self._controller = controller

    def pull(self, _controller: ReadableStreamDefaultController[EncodedFrame]) -> None:
        self._transformer._deliver()


class _FrameSink:
    def __init__(self, transformer: RTCRtpScriptTransformer) -> None:
        self._transformer = transformer

    def write(self, chunk: object, _controller: WritableStreamDefaultController[EncodedFrame]) -> None:
        self._transformer._write(chunk)


class RTCRtpScriptTransformer(UniformEventTarget[Literal['keyframerequest'], KeyFrameRequestEvent]):
    """The encoded frames of the sender or receiver of an :obj:`RTCRtpScriptTransform`, as streams.

    The worker of the transform gets it with the ``rtctransform`` event. Frames are read from :attr:`readable` and
    written to :attr:`writable` to be sent (or decoded), changed or not; frames that aren't written are dropped.
    Frames are queued until they're read, up to 120, then the oldest one is dropped.

    Events:
        ``keyframerequest`` (:obj:`webrtc.KeyFrameRequestEvent`): the remote peer asked for a key frame.
    """

    def __init__(self, transform: RTCRtpScriptTransform, options: object) -> None:
        self._transform = transform
        self._options = options
        self._source = _FrameSource(self)
        self._readable: ReadableStream[EncodedFrame] = ReadableStream(self._source, QueuingStrategy(high_water_mark=0))
        self._writable: WritableStream[EncodedFrame] = WritableStream(
            _FrameSink(self), QueuingStrategy(high_water_mark=float('inf'))
        )
        self._last_enqueued = 0
        self._last_received = 0
        self._key_frame_requests: list[_KeyFrameRequest] = []
        self._ended = False

    @property
    @override
    def _native_obj(self) -> wrtc.RTCRtpScriptTransform:
        return self._transform._native_obj

    @override
    def _on_event(self, name: str, *_args: object) -> None:
        if name == '_ready':
            self._native_obj._ackWakeup()
            self._deliver()

    def _deliver(self) -> None:
        native = self._native_obj
        stream = self._readable
        controller = self._source._controller
        if controller is None:
            return
        owner = native.sourceId
        while stream._state == 'readable' and stream._reader is not None and len(stream._reader._read_requests) > 0:
            item = native.read()
            if item is None:
                break
            self._last_enqueued += 1
            cls = RTCEncodedVideoFrame if item.video else RTCEncodedAudioFrame
            frame = cls._from_native(item, owner, self._last_enqueued)
            controller.enqueue(frame)
            # after the read it fulfills, so whoever awaits generate_key_frame() finds the frame read
            if isinstance(frame, RTCEncodedVideoFrame) and frame.type == EncodedVideoChunkType.key:
                self._key_frame_produced(frame._rid)
        if native.state == _DISASSOCIATED and not self._ended:
            self._end()

    def _end(self) -> None:
        self._ended = True
        error = InvalidStateError('The transform was removed from its sender or receiver')
        _ = _handled(self._readable._cancel(error))
        _ = _handled(self._writable._abort(error))

    def _write(self, chunk: object) -> None:
        if not isinstance(chunk, (RTCEncodedVideoFrame, RTCEncodedAudioFrame)):
            msg = f'the writable stream takes RTCEncodedVideoFrame and RTCEncodedAudioFrame, not {type(chunk).__name__}'
            raise TypeError(msg)
        # a frame of another sender or receiver, a constructed one, or one out of order is dropped
        if chunk._owner == 0 or chunk._owner != self._native_obj.sourceId:
            return
        if chunk._counter <= self._last_received:
            return
        self._last_received = chunk._counter
        native, payload = chunk._detach()
        if native is not None:
            _ = self._native_obj.write(native, payload)

    def _key_frame_produced(self, rid: str | None) -> None:
        remaining: list[_KeyFrameRequest] = []
        for request in self._key_frame_requests:
            if request.future.done():
                continue
            if request.rid is None or rid is None or request.rid == rid:
                request.future.set_result(None)
            else:
                remaining.append(request)
        self._key_frame_requests = remaining

    @property
    def readable(self) -> ReadableStream[EncodedFrame]:
        """:obj:`webrtc.ReadableStream`: The frames of the sender or receiver, encoded video or audio frames."""
        return self._readable

    @property
    def writable(self) -> WritableStream[EncodedFrame]:
        """:obj:`webrtc.WritableStream`: Takes the frames read back, to be sent or decoded.

        Frames of another transformer, copies and frames written out of order (or twice) are dropped. Anything else
        than a frame errors the stream with :obj:`TypeError`.
        """
        return self._writable

    @property
    def options(self) -> object:
        """The options of the transform, as given to it."""
        return self._options

    async def generate_key_frame(self, rid: str | None = None) -> None:
        """Asks the encoder of the sender for a key frame, done once one of the layer is read from :attr:`readable`.

        Args:
            rid (:obj:`str`, optional): The simulcast layer, any if omitted.

        Raises:
            webrtc.InvalidStateError: If the transform isn't of a video sender.
            webrtc.NotAllowedError: If the rid isn't alphanumeric, or longer than 255 characters.
            webrtc.NotFoundError: If the sender has no layer of that rid.
        """
        kind = self._native_obj.sourceKind
        if kind is None or not kind[0] or not kind[1]:
            msg = 'generate_key_frame() is for the transform of a video sender'
            raise InvalidStateError(msg)
        if rid is not None and _RID.fullmatch(rid) is None:
            msg = f'{rid!r} is not a valid rid'
            raise NotAllowedError(msg)
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        result = self._native_obj.generateKeyFrame(rid)
        if result == _KEY_FRAME_INVALID_STATE:
            msg = 'generate_key_frame() is for the transform of a video sender'
            raise InvalidStateError(msg)
        if result == _KEY_FRAME_NOT_FOUND:
            msg = f'The sender has no layer of rid {rid!r}'
            raise NotFoundError(msg)
        self._key_frame_requests.append(_KeyFrameRequest(rid, future))
        await future

    async def send_key_frame_request(self) -> None:
        """Asks the remote sender for a key frame (a picture loss indication).

        Raises:
            webrtc.InvalidStateError: If the transform isn't of a video receiver.
        """
        if not self._native_obj.sendKeyFrameRequest():
            msg = 'send_key_frame_request() is for the transform of a video receiver'
            raise InvalidStateError(msg)

    #: Alias for :meth:`generate_key_frame`
    generateKeyFrame = generate_key_frame
    #: Alias for :meth:`send_key_frame_request`
    sendKeyFrameRequest = send_key_frame_request


class RTCRtpScriptTransform(WebRTCObject[wrtc.RTCRtpScriptTransform]):
    """Transforms the encoded frames of a sender or receiver in Python, set as its ``transform``.

    The worker is called on the event loop the transform is created on, with an :obj:`webrtc.RTCTransformEvent`
    whose ``transformer`` reads and writes the frames. A coroutine function runs as a task of that loop.
    A transform is used by one sender or receiver only.

    Args:
        worker_or_worker_and_parameters (:obj:`callable` or :obj:`WorkerAndParameters`): The worker.
        options (optional): Any value, the ``options`` of the transformer.
        transfer (:obj:`list`, optional): Objects given up to the transformer. Python can't detach them, they're
            only checked to be listed once.

    Raises:
        TypeError: If the worker isn't callable, or ``transfer`` isn't a sequence.
        webrtc.DataCloneError: If an object is in ``transfer`` more than once.
        RuntimeError: If called outside of a running event loop.

    Example::

        async def worker(event):
            transformer = event.transformer
            async for frame in transformer.readable:
                frame.data = encrypt(frame.data)
                await transformer.writable.get_writer().write(frame)


        sender.transform = webrtc.RTCRtpScriptTransform(worker)
    """

    _class = wrtc.RTCRtpScriptTransform

    def __init__(
        self,
        worker_or_worker_and_parameters: Worker | WorkerAndParameters,
        options: object = None,
        transfer: Iterable[object] | None = None,
    ) -> None:
        self._type: RTCRtpScriptTransformType | None = None
        if isinstance(worker_or_worker_and_parameters, WorkerAndParameters):
            worker = worker_or_worker_and_parameters.worker
            self._type = cast('RTCRtpScriptTransformType | None', worker_or_worker_and_parameters.type)
        else:
            worker = worker_or_worker_and_parameters
        if not callable(worker):
            msg = f'the worker must be callable, not {type(worker).__name__}'
            raise TypeError(msg)
        _check_transfer(transfer)
        loop = asyncio.get_running_loop()
        super().__init__()
        self._transformer = RTCRtpScriptTransformer(self, options)
        self._transformer._attach()
        # the native object, and so its id, lives as long as this one
        _transforms[id(self._native_obj)] = self
        _ = loop.call_soon(self._fire, worker, loop)

    def _fire(self, worker: Worker, loop: asyncio.AbstractEventLoop) -> None:
        event = RTCTransformEvent('rtctransform', self._transformer)
        try:
            result = worker(event)
            if inspect.isawaitable(result):
                task = asyncio.ensure_future(result, loop=loop)
                _handler_tasks.add(task)
                task.add_done_callback(_handler_tasks.discard)
        except Exception as e:  # ruff: ignore[blind-except] # reported like the exception of a handler
            loop.call_exception_handler({
                'message': 'Exception in the worker of an RTCRtpScriptTransform',
                'exception': e,
                'event': event,
            })

    @classmethod
    def _of_native(cls, native: wrtc._RtpTransform | None) -> RTCRtpScriptTransform | None:
        """The transform of a native one, or a new wrapper once that's gone."""
        if not isinstance(native, wrtc.RTCRtpScriptTransform):
            return None
        transform = _transforms.get(id(native))
        if transform is not None and transform._native_obj is native:
            return transform
        return cls._wrap(native)


def _check_transfer(transfer: Iterable[object] | None) -> None:
    if transfer is None:
        return
    if isinstance(transfer, (str, bytes, bytearray, memoryview)) or not isinstance(transfer, Iterable):
        msg = 'transfer is a sequence of objects'
        raise TypeError(msg)
    seen: list[object] = []
    for item in transfer:
        if any(item is other for other in seen):
            msg = 'An object is in transfer more than once'
            raise DataCloneError(msg)
        seen.append(item)
