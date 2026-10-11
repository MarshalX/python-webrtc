#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""One Python wrapper per native object, keyed by its native id."""

from __future__ import annotations

import threading
import weakref
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

if TYPE_CHECKING:
    from webrtc.base import WebRTCObject

_N = TypeVar('_N')


class Native(Protocol):
    """A native object with an id that's never reused."""

    @property
    def _id(self) -> int: ...


#: live wrappers by native id
wrappers: weakref.WeakValueDictionary[int, WebRTCObject[object]] = weakref.WeakValueDictionary()
_lock = threading.Lock()
_classes: dict[type, type[WebRTCObject[object]]] = {}


def register(native_cls: type[_N], wrapper_cls: type[WebRTCObject[_N]]) -> None:
    """Registers the wrapper class of a native class; the first registration wins."""
    with _lock:
        _ = _classes.setdefault(native_cls, cast('type[WebRTCObject[object]]', wrapper_cls))


def adopt(wrapper: WebRTCObject[_N]) -> None:
    """Makes a newly constructed wrapper the one of its native object."""
    native = cast('Native', wrapper._native_obj)
    with _lock:
        wrappers[native._id] = cast('WebRTCObject[object]', wrapper)


def find(native: Native) -> WebRTCObject[object] | None:
    """Returns the live wrapper of a native object, or None."""
    with _lock:
        return wrappers.get(native._id)


def wrap(cls: type[WebRTCObject[_N]], native: _N) -> WebRTCObject[_N]:
    """Returns the live wrapper of a native object, or a new ``cls`` one that skips its constructor."""
    key = cast('Native', native)._id
    with _lock:
        wrapper = wrappers.get(key)
        if wrapper is None:
            # under the lock so racing threads get one wrapper; nothing native runs here
            created = object.__new__(cls)
            created._init_native(native)
            wrapper = wrappers[key] = cast('WebRTCObject[object]', created)
    return cast('WebRTCObject[_N]', wrapper)


def wrapper_of(native: Native) -> WebRTCObject[object]:
    """Returns the wrapper of a native object, creating one of its registered class."""
    with _lock:
        wrapper = wrappers.get(native._id)
        registered = _classes.get(type(native))
    if wrapper is not None:
        return wrapper
    if registered is None:
        msg = f'no wrapper class is registered for {type(native).__name__}'
        raise TypeError(msg)
    return wrap(registered._default_wrapper_class(native), native)


def alive() -> list[WebRTCObject[object]]:
    """Returns the live wrappers."""
    with _lock:
        refs = wrappers.valuerefs()
    return [wrapper for ref in refs if (wrapper := ref()) is not None]
