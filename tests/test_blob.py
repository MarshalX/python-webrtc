#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Blob of the File API: parts, line endings, slices and streams."""

from __future__ import annotations

import os

import pytest

import webrtc
from tests.helpers import mistyped


@pytest.mark.asyncio
async def test_blob() -> None:
    """A Blob is immutable bytes with a type, sliced like a sequence."""
    blob = webrtc.Blob(['héllo', b' ', bytearray(b'world')], webrtc.BlobPropertyBag(type='Text/Plain'))
    assert blob.size == len(bytes(blob)) == 12
    assert blob.type == 'text/plain'
    assert await blob.text() == 'héllo world'
    assert await blob.slice(-5).bytes() == b'world'
    assert await blob.slice(1, 3).array_buffer() == b'\xc3\xa9'
    assert blob.slice(0, 1, 'A/B').type == 'a/b'
    assert webrtc.Blob(options=webrtc.BlobPropertyBag(type='é')).type == ''
    assert webrtc.Blob().size == 0


def test_endings() -> None:
    """Native endings convert the line breaks of string parts only, transparent ones keep them."""
    parts: list[str | bytes] = ['a\r\nb\rc\nd', b'\r\n']
    assert bytes(webrtc.Blob(parts)) == b'a\r\nb\rc\nd\r\n'
    native = webrtc.Blob(parts, webrtc.BlobPropertyBag(endings=webrtc.EndingType.native))
    assert bytes(native) == f'a{os.linesep}b{os.linesep}c{os.linesep}d'.encode() + b'\r\n'
    with pytest.raises(ValueError, match='not a valid EndingType'):
        webrtc.Blob(['a'], webrtc.BlobPropertyBag(endings=mistyped('crlf')))


@pytest.mark.asyncio
async def test_text_drops_bom() -> None:
    """text() decodes UTF-8 as the spec does: a leading BOM is dropped, invalid bytes become U+FFFD."""
    assert await webrtc.Blob([b'\xef\xbb\xbfhi\xff']).text() == 'hi�'


@pytest.mark.asyncio
async def test_stream() -> None:
    """stream() reads the bytes in chunks, and an empty blob closes at once."""
    data = bytes(range(256)) * 1000
    stream = webrtc.Blob([data]).stream()
    assert isinstance(stream, webrtc.ReadableStream)
    chunks = [chunk async for chunk in stream]
    assert len(chunks) > 1
    assert all(isinstance(chunk, bytes) for chunk in chunks)
    assert b''.join(chunks) == data
    assert [chunk async for chunk in webrtc.Blob().stream()] == []


@pytest.mark.asyncio
async def test_text_stream() -> None:
    """textStream() decodes across chunk boundaries."""
    text = 'é' * 100_000
    stream = webrtc.Blob([text]).textStream()
    chunks = [chunk async for chunk in stream]
    assert len(chunks) > 1
    assert all(isinstance(chunk, str) for chunk in chunks)
    assert ''.join(chunks) == text
    assert [chunk async for chunk in webrtc.Blob([b'\xef\xbb\xbf']).text_stream()] == []
