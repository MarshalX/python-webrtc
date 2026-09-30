#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Objects holding memory until closed, like media."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import Self


class Closable(ABC):
    """An object holding memory until :meth:`close`, which is called on leaving a ``with`` block too."""

    @abstractmethod
    def close(self) -> None:
        """Releases the memory. Closing a closed object does nothing."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
