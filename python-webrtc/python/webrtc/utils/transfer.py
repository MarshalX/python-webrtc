#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The ``transfer`` member of the WebCodecs inits: buffers given up to the created object.

Python can't detach a buffer the way JS detaches an ``ArrayBuffer``: transferred :obj:`memoryview` objects are released,
and other buffers are only promised not to be used anymore.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from webrtc.exceptions import DataCloneError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing_extensions import Buffer


class Transfer:
    """The validated buffers of a ``transfer`` member, by the object that owns their memory."""

    def __init__(self, transfer: Sequence[Buffer]) -> None:
        if isinstance(transfer, (str, bytes, bytearray, memoryview)):
            msg = 'transfer is a sequence of buffers'
            raise TypeError(msg)
        self._views: list[memoryview] = []
        for item in transfer:
            try:
                view = memoryview(item)
            except TypeError:
                msg = f'transfer takes buffers, not {type(item).__name__}'
                raise TypeError(msg) from None
            except ValueError:
                # a released memoryview is the detached buffer of Python
                msg = 'A buffer in transfer is released'
                raise DataCloneError(msg) from None
            if self.has(view):
                msg = 'A buffer is in transfer more than once'
                raise DataCloneError(msg)
            self._views.append(view)
        self._items = list(transfer)

    def has(self, data: Buffer) -> bool:
        """Whether the memory of a buffer is transferred, which the created object may then keep without copying."""
        owner = memoryview(data).obj
        return any(view.obj is owner for view in self._views)

    def detach(self) -> None:
        """Releases the transferred memoryviews, once the object is created."""
        for view in self._views:
            view.release()
        for item in self._items:
            if isinstance(item, memoryview):
                with contextlib.suppress(BufferError):  # views of it are exported, like to numpy
                    item.release()
