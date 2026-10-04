#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Immutable bytes with a MIME type.

A data channel delivers binary messages as blobs when its binary type is ``'blob'``.
"""

from __future__ import annotations

import asyncio
import codecs
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, Union

import webrtc  # the streams come after the models in the package
from webrtc.enums import EndingType, EndingTypeValue
from webrtc.models.dictionary import Dictionary
from webrtc.utils.strings import usv_string

if TYPE_CHECKING:
    import builtins
    from collections.abc import Iterable

    from webrtc.streams import ReadableStream, ReadableStreamDefaultController

#: A part of a new :obj:`Blob`. It can be a :obj:`str`, a bytes-like object or another :obj:`Blob`.
BlobPart = Union[str, bytes, bytearray, memoryview, 'Blob']
_T = TypeVar('_T')

# the printable ASCII range of a MIME type
_MIN_TYPE_CHAR = 0x20
_MAX_TYPE_CHAR = 0x7E
# the bytes a stream of a blob reads at once
_CHUNK_SIZE = 65536


def _done(value: _T) -> asyncio.Future[_T]:
    future = asyncio.get_running_loop().create_future()
    future.set_result(value)
    return future


def _content_type(value: str) -> str:
    """The type of a blob: lowercased, or empty if it has characters outside of U+0020-U+007E."""
    value = str(value)
    return value.lower() if all(_MIN_TYPE_CHAR <= ord(c) <= _MAX_TYPE_CHAR for c in value) else ''


def _native_endings(text: str) -> str:
    """Converts every CR LF, CR and LF to the line ending of the platform."""
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', os.linesep)


def _decode(data: builtins.bytes) -> str:
    # UTF-8 decode: a leading BOM is dropped and invalid bytes become U+FFFD
    return data.decode('utf-8-sig', 'replace')


@dataclass
class BlobPropertyBag(Dictionary):
    """The options of a new :obj:`Blob`.

    See :mdn:`Blob/Blob`.

    Args:
        type (:obj:`str`, optional): The MIME type. The blob lowercases it, or leaves it empty if it has characters
            outside of U+0020 to U+007E.
        endings (:obj:`webrtc.EndingType`, optional): How the line endings of the :obj:`str` parts are written.
            The default is ``'transparent'``, which keeps them as they are.
    """

    type: str = ''
    endings: EndingType | EndingTypeValue = EndingType.transparent


class _Source:
    """The underlying source of a stream of a blob, which reads it a chunk at a time."""

    def __init__(self, data: builtins.bytes, *, text: bool) -> None:
        self._data = data
        self._offset = 0
        self._decoder = codecs.getincrementaldecoder('utf-8-sig')('replace') if text else None

    def pull(self, controller: ReadableStreamDefaultController[bytes | str]) -> None:
        chunk = self._data[self._offset : self._offset + _CHUNK_SIZE]
        self._offset += len(chunk)
        final = self._offset >= len(self._data)
        if self._decoder is None:
            if len(chunk) > 0:
                controller.enqueue(chunk)
        else:
            text = self._decoder.decode(chunk, final=final)
            if text != '':
                controller.enqueue(text)
        if final:
            controller.close()


class Blob:
    """Immutable bytes with a MIME type.

    The bytes are held in memory. ``bytes(blob)`` and ``len(blob)`` give the bytes and their number, and blobs with
    the same bytes and type are equal. The reading methods return futures that are already done, so they must be
    called while an event loop runs.

    See :mdn:`Blob`.

    Args:
        blob_parts (iterable of :obj:`BlobPart`, optional): The parts, concatenated. A :obj:`str` is encoded as UTF-8,
            with lone surrogates replaced by U+FFFD.
        options (:obj:`BlobPropertyBag`, optional): The MIME type, and how the line endings of strings are written.
    """

    def __init__(self, blob_parts: Iterable[BlobPart] | None = None, options: BlobPropertyBag | None = None) -> None:
        if options is None:
            options = BlobPropertyBag()
        native = EndingType(options.endings) == EndingType.native
        chunks: list[builtins.bytes] = []
        for part in blob_parts if blob_parts is not None else ():
            if isinstance(part, Blob):
                chunks.append(part._bytes)
            elif isinstance(part, str):
                text = usv_string(part)
                chunks.append((_native_endings(text) if native else text).encode())
            else:
                chunks.append(bytes(memoryview(part)))
        self._bytes = b''.join(chunks)
        self._type = _content_type(options.type)

    @property
    def size(self) -> int:
        """:obj:`int`: The number of bytes.

        See :mdn:`Blob/size`.
        """
        return len(self._bytes)

    @property
    def type(self) -> str:
        """:obj:`str`: The MIME type in lowercase, empty if unknown.

        See :mdn:`Blob/type`.
        """
        return self._type

    def slice(self, start: int = 0, end: int | None = None, content_type: str = '') -> Blob:
        """Returns a new blob with a range of the bytes. Indices out of range are clamped.

        See :mdn:`Blob/slice`.

        Args:
            start (:obj:`int`, optional): The index of the first byte, counted from the end if negative.
            end (:obj:`int`, optional): The index after the last byte, counted from the end if negative. The end of
                the blob by default.
            content_type (:obj:`str`, optional): The MIME type of the new blob, empty by default.

        Returns:
            :obj:`Blob`: The new blob.
        """
        size = len(self._bytes)
        start = max(size + start, 0) if start < 0 else min(start, size)
        end = size if end is None else (max(size + end, 0) if end < 0 else min(end, size))
        return Blob([self._bytes[start : max(start, end)]], BlobPropertyBag(type=content_type))

    def array_buffer(self) -> asyncio.Future[bytes]:
        """Reads the bytes. They come as :obj:`bytes`, where the specification gives an array buffer.

        See :mdn:`Blob/arrayBuffer`.

        Returns:
            :obj:`asyncio.Future` of :obj:`bytes`: The bytes, already done.
        """
        return _done(self._bytes)

    def bytes(self) -> asyncio.Future[bytes]:
        """Reads the bytes. They come as :obj:`bytes`, where the specification gives a byte array.

        See :mdn:`Blob/bytes`.

        Returns:
            :obj:`asyncio.Future` of :obj:`bytes`: The bytes, already done.
        """
        return _done(self._bytes)

    def text(self) -> asyncio.Future[str]:
        """Reads the bytes decoded as UTF-8. A leading BOM is dropped, and invalid bytes become U+FFFD.

        See :mdn:`Blob/text`.

        Returns:
            :obj:`asyncio.Future` of :obj:`str`: The text, already done.
        """
        return _done(_decode(self._bytes))

    def stream(self) -> ReadableStream[builtins.bytes]:
        """Returns a stream of the bytes, in :obj:`bytes` chunks of up to 64 KiB.

        See :mdn:`Blob/stream`.

        Returns:
            :obj:`webrtc.ReadableStream` of :obj:`bytes`: The stream.
        """
        return webrtc.ReadableStream(_Source(self._bytes, text=False))

    def text_stream(self) -> ReadableStream[str]:
        """Returns a stream of :obj:`str` chunks, decoded from the bytes the same way :meth:`text` does.

        See :mdn:`Blob/textStream`.

        Returns:
            :obj:`webrtc.ReadableStream` of :obj:`str`: The stream.
        """
        return webrtc.ReadableStream(_Source(self._bytes, text=True))

    # the bytes() method hides the builtin in the class
    def __bytes__(self) -> builtins.bytes:
        return self._bytes

    def __len__(self) -> int:
        return len(self._bytes)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Blob):
            return self._bytes == other._bytes and self._type == other._type
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._bytes, self._type))

    def __repr__(self) -> str:
        return f'<webrtc.Blob size={self.size} type={self._type!r}>'

    #: Alias for :meth:`array_buffer`
    arrayBuffer = array_buffer
    #: Alias for :meth:`text_stream`
    textStream = text_stream
