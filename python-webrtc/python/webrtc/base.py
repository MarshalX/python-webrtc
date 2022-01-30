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
