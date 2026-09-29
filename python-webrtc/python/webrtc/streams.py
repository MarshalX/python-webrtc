#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The part of WHATWG Streams (https://streams.spec.whatwg.org) that media processing uses: readable, writable and
transform streams of objects. Methods return futures like the promises of the specification, so a read or a write
is requested when it's called, not when it's awaited. They need a running asyncio event loop."""

import asyncio
import collections
import inspect
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Deque, Optional, Set, Tuple

__all__ = [
    'ReadableStream',
    'ReadableStreamDefaultReader',
    'ReadableStreamDefaultController',
    'ReadableStreamReadResult',
    'WritableStream',
    'WritableStreamDefaultWriter',
    'WritableStreamDefaultController',
    'TransformStream',
    'TransformStreamDefaultController',
]


def _loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError('streams are used from a running asyncio event loop') from None


def _pending() -> asyncio.Future:
    return _loop().create_future()


def _resolved(value: Any = None) -> asyncio.Future:
    future = _pending()
    future.set_result(value)
    return future


# pipes running, see ReadableStream.pipe_to
_running_pipes: Set[asyncio.Future] = set()


def _rejected(error: BaseException) -> asyncio.Future:
    future = _pending()
    future.set_exception(error)
    return future


def _handled(future: asyncio.Future) -> asyncio.Future:
    """Marks a future whose exception may be left unretrieved (like the closed promise of a reader)."""
    future.add_done_callback(lambda f: f.cancelled() or f.exception())
    return future


def _settle(future: Optional[asyncio.Future], value: Any = None, error: Optional[BaseException] = None) -> None:
    if future is None or future.done():
        return
    if error is not None:
        future.set_exception(error)
    else:
        future.set_result(value)


def _reject(future: asyncio.Future, error: BaseException) -> asyncio.Future:
    """Rejects a pending future, or returns a new rejected one in place of a settled one."""
    if future.done():
        return _handled(_rejected(error))
    future.set_exception(error)
    return future


def _error_or_default(error: Optional[BaseException]) -> BaseException:
    return error if error is not None else TypeError('The stream errored')


def _reason_error(reason: Any) -> BaseException:
    return reason if isinstance(reason, BaseException) else TypeError(str(reason))


def _member(obj: Any, name: str) -> Any:
    """A method of an underlying source, sink or transformer: an object, or a dictionary as in browsers"""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None) if obj is not None else None


def _call(obj: Any, name: str, *args) -> Any:
    """Calls a method of an underlying source, sink or transformer, if it has one."""
    method = _member(obj, name)
    return method(*args) if method is not None else None


async def _await(result: Any) -> Any:
    return await result if inspect.isawaitable(result) else result


def _then(result: Any, on_done: Callable[[], None], on_error: Callable[[BaseException], None]) -> None:
    """Runs a callback once the result of an algorithm (a value or an awaitable) settles."""
    if not inspect.isawaitable(result):
        on_done()
        return

    def done(future: asyncio.Future):
        error = asyncio.CancelledError() if future.cancelled() else future.exception()
        if error is not None:
            on_error(error)
        else:
            on_done()

    asyncio.ensure_future(result).add_done_callback(done)


def _future_of(result: Any) -> asyncio.Future:
    """Returns a future settled like the result of an algorithm (a value or an awaitable)."""
    future = _pending()
    _then(result, lambda: _settle(future), lambda e: _settle(future, error=e))
    return future


@dataclass
class ReadableStreamReadResult:
    """The result of :meth:`ReadableStreamDefaultReader.read`.

    Args:
        value: The chunk, :obj:`None` once done.
        done (:obj:`bool`): Whether the stream is closed and has no more chunks.
    """

    value: Any
    done: bool


class ReadableStreamDefaultController:
    """Lets an underlying source enqueue chunks, close or error its stream."""

    def __init__(self, stream: 'ReadableStream', source: Any, high_water_mark: float):
        self._stream = stream
        self._source = source
        self._high_water_mark = high_water_mark
        self._queue: Deque[Any] = collections.deque()
        self._close_requested = False
        self._started = False
        self._pulling = False
        self._pull_again = False

    @property
    def desired_size(self) -> Optional[float]:
        """:obj:`float`, optional: How many chunks the queue can take until it's full, :obj:`None` if errored."""
        state = self._stream._state
        if state == 'errored':
            return None
        if state == 'closed':
            return 0
        return self._high_water_mark - len(self._queue)

    def enqueue(self, chunk: Any) -> None:
        """Enqueues a chunk, which fulfills a pending read if there's one.

        Raises:
            :obj:`TypeError`: If the stream is closed or closing.
        """
        if self._close_requested or self._stream._state != 'readable':
            raise TypeError('The stream is closed or closing')
        reader = self._stream._reader
        if reader is not None and reader._read_requests:
            _settle(reader._read_requests.popleft(), ReadableStreamReadResult(chunk, False))
        else:
            self._queue.append(chunk)
        self._call_pull_if_needed()

    def close(self) -> None:
        """Closes the stream once its queue is read.

        Raises:
            :obj:`TypeError`: If the stream is closed or closing.
        """
        if self._close_requested or self._stream._state != 'readable':
            raise TypeError('The stream is closed or closing')
        self._close_requested = True
        if not self._queue:
            self._stream._close()

    def error(self, error: Optional[BaseException] = None) -> None:
        """Errors the stream: pending and later reads fail with the error."""
        if self._stream._state != 'readable':
            return
        self._queue.clear()
        self._stream._error(_error_or_default(error))

    def _start(self) -> None:
        def started():
            self._started = True
            self._call_pull_if_needed()

        _then(_call(self._source, 'start', self), started, self.error)

    def _should_call_pull(self) -> bool:
        stream = self._stream
        if not self._started or self._close_requested or stream._state != 'readable':
            return False
        if stream._reader is not None and stream._reader._read_requests:
            return True
        return self.desired_size > 0

    def _call_pull_if_needed(self) -> None:
        if not self._should_call_pull():
            return
        if self._pulling:
            self._pull_again = True
            return
        self._pulling = True

        def pulled():
            self._pulling = False
            if self._pull_again:
                self._pull_again = False
                self._call_pull_if_needed()

        try:
            result = _call(self._source, 'pull', self)
        except Exception as e:
            self.error(e)
            return
        _then(result, pulled, self.error)

    def _read(self, request: asyncio.Future) -> None:
        if self._queue:
            chunk = self._queue.popleft()
            if self._close_requested and not self._queue:
                self._stream._close()
            else:
                self._call_pull_if_needed()
            _settle(request, ReadableStreamReadResult(chunk, False))
        else:
            self._stream._reader._read_requests.append(request)
            self._call_pull_if_needed()

    def _cancel(self, reason: Any) -> Any:
        self._queue.clear()
        return _call(self._source, 'cancel', reason)

    #: Alias for :attr:`desired_size`
    desiredSize = desired_size


class ReadableStream:
    """A stream of chunks to read (https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream).

    Args:
        underlying_source (optional): An object with optional ``start(controller)``, ``pull(controller)`` and
            ``cancel(reason)`` methods (or a :obj:`dict` of them), which may be coroutine functions.
        high_water_mark (:obj:`float`, optional): How many chunks are queued ahead of reads, 1 by default.
    """

    def __init__(self, underlying_source: Any = None, high_water_mark: float = 1):
        self._state = 'readable'
        self._stored_error: Optional[BaseException] = None
        self._reader: Optional[ReadableStreamDefaultReader] = None
        self._controller = ReadableStreamDefaultController(self, underlying_source, high_water_mark)
        self._controller._start()

    @property
    def locked(self) -> bool:
        """:obj:`bool`: Whether a reader holds the stream."""
        return self._reader is not None

    def get_reader(self) -> 'ReadableStreamDefaultReader':
        """Returns a reader, which holds the stream until it's released.

        Raises:
            :obj:`TypeError`: If the stream is locked.
        """
        return ReadableStreamDefaultReader(self)

    def cancel(self, reason: Any = None) -> asyncio.Future:
        """Cancels the stream: its source stops and its chunks are dropped.

        Returns:
            :obj:`asyncio.Future`: Done once the source is canceled.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._cancel(reason)

    def pipe_to(
        self,
        destination: 'WritableStream',
        prevent_close: bool = False,
        prevent_abort: bool = False,
        prevent_cancel: bool = False,
    ) -> asyncio.Future:
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
        pipe = asyncio.ensure_future(self._pipe(reader, writer, prevent_close, prevent_abort, prevent_cancel))
        # kept until done, as in browsers: asyncio keeps tasks weakly
        _running_pipes.add(pipe)
        pipe.add_done_callback(_running_pipes.discard)
        return pipe

    @staticmethod
    async def _pipe(
        reader: 'ReadableStreamDefaultReader',
        writer: 'WritableStreamDefaultWriter',
        prevent_close: bool,
        prevent_abort: bool,
        prevent_cancel: bool,
    ) -> None:
        try:
            while True:
                await writer.ready
                result = await reader.read()
                if result.done:
                    if not prevent_close:
                        await writer.close()
                    return
                # writes aren't awaited, like in the specification
                _handled(writer.write(result.value))
        except GeneratorExit:
            # closed, at exit: nothing can be awaited anymore
            raise
        except BaseException as e:
            if writer._stream._state in ('erroring', 'errored'):
                if not prevent_cancel:
                    await _handled(reader.cancel(e))
            elif not prevent_abort:
                await _handled(writer.abort(e))
            raise
        finally:
            reader.release_lock()
            writer.release_lock()

    def pipe_through(self, transform: Any, **options) -> 'ReadableStream':
        """Pipes the stream into the writable side of a transform (like :obj:`TransformStream`) and returns its
        readable side.

        Args:
            transform: An object with ``writable`` and ``readable`` streams.
            **options: The options of :meth:`pipe_to`.

        Returns:
            :obj:`ReadableStream`: The readable side of the transform.
        """
        _handled(self.pipe_to(transform.writable, **options))
        return transform.readable

    def values(self, prevent_cancel: bool = False) -> AsyncIterator[Any]:
        """Iterates over the chunks, like ``async for``. Stopping early cancels the stream once the iterator is
        finalized, right away with :func:`contextlib.aclosing`.

        Args:
            prevent_cancel (:obj:`bool`, optional): Whether the stream is left open when the iteration stops early.
        """
        return _iterate(self.get_reader(), prevent_cancel)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self.values()

    def _close(self) -> None:
        if self._state != 'readable':
            return
        self._state = 'closed'
        if self._reader is not None:
            self._reader._settle_read_requests(ReadableStreamReadResult(None, True))
            _settle(self._reader._closed)

    def _error(self, error: BaseException) -> None:
        if self._state != 'readable':
            return
        self._state = 'errored'
        self._stored_error = error
        if self._reader is not None:
            self._reader._settle_read_requests(error=error)
            _settle(self._reader._closed, error=error)

    def _cancel(self, reason: Any) -> asyncio.Future:
        if self._state == 'closed':
            return _resolved()
        if self._state == 'errored':
            return _rejected(self._stored_error)
        self._close()
        return _future_of(self._controller._cancel(reason))

    #: Alias for :meth:`get_reader`
    getReader = get_reader
    #: Alias for :meth:`pipe_to`
    pipeTo = pipe_to
    #: Alias for :meth:`pipe_through`
    pipeThrough = pipe_through


class ReadableStreamDefaultReader:
    """Reads the chunks of a stream, which it locks until :meth:`release_lock`.

    Args:
        stream (:obj:`ReadableStream`): The stream.

    Raises:
        :obj:`TypeError`: If the stream is locked.
    """

    def __init__(self, stream: ReadableStream):
        if stream.locked:
            raise TypeError('The stream is locked')
        self._stream: Optional[ReadableStream] = stream
        self._read_requests: Deque[asyncio.Future] = collections.deque()
        self._closed = _handled(_pending())
        stream._reader = self
        if stream._state == 'closed':
            _settle(self._closed)
        elif stream._state == 'errored':
            _settle(self._closed, error=stream._stored_error)

    @property
    def closed(self) -> asyncio.Future:
        """:obj:`asyncio.Future`: Done once the stream is closed, failed if it errors or the lock is released."""
        return self._closed

    def read(self) -> asyncio.Future:
        """Reads the next chunk.

        Returns:
            :obj:`asyncio.Future`: Its :obj:`ReadableStreamReadResult`, done once a chunk is there or the stream is
            closed, failed if the stream errors.
        """
        stream = self._stream
        if stream is None:
            return _rejected(TypeError('The reader is released'))
        if stream._state == 'closed':
            return _resolved(ReadableStreamReadResult(None, True))
        if stream._state == 'errored':
            return _rejected(stream._stored_error)
        request = _pending()
        stream._controller._read(request)
        return request

    def cancel(self, reason: Any = None) -> asyncio.Future:
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
        self._settle_read_requests(error=error)
        if stream._state == 'readable':
            _settle(self._closed, error=error)
        else:
            self._closed = _handled(_rejected(error))
        stream._reader = None
        self._stream = None

    def _settle_read_requests(self, value: Any = None, error: Optional[BaseException] = None) -> None:
        while self._read_requests:
            _settle(self._read_requests.popleft(), value, error)

    #: Alias for :meth:`release_lock`
    releaseLock = release_lock


async def _iterate(reader: ReadableStreamDefaultReader, prevent_cancel: bool) -> AsyncIterator[Any]:
    done = False
    try:
        while True:
            result = await reader.read()
            if result.done:
                done = True
                return
            yield result.value
    finally:
        # runs once the generator is finalized, so an early stop cancels then
        if reader._stream is not None:
            if not done and not prevent_cancel:
                await reader.cancel()
            reader.release_lock()


# the close request queued after the writes
_CLOSE = object()


class WritableStreamDefaultController:
    """Lets an underlying sink error its stream."""

    def __init__(self, stream: 'WritableStream', sink: Any, high_water_mark: float):
        self._stream = stream
        self._sink = sink
        self._high_water_mark = high_water_mark
        # (chunk, future) of the writes, then (_CLOSE, future)
        self._queue: Deque[Tuple[Any, asyncio.Future]] = collections.deque()
        self._started = False
        self._in_flight = False

    def error(self, error: Optional[BaseException] = None) -> None:
        """Errors the stream: pending and later writes fail with the error."""
        if self._stream._state == 'writable':
            self._stream._start_erroring(_error_or_default(error))

    def _desired_size(self) -> float:
        return self._high_water_mark - sum(1 for chunk, _ in self._queue if chunk is not _CLOSE)

    def _start(self) -> None:
        def started():
            self._started = True
            self._advance()

        def failed(error: BaseException):
            self._started = True
            self._stream._deal_with_rejection(error)

        _then(_call(self._sink, 'start', self), started, failed)

    def _write(self, chunk: Any, future: asyncio.Future) -> None:
        self._queue.append((chunk, future))
        # advance first: a sink done right away leaves no backpressure to signal
        self._advance()
        self._stream._update_backpressure()

    def _close(self, future: asyncio.Future) -> None:
        self._queue.append((_CLOSE, future))
        self._advance()

    def _advance(self) -> None:
        stream = self._stream
        if not self._started or self._in_flight or not self._queue:
            return
        if stream._state == 'erroring':
            stream._finish_erroring()
            return
        if stream._state != 'writable':
            return
        chunk, future = self._queue[0]
        self._in_flight = True

        def finish():
            self._in_flight = False
            self._queue.popleft()

        def succeeded():
            finish()
            _settle(future)
            if chunk is _CLOSE:
                stream._state = 'closed'
                if stream._writer is not None:
                    _settle(stream._writer._closed)
            else:
                stream._update_backpressure()
                self._advance()

        def failed(error: BaseException):
            finish()
            _settle(future, error=error)
            stream._deal_with_rejection(error)

        try:
            result = _call(self._sink, 'close') if chunk is _CLOSE else _call(self._sink, 'write', chunk, self)
        except Exception as e:
            failed(e)
            return
        _then(result, succeeded, failed)

    def _reject_queue(self, error: BaseException) -> None:
        """Rejects the queued requests but the one in flight."""
        in_flight = self._queue.popleft() if self._in_flight else None
        for _, future in self._queue:
            _settle(future, error=error)
        self._queue.clear()
        if in_flight is not None:
            self._queue.append(in_flight)


class WritableStream:
    """A stream to write chunks to (https://developer.mozilla.org/en-US/docs/Web/API/WritableStream).

    Args:
        underlying_sink (optional): An object with optional ``start(controller)``, ``write(chunk, controller)``,
            ``close()`` and ``abort(reason)`` methods (or a :obj:`dict` of them), which may be coroutine functions.
        high_water_mark (:obj:`float`, optional): How many chunks are queued until writers see backpressure,
            1 by default.
    """

    def __init__(self, underlying_sink: Any = None, high_water_mark: float = 1):
        self._state = 'writable'
        self._stored_error: Optional[BaseException] = None
        self._writer: Optional[WritableStreamDefaultWriter] = None
        self._close_requested = False
        self._controller = WritableStreamDefaultController(self, underlying_sink, high_water_mark)
        self._controller._start()

    @property
    def locked(self) -> bool:
        """:obj:`bool`: Whether a writer holds the stream."""
        return self._writer is not None

    def get_writer(self) -> 'WritableStreamDefaultWriter':
        """Returns a writer, which holds the stream until it's released.

        Raises:
            :obj:`TypeError`: If the stream is locked.
        """
        return WritableStreamDefaultWriter(self)

    def close(self) -> asyncio.Future:
        """Closes the stream once the chunks written before are.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is closed.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._close()

    def abort(self, reason: Any = None) -> asyncio.Future:
        """Aborts the stream: queued chunks are dropped and the sink is aborted.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is aborted.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._abort(reason)

    def _close(self) -> asyncio.Future:
        if self._state in ('closed', 'errored') or self._close_requested:
            return _rejected(TypeError('The stream is closed or closing'))
        self._close_requested = True
        future = _pending()
        self._controller._close(future)
        return future

    def _abort(self, reason: Any) -> asyncio.Future:
        if self._state in ('closed', 'errored'):
            return _resolved()
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
            _settle(self._writer._ready, error=error)
            self._writer._ready = _handled(_rejected(error))
        if not self._controller._in_flight and self._controller._started:
            self._finish_erroring()

    def _finish_erroring(self) -> None:
        self._state = 'errored'
        self._controller._reject_queue(self._stored_error)
        self._reject_writer(self._stored_error)
        _call(self._controller._sink, 'abort', self._stored_error)

    def _deal_with_rejection(self, error: BaseException) -> None:
        if self._state == 'writable':
            self._start_erroring(error)
        if self._state == 'erroring':
            self._finish_erroring()

    def _reject_writer(self, error: BaseException) -> None:
        writer = self._writer
        if writer is None:
            return
        _settle(writer._closed, error=error)
        writer._ready = _reject(writer._ready, error)

    def _update_backpressure(self) -> None:
        writer = self._writer
        if writer is None or self._state != 'writable':
            return
        backpressure = self._controller._desired_size() <= 0
        if backpressure and writer._ready.done():
            writer._ready = _handled(_pending())
        elif not backpressure:
            _settle(writer._ready)

    #: Alias for :meth:`get_writer`
    getWriter = get_writer


class WritableStreamDefaultWriter:
    """Writes chunks to a stream, which it locks until :meth:`release_lock`.

    Args:
        stream (:obj:`WritableStream`): The stream.

    Raises:
        :obj:`TypeError`: If the stream is locked.
    """

    def __init__(self, stream: WritableStream):
        if stream.locked:
            raise TypeError('The stream is locked')
        self._stream: Optional[WritableStream] = stream
        stream._writer = self
        self._closed = _handled(_pending())
        self._ready = _handled(_pending())
        if stream._state == 'writable':
            if stream._controller._desired_size() > 0 or stream._close_requested:
                _settle(self._ready)
        elif stream._state == 'closed':
            _settle(self._ready)
            _settle(self._closed)
        else:
            _settle(self._ready, error=stream._stored_error)
            _settle(self._closed, error=stream._stored_error)

    @property
    def closed(self) -> asyncio.Future:
        """:obj:`asyncio.Future`: Done once the stream is closed, failed if it errors or the lock is released."""
        return self._closed

    @property
    def ready(self) -> asyncio.Future:
        """:obj:`asyncio.Future`: Done when the stream can take a chunk without queuing it beyond its limit."""
        return self._ready

    @property
    def desired_size(self) -> Optional[float]:
        """:obj:`float`, optional: How many chunks can be written until the queue is full.

        Raises:
            :obj:`TypeError`: If the writer is released.
        """
        stream = self._stream
        if stream is None:
            raise TypeError('The writer is released')
        if stream._state in ('errored', 'erroring'):
            return None
        if stream._state == 'closed':
            return 0
        return stream._controller._desired_size()

    def write(self, chunk: Any) -> asyncio.Future:
        """Writes a chunk.

        Returns:
            :obj:`asyncio.Future`: Done once the sink took it, failed if it didn't.
        """
        stream = self._stream
        if stream is None:
            return _rejected(TypeError('The writer is released'))
        if stream._state in ('errored', 'erroring'):
            return _rejected(stream._stored_error)
        if stream._close_requested or stream._state == 'closed':
            return _rejected(TypeError('The stream is closed or closing'))
        future = _pending()
        stream._controller._write(chunk, future)
        return future

    def close(self) -> asyncio.Future:
        """Closes the stream (see :meth:`WritableStream.close`)."""
        if self._stream is None:
            return _rejected(TypeError('The writer is released'))
        return self._stream._close()

    def abort(self, reason: Any = None) -> asyncio.Future:
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


class TransformStreamDefaultController:
    """Lets a transformer enqueue chunks to the readable side, error or terminate its stream."""

    def __init__(self, stream: 'TransformStream'):
        self._stream = stream

    @property
    def desired_size(self) -> Optional[float]:
        """:obj:`float`, optional: The desired size of the readable side."""
        return self._stream._readable._controller.desired_size

    def enqueue(self, chunk: Any) -> None:
        """Enqueues a chunk to the readable side."""
        self._stream._readable._controller.enqueue(chunk)

    def error(self, error: Optional[BaseException] = None) -> None:
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


class TransformStream:
    """A pair of streams where what's written is transformed and read
    (https://developer.mozilla.org/en-US/docs/Web/API/TransformStream).

    Args:
        transformer (optional): An object with optional ``start(controller)``, ``transform(chunk, controller)`` and
            ``flush(controller)`` methods (or a :obj:`dict` of them), which may be coroutine functions. Chunks pass
            unchanged without ``transform``.
    """

    def __init__(self, transformer: Any = None):
        self._transformer = transformer
        self._controller = TransformStreamDefaultController(self)
        # settled by a pull of the readable side, which relieves backpressure
        self._pull_waiter: Optional[asyncio.Future] = None
        self._readable = ReadableStream(_TransformSource(self), high_water_mark=0)
        self._writable = WritableStream(_TransformSink(self), high_water_mark=1)
        _call(transformer, 'start', self._controller)

    @property
    def readable(self) -> ReadableStream:
        """:obj:`ReadableStream`: The transformed chunks."""
        return self._readable

    @property
    def writable(self) -> WritableStream:
        """:obj:`WritableStream`: The chunks to transform."""
        return self._writable


class _TransformSink:
    def __init__(self, stream: TransformStream):
        self._stream = stream

    async def write(self, chunk, controller):
        stream = self._stream
        readable = stream._readable
        # waits for the readable side to have room
        while (
            readable._state == 'readable'
            and readable._controller.desired_size <= 0
            and not (readable._reader is not None and readable._reader._read_requests)
        ):
            stream._pull_waiter = _pending()
            await stream._pull_waiter
        transform = _member(stream._transformer, 'transform')
        if transform is None:
            stream._controller.enqueue(chunk)
        else:
            await _await(transform(chunk, stream._controller))

    async def close(self):
        stream = self._stream
        await _await(_call(stream._transformer, 'flush', stream._controller))
        if stream._readable._state == 'readable' and not stream._readable._controller._close_requested:
            stream._readable._controller.close()

    def abort(self, reason):
        self._stream._readable._controller.error(_reason_error(reason))


class _TransformSource:
    def __init__(self, stream: TransformStream):
        self._stream = stream

    def pull(self, controller):
        _settle(self._stream._pull_waiter)

    def cancel(self, reason):
        self._stream._writable._controller.error(_reason_error(reason))
