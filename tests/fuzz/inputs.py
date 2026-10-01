#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Values for the fuzz targets, drawn from the fuzzer's bytes and biased to the edges where checks go wrong."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, TypeVar, Union

import atheris

if TYPE_CHECKING:
    from collections.abc import Iterable

T = TypeVar('T')
Buffer = Union[bytes, bytearray, memoryview]

# where sizes overflow: 16, 24 (the native limit of a frame side), 31, 32 and 64 bits
EDGES = [0, 1, 2, 3, 4, 7, 8, 15, 16, 255, 256, 2**16 - 1, 2**16, 2**24, 2**24 + 1, 2**31 - 1, 2**31]
EDGES += [2**32 - 1, 2**32, 2**32 + 1, 2**63 - 1, 2**63, 2**64 - 1, 2**64, 2**65]
FLOATS = [0.0, -0.0, 0.5, 1.5, -1.0, 1e-300, 1e300, float('inf'), float('-inf'), float('nan')]
# the source buffers of Input.buffer: a copy, strided views and a 2D view
VIEWS: list[Callable[[bytes], Buffer]] = [
    bytearray,
    lambda data: memoryview(bytearray(data * 2))[::2],
    lambda data: memoryview(bytearray(data))[::-1],
    lambda data: memoryview(bytearray(data)).cast('B', [len(data), 1]) if len(data) > 0 else memoryview(bytearray()),
]


class Input:
    """The fuzzer's bytes as values."""

    def __init__(self, data: bytes) -> None:
        self._fdp = atheris.FuzzedDataProvider(data)

    def flag(self) -> bool:
        return self._fdp.ConsumeBool()

    def choice(self, values: Iterable[T]) -> T:
        return self._fdp.PickValueInList(list(values))

    def small(self, limit: int = 64) -> int:
        return self._fdp.ConsumeIntInRange(0, limit)

    def unsigned(self, limit: int = 64) -> int:
        """Mostly small, sometimes an edge."""
        mode = self._fdp.ConsumeIntInRange(0, 7)
        if mode == 0:
            return self.choice(EDGES)
        if mode == 1:
            return self._fdp.ConsumeIntInRange(0, 2**64 - 1)
        return self.small(limit)

    def integer(self, limit: int = 64) -> object:
        """An unsigned value, a negative one, or something that isn't an integer."""
        mode = self._fdp.ConsumeIntInRange(0, 15)
        if mode == 0:
            return -self.unsigned(limit) - 1
        if mode == 1:
            return self.number()
        if mode == 2:
            return self.choice([None, True, '1', b'1'])
        return self.unsigned(limit)

    def number(self, limit: int = 64) -> float:
        mode = self._fdp.ConsumeIntInRange(0, 3)
        if mode == 0:
            return self.choice(FLOATS)
        if mode == 1:
            return self.small(limit) + self.choice([0, 0, 0.5, 1e-9])
        return self.small(limit)

    def maybe(self, make: Callable[[], T]) -> T | None:
        return make() if self.flag() else None

    def buffer(self, size: int) -> Buffer:
        """Size bytes as bytes, a bytearray, or a view of one, which may be strided."""
        data = self._fdp.ConsumeBytes(size)
        data += bytes(size - len(data))
        kind = self._fdp.ConsumeIntInRange(0, 7)
        return VIEWS[kind](data) if kind < len(VIEWS) else data

    def destination(self, size: int) -> Buffer:
        """A writable buffer of about size bytes."""
        size = max(0, size + self.choice([0, 0, 0, -1, 1, 64]))
        kind = self._fdp.ConsumeIntInRange(0, 7)
        if kind == 0:
            return memoryview(bytearray(size * 2))[::2]
        if kind == 1:
            return memoryview(bytearray(size))[::-1]
        if kind == 2:
            return bytes(size)
        return bytearray(size)
