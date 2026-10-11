#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The base class of objects that wrap a native WebRTC object."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, ClassVar, Generic, TypeVar, cast

from webrtc.utils import lifetime
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Never, Self

    import webrtc
    from webrtc.utils.events import _Handlers

_NativeT = TypeVar('_NativeT')


class WebRTCObject(Generic[_NativeT]):
    """The base class of the objects that wrap a native object.

    A native object has one wrapper at a time, the same object wherever it's returned from.

    Args:
        native_obj (optional): The native object to wrap. If omitted, a new one of the native class is created.

    Raises:
        TypeError: If ``native_obj`` is omitted and the class has no native class.
    """

    __slots__ = ('_WebRTCObject__connection', '_WebRTCObject__obj', '__weakref__', '_handlers')

    #: The native class, created with no arguments when no native object is given
    _class: Callable[..., _NativeT] | None = None
    #: one wrapper per native object; value-like classes compare by value instead
    _canonical: ClassVar[bool] = True
    __obj: _NativeT
    __connection: webrtc.RTCPeerConnection | None
    _handlers: _Handlers | None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if cls._canonical and isinstance(cls._class, type):
            lifetime.register(cls._class, cls)

    def __init__(self, native_obj: _NativeT | None = None) -> None:
        self._init_native(native_obj)
        if self._canonical:
            lifetime.adopt(self)

    def _init_native(self, native_obj: _NativeT | None) -> None:
        if native_obj is None:
            if self._class is None:
                msg = f'{type(self).__name__} has no native class'
                raise TypeError(msg)
            native_obj = self._class()
        self.__obj = native_obj
        self.__connection = None
        self._handlers = None

    @property
    def _native_obj(self) -> _NativeT:
        return self.__obj

    @property
    def _connection(self) -> webrtc.RTCPeerConnection | None:
        """The parent connection, which the object keeps alive per spec."""
        return self.__connection

    @_connection.setter
    def _connection(self, connection: webrtc.RTCPeerConnection | None) -> None:
        self.__connection = connection

    def _target(self) -> EventTarget[Never] | None:
        """The object the native events reach."""
        return self if isinstance(self, EventTarget) else None

    @classmethod
    def _default_wrapper_class(cls, _native: _NativeT, /) -> type[WebRTCObject[_NativeT]]:
        """The class of a new wrapper for an unwrapped native object."""
        return cls

    @classmethod
    def _wrap(cls, item: _NativeT, *, connection: webrtc.RTCPeerConnection | None = None) -> Self:
        """The wrapper of a native object, skipping the public constructor."""
        if cls._canonical:
            obj = cast('Self', lifetime.wrap(cls, item))
        else:
            obj = cls.__new__(cls)
            obj._init_native(item)
        if connection is not None and obj._connection is None:
            obj._connection = connection
        if isinstance(obj, EventTarget):
            _ = obj._attach()
        elif connection is not None:
            _ = connection._attach()
        return obj

    @classmethod
    def _wrap_optional(
        cls, item: _NativeT | None, *, connection: webrtc.RTCPeerConnection | None = None
    ) -> Self | None:
        """The wrapper of a native object, or :obj:`None` for :obj:`None`."""
        return cls._wrap(item, connection=connection) if item is not None else None

    @classmethod
    def _wrap_many(cls, items: Iterable[_NativeT], *, connection: webrtc.RTCPeerConnection | None = None) -> list[Self]:
        return [cls._wrap(item, connection=connection) for item in items]

    def __repr__(self) -> str:
        return f'<webrtc.{self.__class__.__name__} object at {hex(id(self))}>'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, WebRTCObject):
            other_obj: object = other._native_obj
            return self._native_obj is other_obj
        return NotImplemented

    def __hash__(self) -> int:
        return id(self._native_obj)
