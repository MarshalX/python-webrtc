#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import List

from abc import ABCMeta


class WebRTCObject(object, metaclass=ABCMeta):
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
        return cls(item)

    @classmethod
    def _wrap_many(cls, items) -> List['WebRTCObject']:
        return [cls(item) for item in items]

    def __repr__(self):
        return f'<webrtc.{self.__class__.__name__} object at {hex(id(self))}'

    def __eq__(self, other):
        if isinstance(other, WebRTCObject):
            return id(self._native_obj) == id(other._native_obj)

        return super().__eq__(other)
