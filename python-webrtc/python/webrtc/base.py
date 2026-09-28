#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from abc import ABCMeta
from typing import List


class WebRTCObject(metaclass=ABCMeta):
    _class = None

    def __init__(self, native_obj=None):
        self.__obj = native_obj
        if not self.__obj:
            self.__obj = self._class()

    @property
    def _native_obj(self):
        return self.__obj

    def _set_native_obj(self, value):
        self.__obj = value

    @classmethod
    def _wrap(cls, item) -> 'WebRTCObject':
        obj = cls(item)
        # an object that emits events delivers them to the loop that has it (see EventTarget._attach)
        attach = getattr(obj, '_attach', None)
        if attach is not None:
            attach()
        return obj

    @classmethod
    def _wrap_many(cls, items) -> List['WebRTCObject']:
        return [cls._wrap(item) for item in items]

    def __repr__(self):
        return f'<webrtc.{self.__class__.__name__} object at {hex(id(self))}'

    def __eq__(self, other):
        if isinstance(other, WebRTCObject):
            return id(self._native_obj) == id(other._native_obj)

        return super().__eq__(other)
