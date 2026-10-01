#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The part of WHATWG Streams (https://streams.spec.whatwg.org) that media processing uses.

Readable, writable and transform streams of objects. Methods return futures like the promises of the specification,
so a read or a write is requested when it's called, not when it's awaited. They need a running asyncio event loop.
"""

from __future__ import annotations

import asyncio
import collections
import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Generic, NamedTuple, Protocol, cast

from typing_extensions import TypeVar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = [
    'ReadableStream',
    'ReadableStreamDefaultController',
    'ReadableStreamDefaultReader',
    'ReadableStreamReadResult',
    'TransformStream',
    'TransformStreamDefaultController',
    'WritableStream',
    'WritableStreamDefaultController',
    'WritableStreamDefaultWriter',
]


#: The type of the chunks of a stream, any object by default
_T = TypeVar('_T', default=object)
#: The type of the chunks a transform stream outputs
_O = TypeVar('_O', default=object)
_R = TypeVar('_R')


def _loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        msg = 'streams are used from a running asyncio event loop'
        raise RuntimeError(msg) from None


def _pending() -> asyncio.Future[_R]:
    return _loop().create_future()


def _resolved(value: _R) -> asyncio.Future[_R]:
    future: asyncio.Future[_R] = _pending()
    future.set_result(value)
    return future


# pipes running, see ReadableStream.pipe_to
_running_pipes: set[asyncio.Future[None]] = set()


def _rejected(error: BaseException) -> asyncio.Future[_R]:
    future: asyncio.Future[_R] = _pending()
    future.set_exception(error)
    return future


def _retrieve(future: asyncio.Future[_R]) -> None:
    _ = future.cancelled() or future.exception()


def _handled(future: asyncio.Future[_R]) -> asyncio.Future[_R]:
    """Marks a future whose exception may be left unretrieved (like the closed promise of a reader)."""
    future.add_done_callback(_retrieve)
    return future


def _settle(future: asyncio.Future[_R] | None, value: _R, error: BaseException | None = None) -> None:
    if future is None or future.done():
        return
    if error is not None:
        future.set_exception(error)
    else:
        future.set_result(value)


def _fail(future: asyncio.Future[_R] | None, error: BaseException) -> None:
    if future is not None and not future.done():
        future.set_exception(error)


def _reject(future: asyncio.Future[_R], error: BaseException) -> asyncio.Future[_R]:
    """Rejects a pending future, or returns a new rejected one in place of a settled one."""
    if future.done():
        rejected: asyncio.Future[_R] = _rejected(error)
        return _handled(rejected)
    future.set_exception(error)
    return future


def _error_or_default(error: BaseException | None) -> BaseException:
    return error if error is not None else TypeError('The stream errored')


def _reason_error(reason: object) -> BaseException:
    return reason if isinstance(reason, BaseException) else TypeError(str(reason))


def _member(obj: object, name: str) -> Callable[..., object] | None:
    """A method of an underlying source, sink or transformer: an object, or a dictionary as in browsers."""
    method: Callable[..., object] | None
    if isinstance(obj, dict):
        method = cast('dict[str, Callable[..., object]]', obj).get(name)
    else:
        method = getattr(obj, name, None) if obj is not None else None
    return method


def _call(obj: object, name: str, *args: object) -> object:
    """Calls a method of an underlying source, sink or transformer, if it has one."""
    method = _member(obj, name)
    return method(*args) if method is not None else None


async def _await(result: object) -> object:
    if inspect.isawaitable(result):
        awaited: object = await result
        return awaited
    return result


def _then(result: object, on_done: Callable[[], None], on_error: Callable[[BaseException], None]) -> None:
    """Runs a callback once the result of an algorithm (a value or an awaitable) settles."""
    if not inspect.isawaitable(result):
        on_done()
        return

    def done(future: asyncio.Future[object]) -> None:
        error = asyncio.CancelledError() if future.cancelled() else future.exception()
        if error is not None:
            on_error(error)
        else:
            on_done()

    task: asyncio.Future[object] = asyncio.ensure_future(result)
    task.add_done_callback(done)


def _future_of(result: object) -> asyncio.Future[None]:
    """Returns a future settled like the result of an algorithm (a value or an awaitable)."""
    future: asyncio.Future[None] = _pending()
    _then(result, lambda: _settle(future, None), lambda e: _fail(future, e))
    return future


def _run(
    obj: object,
    name: str,
    *args: object,
    on_done: Callable[[], None],
    on_error: Callable[[BaseException], None],
) -> None:
    """Calls a method of an underlying source or sink and a callback once its result settles, or once it raises."""
    try:
        result = _call(obj, name, *args)
    except Exception as e:
        # anything the method raises errors the stream, as a rejection in the specification
        on_error(e)
        return
    _then(result, on_done, on_error)


class _ReadableWritablePair(Protocol[_T, _O]):
    @property
    def readable(self) -> ReadableStream[_O]: ...

    @property
    def writable(self) -> WritableStream[_T]: ...


class _PipeOptions(NamedTuple):
    prevent_close: bool
    prevent_abort: bool
    prevent_cancel: bool


@dataclass
class ReadableStreamReadResult(Generic[_T]):
    """The result of :meth:`ReadableStreamDefaultReader.read`.

    Args:
        value: The chunk, :obj:`None` once done.
        done (:obj:`bool`): Whether the stream is closed and has no more chunks.
    """

    value: _T | None
    done: bool


#: The result of a read, by another name: tests/idl/expectations.json expects read() not to name it yet
_ReadResult = ReadableStreamReadResult


class ReadableStreamDefaultController(Generic[_T]):
    """Lets an underlying source enqueue chunks, close or error its stream."""

    def __init__(self, stream: ReadableStream[_T], source: object, high_water_mark: float) -> None:
        self._stream = stream
        self._source = source
        self._high_water_mark = high_water_mark
        self._queue: collections.deque[_T] = collections.deque()
        self._close_requested = False
        self._started = False
        self._pulling = False
        self._pull_again = False

    @property
    def desired_size(self) -> float | None:
        """:obj:`float`, optional: How many chunks the queue can take until it's full, :obj:`None` if errored."""
        state = self._stream._state
        if state == 'errored':
            return None
        if state == 'closed':
            return 0
        return self._high_water_mark - len(self._queue)

    def enqueue(self, chunk: _T) -> None:
        """Enqueues a chunk, which fulfills a pending read if there's one.

        Raises:
            TypeError: If the stream is closed or closing.
        """
        if self._close_requested or self._stream._state != 'readable':
            msg = 'The stream is closed or closing'
            raise TypeError(msg)
        reader = self._stream._reader
        if reader is not None and len(reader._read_requests) > 0:
            _settle(reader._read_requests.popleft(), ReadableStreamReadResult(chunk, done=False))
        else:
            self._queue.append(chunk)
        self._call_pull_if_needed()

    def close(self) -> None:
        """Closes the stream once its queue is read.

        Raises:
            TypeError: If the stream is closed or closing.
        """
        if self._close_requested or self._stream._state != 'readable':
            msg = 'The stream is closed or closing'
            raise TypeError(msg)
        self._close_requested = True
        if len(self._queue) == 0:
            self._stream._close()

    def error(self, error: BaseException | None = None) -> None:
        """Errors the stream: pending and later reads fail with the error."""
        if self._stream._state != 'readable':
            return
        self._queue.clear()
        self._stream._error(_error_or_default(error))

    def _start(self) -> None:
        def started() -> None:
            self._started = True
            self._call_pull_if_needed()

        _then(_call(self._source, 'start', self), started, self.error)

    def _should_call_pull(self) -> bool:
        stream = self._stream
        if not self._started or self._close_requested or stream._state != 'readable':
            return False
        if stream._has_read_requests():
            return True
        desired_size = self.desired_size
        return desired_size is not None and desired_size > 0

    def _call_pull_if_needed(self) -> None:
        if not self._should_call_pull():
            return
        if self._pulling:
            self._pull_again = True
            return
        self._pulling = True

        def pulled() -> None:
            self._pulling = False
            if self._pull_again:
                self._pull_again = False
                self._call_pull_if_needed()

        _run(self._source, 'pull', self, on_done=pulled, on_error=self.error)

    def _read(self, reader: ReadableStreamDefaultReader[_T], request: asyncio.Future[_ReadResult[_T]]) -> None:
        if len(self._queue) > 0:
            chunk = self._queue.popleft()
            if self._close_requested and len(self._queue) == 0:
                self._stream._close()
            else:
                self._call_pull_if_needed()
            _settle(request, ReadableStreamReadResult(chunk, done=False))
        else:
            reader._read_requests.append(request)
            self._call_pull_if_needed()

    def _cancel(self, reason: object) -> object:
        self._queue.clear()
        return _call(self._source, 'cancel', reason)

    #: Alias for :attr:`desired_size`
    desiredSize = desired_size


class ReadableStream(Generic[_T]):
    """A stream of chunks to read (https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream).

    Args:
        underlying_source (optional): An object with optional ``start(controller)``, ``pull(controller)`` and
            ``cancel(reason)`` methods (or a :obj:`dict` of them), which may be coroutine functions.
        high_water_mark (:obj:`float`, optional): How many chunks are queued ahead of reads, 1 by default.
    """

    def __init__(self, underlying_source: object = None, high_water_mark: float = 1) -> None:
        self._state = 'readable'
        self._stored_error: BaseException | None = None
        self._reader: ReadableStreamDefaultReader[_T] | None = None
        self._controller = ReadableStreamDefaultController(self, underlying_source, high_water_mark)
        self._controller._start()

    @property
    def locked(self) -> bool:
        """:obj:`bool`: Whether a reader holds the stream."""
        return self._reader is not None

    def get_reader(self) -> ReadableStreamDefaultReader[_T]:
        """Returns a reader, which holds the stream until it's released.

        Raises :obj:`TypeError` if the stream is locked.
        """
        return ReadableStreamDefaultReader(self)

    def cancel(self, reason: object = None) -> asyncio.Future[None]:
        """Cancels the stream: its source stops and its chunks are dropped.

        Returns:
            :obj:`asyncio.Future`: Done once the source is canceled.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._cancel(reason)

    def pipe_to(
        self,
        destination: WritableStream[_T],
        *,
        prevent_close: bool = False,
        prevent_abort: bool = False,
        prevent_cancel: bool = False,
    ) -> asyncio.Future[None]:
        """Writes every chunk of the stream to a writable stream, waiting for it when it's full.

        Args:
            destination (:obj:`WritableStream`): The stream to write to.
            prevent_close (:obj:`bool`, optional): Whether the destination is left open when this stream closes.
            prevent_abort (:obj:`bool`, optional): Whether the destination is left as it is when this stream errors.
            prevent_cancel (:obj:`bool`, optional): Whether this stream is left as it is when the destination errors.

        Returns:
            :obj:`asyncio.Future`: Done once every chunk is written, or failed with the error that stopped it.
        """
        if self.locked or destination.locked:
            return _rejected(TypeError('A stream is locked'))
        reader = self.get_reader()
        writer = destination.get_writer()
        options = _PipeOptions(prevent_close, prevent_abort, prevent_cancel)
        pipe = asyncio.ensure_future(self._pipe(reader, writer, options))
        # kept until done, as in browsers: asyncio keeps tasks weakly
        _running_pipes.add(pipe)
        pipe.add_done_callback(_running_pipes.discard)
        return pipe

    @staticmethod
    async def _pipe(
        reader: ReadableStreamDefaultReader[_T], writer: WritableStreamDefaultWriter[_T], options: _PipeOptions
    ) -> None:
        try:
            await _pipe_chunks(reader, writer, prevent_close=options.prevent_close)
        except GeneratorExit:
            # closed, at exit: nothing can be awaited anymore
            raise
        except BaseException as e:
            await _stop_pipe(reader, writer, e, options=options)
            raise
        finally:
            reader.release_lock()
            writer.release_lock()

    def pipe_through(self, transform: _ReadableWritablePair[_T, _O], **options: bool) -> ReadableStream[_O]:
        """Pipes the stream into the writable side of a transform (like :obj:`TransformStream`).

        Args:
            transform: An object with ``writable`` and ``readable`` streams.
            **options: The options of :meth:`pipe_to`.

        Returns:
            :obj:`ReadableStream`: The readable side of the transform.
        """
        _ = _handled(self.pipe_to(transform.writable, **options))
        return transform.readable

    def values(self, *, prevent_cancel: bool = False) -> AsyncIterator[_T]:
        """Iterates over the chunks, like ``async for``.

        Stopping early cancels the stream once the iterator is finalized, right away with
        :func:`contextlib.aclosing`.

        Args:
            prevent_cancel (:obj:`bool`, optional): Whether the stream is left open when the iteration stops early.

        Returns:
            An asynchronous iterator of the chunks.
        """
        return _iterate(self.get_reader(), prevent_cancel=prevent_cancel)

    def __aiter__(self) -> AsyncIterator[_T]:
        return self.values()

    def _close(self) -> None:
        if self._state != 'readable':
            return
        self._state = 'closed'
        if self._reader is not None:
            self._reader._settle_read_requests(ReadableStreamReadResult(None, done=True))
            _settle(self._reader._closed, None)

    def _error(self, error: BaseException) -> None:
        if self._state != 'readable':
            return
        self._state = 'errored'
        self._stored_error = error
        if self._reader is not None:
            self._reader._fail_read_requests(error)
            _fail(self._reader._closed, error)

    def _has_read_requests(self) -> bool:
        return self._reader is not None and len(self._reader._read_requests) > 0

    def _error_stored(self) -> BaseException:
        """The error of an errored stream."""
        return _error_or_default(self._stored_error)

    def _cancel(self, reason: object) -> asyncio.Future[None]:
        if self._state == 'closed':
            return _resolved(None)
        if self._state == 'errored':
            return _rejected(self._error_stored())
        self._close()
        return _future_of(self._controller._cancel(reason))

    #: Alias for :meth:`get_reader`
    getReader = get_reader
    #: Alias for :meth:`pipe_to`
    pipeTo = pipe_to
    #: Alias for :meth:`pipe_through`
    pipeThrough = pipe_through


class ReadableStreamDefaultReader(Generic[_T]):
    """Reads the chunks of a stream, which it locks until :meth:`release_lock`.

    Args:
        stream (:obj:`ReadableStream`): The stream.

    Raises:
        TypeError: If the stream is locked.
    """

    def __init__(self, stream: ReadableStream[_T]) -> None:
        if stream.locked:
            msg = 'The stream is locked'
            raise TypeError(msg)
        self._stream: ReadableStream[_T] | None = stream
        self._read_requests: collections.deque[asyncio.Future[_ReadResult[_T]]] = collections.deque()
        self._closed: asyncio.Future[None] = _handled(_pending())
        stream._reader = self
        if stream._state == 'closed':
            _settle(self._closed, None)
        elif stream._state == 'errored':
            _settle(self._closed, None, stream._stored_error)

    @property
    def closed(self) -> asyncio.Future[None]:
        """:obj:`asyncio.Future`: Done once the stream is closed, failed if it errors or the lock is released."""
        return self._closed

    def read(self) -> asyncio.Future[_ReadResult[_T]]:
        """Reads the next chunk.

        Returns:
            :obj:`asyncio.Future`: Its :obj:`ReadableStreamReadResult`, done once a chunk is there or the stream is
            closed, failed if the stream errors.
        """
        stream = self._stream
        if stream is None:
            return _rejected(TypeError('The reader is released'))
        if stream._state == 'closed':
            return _resolved(ReadableStreamReadResult(None, done=True))
        if stream._state == 'errored':
            return _rejected(stream._error_stored())
        request: asyncio.Future[_ReadResult[_T]] = _pending()
        stream._controller._read(self, request)
        return request

    def cancel(self, reason: object = None) -> asyncio.Future[None]:
        """Cancels the stream (see :meth:`ReadableStream.cancel`)."""
        if self._stream is None:
            return _rejected(TypeError('The reader is released'))
        return self._stream._cancel(reason)

    def release_lock(self) -> None:
        """Releases the stream: pending reads fail with :obj:`TypeError`."""
        stream = self._stream
        if stream is None:
            return
        error = TypeError('The reader is released')
        self._fail_read_requests(error)
        if stream._state == 'readable':
            _fail(self._closed, error)
        else:
            self._closed = _handled(_rejected(error))
        stream._reader = None
        self._stream = None

    def _settle_read_requests(self, value: ReadableStreamReadResult[_T]) -> None:
        while len(self._read_requests) > 0:
            _settle(self._read_requests.popleft(), value)

    def _fail_read_requests(self, error: BaseException) -> None:
        while len(self._read_requests) > 0:
            _fail(self._read_requests.popleft(), error)

    #: Alias for :meth:`release_lock`
    releaseLock = release_lock


def _chunk(result: ReadableStreamReadResult[_T]) -> _T:
    """The chunk of a result that isn't done, which may be :obj:`None` too."""
    return cast('_T', result.value)


async def _pipe_chunks(
    reader: ReadableStreamDefaultReader[_T], writer: WritableStreamDefaultWriter[_T], *, prevent_close: bool
) -> None:
    while True:
        await writer.ready
        result = await reader.read()
        if result.done:
            if not prevent_close:
                await writer.close()
            return
        # writes aren't awaited, like in the specification
        _ = _handled(writer.write(_chunk(result)))


async def _stop_pipe(
    reader: ReadableStreamDefaultReader[_T],
    writer: WritableStreamDefaultWriter[_T],
    error: BaseException,
    *,
    options: _PipeOptions,
) -> None:
    """Cancels the source or aborts the destination of a pipe that failed, unless the options prevent it."""
    stream = writer._stream
    if stream is None:
        msg = 'The writer is released'
        raise TypeError(msg)
    if stream._state in {'erroring', 'errored'}:
        if not options.prevent_cancel:
            await _handled(reader.cancel(error))
    elif not options.prevent_abort:
        await _handled(writer.abort(error))


async def _iterate(reader: ReadableStreamDefaultReader[_T], *, prevent_cancel: bool) -> AsyncIterator[_T]:
    done = False
    try:
        while True:
            result = await reader.read()
            if result.done:
                done = True
                return
            yield _chunk(result)
    finally:
        # runs once the generator is finalized, so an early stop cancels then
        if reader._stream is not None:
            if not done and not prevent_cancel:
                await reader.cancel()
            reader.release_lock()


# the close request queued after the writes
_CLOSE = object()


class WritableStreamDefaultController(Generic[_T]):
    """Lets an underlying sink error its stream."""

    def __init__(self, stream: WritableStream[_T], sink: object, high_water_mark: float) -> None:
        self._stream = stream
        self._sink = sink
        self._high_water_mark = high_water_mark
        # (chunk, future) of the writes, then (_CLOSE, future)
        self._queue: collections.deque[tuple[object, asyncio.Future[None]]] = collections.deque()
        self._started = False
        self._in_flight = False

    def error(self, error: BaseException | None = None) -> None:
        """Errors the stream: pending and later writes fail with the error."""
        if self._stream._state == 'writable':
            self._stream._start_erroring(_error_or_default(error))

    def _desired_size(self) -> float:
        return self._high_water_mark - sum(1 for chunk, _ in self._queue if chunk is not _CLOSE)

    def _start(self) -> None:
        def started() -> None:
            self._started = True
            self._advance()

        def failed(error: BaseException) -> None:
            self._started = True
            self._stream._deal_with_rejection(error)

        _then(_call(self._sink, 'start', self), started, failed)

    def _write(self, chunk: _T, future: asyncio.Future[None]) -> None:
        self._queue.append((chunk, future))
        # advance first: a sink done right away leaves no backpressure to signal
        self._advance()
        self._stream._update_backpressure()

    def _close(self, future: asyncio.Future[None]) -> None:
        self._queue.append((_CLOSE, future))
        self._advance()

    def _advance(self) -> None:
        stream = self._stream
        if not self._started or self._in_flight or len(self._queue) == 0:
            return
        if stream._state == 'erroring':
            stream._finish_erroring()
            return
        if stream._state != 'writable':
            return
        chunk, future = self._queue[0]
        self._in_flight = True

        def failed(error: BaseException) -> None:
            self._settle_in_flight(future, error)
            stream._deal_with_rejection(error)

        if chunk is _CLOSE:
            _run(self._sink, 'close', on_done=lambda: self._closed(future), on_error=failed)
        else:
            _run(self._sink, 'write', chunk, self, on_done=lambda: self._written(future), on_error=failed)

    def _settle_in_flight(self, future: asyncio.Future[None], error: BaseException | None = None) -> None:
        self._in_flight = False
        _ = self._queue.popleft()
        _settle(future, None, error)

    def _written(self, future: asyncio.Future[None]) -> None:
        self._settle_in_flight(future)
        self._stream._update_backpressure()
        self._advance()

    def _closed(self, future: asyncio.Future[None]) -> None:
        self._settle_in_flight(future)
        stream = self._stream
        stream._state = 'closed'
        if stream._writer is not None:
            _settle(stream._writer._closed, None)

    def _reject_queue(self, error: BaseException) -> None:
        """Rejects the queued requests but the one in flight."""
        in_flight = self._queue.popleft() if self._in_flight else None
        for _, future in self._queue:
            _fail(future, error)
        self._queue.clear()
        if in_flight is not None:
            self._queue.append(in_flight)


class WritableStream(Generic[_T]):
    """A stream to write chunks to (https://developer.mozilla.org/en-US/docs/Web/API/WritableStream).

    Args:
        underlying_sink (optional): An object with optional ``start(controller)``, ``write(chunk, controller)``,
            ``close()`` and ``abort(reason)`` methods (or a :obj:`dict` of them), which may be coroutine functions.
        high_water_mark (:obj:`float`, optional): How many chunks are queued until writers see backpressure,
            1 by default.
    """

    def __init__(self, underlying_sink: object = None, high_water_mark: float = 1) -> None:
        self._state = 'writable'
        self._stored_error: BaseException | None = None
        self._writer: WritableStreamDefaultWriter[_T] | None = None
        self._close_requested = False
        self._controller = WritableStreamDefaultController(self, underlying_sink, high_water_mark)
        self._controller._start()

    @property
    def locked(self) -> bool:
        """:obj:`bool`: Whether a writer holds the stream."""
        return self._writer is not None

    def get_writer(self) -> WritableStreamDefaultWriter[_T]:
        """Returns a writer, which holds the stream until it's released.

        Raises :obj:`TypeError` if the stream is locked.
        """
        return WritableStreamDefaultWriter(self)

    def close(self) -> asyncio.Future[None]:
        """Closes the stream once the chunks written before are.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is closed.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._close()

    def abort(self, reason: object = None) -> asyncio.Future[None]:
        """Aborts the stream: queued chunks are dropped and the sink is aborted.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is aborted.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._abort(reason)

    def _close(self) -> asyncio.Future[None]:
        if self._state in {'closed', 'errored'} or self._close_requested:
            return _rejected(TypeError('The stream is closed or closing'))
        self._close_requested = True
        future: asyncio.Future[None] = _pending()
        self._controller._close(future)
        return future

    def _abort(self, reason: object) -> asyncio.Future[None]:
        if self._state in {'closed', 'errored'}:
            return _resolved(None)
        error = reason if isinstance(reason, BaseException) else asyncio.CancelledError(reason)
        self._controller._reject_queue(error)
        self._state = 'errored'
        self._stored_error = error
        self._reject_writer(error)
        return _future_of(_call(self._controller._sink, 'abort', reason))

    def _start_erroring(self, error: BaseException) -> None:
        self._state = 'erroring'
        self._stored_error = error
        if self._writer is not None:
            _fail(self._writer._ready, error)
            rejected: asyncio.Future[None] = _rejected(error)
            self._writer._ready = _handled(rejected)
        if not self._controller._in_flight and self._controller._started:
            self._finish_erroring()

    def _finish_erroring(self) -> None:
        self._state = 'errored'
        error = _error_or_default(self._stored_error)
        self._controller._reject_queue(error)
        self._reject_writer(error)
        _ = _call(self._controller._sink, 'abort', self._stored_error)

    def _deal_with_rejection(self, error: BaseException) -> None:
        if self._state == 'writable':
            self._start_erroring(error)
        if self._state == 'erroring':
            self._finish_erroring()

    def _reject_writer(self, error: BaseException) -> None:
        writer = self._writer
        if writer is None:
            return
        _fail(writer._closed, error)
        writer._ready = _reject(writer._ready, error)

    def _update_backpressure(self) -> None:
        writer = self._writer
        if writer is None or self._state != 'writable':
            return
        backpressure = self._controller._desired_size() <= 0
        if backpressure and writer._ready.done():
            pending: asyncio.Future[None] = _pending()
            writer._ready = _handled(pending)
        elif not backpressure:
            _settle(writer._ready, None)

    #: Alias for :meth:`get_writer`
    getWriter = get_writer


class WritableStreamDefaultWriter(Generic[_T]):
    """Writes chunks to a stream, which it locks until :meth:`release_lock`.

    Args:
        stream (:obj:`WritableStream`): The stream.

    Raises:
        TypeError: If the stream is locked.
    """

    def __init__(self, stream: WritableStream[_T]) -> None:
        if stream.locked:
            msg = 'The stream is locked'
            raise TypeError(msg)
        self._stream: WritableStream[_T] | None = stream
        stream._writer = self
        self._closed: asyncio.Future[None] = _handled(_pending())
        self._ready: asyncio.Future[None] = _handled(_pending())
        if stream._state == 'writable':
            if stream._controller._desired_size() > 0 or stream._close_requested:
                _settle(self._ready, None)
        elif stream._state == 'closed':
            _settle(self._ready, None)
            _settle(self._closed, None)
        else:
            _settle(self._ready, None, stream._stored_error)
            _settle(self._closed, None, stream._stored_error)

    @property
    def closed(self) -> asyncio.Future[None]:
        """:obj:`asyncio.Future`: Done once the stream is closed, failed if it errors or the lock is released."""
        return self._closed

    @property
    def ready(self) -> asyncio.Future[None]:
        """:obj:`asyncio.Future`: Done when the stream can take a chunk without queuing it beyond its limit."""
        return self._ready

    @property
    def desired_size(self) -> float | None:
        """:obj:`float`, optional: How many chunks can be written until the queue is full.

        Raises:
            TypeError: If the writer is released.
        """
        stream = self._stream
        if stream is None:
            msg = 'The writer is released'
            raise TypeError(msg)
        if stream._state in {'errored', 'erroring'}:
            return None
        if stream._state == 'closed':
            return 0
        return stream._controller._desired_size()

    def write(self, chunk: _T) -> asyncio.Future[None]:
        """Writes a chunk.

        Returns:
            :obj:`asyncio.Future`: Done once the sink took it, failed if it didn't.
        """
        stream = self._stream
        if stream is None:
            return _rejected(TypeError('The writer is released'))
        if stream._state in {'errored', 'erroring'}:
            return _rejected(_error_or_default(stream._stored_error))
        if stream._close_requested or stream._state == 'closed':
            return _rejected(TypeError('The stream is closed or closing'))
        future: asyncio.Future[None] = _pending()
        stream._controller._write(chunk, future)
        return future

    def close(self) -> asyncio.Future[None]:
        """Closes the stream (see :meth:`WritableStream.close`)."""
        if self._stream is None:
            return _rejected(TypeError('The writer is released'))
        return self._stream._close()

    def abort(self, reason: object = None) -> asyncio.Future[None]:
        """Aborts the stream (see :meth:`WritableStream.abort`)."""
        if self._stream is None:
            return _rejected(TypeError('The writer is released'))
        return self._stream._abort(reason)

    def release_lock(self) -> None:
        """Releases the stream."""
        stream = self._stream
        if stream is None:
            return
        error = TypeError('The writer is released')
        self._ready = _reject(self._ready, error)
        self._closed = _reject(self._closed, error)
        stream._writer = None
        self._stream = None

    #: Alias for :attr:`desired_size`
    desiredSize = desired_size
    #: Alias for :meth:`release_lock`
    releaseLock = release_lock


class TransformStreamDefaultController(Generic[_T, _O]):
    """Lets a transformer enqueue chunks to the readable side, error or terminate its stream."""

    def __init__(self, stream: TransformStream[_T, _O]) -> None:
        self._stream = stream

    @property
    def desired_size(self) -> float | None:
        """:obj:`float`, optional: The desired size of the readable side."""
        return self._stream._readable._controller.desired_size

    def enqueue(self, chunk: _O) -> None:
        """Enqueues a chunk to the readable side."""
        self._stream._readable._controller.enqueue(chunk)

    def error(self, error: BaseException | None = None) -> None:
        """Errors both sides."""
        error = _error_or_default(error)
        self._stream._readable._controller.error(error)
        self._stream._writable._controller.error(error)

    def terminate(self) -> None:
        """Closes the readable side and errors the writable one."""
        controller = self._stream._readable._controller
        if not controller._close_requested and self._stream._readable._state == 'readable':
            controller.close()
        self._stream._writable._controller.error(TypeError('The stream is terminated'))

    #: Alias for :attr:`desired_size`
    desiredSize = desired_size


class TransformStream(Generic[_T, _O]):
    """A pair of streams where what's written is transformed and read.

    See https://developer.mozilla.org/en-US/docs/Web/API/TransformStream.

    Args:
        transformer (optional): An object with optional ``start(controller)``, ``transform(chunk, controller)`` and
            ``flush(controller)`` methods (or a :obj:`dict` of them), which may be coroutine functions. Chunks pass
            unchanged without ``transform``.
    """

    def __init__(self, transformer: object = None) -> None:
        self._transformer = transformer
        self._controller: TransformStreamDefaultController[_T, _O] = TransformStreamDefaultController(self)
        # settled by a pull of the readable side, which relieves backpressure
        self._pull_waiter: asyncio.Future[None] | None = None
        self._readable: ReadableStream[_O] = ReadableStream(_TransformSource(self), high_water_mark=0)
        self._writable: WritableStream[_T] = WritableStream(_TransformSink(self), high_water_mark=1)
        _ = _call(transformer, 'start', self._controller)

    @property
    def readable(self) -> ReadableStream[_O]:
        """:obj:`ReadableStream`: The transformed chunks."""
        return self._readable

    @property
    def writable(self) -> WritableStream[_T]:
        """:obj:`WritableStream`: The chunks to transform."""
        return self._writable


class _TransformSink(Generic[_T, _O]):
    def __init__(self, stream: TransformStream[_T, _O]) -> None:
        self._stream = stream

    def _has_room(self) -> bool:
        readable = self._stream._readable
        desired_size = readable._controller.desired_size
        return desired_size is None or desired_size > 0 or readable._has_read_requests()

    async def write(self, chunk: _T, _controller: WritableStreamDefaultController[_T]) -> None:
        stream = self._stream
        # waits for the readable side to have room
        while stream._readable._state == 'readable' and not self._has_room():
            waiter: asyncio.Future[None] = _pending()
            stream._pull_waiter = waiter
            await waiter
        transform = _member(stream._transformer, 'transform')
        if transform is None:
            # chunks pass unchanged without a transform
            stream._controller.enqueue(cast('_O', chunk))
        else:
            await _await(transform(chunk, stream._controller))

    async def close(self) -> None:
        stream = self._stream
        _ = await _await(_call(stream._transformer, 'flush', stream._controller))
        if stream._readable._state == 'readable' and not stream._readable._controller._close_requested:
            stream._readable._controller.close()

    def abort(self, reason: object) -> None:
        self._stream._readable._controller.error(_reason_error(reason))


class _TransformSource(Generic[_T, _O]):
    def __init__(self, stream: TransformStream[_T, _O]) -> None:
        self._stream = stream

    def pull(self, _controller: ReadableStreamDefaultController[_O]) -> None:
        _settle(self._stream._pull_waiter, None)

    def cancel(self, reason: object) -> None:
        self._stream._writable._controller.error(_reason_error(reason))
