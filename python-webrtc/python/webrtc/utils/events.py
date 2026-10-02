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
from typing import TYPE_CHECKING, Callable, Generic, NamedTuple, Protocol, TypeVar, cast, overload

from typing_extensions import Literal, Never, get_args, get_origin

import webrtc
from webrtc.utils.task_queue import TaskQueue

Handler = Callable[['webrtc.Event'], object]
# any one-argument callable: a handler takes the event subclass of its event, like RTCTrackEvent
AnyHandler = Callable[[Never], object]

#: Event names, a ``Literal``; ``EventTarget[Never]`` is any target
_N_contra = TypeVar('_N_contra', bound=str, contravariant=True)
_E = TypeVar('_E', bound='webrtc.Event')
_E_contra = TypeVar('_E_contra', bound='webrtc.Event', contravariant=True)
_R = TypeVar('_R')


class HandlerDecorator(Protocol[_E_contra]):
    """Registers the decorated handler."""

    def __call__(self, handler: Callable[[_E_contra], _R], /) -> Callable[[_E_contra], _R]:
        """Registers the handler."""
        ...


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

    def __init__(self, target: EventTarget[Never]) -> None:
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
        if 'registrations' not in self.__dict__:
            # the garbage collector cleared this object since the event was posted
            return
        if loop is self.primary_loop:
            self.target._on_event(name, *args)
        registrations = [r for r in self.registrations.get(name, ()) if r.loop is loop]
        if len(registrations) == 0:
            return
        event = self.target._create_event(name, *args)
        if event is None:
            return
        event.target = self.target
        self._call(loop, name, event, registrations=registrations)

    def _call(
        self, loop: asyncio.AbstractEventLoop, name: str, event: webrtc.Event, *, registrations: list[_Registration]
    ) -> None:
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

    def remove(self, name: str | None, handler: AnyHandler | None) -> None:
        # replaced, not mutated: libwebrtc threads read it
        names = list(self.registrations) if name is None else [name]
        registrations = dict(self.registrations)
        for each in names:
            kept = [r for r in registrations.get(each, ()) if handler is not None and r.handler != handler]
            if len(kept) > 0:
                registrations[each] = kept
            else:
                _ = registrations.pop(each, None)
        self.registrations = registrations


class _NativeEventTarget(Protocol):
    """A native object that emits events, through the listeners it holds."""

    _listeners: _Listeners | None


class EventTarget(Generic[_N_contra]):
    """Mixin of :obj:`webrtc.WebRTCObject` subclasses that emit events.

    Handlers are called with one event object, on the event loop they were registered from.
    They can be plain functions or coroutine functions.

    Example::

        @pc.on('icecandidate')
        async def on_candidate(event):
            await signaling.send(event.candidate)


        pc.on('track', lambda event: print(event.track))
    """

    #: Event names, from the ``Literal`` parameter
    _events: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        for base in cast('tuple[object, ...]', cls.__dict__.get('__orig_bases__', ())):
            names = _literal_names(get_args(base)[0]) if _is_target_base(base) else ()
            if len(names) > 0:
                cls._events = names

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

    def _add(self, name: str, handler: AnyHandler | None, *, once: bool) -> object:
        """Registers a handler, or returns a decorator."""
        self._check_event(name)
        if handler is None:

            def decorator(func: AnyHandler) -> AnyHandler:
                return self._add_handler(name, func, once=once)

            return decorator
        return self._add_handler(name, handler, once=once)

    def _add_handler(self, name: str, handler: AnyHandler, *, once: bool) -> AnyHandler:
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

    def off(self, name: _N_contra | None = None, handler: AnyHandler | None = None) -> None:
        """Removes handlers.

        Args:
            name (:obj:`str`, optional): The name of the event. If omitted, every event.
            handler (:obj:`callable`, optional): The handler to remove. If omitted, every handler.

        Raises:
            ValueError: If the object has no such event.
        """
        if name is not None:
            self._check_event(name)
        listeners = self._listeners()
        if listeners is not None:
            listeners.remove(name, handler)

    def remove_listener(self, name: _N_contra, handler: AnyHandler) -> None:
        """Removes a handler of an event.

        Args:
            name (:obj:`str`): The name of the event.
            handler (:obj:`callable`): The handler to remove.

        Raises:
            ValueError: If the object has no such event.
        """
        self.off(name, handler)

    def remove_all_listeners(self, name: _N_contra | None = None) -> None:
        """Removes every handler of an event, or of all events.

        Args:
            name (:obj:`str`, optional): The name of the event. If omitted, every event.

        Raises:
            ValueError: If the object has no such event.
        """
        self.off(name)

    def listeners(self, name: _N_contra) -> list[AnyHandler]:
        """Returns the handlers of an event.

        Args:
            name (:obj:`str`): The name of the event.

        Raises:
            ValueError: If the object has no such event.
        """
        self._check_event(name)
        listeners = self._listeners()
        if listeners is None:
            return []
        return [r.handler for r in listeners.registrations.get(name, ())]

    def event_names(self) -> set[str]:
        """Returns the names of the events that have handlers."""
        listeners = self._listeners()
        if listeners is None:
            return set()
        return {name for name, registrations in listeners.registrations.items() if len(registrations) > 0}


def _literal_names(literal: object) -> tuple[str, ...]:
    """The strings of a possibly nested ``Literal``."""
    if get_origin(literal) is not Literal:
        return ()
    names: list[str] = []
    for arg in cast('tuple[object, ...]', get_args(literal)):
        names.extend(_literal_names(arg) if get_origin(arg) is Literal else [arg] if isinstance(arg, str) else [])
    return tuple(dict.fromkeys(names))


def _is_target_base(base: object) -> bool:
    """Whether a base is a parametrized :obj:`EventTarget`."""
    origin = get_origin(base)
    return isinstance(origin, type) and issubclass(origin, EventTarget)


class UniformEventTarget(EventTarget[_N_contra], Generic[_N_contra, _E]):
    """An :obj:`EventTarget` whose events share one event class."""

    @overload
    def on(self, name: _N_contra, handler: None = None) -> HandlerDecorator[_E]: ...

    @overload
    def on(self, name: _N_contra, handler: Callable[[_E], _R]) -> Callable[[_E], _R]: ...

    def on(self, name: _N_contra, handler: Callable[[_E], _R] | None = None) -> object:
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
    def once(self, name: _N_contra, handler: None = None) -> HandlerDecorator[_E]: ...

    @overload
    def once(self, name: _N_contra, handler: Callable[[_E], _R]) -> Callable[[_E], _R]: ...

    def once(self, name: _N_contra, handler: Callable[[_E], _R] | None = None) -> object:
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
