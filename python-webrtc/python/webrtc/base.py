#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The base class of objects that wrap a native WebRTC object."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Self

_NativeT = TypeVar('_NativeT')


class WebRTCObject(Generic[_NativeT]):
    """The base class of the objects that wrap a native object.

    Two wrappers are equal, and hash the same, when they wrap the same native object, so a sender returned twice
    compares equal to itself.

    Args:
        native_obj (optional): The native object to wrap. If omitted, a new one of the native class is created.

    Raises:
        TypeError: If ``native_obj`` is omitted and the class has no native class.
    """

    #: The native class, created with no arguments when no native object is given
    _class: Callable[..., _NativeT] | None = None
    __obj: _NativeT

    def __init__(self, native_obj: _NativeT | None = None) -> None:
        self._init_native(native_obj)

    def _init_native(self, native_obj: _NativeT | None) -> None:
        if native_obj is None:
            if self._class is None:
                msg = f'{type(self).__name__} has no native class'
                raise TypeError(msg)
            native_obj = self._class()
        self.__obj = native_obj

    @property
    def _native_obj(self) -> _NativeT:
        return self.__obj

    @classmethod
    def _wrap(cls, item: _NativeT) -> Self:
        """The wrapper of a native object. It skips the constructor, which takes the public arguments."""
        obj = cls.__new__(cls)
        obj._init_native(item)
        if isinstance(obj, EventTarget):
            obj._attach()
        return obj

    @classmethod
    def _wrap_optional(cls, item: _NativeT | None) -> Self | None:
        """The wrapper of a native object, or :obj:`None` for :obj:`None`."""
        return cls._wrap(item) if item is not None else None

    @classmethod
    def _wrap_many(cls, items: Iterable[_NativeT]) -> list[Self]:
        return [cls._wrap(item) for item in items]

    def __repr__(self) -> str:
        return f'<webrtc.{self.__class__.__name__} object at {hex(id(self))}'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, WebRTCObject):
            other_obj: object = other._native_obj
            return self._native_obj is other_obj
        return NotImplemented

    def __hash__(self) -> int:
        return id(self._native_obj)
