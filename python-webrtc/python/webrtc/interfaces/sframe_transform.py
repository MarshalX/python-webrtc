#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""SFrame transforms of WebRTC Encoded Transform, which encrypt encoded frames end to end with SFrame (RFC 9605).

A key is given as the raw bytes of the RFC 9605 base key together with a key id, in place of a ``CryptoKey``. Whole
frames are encrypted ("per-frame"). Codecs whose RTP packetization parses the payload, such as H.264 and AV1, can't
be used. VP8, VP9 and Opus work.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Generic, Literal, Union, cast

from typing_extensions import Buffer, TypeVar, override

import webrtc
import wrtc
from webrtc.base import WebRTCObject
from webrtc.enums import SFrameCipherSuite, SFrameTransformErrorEventType, SFrameType
from webrtc.exceptions import InvalidRangeError, NotSupportedError
from webrtc.interfaces.rtc_rtp_script_transform import _ASSOCIATED
from webrtc.models.events import SFrameTransformErrorEvent, SFrameTransformErrorEventInit
from webrtc.models.rtc_encoded_frame import RTCEncodedAudioFrame, RTCEncodedVideoFrame
from webrtc.models.sframe_transform_options import RTCRtpSFrameEncryptorOptions, SFrameTransformOptions
from webrtc.streams import ReadableStream, TransformStream, WritableStream
from webrtc.utils.events import UniformEventTarget

if TYPE_CHECKING:
    from webrtc.streams import TransformStreamDefaultController

#: A chunk the SFrame streams take, which is an encoded frame or any buffer
SFrameInput = Union[RTCEncodedVideoFrame, RTCEncodedAudioFrame, Buffer]
#: A chunk the SFrame streams output, which is the encoded frame written or :obj:`bytes` for a buffer
SFrameChunk = Union[RTCEncodedVideoFrame, RTCEncodedAudioFrame, bytes]

_C = TypeVar('_C', bound=SFrameChunk, default=Union[RTCEncodedVideoFrame, RTCEncodedAudioFrame])

# the identifiers of the cipher suites, of RFC 9605 Section 8.1 and draft-barnes-sframe-iana-256
_CIPHER_SUITE_IDS = {suite: index + 1 for index, suite in enumerate(SFrameCipherSuite)}
_ERROR_TYPES = {
    1: SFrameTransformErrorEventType.authentication,
    2: SFrameTransformErrorEventType.key_id,
    3: SFrameTransformErrorEventType.syntax,
}
_MAX_KEY_ID = 2**64 - 1


def _key(key: Buffer) -> bytes:
    try:
        return bytes(memoryview(key))
    except TypeError:
        msg = f'key must be the bytes of the key, not {type(key).__name__}'
        raise TypeError(msg) from None


def _key_id(key_id: int) -> int:
    if isinstance(key_id, bool) or not isinstance(key_id, int):
        msg = f'key_id must be an int, not {type(key_id).__name__}'
        raise TypeError(msg)
    if not 0 <= key_id <= _MAX_KEY_ID:
        msg = 'Not a 64 bits integer'
        raise InvalidRangeError(msg)
    return key_id


def _buffer(chunk: object) -> memoryview:
    try:
        return memoryview(cast('Buffer', chunk))
    except TypeError:
        msg = f'An SFrame stream takes encoded frames and buffers, not {type(chunk).__name__}'
        raise TypeError(msg) from None


def _native(options: SFrameTransformOptions, *, encrypting: bool) -> wrtc.SFrameTransform:
    if not isinstance(options, SFrameTransformOptions):
        msg = f'options must be an SFrameTransformOptions, not {type(options).__name__}'
        raise TypeError(msg)
    return wrtc.SFrameTransform(_CIPHER_SUITE_IDS[SFrameCipherSuite(options.cipher_suite)], encrypting)


def _error_event(name: str, *args: object) -> SFrameTransformErrorEvent:
    error, key_id, frame = args
    if isinstance(frame, wrtc.RTCEncodedFrame):
        # a frame libwebrtc gave, of no transformer
        cls = RTCEncodedVideoFrame if frame.video else RTCEncodedAudioFrame
        frame = cls._from_native(frame, 0, 0)
    if not isinstance(frame, (RTCEncodedVideoFrame, RTCEncodedAudioFrame, bytes)):
        msg = f'An SFrame error is of a frame or bytes, not {type(frame).__name__}'
        raise TypeError(msg)
    error_type = _ERROR_TYPES[cast('int', error)]
    is_key_id = error_type == SFrameTransformErrorEventType.key_id
    init = SFrameTransformErrorEventInit(error_type, frame, cast('int | None', key_id) if is_key_id else None)
    return SFrameTransformErrorEvent(name, init)


class _SFrameEncryptorManager:
    __slots__ = ()

    if TYPE_CHECKING:

        @property
        def _native_obj(self) -> wrtc.SFrameTransform: ...

    async def set_encryption_key(self, key: Buffer, key_id: int) -> None:
        """Sets the key that encrypts the next frames and replaces the current one.

        The frame counter isn't reset, so setting a key again never reuses a counter with it.

        Args:
            key (:obj:`bytes`): The RFC 9605 base key, as any buffer.
            key_id (:obj:`int`): The key id sent with the frames, from 0 to 2**64 - 1.

        Raises:
            TypeError: If the key isn't a buffer, or the key id isn't an :obj:`int`.
            webrtc.InvalidRangeError: If the key id doesn't fit 64 bits.
            webrtc.InvalidModificationError: If the key can't be derived.
        """
        raw, key_id = _key(key), _key_id(key_id)
        if not self._native_obj.setEncryptionKey(raw, key_id):
            msg = 'The key can not be derived'
            raise webrtc.InvalidModificationError(msg)

    #: Alias for :meth:`set_encryption_key`
    setEncryptionKey = set_encryption_key


class _SFrameDecryptorManager:
    __slots__ = ()

    if TYPE_CHECKING:

        @property
        def _native_obj(self) -> wrtc.SFrameTransform: ...

    async def add_decryption_key(self, key: Buffer, key_id: int) -> None:
        """Adds the key that decrypts the frames of a key id. It replaces any key that has the same id.

        Args:
            key (:obj:`bytes`): The RFC 9605 base key, as any buffer.
            key_id (:obj:`int`): The key id, from 0 to 2**64 - 1.

        Raises:
            TypeError: If the key isn't a buffer, or the key id isn't an :obj:`int`.
            webrtc.InvalidRangeError: If the key id doesn't fit 64 bits.
            webrtc.InvalidModificationError: If the key can't be derived.
        """
        raw, key_id = _key(key), _key_id(key_id)
        if not self._native_obj.addDecryptionKey(raw, key_id):
            msg = 'The key can not be derived'
            raise webrtc.InvalidModificationError(msg)

    async def remove_decryption_key(self, key_id: int) -> None:
        """Removes the key of a key id. From now on, frames with that id fail with a ``keyID`` error.

        Args:
            key_id (:obj:`int`): The key id, from 0 to 2**64 - 1.

        Raises:
            TypeError: If the key id isn't an :obj:`int`.
            webrtc.InvalidRangeError: If the key id doesn't fit 64 bits.
        """
        self._native_obj.removeDecryptionKey(_key_id(key_id))

    @staticmethod
    def _create_event(name: str, *args: object) -> SFrameTransformErrorEvent:
        return _error_event(name, *args)

    #: Alias for :meth:`add_decryption_key`
    addDecryptionKey = add_decryption_key
    #: Alias for :meth:`remove_decryption_key`
    removeDecryptionKey = remove_decryption_key


class RTCRtpSFrameEncryptor(_SFrameEncryptorManager, WebRTCObject[wrtc.SFrameTransform]):
    """Encrypts the frames of a sender with SFrame, once set as its ``transform``.

    Frames are encrypted natively, off the event loop. Until a key is set, frames are dropped so none go out in
    clear.

    Args:
        options (:obj:`webrtc.RTCRtpSFrameEncryptorOptions`): The cipher suite and SFrame type.

    Raises:
        TypeError: If the options aren't :obj:`webrtc.SFrameTransformOptions`.
        webrtc.NotSupportedError: For the ``'per-packet'`` type, because SFrame RTP packetization isn't available.

    Example::

        encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions('AES_128_GCM_SHA256_128'))
        await encryptor.set_encryption_key(key, 1)
        sender.transform = encryptor
    """

    __slots__ = ()

    _class = wrtc.SFrameTransform

    def __init__(self, options: RTCRtpSFrameEncryptorOptions) -> None:
        native = _native(options, encrypting=True)
        if SFrameType(getattr(options, 'type', SFrameType.per_frame)) == SFrameType.per_packet:
            msg = 'per-packet SFrame needs the SFrame packetization of RTP, which is not supported'
            raise NotSupportedError(msg)
        super().__init__(native)

    @classmethod
    @override
    def _default_wrapper_class(cls, native: wrtc.SFrameTransform, /) -> type[WebRTCObject[wrtc.SFrameTransform]]:
        return cls if native.encrypting else RTCRtpSFrameDecryptor


class RTCRtpSFrameDecryptor(
    _SFrameDecryptorManager,
    WebRTCObject[wrtc.SFrameTransform],
    UniformEventTarget[Literal['error'], SFrameTransformErrorEvent],
):
    """Decrypts the SFrame frames of a receiver, once set as its ``transform``.

    Frames are decrypted natively, off the event loop. A frame that fails to decrypt is dropped and reported by an
    ``error`` event.

    Args:
        options (:obj:`webrtc.SFrameTransformOptions`): The cipher suite.

    Raises:
        TypeError: If the options aren't :obj:`webrtc.SFrameTransformOptions`.

    Events:
        error (:obj:`webrtc.SFrameTransformErrorEvent`): A frame didn't decrypt.
    """

    __slots__ = ()

    _class = wrtc.SFrameTransform

    def __init__(self, options: SFrameTransformOptions) -> None:
        super().__init__(_native(options, encrypting=False))
        _ = self._attach()

    @override
    def _open(self) -> bool:
        # a detached transform fires no more, even queued events
        return super()._open() and self._native_obj.state == _ASSOCIATED

    @override
    def _activity(self) -> str | None:
        if not self._open() or len(self.event_names()) == 0:
            return None
        return 'associated with handlers'


class _SFrameStreamTransformer(Generic[_C]):
    def __init__(self, stream: _SFrameStream[_C], *, encrypting: bool) -> None:
        self._stream = stream
        self._encrypting = encrypting

    def transform(self, chunk: object, controller: TransformStreamDefaultController[SFrameInput, SFrameChunk]) -> None:
        frame = chunk if isinstance(chunk, (RTCEncodedVideoFrame, RTCEncodedAudioFrame)) else None
        data = frame.data if frame is not None else _buffer(chunk)
        out = self._encrypt(data) if self._encrypting else self._decrypt(data, frame)
        if out is None:
            return
        if frame is not None:
            frame.data = bytearray(out)
            controller.enqueue(frame)
        else:
            controller.enqueue(out)

    def _encrypt(self, data: Buffer) -> bytes | None:
        return self._stream._native_obj.encrypt(data)

    def _decrypt(self, data: Buffer, frame: RTCEncodedVideoFrame | RTCEncodedAudioFrame | None) -> bytes | None:
        out, error, key_id = self._stream._native_obj.decrypt(data)
        stream = self._stream
        if out is None and isinstance(stream, SFrameDecryptorStream):
            # the event is queued, like a task
            reported = frame if frame is not None else bytes(data)
            _ = asyncio.get_running_loop().call_soon(stream._dispatch, 'error', error, key_id, reported)
        return out


class _SFrameStream(WebRTCObject[wrtc.SFrameTransform], Generic[_C]):
    """A GenericTransformStream of SFrame. Frames or buffers written to :attr:`writable` are read back transformed.

    The type parameter is its chunk type. It's encoded frames by default, to match the streams of the transformer
    it's piped between. Use ``bytes`` for buffers, as in ``SFrameEncryptorStream[bytes]``, or :obj:`SFrameChunk`
    for both.
    """

    __slots__ = ('_transform',)

    _class = wrtc.SFrameTransform

    def __init__(self, native: wrtc.SFrameTransform, *, encrypting: bool) -> None:
        super().__init__(native)
        self._transform = TransformStream[SFrameInput, SFrameChunk](
            _SFrameStreamTransformer(self, encrypting=encrypting)
        )

    @property
    def readable(self) -> ReadableStream[_C]:
        """:obj:`webrtc.ReadableStream`: The output chunks.

        Each frame written comes out with its data replaced, and each buffer comes out as :obj:`bytes`.
        """
        return cast('ReadableStream[_C]', self._transform.readable)

    @property
    def writable(self) -> WritableStream[_C | Buffer]:
        """:obj:`webrtc.WritableStream`: The input chunks.

        Takes :obj:`webrtc.RTCEncodedVideoFrame`, :obj:`webrtc.RTCEncodedAudioFrame` or any buffer. Anything else
        errors the stream with :obj:`TypeError`.
        """
        return self._transform.writable


class SFrameEncryptorStream(_SFrameEncryptorManager, _SFrameStream[_C]):
    """A transform stream that encrypts the frames or buffers written to it with SFrame.

    It has :attr:`readable` and :attr:`writable` like a :obj:`webrtc.TransformStream`, so it can be piped through in
    the worker of an :obj:`webrtc.RTCRtpScriptTransform`. A frame comes out with its data encrypted, and a buffer
    comes out as the :obj:`bytes` of the ciphertext. Until a key is set, chunks are dropped. The type parameter is
    the output type. It's encoded frames by default, and ``SFrameEncryptorStream[bytes]`` handles buffers.

    Args:
        options (:obj:`webrtc.SFrameTransformOptions`): The cipher suite.

    Raises:
        TypeError: If the options aren't :obj:`webrtc.SFrameTransformOptions`.

    Example::

        async def worker(event):
            encryptor = webrtc.SFrameEncryptorStream(webrtc.SFrameTransformOptions('AES_128_GCM_SHA256_128'))
            await encryptor.set_encryption_key(key, 1)
            transformer = event.transformer
            await transformer.readable.pipe_through(encryptor).pipe_to(transformer.writable)
    """

    __slots__ = ()

    def __init__(self, options: SFrameTransformOptions) -> None:
        super().__init__(_native(options, encrypting=True), encrypting=True)


class SFrameDecryptorStream(
    _SFrameDecryptorManager, _SFrameStream[_C], UniformEventTarget[Literal['error'], SFrameTransformErrorEvent]
):
    """A transform stream that decrypts the SFrame frames or buffers written to it.

    It has :attr:`readable` and :attr:`writable` like a :obj:`webrtc.TransformStream`. A frame comes out with its
    data decrypted, and a buffer comes out as the :obj:`bytes` of the plaintext. A chunk that fails to decrypt is
    dropped and reported by an ``error`` event. The type parameter is the output type. It's encoded frames by
    default, and ``SFrameDecryptorStream[bytes]`` handles buffers.

    Args:
        options (:obj:`webrtc.SFrameTransformOptions`): The cipher suite.

    Raises:
        TypeError: If the options aren't :obj:`webrtc.SFrameTransformOptions`.

    Events:
        error (:obj:`webrtc.SFrameTransformErrorEvent`): A chunk didn't decrypt.
    """

    __slots__ = ()

    def __init__(self, options: SFrameTransformOptions) -> None:
        super().__init__(_native(options, encrypting=False), encrypting=False)
        _ = self._attach()
