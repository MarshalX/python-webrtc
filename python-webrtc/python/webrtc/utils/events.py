#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Event handling of WebRTC objects.

Events are delivered in order on the loop an object is bound to; handlers run on the loop they were registered from.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import threading
import typing
from typing import TYPE_CHECKING, Callable, Generic, NamedTuple, Protocol, TypeVar, cast, overload

from typing_extensions import Literal, Never, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Generator

    import wrtc

import webrtc
from webrtc.utils.loops import LoopState, checking_roots, record_mismatch, states_elsewhere

#: A handler, which is a function or a coroutine function called with the :obj:`webrtc.Event` of an event
Handler = Callable[['webrtc.Event'], object]
#: Any handler, which takes the event class of its event, like :obj:`webrtc.RTCTrackEvent`
AnyHandler = Callable[[Never], object]

#: Event names as a ``Literal``. ``EventTarget[Never]`` is any target
_N_contra = TypeVar('_N_contra', bound=str, contravariant=True)
_E = TypeVar('_E', bound='webrtc.Event')
_E_contra = TypeVar('_E_contra', bound='webrtc.Event', contravariant=True)
_R = TypeVar('_R')


class HandlerDecorator(Protocol[_E_contra]):
    """The decorator returned by ``on()`` and ``once()`` without a handler, which registers the decorated one."""

    def __call__(self, handler: Callable[[_E_contra], _R], /) -> Callable[[_E_contra], _R]:
        """Registers the handler and returns it unchanged."""
        ...


def call_handler(loop: asyncio.AbstractEventLoop, handler: Callable[[_E], object], event: _E, *, message: str) -> None:
    """Calls a handler; exceptions, async ones too, go to the loop's exception handler."""

    def report(exception: BaseException) -> None:
        loop.call_exception_handler({'message': message, 'exception': exception, 'event': event})

    def done(task: asyncio.Future[object]) -> None:
        tasks.discard(task)
        if not task.cancelled() and (exception := task.exception()) is not None:
            report(exception)

    try:
        result = handler(event)
    except Exception as e:
        report(e)
        return
    if inspect.isawaitable(result):
        task = asyncio.ensure_future(result, loop=loop)
        # strong ref until done, or the task could be collected
        tasks = LoopState.of(loop).tasks
        tasks.add(task)
        task.add_done_callback(done)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# guards lazy creation of an object's handler table
_handlers_lock = threading.Lock()


class _Registration(NamedTuple):
    handler: Handler
    loop: asyncio.AbstractEventLoop
    once: bool


class _Handlers:
    """An object's handlers by event name, each with its registering loop."""

    __slots__ = ('_lock', '_registrations')

    def __init__(self) -> None:
        self._registrations: dict[str, list[_Registration]] = {}
        # re-entrant: gc may release a loop under it, which removes handlers
        self._lock = threading.RLock()

    def add(self, name: str, handler: Handler, loop: asyncio.AbstractEventLoop, *, once: bool) -> None:
        with self._lock:
            registrations = self._registrations.setdefault(name, [])
            if any(r.handler == handler for r in registrations):
                return  # registered once, per addEventListener
            registrations.append(_Registration(handler, loop, once))
            # re-stored: a loop released under the lock may have dropped the emptied list
            self._registrations[name] = registrations

    def remove(self, name: str | None, handler: AnyHandler | None) -> None:
        """Removes a handler of an event, every handler of it, or every handler of every event."""
        with self._lock:
            for each in list(self._registrations) if name is None else [name]:
                self._keep(each, lambda r: handler is not None and r.handler != handler)

    def remove_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Removes the handlers registered from a loop."""
        with self._lock:
            for name in list(self._registrations):
                self._keep(name, lambda r: r.loop is not loop)

    def _keep(self, name: str, keep: Callable[[_Registration], bool]) -> None:
        """Drops unkept registrations in place, so a nested removal sees it."""
        registrations = self._registrations.get(name)
        if registrations is None:
            return
        for registration in list(registrations):
            if not keep(registration):
                _discard(registrations, registration)
        if len(registrations) == 0:
            _ = self._registrations.pop(name, None)

    def has(self, name: str, registration: _Registration) -> bool:
        with self._lock:
            return any(r is registration for r in self._registrations.get(name, ()))

    def for_loop(self, name: str, loop: asyncio.AbstractEventLoop) -> list[_Registration]:
        """An event's handlers registered from a loop, in order."""
        with self._lock:
            return [r for r in self._registrations.get(name, ()) if r.loop is loop]

    def loops(self, name: str) -> list[asyncio.AbstractEventLoop]:
        """The loops with a handler of an event."""
        with self._lock:
            return list(dict.fromkeys(r.loop for r in self._registrations.get(name, ())))

    def of(self, name: str) -> list[AnyHandler]:
        with self._lock:
            return [r.handler for r in self._registrations.get(name, ())]

    def names(self) -> set[str]:
        with self._lock:
            return {name for name, registrations in self._registrations.items() if len(registrations) > 0}


def _discard(registrations: list[_Registration], registration: _Registration) -> None:
    """Removes a registration by identity without allocating, so gc can't interleave."""
    for i in range(len(registrations)):
        if registrations[i] is registration:
            del registrations[i]
            return


def _handler_names(registrations: list[_Registration]) -> str:
    return ', '.join(getattr(r.handler, '__qualname__', repr(r.handler)) for r in registrations)


def _roots_of(loop: asyncio.AbstractEventLoop | None) -> LoopState | None:
    """The loop's state if the loop is open."""
    return LoopState.of(loop) if loop is not None and not loop.is_closed() else None


def _check_handled(
    target: EventTarget[Never], name: str, registrations: list[_Registration], *, roots: LoopState, generation: int
) -> None:
    """Asserts an object about to run handlers is rooted or active."""
    if not target._rootable:
        # its events come from the code holding it, e.g. SFrame stream writes
        return
    with roots._lock:
        rooted = target in roots.active
    if rooted or target._activity() is not None:
        return
    with roots._lock:
        # raced a change on another thread; the next check sees it settled
        if roots.changes > 0 or roots.generation != generation:
            return
    msg = (
        f'{type(target).__name__} is neither rooted nor active while {name!r} is handled by '
        f'{_handler_names(registrations)}'
    )
    record_mismatch(msg)
    raise AssertionError(msg)


class _Bound(Protocol):
    """A native object with events, bound to a loop's mailbox."""

    def _bind(self, mailbox: wrtc.Mailbox) -> bool: ...

    @property
    def _bound(self) -> bool: ...

    @property
    def _mailbox(self) -> int | None: ...


class EventTarget(Generic[_N_contra]):
    """The base class of objects that emit events.

    Handlers are registered with ``on()`` or ``once()`` by event name, from a running asyncio event loop, and are
    called on that loop with one event object. They can be functions or coroutine functions, and a coroutine is run as a
    task. An exception in a handler goes to the exception handler of the loop, and doesn't stop the other handlers. A
    handler registered twice for an event is called once.

    An object with handlers stays alive while it can still fire them; handlers go when their loop closes.

    See :mdn:`EventTarget`.

    Example::

        @pc.on('icecandidate')
        async def on_candidate(event):
            await signaling.send(event.candidate)


        pc.on('track', lambda event: print(event.track))
    """

    __slots__ = ()

    #: Event names, from the ``Literal`` parameter
    _events: tuple[str, ...] = ()
    #: whether the class overrides :meth:`_activity`
    _rootable: bool = False
    #: a slot of the classes mixing this in
    _handlers: _Handlers | None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls._rootable = cls._activity is not EventTarget._activity
        for base in cast('tuple[object, ...]', cls.__dict__.get('__orig_bases__', ())):
            names = _literal_names(get_args(base)[0]) if _is_target_base(base) else ()
            if len(names) > 0:
                cls._events = names

    if TYPE_CHECKING:

        @property
        def _native_obj(self) -> _Bound: ...

    @property
    def _connection(self) -> webrtc.RTCPeerConnection | None:
        """The parent connection, if any."""
        return None

    def _state(self) -> LoopState | None:
        """The bound loop's state while it's open."""
        return LoopState.find(self._native_obj._mailbox)

    def _loop(self) -> asyncio.AbstractEventLoop | None:
        """The bound loop, if any."""
        state = self._state()
        return state.loop if state is not None else None

    def _attach(self) -> bool:
        """Binds the object and its connection to the running loop; the first binding wins until released."""
        loop = _running_loop()
        if loop is None:
            return False
        connection = self._connection
        if connection is not None:
            _ = connection._attach()
        bound = self._native_obj._bind(LoopState.of(loop).mailbox)
        if bound:
            self._update(loop)
        return bound

    @staticmethod
    def _activity() -> str | None:
        """Why the object is kept alive while unreferenced, or None."""
        return None

    def _open(self) -> bool:
        """Whether the parent connection, if any, isn't closed."""
        connection = self._connection
        return connection is None or not connection._is_closed()

    def _update(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Re-evaluates the object's root; ``loop`` covers a native object that dropped its binding."""
        if loop is None:
            loop = self._loop()
        if loop is None:
            loop = _running_loop()
        state = _roots_of(loop)
        if state is not None:
            state.update(self)

    @contextlib.contextmanager
    def _changing(self) -> Generator[None, None, None]:
        """Wraps a call that changes the object's activity, then updates its root."""
        # read before the call: the native object may drop its binding
        loop = self._loop()
        # root checks on other threads wait until the call is over
        states = states_elsewhere()
        for state in states:
            state.changing(1)
        try:
            yield
        finally:
            self._update(loop)
            for state in states:
                state.changing(-1)

    def _released(self, loop: asyncio.AbstractEventLoop) -> None:
        """Drops a released loop's handlers and updates the root."""
        handlers = self._handlers
        if handlers is not None:
            handlers.remove_loop(loop)
        state = self._state()
        if state is not None:
            state.update(self)

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
        loop = _running_loop()
        if loop is None:
            msg = 'event handlers must be registered from a running asyncio event loop'
            raise RuntimeError(msg)
        with self._changing():
            _ = self._attach()
            self._handler_table().add(name, cast('Handler', handler), loop, once=once)
        # the handler's loop removes it on release; the bound loop checks roots
        for state in (LoopState.of(loop), self._state()):
            if state is not None:
                state.remember(self)
        return handler

    def _handler_table(self) -> _Handlers:
        """The handler table, created on first use."""
        handlers = self._handlers
        if handlers is None:
            with _handlers_lock:
                handlers = self._handlers
                if handlers is None:
                    handlers = self._handlers = _Handlers()
        return handlers

    def _dispatch(self, name: str, *args: object) -> None:
        """Delivers an event to the handlers on the running loop right away, from an event being delivered."""
        state = LoopState.of(asyncio.get_running_loop())
        binding = self._state()
        primary = binding is None or binding is state
        self._deliver(state, name, args, primary=primary)
        if primary:
            state.update(self)

    def _deliver(self, state: LoopState, name: str, args: tuple[object, ...], *, primary: bool = True) -> None:
        """Delivers an event on a loop; the bound (primary) loop also updates state and forwards to other loops."""
        if primary:
            self._on_event(name, *args)
        handlers = self._handlers
        if handlers is None:
            return
        loop = state.loop
        registrations = handlers.for_loop(name, loop)
        # read before _open(), so the check can detect a racing change
        generation = state.generation
        event = self._create_event(name, *args) if len(registrations) > 0 and self._open() else None
        if event is not None:
            if primary and checking_roots():
                _check_handled(self, name, registrations, roots=state, generation=generation)
            self._call(loop, name, event, registrations=registrations)
        if primary:
            self._forward(handlers, name, args, delivering=loop)

    def _forward(
        self, handlers: _Handlers, name: str, args: tuple[object, ...], *, delivering: asyncio.AbstractEventLoop
    ) -> None:
        """Posts an event to the other loops with handlers for it."""
        for other in handlers.loops(name):
            if other is not delivering and not other.is_closed():
                elsewhere = LoopState.of(other)
                elsewhere.post(functools.partial(self._deliver, elsewhere, name, args, primary=False))

    def _call(
        self, loop: asyncio.AbstractEventLoop, name: str, event: webrtc.Event, *, registrations: list[_Registration]
    ) -> None:
        event.target = self
        handlers = self._handlers
        for registration in registrations:
            if handlers is None or not handlers.has(name, registration):
                continue
            if registration.once:
                handlers.remove(name, registration.handler)
                self._update()
            call_handler(loop, registration.handler, event, message=f'Exception in {name!r} event handler')

    def _on_event(self, name: str, *args: object) -> None:
        """Called for every event on the bound loop, before its handlers.

        Names starting with ``_`` (like ``'_sent'``) are internal events of the native object. They only reach this
        method and never reach handlers.
        """

    @staticmethod
    def _create_event(name: str, *_args: object) -> webrtc.Event | None:
        """Creates the event object from the native arguments of an event, or returns :obj:`None` to drop it."""
        return webrtc.Event(name)

    def off(self, name: _N_contra | None = None, handler: AnyHandler | None = None) -> None:
        """Removes one handler or all of them, for one event or for all events.

        See :mdn:`EventTarget/removeEventListener`.

        Args:
            name (:obj:`str`, optional): The name of the event. If omitted, every event.
            handler (:obj:`callable`, optional): The handler to remove. If omitted, every handler.

        Raises:
            ValueError: If the object has no such event.
        """
        if name is not None:
            self._check_event(name)
        handlers = self._handlers
        if handlers is not None:
            with self._changing():
                handlers.remove(name, handler)

    def remove_listener(self, name: _N_contra, handler: AnyHandler) -> None:
        """Removes a handler of an event. Removing one that isn't registered does nothing.

        See :mdn:`EventTarget/removeEventListener`.

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
        """Returns the handlers of an event, in the order they were registered.

        Args:
            name (:obj:`str`): The name of the event.

        Returns:
            :obj:`list` of :obj:`callable`: The handlers.

        Raises:
            ValueError: If the object has no such event.
        """
        self._check_event(name)
        handlers = self._handlers
        return handlers.of(name) if handlers is not None else []

    def event_names(self) -> set[str]:
        """Returns the names of the events that have handlers.

        Returns:
            :obj:`set` of :obj:`str`: The names.
        """
        handlers = self._handlers
        return handlers.names() if handlers is not None else set()


# distinct objects before Python 3.10
_LITERALS = (typing.Literal, Literal)


def _literal_names(literal: object) -> tuple[str, ...]:
    """The strings of a possibly nested ``Literal``."""
    if get_origin(literal) not in _LITERALS:
        return ()
    names: list[str] = []
    for arg in cast('tuple[object, ...]', get_args(literal)):
        names.extend(_literal_names(arg) if get_origin(arg) in _LITERALS else [arg] if isinstance(arg, str) else [])
    return tuple(dict.fromkeys(names))


def _is_target_base(base: object) -> bool:
    """Whether a base is a parametrized :obj:`EventTarget`."""
    origin = get_origin(base)
    return isinstance(origin, type) and issubclass(origin, EventTarget)


class UniformEventTarget(EventTarget[_N_contra], Generic[_N_contra, _E]):
    """An :obj:`EventTarget` whose events all have the same event class, which typed handlers take."""

    __slots__ = ()

    @overload
    def on(self, name: _N_contra, handler: None = None) -> HandlerDecorator[_E]: ...

    @overload
    def on(self, name: _N_contra, handler: Callable[[_E], _R]) -> Callable[[_E], _R]: ...

    def on(self, name: _N_contra, handler: Callable[[_E], _R] | None = None) -> object:
        """Registers a handler of an event. Can be used as a decorator.

        See :mdn:`EventTarget/addEventListener`.

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
        """Registers a handler that is removed before its first call. Can be used as a decorator.

        See :mdn:`EventTarget/addEventListener`.

        Args:
            name (:obj:`str`): The name of the event.
            handler (:obj:`callable`, optional): A function or a coroutine function called with the event object.
                If omitted, a decorator is returned.

        Returns:
            :obj:`callable`: The handler, or a decorator registering it.

        Raises:
            ValueError: If the object has no such event.
            RuntimeError: If called outside of a running event loop.
        """
        return self._add(name, handler, once=True)
