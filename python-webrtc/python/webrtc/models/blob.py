#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Blob (https://developer.mozilla.org/en-US/docs/Web/API/Blob): immutable bytes with a MIME type.

Like the binary messages of a data channel with a ``binaryType`` of ``'blob'``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar, Union

if TYPE_CHECKING:
    import builtins
    from collections.abc import Iterable

BlobPart = Union[str, bytes, bytearray, memoryview, 'Blob']
_T = TypeVar('_T')

# the printable ASCII range of a MIME type
_MIN_TYPE_CHAR = 0x20
_MAX_TYPE_CHAR = 0x7E


def _done(value: _T) -> asyncio.Future[_T]:
    future = asyncio.get_running_loop().create_future()
    future.set_result(value)
    return future


class Blob:
    """Immutable bytes with a MIME type.

    Args:
        parts (iterable, optional): Strings (encoded as UTF-8), bytes-like objects and blobs, concatenated.
        type (:obj:`str`, optional): The MIME type, lowercased; empty if it has characters outside of U+0020-U+007E.
    """

    def __init__(self, parts: Iterable[BlobPart] | None = None, type: str = '') -> None:
        chunks: list[bytes] = []
        for part in parts if parts is not None else ():
            if isinstance(part, Blob):
                chunks.append(part._bytes)
            elif isinstance(part, str):
                # lone surrogates become U+FFFD
                chunks.append(part.encode('utf-8', 'surrogatepass').decode('utf-8', 'replace').encode())
            else:
                chunks.append(bytes(memoryview(part)))
        self._bytes = b''.join(chunks)
        type = str(type)
        self._type = type.lower() if all(_MIN_TYPE_CHAR <= ord(c) <= _MAX_TYPE_CHAR for c in type) else ''

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
        return Blob([self._bytes[start : max(start, end)]], content_type)

    def array_buffer(self) -> asyncio.Future[bytes]:
        """Returns a future of the bytes, as :obj:`bytes`."""
        return _done(self._bytes)

    def bytes(self) -> asyncio.Future[bytes]:
        """Returns a future of the bytes, as :obj:`bytes`."""
        return _done(self._bytes)

    def text(self) -> asyncio.Future[str]:
        """Returns a future of the bytes decoded as UTF-8."""
        return _done(self._bytes.decode('utf-8', 'replace'))

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
