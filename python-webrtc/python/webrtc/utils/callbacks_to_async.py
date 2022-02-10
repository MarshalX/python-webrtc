#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio

from .convert_exceptions import convert_from_callback_exception_to_exception


class _ThreadSafeEvent(asyncio.Event):
    def __init__(self):
        self.loop = asyncio.events.get_running_loop()
        super().__init__()

    def set(self):
        self.loop.call_soon_threadsafe(super().set)


class _AsyncWrapper:
    def __init__(self, func: callable):
        self.__event = _ThreadSafeEvent()
        self.__func = func

        self.__args_for_run = []
        self.__kwargs_for_run = {}

        self.__result = self.__error = None

    def set(self):
        self.__event.set()

    def _on_success(self, result=None):  # TODO many results mb
        self.__result = result
        self.set()

    def _on_failure(self, error):
        self.__error = error
        self.set()

    async def run(self, timeout=10):
        self.__func(self._on_success, self._on_failure, *self.__args_for_run, **self.__kwargs_for_run)
        await asyncio.wait_for(self.__event.wait(), timeout)

        if self.__error:
            raise convert_from_callback_exception_to_exception(self.__error)

        return self.__result

    def __call__(self, *args, **kwargs):
        self.__args_for_run = args
        self.__kwargs_for_run = kwargs

        return self

    def __await__(self):
        return self.run().__await__()


to_async = _AsyncWrapper
