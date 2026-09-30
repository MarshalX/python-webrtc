#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The camelCase names of the WebRTC specification next to the snake_case ones of the library."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_CAMEL = re.compile(r'_([a-z0-9])')
_T = TypeVar('_T')


def camel_case(name: str) -> str:
    """``'bytes_sent'`` -> ``'bytesSent'``."""
    return _CAMEL.sub(lambda match: match.group(1).upper(), name)


def snake_case(name: str) -> str:
    """``'namedCurve'`` -> ``'named_curve'``."""
    return ''.join(f'_{c.lower()}' if c.isupper() else c for c in name)


def members(value: Mapping[str, Any], names: Iterable[str]) -> dict[str, Any]:
    """The members of a dictionary, with snake_case or camelCase names: unknown ones are ignored, as in WebIDL."""
    wanted = set(names)
    return {snake_case(name): member for name, member in value.items() if snake_case(name) in wanted}


class Alias(Generic[_T]):
    """A camelCase alias of an instance attribute, like a dataclass field: ``maxBitrate = alias('max_bitrate')``.

    It isn't a field itself, so ``__init__``, ``repr()``, ``==`` and :obj:`dataclasses.asdict` don't see it.
    Setting it sets the attribute, which a frozen dataclass doesn't allow.

    Args:
        name (:obj:`str`): The name of the attribute.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.__doc__ = f'Alias for :attr:`{name}`'

    @overload
    def __get__(self, obj: None, owner: type | None = None) -> Alias[_T]: ...

    @overload
    def __get__(self, obj: object, owner: type | None = None) -> _T: ...

    def __get__(self, obj: object, owner: type | None = None) -> Alias[_T] | _T:
        return self if obj is None else getattr(obj, self.name)

    def __set__(self, obj: object, value: _T) -> None:
        setattr(obj, self.name, value)


def alias(name: str) -> Alias[Any]:
    """The :obj:`Alias` of an attribute, like :func:`dataclasses.field` for a field.

    Args:
        name (:obj:`str`): The name of the attribute.

    Returns:
        :obj:`Alias`: The alias.
    """
    return Alias(name)
