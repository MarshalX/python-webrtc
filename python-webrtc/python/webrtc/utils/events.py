#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Events of WebRTC objects. libwebrtc threads only schedule them: handlers run on their event loop."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Callable, NamedTuple, Protocol, TypeVar, cast, overload

from typing_extensions import Never

import webrtc
from webrtc.utils.task_queue import TaskQueue

Handler = Callable[['webrtc.Event'], object]
# any one-argument callable: a handler takes the event subclass of its event, like RTCTrackEvent
_H = TypeVar('_H', bound=Callable[[Never], object])

#: The tasks of the coroutine handlers, referenced until they're done
_handler_tasks: set[asyncio.Future[object]] = set()


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class _Registration(NamedTuple):
    handler: Handler
    loop: asyncio.AbstractEventLoop
    once: bool


class _Listeners:
    """Handlers of one native object, called by it with the name and the native arguments of an event."""

    def __init__(self, target: EventTarget) -> None:
        self.target = target
        self.registrations: dict[str, list[_Registration]] = {}
        # the loop of the first handler, which delivers every event, even without handlers for it,
        # as events also update what the object shows (see EventTarget._on_event)
        self.primary_loop: asyncio.AbstractEventLoop | None = None

    def __call__(self, name: str, *args: object) -> None:
        # a libwebrtc thread, with the GIL held: only schedule
        registrations: dict[str, list[_Registration]] | None = self.__dict__.get('registrations')
        if registrations is None:
            # the garbage collector cleared this object (in a cycle with its target) before the native one let go
            return
        primary_loop = self.primary_loop
        if primary_loop is not None and primary_loop.is_closed():
            # used from another loop since (like another asyncio.run): a handler's open loop takes over, on copies
            primary_loop = self.primary_loop = next(
                (r.loop for regs in list(registrations.values()) for r in list(regs) if not r.loop.is_closed()), None
            )
        loops: list[asyncio.AbstractEventLoop] = [primary_loop] if primary_loop is not None else []
        for registration in registrations.get(name, ()):
            if registration.loop not in loops:
                loops.append(registration.loop)
        for loop in loops:
            if not loop.is_closed():
                TaskQueue.of(loop).post(self.deliver, loop, name, args)

    def ensure_primary_loop(self) -> asyncio.AbstractEventLoop | None:
        """Makes the running loop the primary one if there's none yet. Returns the running loop, if any."""
        loop = _running_loop()
        if loop is not None and (self.primary_loop is None or self.primary_loop.is_closed()):
            self.primary_loop = loop
        return loop

    def deliver(self, loop: asyncio.AbstractEventLoop, name: str, args: tuple[object, ...]) -> None:
        if loop is self.primary_loop:
            self.target._on_event(name, *args)
        registrations = [r for r in self.registrations.get(name, ()) if r.loop is loop]
        if len(registrations) == 0:
            return
        event = self.target._create_event(name, *args)
        if event is None:
            return
        event.target = self.target

        for registration in registrations:
            if registration.once:
                self.remove(name, registration.handler)
            try:
                result = registration.handler(event)
                if inspect.isawaitable(result):
                    task = asyncio.ensure_future(result, loop=loop)
                    _handler_tasks.add(task)
                    task.add_done_callback(_handler_tasks.discard)
            except Exception as e:
                loop.call_exception_handler({
                    'message': f'Exception in {name!r} event handler',
                    'exception': e,
                    'event': event,
                })

    def add(self, name: str, handler: Handler, *, once: bool) -> None:
        loop = self.ensure_primary_loop()
        if loop is None:
            msg = 'event handlers must be registered from a running asyncio event loop'
            raise RuntimeError(msg)

        registrations = self.registrations.setdefault(name, [])
        if any(r.handler == handler for r in registrations):
            return  # like addEventListener, a handler is registered once
        registrations.append(_Registration(handler, loop, once))

    def remove(self, name: str, handler: Callable[[Never], object] | None) -> None:
        if handler is None:
            _ = self.registrations.pop(name, None)
            return
        registrations = self.registrations.get(name, [])
        self.registrations[name] = [r for r in registrations if r.handler != handler]


class _NativeEventTarget(Protocol):
    """A native object that emits events, through the listeners it holds."""

    _listeners: _Listeners | None


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
    _events: tuple[str, ...] = ()

    if TYPE_CHECKING:

        @property
        def _native_obj(self) -> _NativeEventTarget: ...

    def _listeners(self) -> _Listeners | None:
        return self._native_obj._listeners

    def _created_listeners(self) -> _Listeners:
        native = self._native_obj
        listeners = native._listeners
        if listeners is None:
            listeners = _Listeners(self)
            # before the native object gets it: it delivers the events it held right away
            _ = listeners.ensure_primary_loop()
            native._listeners = listeners
        return listeners

    def _attach(self) -> None:
        """Delivers the events of the object to the running loop from now on, even without handlers.

        Events also update what the object shows (like its state, see :meth:`_on_event`). Does nothing outside of
        a loop.
        """
        if _running_loop() is not None:
            _ = self._created_listeners().ensure_primary_loop()

    def _check_event(self, name: str) -> None:
        if name not in self._events:
            msg = f'{type(self).__name__} has no event {name!r}, its events are: {", ".join(self._events)}'
            raise ValueError(msg)

    def _add(self, name: str, handler: _H | None, *, once: bool) -> _H | Callable[[_H], _H]:
        self._check_event(name)
        if handler is None:
            return lambda func: self._add_handler(name, func, once=once)
        return self._add_handler(name, handler, once=once)

    def _add_handler(self, name: str, handler: _H, *, once: bool) -> _H:
        # the handler takes the event of its name, which only the native object knows
        self._created_listeners().add(name, cast('Handler', handler), once=once)
        return handler

    def _dispatch(self, name: str, *args: object) -> None:
        """Delivers an event to the handlers on the running loop right away, from an event being delivered."""
        listeners = self._listeners()
        if listeners is not None:
            listeners.deliver(asyncio.get_running_loop(), name, args)

    def _on_event(self, name: str, *args: object) -> None:
        """Called for every event on the loop of the first handler, before the handlers of the event.

        Names starting with ``_`` (like ``'_sent'``) are internal events of the native object: they only reach this
        method, never handlers.
        """

    @staticmethod
    def _create_event(name: str, *_args: object) -> webrtc.Event | None:
        """Creates the event object from the native arguments of an event, or returns :obj:`None` to drop it."""
        return webrtc.Event(name)

    @overload
    def on(self, name: str, handler: None = None) -> Callable[[_H], _H]: ...

    @overload
    def on(self, name: str, handler: _H) -> _H: ...

    def on(self, name: str, handler: _H | None = None) -> _H | Callable[[_H], _H]:
        """Registers a handler of an event. Can be used as a decorator.

        Args:
            name (:obj:`str`): The name of the event, like ``'icecandidate'``.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.
                If omitted, a decorator is returned.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            ValueError: If the object has no such event.
            RuntimeError: If called outside of a running event loop.
        """
        return self._add(name, handler, once=False)

    @overload
    def once(self, name: str, handler: None = None) -> Callable[[_H], _H]: ...

    @overload
    def once(self, name: str, handler: _H) -> _H: ...

    def once(self, name: str, handler: _H | None = None) -> _H | Callable[[_H], _H]:
        """Registers a handler that is removed after it's called for the first time. Can be used as a decorator.

        Args:
            name (:obj:`str`): The name of the event.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            ValueError: If the object has no such event.
            RuntimeError: If called outside of a running event loop.
        """
        return self._add(name, handler, once=True)

    def off(self, name: str, handler: Callable[[Never], object] | None = None) -> None:
        """Removes a handler of an event, or every handler of the event.

        Args:
            name (:obj:`str`): The name of the event.
            handler (:obj:`callable`, optional): The handler to remove. If omitted, all handlers of the event are.

        Raises:
            ValueError: If the object has no such event.
        """
        self._check_event(name)
        listeners = self._listeners()
        if listeners is not None:
            listeners.remove(name, handler)
