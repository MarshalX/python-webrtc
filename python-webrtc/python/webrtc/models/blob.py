#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Blob (https://developer.mozilla.org/en-US/docs/Web/API/Blob): immutable bytes with a MIME type.

Like the binary messages of a data channel with a ``binaryType`` of ``'blob'``.
"""

from __future__ import annotations

import asyncio
import codecs
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, Union

import webrtc  # the streams come after the models in the package
from webrtc import EndingType, EndingTypeValue
from webrtc.models.dictionary import Dictionary

if TYPE_CHECKING:
    import builtins
    from collections.abc import Iterable

    from webrtc.streams import ReadableStream, ReadableStreamDefaultController

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
    """How to create a :obj:`Blob`.

    Args:
        type (:obj:`str`, optional): The MIME type, lowercased; empty if it has characters outside of U+0020-U+007E.
        endings (:obj:`webrtc.EndingType`, optional): How the line endings of the string parts are written.
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

    Args:
        blob_parts (iterable, optional): Strings (encoded as UTF-8), bytes-like objects and blobs, concatenated.
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
                # lone surrogates become U+FFFD
                text = part.encode('utf-8', 'surrogatepass').decode('utf-8', 'replace')
                chunks.append((_native_endings(text) if native else text).encode())
            else:
                chunks.append(bytes(memoryview(part)))
        self._bytes = b''.join(chunks)
        self._type = _content_type(options.type)

    @property
    def size(self) -> int:
        """:obj:`int`: The number of bytes."""
        return len(self._bytes)

    @property
    def type(self) -> str:
        """:obj:`str`: The MIME type, empty if unknown."""
        return self._type

    def slice(self, start: int = 0, end: int | None = None, content_type: str = '') -> Blob:
        """Returns a blob of a range of the bytes.

        Args:
            start (:obj:`int`, optional): The first byte, counted from the end if negative.
            end (:obj:`int`, optional): The byte after the last one, counted from the end if negative.
            content_type (:obj:`str`, optional): The MIME type of the new blob.
        """
        size = len(self._bytes)
        start = max(size + start, 0) if start < 0 else min(start, size)
        end = size if end is None else (max(size + end, 0) if end < 0 else min(end, size))
        return Blob([self._bytes[start : max(start, end)]], BlobPropertyBag(type=content_type))

    def array_buffer(self) -> asyncio.Future[bytes]:
        """Returns a future of the bytes, as :obj:`bytes`."""
        return _done(self._bytes)

    def bytes(self) -> asyncio.Future[bytes]:
        """Returns a future of the bytes, as :obj:`bytes`."""
        return _done(self._bytes)

    def text(self) -> asyncio.Future[str]:
        """Returns a future of the bytes decoded as UTF-8."""
        return _done(_decode(self._bytes))

    def stream(self) -> ReadableStream[builtins.bytes]:
        """Returns a :obj:`webrtc.ReadableStream` of the bytes, in :obj:`bytes` chunks."""
        return webrtc.ReadableStream(_Source(self._bytes, text=False))

    def text_stream(self) -> ReadableStream[str]:
        """Returns a :obj:`webrtc.ReadableStream` of the bytes decoded as UTF-8, in :obj:`str` chunks."""
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
