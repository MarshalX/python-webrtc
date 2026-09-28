#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The camelCase names of the WebRTC specification next to the snake_case ones of the library."""

import re
from typing import Any

_CAMEL = re.compile(r'_([a-z0-9])')


def camel_case(name: str) -> str:
    """``'bytes_sent'`` -> ``'bytesSent'``."""
    return _CAMEL.sub(lambda match: match.group(1).upper(), name)


def snake_case(name: str) -> str:
    """``'namedCurve'`` -> ``'named_curve'``."""
    return ''.join(f'_{c.lower()}' if c.isupper() else c for c in name)


class alias:
    """A camelCase alias of an instance attribute, like a dataclass field: ``maxBitrate = alias('max_bitrate')``.

    It isn't a field itself, so ``__init__``, ``repr()``, ``==`` and :obj:`dataclasses.asdict` don't see it.
    Setting it sets the attribute, which a frozen dataclass doesn't allow.
    """

    def __init__(self, name: str):
        self.name = name
        self.__doc__ = f'Alias for :attr:`{name}`'

    def __get__(self, obj: Any, owner: Any = None) -> Any:
        return self if obj is None else getattr(obj, self.name)

    def __set__(self, obj: Any, value: Any) -> None:
        setattr(obj, self.name, value)
