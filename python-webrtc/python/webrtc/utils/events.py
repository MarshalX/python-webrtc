#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Events of WebRTC objects.

libwebrtc reports events on its own threads. The native wrapper passes them to a :class:`_Listeners` object with
the GIL held, which schedules delivery on the event loop of every handler (with ``loop.call_soon_threadsafe``,
through :obj:`webrtc.utils.task_queue.TaskQueue`, which keeps events and results of operations in order).
No handler ever runs on a libwebrtc thread.

The listeners object is kept by the native wrapper, so handlers stay registered as long as the libwebrtc object
lives, even when no Python wrapper of it exists at the moment (like event listeners in a browser).
"""

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple

from webrtc.utils.task_queue import TaskQueue

Handler = Callable[[Any], Any]


class _Registration:
    __slots__ = ('handler', 'loop', 'once')

    def __init__(self, handler: Handler, loop: asyncio.AbstractEventLoop, once: bool):
        self.handler = handler
        self.loop = loop
        self.once = once


class _Listeners:
    """Handlers of one native object, called by it with the name and the native arguments of an event"""

    def __init__(self, target: 'EventTarget'):
        self.target = target
        self.registrations: Dict[str, List[_Registration]] = {}
        # the loop of the first handler, which delivers every event, even without handlers for it,
        # as events also update what the object shows (see EventTarget._on_event)
        self.primary_loop: Optional[asyncio.AbstractEventLoop] = None

    def __call__(self, name: str, *args):
        # a libwebrtc thread, with the GIL held: only schedule
        loops = [self.primary_loop] if self.primary_loop else []
        for registration in self.registrations.get(name, ()):
            if registration.loop not in loops:
                loops.append(registration.loop)
        for loop in loops:
            if not loop.is_closed():
                TaskQueue.of(loop).post(self._deliver, loop, name, args)

    def _deliver(self, loop: asyncio.AbstractEventLoop, name: str, args: Tuple):
        if loop is self.primary_loop:
            self.target._on_event(name, *args)
        registrations = [r for r in self.registrations.get(name, ()) if r.loop is loop]
        if not registrations:
            return
        event = self.target._create_event(name, *args)
        if event is None:
            return

        for registration in registrations:
            if registration.once:
                self.remove(name, registration.handler)
            try:
                result = registration.handler(event)
                if inspect.isawaitable(result):
                    loop.create_task(_await(result))
            except Exception as e:
                loop.call_exception_handler(
                    {'message': f'Exception in {name!r} event handler', 'exception': e, 'event': event}
                )

    def add(self, name: str, handler: Handler, once: bool):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError('event handlers must be registered from a running asyncio event loop') from None

        if self.primary_loop is None:
            self.primary_loop = loop
        registrations = self.registrations.setdefault(name, [])
        if any(r.handler == handler for r in registrations):
            return  # like addEventListener, a handler is registered once
        registrations.append(_Registration(handler, loop, once))

    def remove(self, name: str, handler: Optional[Handler]) -> None:
        if handler is None:
            self.registrations.pop(name, None)
            return
        registrations = self.registrations.get(name, [])
        self.registrations[name] = [r for r in registrations if r.handler != handler]


async def _await(awaitable):
    return await awaitable


class EventTarget:
    """Mixin of :obj:`webrtc.WebRTCObject` subclasses that emit events.

    Handlers are called with one event object, on the event loop they were registered from.
    They can be plain functions or coroutine functions.

    Example::

        @pc.on('icecandidate')
        async def on_candidate(event):
            await signaling.send(event.candidate)

        pc.on('track', lambda event: print(event.track))
    """

    #: Names of the events the object emits
    _events: Tuple[str, ...] = ()

    def _listeners(self, create: bool) -> Optional[_Listeners]:
        native = self._native_obj
        listeners = native._listeners
        if listeners is None and create:
            listeners = _Listeners(self)
            try:
                # before the native object gets it: it delivers the events it held right away
                listeners.primary_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            native._listeners = listeners
        return listeners

    def _attach(self) -> None:
        """Delivers the events of the object to the running loop from now on, even without handlers, as they also
        update what the object shows (like its state, see :meth:`_on_event`). Does nothing outside of a loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        listeners = self._listeners(create=True)
        if listeners.primary_loop is None:
            listeners.primary_loop = loop

    def _check_event(self, name: str):
        if name not in self._events:
            raise ValueError(f'{type(self).__name__} has no event {name!r}, its events are: {", ".join(self._events)}')

    def on(self, name: str, handler: Optional[Handler] = None):
        """Registers a handler of an event. Can be used as a decorator.

        Args:
            name (:obj:`str`): The name of the event, like ``'icecandidate'``.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.
                If omitted, a decorator is returned.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            :obj:`ValueError`: If the object has no such event.
            :obj:`RuntimeError`: If called outside of a running event loop.
        """
        self._check_event(name)
        if handler is None:
            return lambda func: self.on(name, func)
        self._listeners(create=True).add(name, handler, once=False)
        return handler

    def once(self, name: str, handler: Optional[Handler] = None):
        """Registers a handler that is removed after it's called for the first time. Can be used as a decorator.

        Args:
            name (:obj:`str`): The name of the event.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            :obj:`ValueError`: If the object has no such event.
            :obj:`RuntimeError`: If called outside of a running event loop.
        """
        self._check_event(name)
        if handler is None:
            return lambda func: self.once(name, func)
        self._listeners(create=True).add(name, handler, once=True)
        return handler

    def off(self, name: str, handler: Optional[Handler] = None) -> None:
        """Removes a handler of an event, or every handler of the event.

        Args:
            name (:obj:`str`): The name of the event.
            handler (:obj:`callable`, optional): The handler to remove. If omitted, all handlers of the event are.

        Raises:
            :obj:`ValueError`: If the object has no such event.
        """
        self._check_event(name)
        listeners = self._listeners(create=False)
        if listeners is not None:
            listeners.remove(name, handler)

    def _dispatch(self, name: str, *args) -> None:
        """Delivers an event to the handlers on the running loop right away, from an event being delivered"""
        listeners = self._listeners(create=False)
        if listeners is not None:
            listeners._deliver(asyncio.get_running_loop(), name, args)

    def _on_event(self, name: str, *args) -> None:
        """Called for every event on the loop of the first handler, before the handlers of the event"""

    def _create_event(self, name: str, *args):
        """Creates the event object from the native arguments of an event, or returns :obj:`None` to drop it"""
        from webrtc import Event

        return Event(name, self)
