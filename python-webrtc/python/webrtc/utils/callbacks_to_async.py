#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

import asyncio

from webrtc.utils.task_queue import TaskQueue


class _QueuedEvent(asyncio.Event):
    """An :obj:`asyncio.Event` set from any thread through the task queue of its loop, so the code awaiting the
    result of an operation runs after the handlers of the events libwebrtc emitted before completing it."""

    def __init__(self):
        self.loop = asyncio.get_running_loop()
        super().__init__()

    def set(self):
        TaskQueue.of(self.loop).post(super().set, resumes=True, after_ready=True)


class _AsyncWrapper:
    def __init__(self, func: callable):
        self.__event = _QueuedEvent()
        self.__func = func

        self.__args_for_run = []
        self.__kwargs_for_run = {}

        self.__result = self.__error = None

    def set(self):
        self.__event.set()

    def _on_success(self, result=None):
        self.__result = result
        self.set()

    def _on_failure(self, error):
        self.__error = error
        self.set()

    async def run(self, timeout=10):
        self.__func(self._on_success, self._on_failure, *self.__args_for_run, **self.__kwargs_for_run)
        await asyncio.wait_for(self.__event.wait(), timeout)

        if self.__error:
            # an RTCCallbackException
            raise self.__error.toPython()

        return self.__result

    def __call__(self, *args, **kwargs):
        self.__args_for_run = args
        self.__kwargs_for_run = kwargs

        return self

    def __await__(self):
        return self.run().__await__()


to_async = _AsyncWrapper
