#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The subset of WHATWG Streams that media processing uses, with readable, writable and transform streams of objects.

Where the specification returns a promise, these methods return an :obj:`asyncio.Future`. The operation starts when
the method is called, before the future is awaited. Byte streams and BYOB readers aren't implemented. Streams are
created and used from a running asyncio event loop.
"""

from __future__ import annotations

import asyncio
import collections
import inspect
import math
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Generator, Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, ClassVar, Generic, Protocol, cast

from typing_extensions import TypeVar

from webrtc.enums import ReadableStreamReaderMode
from webrtc.exceptions import InvalidRangeError
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from webrtc.enums import ReadableStreamReaderModeValue

__all__ = [
    'QueuingStrategy',
    'ReadableStream',
    'ReadableStreamDefaultController',
    'ReadableStreamDefaultReader',
    'ReadableStreamGetReaderOptions',
    'ReadableStreamIteratorOptions',
    'ReadableStreamReadResult',
    'ReadableWritablePair',
    'StreamPipeOptions',
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
#: The type of the chunks a writable stream takes. A stream that takes any object accepts chunks of any type
_W_contra = TypeVar('_W_contra', contravariant=True, default=object)


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


def _error_of(e: object) -> BaseException:
    """The exception for the error of a stream, which may be any value as in the specification."""
    if isinstance(e, BaseException):
        return e
    return TypeError('The stream errored' if e is None else str(e))


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


class _GenericTransformStream(Protocol[_W_contra, _O]):
    """A pair of streams like :obj:`TransformStream`."""

    @property
    def readable(self) -> ReadableStream[_O]: ...

    @property
    def writable(self) -> WritableStream[_W_contra]: ...


@dataclass
class QueuingStrategy(Dictionary, Generic[_T]):
    """How a stream measures its queue, given to the constructor of a stream.

    Args:
        high_water_mark (:obj:`float`, optional): The total size of queued chunks at which the stream signals
            backpressure. :obj:`None` takes the default of the stream.
        size (:obj:`callable`, optional): Returns the size of a chunk. Each chunk counts as 1 if :obj:`None`.
    """

    high_water_mark: float | None = None
    size: Callable[[_T], float] | None = None

    #: Alias for :attr:`high_water_mark`
    highWaterMark: ClassVar[Alias[float | None]] = alias('high_water_mark')


@dataclass(frozen=True)
class _Strategy(Generic[_T]):
    high_water_mark: float
    size: Callable[[_T], float] | None


def _extract_strategy(strategy: QueuingStrategy[_T] | None, default: float) -> _Strategy[_T]:
    """The strategy with its default high water mark, which must be a non-negative number."""
    if strategy is None:
        strategy = QueuingStrategy()
    high_water_mark = default if strategy.high_water_mark is None else float(strategy.high_water_mark)
    if math.isnan(high_water_mark) or high_water_mark < 0:
        msg = 'The high water mark is negative or NaN'
        raise InvalidRangeError(msg)
    return _Strategy(high_water_mark, strategy.size)


def _chunk_size(strategy: _Strategy[_T], chunk: _T) -> float:
    """The size of a chunk, which must be a finite non-negative number."""
    if strategy.size is None:
        return 1
    size = float(strategy.size(chunk))
    if not math.isfinite(size) or size < 0:
        msg = 'The size of a chunk is negative, NaN or infinite'
        raise InvalidRangeError(msg)
    return size


@dataclass
class ReadableStreamGetReaderOptions(Dictionary):
    """The options of :meth:`ReadableStream.get_reader`.

    See :mdn:`ReadableStream/getReader`.

    Args:
        mode (:obj:`webrtc.ReadableStreamReaderMode`, optional): The kind of reader. :obj:`None` gives a default
            reader. ``'byob'`` is refused because there are no byte streams.

    Raises:
        ValueError: If the mode isn't a member of :obj:`webrtc.ReadableStreamReaderMode`.
    """

    mode: ReadableStreamReaderMode | ReadableStreamReaderModeValue | None = None

    def __post_init__(self) -> None:
        if self.mode is not None:
            self.mode = ReadableStreamReaderMode(self.mode)


@dataclass
class ReadableStreamIteratorOptions(Dictionary):
    """The options of :meth:`ReadableStream.values`.

    Args:
        prevent_cancel (:obj:`bool`, optional): Keep the stream open when the iteration stops before the end.
    """

    prevent_cancel: bool = False

    #: Alias for :attr:`prevent_cancel`
    preventCancel: ClassVar[Alias[bool]] = alias('prevent_cancel')


@dataclass
class ReadableWritablePair(Dictionary, Generic[_T, _O]):
    """A writable stream and the readable stream its output comes out of, for :meth:`ReadableStream.pipe_through`.

    See :mdn:`ReadableStream/pipeThrough`.

    Args:
        readable (:obj:`ReadableStream`): The output side.
        writable (:obj:`WritableStream`): The input side.
    """

    readable: ReadableStream[_O]
    writable: WritableStream[_T]


@dataclass
class StreamPipeOptions(Dictionary):
    """The options of :meth:`ReadableStream.pipe_to` and :meth:`ReadableStream.pipe_through`.

    There's no ``signal``. To stop a pipe, cancel the future that :meth:`ReadableStream.pipe_to` returns.

    See :mdn:`ReadableStream/pipeTo`.

    Args:
        prevent_close (:obj:`bool`, optional): Don't close the destination when the source closes.
        prevent_abort (:obj:`bool`, optional): Don't abort the destination when the source errors.
        prevent_cancel (:obj:`bool`, optional): Don't cancel the source when the destination errors.
    """

    prevent_close: bool = False
    prevent_abort: bool = False
    prevent_cancel: bool = False

    #: Alias for :attr:`prevent_close`
    preventClose: ClassVar[Alias[bool]] = alias('prevent_close')
    #: Alias for :attr:`prevent_abort`
    preventAbort: ClassVar[Alias[bool]] = alias('prevent_abort')
    #: Alias for :attr:`prevent_cancel`
    preventCancel: ClassVar[Alias[bool]] = alias('prevent_cancel')


@dataclass
class ReadableStreamReadResult(Dictionary, Generic[_T]):
    """The result of :meth:`ReadableStreamDefaultReader.read`.

    See :mdn:`ReadableStreamDefaultReader/read`.

    Args:
        value (optional): The chunk read. It's :obj:`None` when :attr:`done` is set.
        done (:obj:`bool`, optional): :obj:`True` once the stream is closed and every chunk was read.
    """

    value: _T | None = None
    done: bool = False


class ReadableStreamDefaultController(Generic[_T]):
    """Given to an underlying source to enqueue chunks into its stream, close it or error it.

    See :mdn:`ReadableStreamDefaultController`.
    """

    def __init__(self, stream: ReadableStream[_T], source: object, strategy: _Strategy[_T]) -> None:
        self._stream = stream
        self._source = source
        self._strategy = strategy
        # (chunk, size) of the queued chunks
        self._queue: collections.deque[tuple[_T, float]] = collections.deque()
        self._queue_total_size = 0.0
        self._close_requested = False
        self._started = False
        self._pulling = False
        self._pull_again = False

    @property
    def desired_size(self) -> float | None:
        """:obj:`float`, optional: The room left in the queue before backpressure.

        It's negative when the queue is over-full, 0 once the stream is closed and :obj:`None` once it errored.

        See :mdn:`ReadableStreamDefaultController/desiredSize`.
        """
        state = self._stream._state
        if state == 'errored':
            return None
        if state == 'closed':
            return 0
        return self._strategy.high_water_mark - self._queue_total_size

    def enqueue(self, chunk: _T | None = None) -> None:
        """Adds a chunk to the stream. If a read is pending, the chunk goes straight to it.

        See :mdn:`ReadableStreamDefaultController/enqueue`.

        Args:
            chunk: The chunk.

        Raises:
            TypeError: If the stream is closed or a close was requested.
            webrtc.InvalidRangeError: If the size of the chunk isn't a finite non-negative number. This error and
                any exception from the ``size`` function also error the stream.
        """
        if not self._can_close_or_enqueue():
            msg = 'The stream is closed or closing'
            raise TypeError(msg)
        self._enqueue(cast('_T', chunk))

    def close(self) -> None:
        """Closes the stream once the chunks already queued are read.

        See :mdn:`ReadableStreamDefaultController/close`.

        Raises:
            TypeError: If the stream is closed or a close was requested.
        """
        if not self._can_close_or_enqueue():
            msg = 'The stream is closed or closing'
            raise TypeError(msg)
        self._close()

    def error(self, e: object = None) -> None:
        """Errors the stream and drops its queue. Pending and later reads fail with the error.

        Does nothing if the stream isn't readable.

        See :mdn:`ReadableStreamDefaultController/error`.

        Args:
            e (optional): The error. A value that isn't an exception is raised as a :obj:`TypeError`.
        """
        if self._stream._state != 'readable':
            return
        self._reset_queue()
        self._stream._error(_error_of(e))

    def _can_close_or_enqueue(self) -> bool:
        return not self._close_requested and self._stream._state == 'readable'

    def _enqueue(self, chunk: _T) -> None:
        reader = self._stream._reader
        if reader is not None and len(reader._read_requests) > 0:
            _settle(reader._read_requests.popleft(), ReadableStreamReadResult(chunk, done=False))
        else:
            try:
                size = _chunk_size(self._strategy, chunk)
            except Exception as e:
                self.error(e)
                raise
            self._queue.append((chunk, size))
            self._queue_total_size += size
        self._call_pull_if_needed()

    def _close(self) -> None:
        self._close_requested = True
        if len(self._queue) == 0:
            self._stream._close()

    def _reset_queue(self) -> None:
        self._queue.clear()
        self._queue_total_size = 0.0

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

    def _read(
        self, reader: ReadableStreamDefaultReader[_T], request: asyncio.Future[ReadableStreamReadResult[_T]]
    ) -> None:
        if len(self._queue) > 0:
            chunk, size = self._queue.popleft()
            # rounding errors could leave it below 0
            self._queue_total_size = max(0.0, self._queue_total_size - size)
            if self._close_requested and len(self._queue) == 0:
                self._stream._close()
            else:
                self._call_pull_if_needed()
            _settle(request, ReadableStreamReadResult(chunk, done=False))
        else:
            reader._read_requests.append(request)
            self._call_pull_if_needed()

    def _cancel(self, reason: object) -> object:
        self._reset_queue()
        return _call(self._source, 'cancel', reason)

    #: Alias for :attr:`desired_size`
    desiredSize = desired_size


class ReadableStream(Generic[_T]):
    """A source of chunks to read, iterable with ``async for``.

    See :mdn:`ReadableStream`.

    Args:
        underlying_source (optional): An object or a :obj:`dict` with optional ``start(controller)``,
            ``pull(controller)`` and ``cancel(reason)`` callables. Each can be a plain or a coroutine function, and
            they get a :obj:`ReadableStreamDefaultController`.
        strategy (:obj:`QueuingStrategy`, optional): How the queue is measured. The default high water mark is 1.

    Raises:
        webrtc.InvalidRangeError: If the high water mark of the strategy is negative or NaN.
    """

    def __init__(self, underlying_source: object = None, strategy: QueuingStrategy[_T] | None = None) -> None:
        extracted = _extract_strategy(strategy, 1)
        self._state = 'readable'
        self._stored_error: BaseException | None = None
        self._reader: ReadableStreamDefaultReader[_T] | None = None
        self._controller = ReadableStreamDefaultController(self, underlying_source, extracted)
        self._controller._start()

    @staticmethod
    def from_(async_iterable: AsyncIterable[_R] | Iterable[_R]) -> ReadableStream[_R]:
        """Creates a stream that reads the items of an iterable, asynchronous or not.

        Named ``from`` in the specification. Items are fetched one at a time, as they're read. Canceling the stream
        closes the iterator if it's a generator.

        See :mdn:`ReadableStream/from_static`.

        Args:
            async_iterable: The iterable or asynchronous iterable.

        Returns:
            :obj:`ReadableStream`: The stream of its items.

        Raises:
            TypeError: If the object isn't iterable.
        """
        iterator: AsyncIterator[_R] | Iterator[_R]
        if isinstance(async_iterable, AsyncIterable):
            iterator = async_iterable.__aiter__()
        elif isinstance(async_iterable, Iterable):
            iterator = iter(async_iterable)
        else:
            msg = f'{type(async_iterable).__name__} is not iterable'
            raise TypeError(msg)
        return ReadableStream(_IteratorSource(iterator), QueuingStrategy(high_water_mark=0))

    @property
    def locked(self) -> bool:
        """:obj:`bool`: Whether a reader holds the lock of the stream.

        See :mdn:`ReadableStream/locked`.
        """
        return self._reader is not None

    def get_reader(self, options: ReadableStreamGetReaderOptions | None = None) -> ReadableStreamDefaultReader[_T]:
        """Creates a reader, which locks the stream until :meth:`ReadableStreamDefaultReader.release_lock`.

        See :mdn:`ReadableStream/getReader`.

        Args:
            options (:obj:`ReadableStreamGetReaderOptions`, optional): The kind of reader. Only default readers
                exist.

        Returns:
            :obj:`ReadableStreamDefaultReader`: The reader.

        Raises:
            TypeError: If the stream is locked or the mode is ``'byob'``.
        """
        if options is not None and options.mode == ReadableStreamReaderMode.byob:
            msg = 'Only byte streams have BYOB readers'
            raise TypeError(msg)
        return ReadableStreamDefaultReader(self)

    def cancel(self, reason: object = None) -> asyncio.Future[None]:
        """Cancels the stream. Queued chunks are dropped and the ``cancel`` of the source is called.

        See :mdn:`ReadableStream/cancel`.

        Args:
            reason (optional): Passed to the ``cancel`` of the source.

        Returns:
            :obj:`asyncio.Future`: Done once the source is canceled. Fails with :obj:`TypeError` if the stream is
            locked, or with the error of an errored stream.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._cancel(reason)

    def pipe_to(
        self, destination: WritableStream[_T], options: StreamPipeOptions | None = None
    ) -> asyncio.Future[None]:
        """Reads every chunk and writes it to a writable stream, respecting its backpressure.

        Both streams are locked while the pipe runs. There's no abort signal, so cancel the returned future to stop
        the pipe. The destination is then aborted unless :attr:`StreamPipeOptions.prevent_abort` is set.

        See :mdn:`ReadableStream/pipeTo`.

        Args:
            destination (:obj:`WritableStream`): The stream to write to.
            options (:obj:`StreamPipeOptions`, optional): What the pipe leaves untouched when it stops.

        Returns:
            :obj:`asyncio.Future`: Done once every chunk is written and the destination is closed, unless closing
            is prevented. It fails with the error that stopped the pipe, or with :obj:`TypeError` if either stream
            is locked.
        """
        if self.locked or destination.locked:
            return _rejected(TypeError('A stream is locked'))
        reader = self.get_reader()
        writer = destination.get_writer()
        pipe = asyncio.ensure_future(
            self._pipe(reader, writer, options if options is not None else StreamPipeOptions())
        )
        # kept until done, as in browsers: asyncio keeps tasks weakly
        _running_pipes.add(pipe)
        pipe.add_done_callback(_running_pipes.discard)
        return pipe

    @staticmethod
    async def _pipe(
        reader: ReadableStreamDefaultReader[_T], writer: WritableStreamDefaultWriter[_T], options: StreamPipeOptions
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

    def pipe_through(
        self,
        transform: ReadableWritablePair[_T, _O] | _GenericTransformStream[_T, _O],
        options: StreamPipeOptions | None = None,
    ) -> ReadableStream[_O]:
        """Sends the chunks of the stream through a transform and returns the readable side of the transform.

        See :mdn:`ReadableStream/pipeThrough`.

        Args:
            transform (:obj:`ReadableWritablePair`): The pair, or any object with ``writable`` and ``readable``
                streams, like :obj:`TransformStream`.
            options (:obj:`StreamPipeOptions`, optional): The options of the pipe, as for :meth:`pipe_to`.

        Returns:
            :obj:`ReadableStream`: The readable side of the transform.

        Raises:
            TypeError: If this stream or the writable side is locked.
        """
        if self.locked or transform.writable.locked:
            msg = 'A stream is locked'
            raise TypeError(msg)
        _ = _handled(self.pipe_to(transform.writable, options))
        return transform.readable

    def tee(self) -> list[ReadableStream[_T]]:
        """Splits the stream into two branches that each read every chunk, and locks the stream.

        Chunks aren't copied, so both branches get the same objects. The stream is canceled once both branches are,
        and both branches error if it errors.

        See :mdn:`ReadableStream/tee`.

        Returns:
            :obj:`list` of :obj:`ReadableStream`: The two branches.

        Raises:
            TypeError: If the stream is locked.
        """
        return _Tee(self).branches

    def values(self, options: ReadableStreamIteratorOptions | None = None) -> AsyncIterator[_T]:
        """Returns an asynchronous iterator over the chunks, which locks the stream. ``async for`` uses it too.

        Stopping early cancels the stream when the iterator is finalized. Wrap it in :func:`contextlib.aclosing`
        to cancel right away.

        Args:
            options (:obj:`ReadableStreamIteratorOptions`, optional): Whether stopping early leaves the stream open.

        Returns:
            :obj:`collections.abc.AsyncIterator`: The chunks.

        Raises:
            TypeError: If the stream is locked.
        """
        prevent_cancel = options is not None and options.prevent_cancel
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
        return _error_of(self._stored_error)

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
    """Reads the chunks of a stream, locking it until :meth:`release_lock`.

    See :mdn:`ReadableStreamDefaultReader`.

    Args:
        stream (:obj:`ReadableStream`): The stream to lock.

    Raises:
        TypeError: If the stream is locked.
    """

    def __init__(self, stream: ReadableStream[_T]) -> None:
        if stream.locked:
            msg = 'The stream is locked'
            raise TypeError(msg)
        self._stream: ReadableStream[_T] | None = stream
        self._read_requests: collections.deque[asyncio.Future[ReadableStreamReadResult[_T]]] = collections.deque()
        self._closed: asyncio.Future[None] = _handled(_pending())
        stream._reader = self
        if stream._state == 'closed':
            _settle(self._closed, None)
        elif stream._state == 'errored':
            _settle(self._closed, None, stream._stored_error)

    @property
    def closed(self) -> asyncio.Future[None]:
        """:obj:`asyncio.Future`: Done once the stream closes. It fails if the stream errors or the lock is released.

        See :mdn:`ReadableStreamDefaultReader/closed`.
        """
        return self._closed

    def read(self) -> asyncio.Future[ReadableStreamReadResult[_T]]:
        """Reads the next chunk.

        See :mdn:`ReadableStreamDefaultReader/read`.

        Returns:
            :obj:`asyncio.Future`: A :obj:`ReadableStreamReadResult`, set once a chunk is available or the stream
            closes. It fails with the error of the stream, or with :obj:`TypeError` once the reader is released.
        """
        stream = self._stream
        if stream is None:
            return _rejected(TypeError('The reader is released'))
        if stream._state == 'closed':
            return _resolved(ReadableStreamReadResult(None, done=True))
        if stream._state == 'errored':
            return _rejected(stream._error_stored())
        request: asyncio.Future[ReadableStreamReadResult[_T]] = _pending()
        stream._controller._read(self, request)
        return request

    def cancel(self, reason: object = None) -> asyncio.Future[None]:
        """Cancels the stream, as :meth:`ReadableStream.cancel` does, while keeping the lock.

        See :mdn:`ReadableStreamDefaultReader/cancel`.

        Args:
            reason (optional): Passed to the ``cancel`` of the source.

        Returns:
            :obj:`asyncio.Future`: Done once the source is canceled. Fails with :obj:`TypeError` once the reader is
            released.
        """
        if self._stream is None:
            return _rejected(TypeError('The reader is released'))
        return self._stream._cancel(reason)

    def release_lock(self) -> None:
        """Unlocks the stream. Pending reads and :attr:`closed` fail with :obj:`TypeError`.

        It does nothing if the reader is already released.

        See :mdn:`ReadableStreamDefaultReader/releaseLock`.
        """
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
    options: StreamPipeOptions,
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


class _Tee(Generic[_T]):
    """Reads a stream for two branches, as ReadableStreamDefaultTee in the specification."""

    def __init__(self, stream: ReadableStream[_T]) -> None:
        self._stream = stream
        self._reader = ReadableStreamDefaultReader(stream)
        self._reading = False
        self._read_again = False
        self._canceled = [False, False]
        self._reasons: list[object] = [None, None]
        self._canceled_future: asyncio.Future[None] = _handled(_pending())
        self.branches: list[ReadableStream[_T]] = [ReadableStream(_TeeBranch(self, i)) for i in range(2)]
        self._reader.closed.add_done_callback(self._closed)

    def _pull(self) -> None:
        if self._reading:
            self._read_again = True
            return
        self._reading = True
        self._reader.read().add_done_callback(self._read)

    def _open_branches(self) -> list[ReadableStreamDefaultController[_T]]:
        controllers = [branch._controller for i, branch in enumerate(self.branches) if not self._canceled[i]]
        return [controller for controller in controllers if controller._can_close_or_enqueue()]

    def _read(self, read: asyncio.Future[ReadableStreamReadResult[_T]]) -> None:
        if read.cancelled() or read.exception() is not None:
            # the closed future errors the branches
            self._reading = False
            return
        result = read.result()
        if result.done:
            self._reading = False
            for controller in self._open_branches():
                controller._close()
            if not all(self._canceled):
                _settle(self._canceled_future, None)
            return
        self._read_again = False
        for controller in self._open_branches():
            controller._enqueue(_chunk(result))
        self._reading = False
        if self._read_again:
            self._pull()

    def _cancel(self, index: int, reason: object) -> asyncio.Future[None]:
        self._canceled[index] = True
        self._reasons[index] = reason
        if all(self._canceled):
            # the stream is canceled with the reasons of both branches
            canceled = self._stream._cancel(list(self._reasons))

            def settle(future: asyncio.Future[None]) -> None:
                error = asyncio.CancelledError() if future.cancelled() else future.exception()
                _settle(self._canceled_future, None, error)

            canceled.add_done_callback(settle)
        return self._canceled_future

    def _closed(self, closed: asyncio.Future[None]) -> None:
        error = None if closed.cancelled() else closed.exception()
        if error is None:
            return
        for branch in self.branches:
            branch._controller.error(error)
        if not all(self._canceled):
            _settle(self._canceled_future, None)


class _TeeBranch(Generic[_T]):
    def __init__(self, tee: _Tee[_T], index: int) -> None:
        self._tee = tee
        self._index = index

    def pull(self, _controller: ReadableStreamDefaultController[_T]) -> None:
        self._tee._pull()

    def cancel(self, reason: object) -> asyncio.Future[None]:
        return self._tee._cancel(self._index, reason)


class _IteratorSource(Generic[_T]):
    """The underlying source of :meth:`ReadableStream.from_`."""

    def __init__(self, iterator: AsyncIterator[_T] | Iterator[_T]) -> None:
        self._iterator = iterator

    async def pull(self, controller: ReadableStreamDefaultController[_T]) -> None:
        iterator = self._iterator
        try:
            chunk = await iterator.__anext__() if isinstance(iterator, AsyncIterator) else next(iterator)
        except (StopAsyncIteration, StopIteration):
            controller.close()
            return
        controller.enqueue(chunk)

    async def cancel(self, _reason: object) -> None:
        # the return() of an iterator in the specification
        iterator = self._iterator
        if isinstance(iterator, AsyncGenerator):
            await iterator.aclose()
        elif isinstance(iterator, Generator):
            iterator.close()


# the close request queued after the writes
_CLOSE = object()


class WritableStreamDefaultController(Generic[_W_contra]):
    """Given to an underlying sink to error its stream.

    See :mdn:`WritableStreamDefaultController`.
    """

    def __init__(self, stream: WritableStream[_W_contra], sink: object, strategy: _Strategy[_W_contra]) -> None:
        self._stream = stream
        self._sink = sink
        self._strategy = strategy
        # (chunk, future, size) of the writes, then (_CLOSE, future, 0)
        self._queue: collections.deque[tuple[object, asyncio.Future[None], float]] = collections.deque()
        self._started = False
        self._in_flight = False

    def error(self, e: object = None) -> None:
        """Errors the stream, so queued and later writes fail with the error.

        It does nothing unless the stream is writable.

        See :mdn:`WritableStreamDefaultController/error`.

        Args:
            e (optional): The error. A value that isn't an exception is raised as a :obj:`TypeError`.
        """
        if self._stream._state == 'writable':
            self._stream._start_erroring(_error_of(e))

    def _desired_size(self) -> float:
        return self._strategy.high_water_mark - sum(size for _, _, size in self._queue)

    def _start(self) -> None:
        def started() -> None:
            self._started = True
            self._advance()

        def failed(error: BaseException) -> None:
            self._started = True
            self._stream._deal_with_rejection(error)

        _then(_call(self._sink, 'start', self), started, failed)

    def _write(self, chunk: _W_contra, future: asyncio.Future[None]) -> None:
        try:
            size = _chunk_size(self._strategy, chunk)
        except Exception as e:
            # queued to be rejected once the stream errors
            self._queue.append((chunk, future, 0))
            self.error(e)
            return
        self._queue.append((chunk, future, size))
        # advance first: a sink done right away leaves no backpressure to signal
        self._advance()
        self._stream._update_backpressure()

    def _close(self, future: asyncio.Future[None]) -> None:
        self._queue.append((_CLOSE, future, 0))
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
        chunk, future, _ = self._queue[0]
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
        for _, future, _ in self._queue:
            _fail(future, error)
        self._queue.clear()
        if in_flight is not None:
            self._queue.append(in_flight)


class WritableStream(Generic[_W_contra]):
    """A destination to write chunks to, one at a time, in order.

    See :mdn:`WritableStream`.

    Args:
        underlying_sink (optional): An object or a :obj:`dict` with optional ``start(controller)``,
            ``write(chunk, controller)``, ``close()`` and ``abort(reason)`` callables. Each can be a plain or a
            coroutine function, and they get a :obj:`WritableStreamDefaultController`.
        strategy (:obj:`QueuingStrategy`, optional): How the queue is measured. The default high water mark is 1.

    Raises:
        webrtc.InvalidRangeError: If the high water mark of the strategy is negative or NaN.
    """

    def __init__(self, underlying_sink: object = None, strategy: QueuingStrategy[_W_contra] | None = None) -> None:
        extracted = _extract_strategy(strategy, 1)
        self._state = 'writable'
        self._stored_error: BaseException | None = None
        self._writer: WritableStreamDefaultWriter[_W_contra] | None = None
        self._close_requested = False
        self._controller = WritableStreamDefaultController(self, underlying_sink, extracted)
        self._controller._start()

    @property
    def locked(self) -> bool:
        """:obj:`bool`: Whether a writer holds the lock of the stream.

        See :mdn:`WritableStream/locked`.
        """
        return self._writer is not None

    def get_writer(self) -> WritableStreamDefaultWriter[_W_contra]:
        """Creates a writer, which locks the stream until :meth:`WritableStreamDefaultWriter.release_lock`.

        See :mdn:`WritableStream/getWriter`.

        Returns:
            :obj:`WritableStreamDefaultWriter`: The writer.

        Raises:
            TypeError: If the stream is locked.
        """
        return WritableStreamDefaultWriter(self)

    def close(self) -> asyncio.Future[None]:
        """Closes the stream after the chunks already written, then calls the ``close`` of the sink.

        See :mdn:`WritableStream/close`.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is closed. It fails with :obj:`TypeError` if the stream is
            locked, closed or closing, or with the error that stops the stream.
        """
        if self.locked:
            return _rejected(TypeError('The stream is locked'))
        return self._close()

    def abort(self, reason: object = None) -> asyncio.Future[None]:
        """Aborts the stream. Queued writes fail, the stream errors and the ``abort`` of the sink is called.

        It doesn't wait for a write in progress. Pending writes fail with ``reason`` if it's an exception, and
        otherwise with an :obj:`asyncio.CancelledError` that holds it.

        See :mdn:`WritableStream/abort`.

        Args:
            reason (optional): Passed to the ``abort`` of the sink.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is aborted, or right away for a closed or errored stream. It
            fails with :obj:`TypeError` if the stream is locked.
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
        error = _error_of(self._stored_error)
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


class WritableStreamDefaultWriter(Generic[_W_contra]):
    """Writes chunks to a stream, locking it until :meth:`release_lock`.

    See :mdn:`WritableStreamDefaultWriter`.

    Args:
        stream (:obj:`WritableStream`): The stream to lock.

    Raises:
        TypeError: If the stream is locked.
    """

    def __init__(self, stream: WritableStream[_W_contra]) -> None:
        if stream.locked:
            msg = 'The stream is locked'
            raise TypeError(msg)
        self._stream: WritableStream[_W_contra] | None = stream
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
        """:obj:`asyncio.Future`: Done once the stream closes. It fails if the stream errors or the lock is released.

        See :mdn:`WritableStreamDefaultWriter/closed`.
        """
        return self._closed

    @property
    def ready(self) -> asyncio.Future[None]:
        """:obj:`asyncio.Future`: Done while the queue is below its high water mark.

        Under backpressure it's replaced by a pending future. It fails if the stream errors or the lock is released.

        See :mdn:`WritableStreamDefaultWriter/ready`.
        """
        return self._ready

    @property
    def desired_size(self) -> float | None:
        """:obj:`float`, optional: The room left in the queue before backpressure.

        It's 0 once the stream is closed and :obj:`None` once it's errored or erroring.

        See :mdn:`WritableStreamDefaultWriter/desiredSize`.

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

    def write(self, chunk: _W_contra | None = None) -> asyncio.Future[None]:
        """Queues a chunk for the ``write`` of the sink.

        See :mdn:`WritableStreamDefaultWriter/write`.

        Args:
            chunk: The chunk.

        Returns:
            :obj:`asyncio.Future`: Done once the sink wrote the chunk. It fails with the error of the sink or the
            stream, or with :obj:`TypeError` if the stream is closing or the writer is released.
        """
        stream = self._stream
        if stream is None:
            return _rejected(TypeError('The writer is released'))
        if stream._state in {'errored', 'erroring'}:
            return _rejected(_error_of(stream._stored_error))
        if stream._close_requested or stream._state == 'closed':
            return _rejected(TypeError('The stream is closed or closing'))
        future: asyncio.Future[None] = _pending()
        stream._controller._write(cast('_W_contra', chunk), future)
        return future

    def close(self) -> asyncio.Future[None]:
        """Closes the stream, as :meth:`WritableStream.close` does, while keeping the lock.

        See :mdn:`WritableStreamDefaultWriter/close`.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is closed. It fails with :obj:`TypeError` once the writer is
            released.
        """
        if self._stream is None:
            return _rejected(TypeError('The writer is released'))
        return self._stream._close()

    def abort(self, reason: object = None) -> asyncio.Future[None]:
        """Aborts the stream, as :meth:`WritableStream.abort` does, while keeping the lock.

        See :mdn:`WritableStreamDefaultWriter/abort`.

        Args:
            reason (optional): Passed to the ``abort`` of the sink.

        Returns:
            :obj:`asyncio.Future`: Done once the sink is aborted. It fails with :obj:`TypeError` once the writer is
            released.
        """
        if self._stream is None:
            return _rejected(TypeError('The writer is released'))
        return self._stream._abort(reason)

    def release_lock(self) -> None:
        """Unlocks the stream. :attr:`ready` and :attr:`closed` fail with :obj:`TypeError`.

        Writes already queued go on. It does nothing if the writer is already released.

        See :mdn:`WritableStreamDefaultWriter/releaseLock`.
        """
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
    """Given to a transformer to enqueue output chunks, error the stream or terminate it.

    See :mdn:`TransformStreamDefaultController`.
    """

    def __init__(self, stream: TransformStream[_T, _O]) -> None:
        self._stream = stream

    @property
    def desired_size(self) -> float | None:
        """:obj:`float`, optional: The room left in the queue of the readable side.

        It matches :attr:`ReadableStreamDefaultController.desired_size` of that side.

        See :mdn:`TransformStreamDefaultController/desiredSize`.
        """
        return self._stream._readable._controller.desired_size

    def enqueue(self, chunk: _O | None = None) -> None:
        """Adds an output chunk to the readable side.

        See :mdn:`TransformStreamDefaultController/enqueue`.

        Args:
            chunk: The chunk.

        Raises:
            TypeError: If the readable side is closed or closing.
            webrtc.InvalidRangeError: If the size of the chunk isn't a finite non-negative number.
        """
        self._stream._readable._controller.enqueue(chunk)

    def error(self, reason: object = None) -> None:
        """Errors both sides of the stream.

        See :mdn:`TransformStreamDefaultController/error`.

        Args:
            reason (optional): The error. A value that isn't an exception is raised as a :obj:`TypeError`.
        """
        error = _error_of(reason)
        self._stream._readable._controller.error(error)
        self._stream._writable._controller.error(error)

    def terminate(self) -> None:
        """Ends the stream. Readers get the end of the stream and writers get a :obj:`TypeError`.

        See :mdn:`TransformStreamDefaultController/terminate`.
        """
        controller = self._stream._readable._controller
        if not controller._close_requested and self._stream._readable._state == 'readable':
            controller.close()
        self._stream._writable._controller.error(TypeError('The stream is terminated'))

    #: Alias for :attr:`desired_size`
    desiredSize = desired_size


class TransformStream(Generic[_T, _O]):
    """A writable side and a readable side. Chunks written to one are transformed and read from the other.

    See :mdn:`TransformStream`.

    Args:
        transformer (optional): An object or a :obj:`dict` with optional ``start(controller)``,
            ``transform(chunk, controller)`` and ``flush(controller)`` callables. Each can be a plain or a coroutine
            function, and they get a :obj:`TransformStreamDefaultController`. Without ``transform``, chunks pass
            through unchanged.
        writable_strategy (:obj:`QueuingStrategy`, optional): How the queue of the writable side is measured. The
            default high water mark is 1.
        readable_strategy (:obj:`QueuingStrategy`, optional): How the queue of the readable side is measured. The
            default high water mark is 0.

    Raises:
        webrtc.InvalidRangeError: If the high water mark of a strategy is negative or NaN.
    """

    def __init__(
        self,
        transformer: object = None,
        writable_strategy: QueuingStrategy[_T] | None = None,
        readable_strategy: QueuingStrategy[_O] | None = None,
    ) -> None:
        writable = _extract_strategy(writable_strategy, 1)
        readable = _extract_strategy(readable_strategy, 0)
        self._transformer = transformer
        self._controller: TransformStreamDefaultController[_T, _O] = TransformStreamDefaultController(self)
        # settled by a pull of the readable side, which relieves backpressure
        self._pull_waiter: asyncio.Future[None] | None = None
        self._readable: ReadableStream[_O] = ReadableStream(
            _TransformSource(self), QueuingStrategy(readable.high_water_mark, readable.size)
        )
        self._writable: WritableStream[_T] = WritableStream(
            _TransformSink(self), QueuingStrategy(writable.high_water_mark, writable.size)
        )
        _ = _call(transformer, 'start', self._controller)

    @property
    def readable(self) -> ReadableStream[_O]:
        """:obj:`ReadableStream`: The side to read the output chunks from.

        See :mdn:`TransformStream/readable`.
        """
        return self._readable

    @property
    def writable(self) -> WritableStream[_T]:
        """:obj:`WritableStream`: The side to write the input chunks to.

        See :mdn:`TransformStream/writable`.
        """
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
        self._stream._readable._controller.error(_error_of(reason))


class _TransformSource(Generic[_T, _O]):
    def __init__(self, stream: TransformStream[_T, _O]) -> None:
        self._stream = stream

    def pull(self, _controller: ReadableStreamDefaultController[_O]) -> None:
        _settle(self._stream._pull_waiter, None)

    def cancel(self, reason: object) -> None:
        self._stream._writable._controller.error(_error_of(reason))
