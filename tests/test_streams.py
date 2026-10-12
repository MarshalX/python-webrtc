#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The streams media processing uses: readable, writable and transform streams of objects."""

from __future__ import annotations

import asyncio
import gc
import inspect
import weakref
from typing import TYPE_CHECKING, NoReturn, cast

import pytest
from typing_extensions import override

import webrtc
from tests.helpers import wait_progressing, wait_until
from webrtc import streams

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Iterable, Iterator


class Chunks:
    """An underlying source of the given chunks, then closed."""

    def __init__(self, chunks: Iterable[object]) -> None:
        self.chunks = list(chunks)
        self.pulls = 0
        self.canceled: object = None

    def pull(self, controller: webrtc.ReadableStreamDefaultController) -> None:
        self.pulls += 1
        if len(self.chunks) > 0:
            controller.enqueue(self.chunks.pop(0))
        else:
            controller.close()

    def cancel(self, reason: object) -> None:
        self.canceled = reason


class Controlled:
    """An underlying source keeping its controller, for the test to enqueue or error."""

    controller: webrtc.ReadableStreamDefaultController

    def start(self, controller: webrtc.ReadableStreamDefaultController) -> None:
        self.controller = controller


@pytest.mark.asyncio
async def test_read_until_done() -> None:
    """A reader reads each chunk, then done."""
    stream = webrtc.ReadableStream(Chunks([1, 2]))
    reader = stream.get_reader()
    assert stream.locked
    assert await reader.read() == webrtc.ReadableStreamReadResult(value=1, done=False)
    assert await reader.read() == webrtc.ReadableStreamReadResult(value=2, done=False)
    assert (await reader.read()).done
    assert await reader.closed is None


@pytest.mark.asyncio
async def test_reads_are_requested_when_called() -> None:
    """Reads are pending from the call on, like promises, and settled in order."""
    source = Controlled()
    reader = webrtc.ReadableStream(source, webrtc.QueuingStrategy(high_water_mark=0)).get_reader()
    reads = [reader.read() for _ in range(3)]
    for i in range(3):
        source.controller.enqueue(i)
    assert [r.value for r in await asyncio.gather(*reads)] == [0, 1, 2]


@pytest.mark.asyncio
async def test_async_iteration_and_cancel() -> None:
    """Async for reads every chunk, and breaking out of it cancels the stream."""
    source = Chunks(range(10))
    stream = webrtc.ReadableStream(source)
    seen: list[object] = []
    async for chunk in stream:
        seen.append(chunk)
        if chunk == 2:
            break
    assert seen == [0, 1, 2]
    # the loop finalizes the iterator
    await wait_until(lambda: not stream.locked, 'the iterator to release the stream')
    assert (await stream.get_reader().read()).done


@pytest.mark.asyncio
async def test_cancel_reaches_source() -> None:
    """Canceling a stream calls the source and settles pending reads as done."""

    class Idle(Chunks):
        @override
        def pull(self, controller: webrtc.ReadableStreamDefaultController) -> None:
            pass

    source = Idle([])
    stream = webrtc.ReadableStream(source, webrtc.QueuingStrategy(high_water_mark=0))
    reader = stream.get_reader()
    read = reader.read()
    await reader.cancel('stop')
    assert (await read).done
    assert source.canceled == 'stop'


@pytest.mark.asyncio
async def test_errored_stream_rejects_reads() -> None:
    """An error of the source fails pending and later reads."""
    source = Controlled()
    reader = webrtc.ReadableStream(source).get_reader()
    read = reader.read()
    source.controller.error(ValueError('broken'))
    with pytest.raises(ValueError, match='broken'):
        await read
    with pytest.raises(ValueError, match='broken'):
        await reader.read()


@pytest.mark.asyncio
async def test_locked_stream() -> None:
    """A locked stream has no second reader until the first one is released."""
    stream = webrtc.ReadableStream(Chunks([1]))
    reader = stream.get_reader()
    with pytest.raises(TypeError):
        stream.get_reader()
    with pytest.raises(TypeError):
        await stream.cancel()
    reader.release_lock()
    with pytest.raises(TypeError):
        await reader.closed
    assert (await stream.get_reader().read()).value == 1


@pytest.mark.asyncio
async def test_writer_backpressure_and_order() -> None:
    """Writes reach the sink in order, one at a time, and ready follows the queue."""
    written: list[int] = []

    class Sink:
        @staticmethod
        async def write(chunk: int, _controller: webrtc.WritableStreamDefaultController) -> None:
            await asyncio.sleep(0.01)
            written.append(chunk)

    writer = webrtc.WritableStream(Sink()).get_writer()
    await writer.ready
    writes = [writer.write(i) for i in range(5)]
    assert not writer.ready.done()
    await asyncio.gather(*writes)
    assert written == [0, 1, 2, 3, 4]
    assert writer.ready.done()
    await writer.close()
    assert await writer.closed is None


@pytest.mark.asyncio
async def test_failed_write_errors_the_stream() -> None:
    """A sink that fails a write errors the stream."""

    class Sink:
        @staticmethod
        def write(_chunk: int, _controller: webrtc.WritableStreamDefaultController) -> NoReturn:
            msg = 'not this'
            raise TypeError(msg)

    writer = webrtc.WritableStream(Sink()).get_writer()
    with pytest.raises(TypeError):
        await writer.write(1)
    with pytest.raises(TypeError):
        await writer.write(2)
    with pytest.raises(TypeError):
        await writer.closed


@pytest.mark.asyncio
async def test_abort_drops_queued_writes() -> None:
    """Aborting fails the writes not done yet and tells the sink."""
    reasons: list[str] = []

    class Sink:
        @staticmethod
        async def write(_chunk: int, _controller: webrtc.WritableStreamDefaultController) -> None:
            await asyncio.sleep(0.05)

        @staticmethod
        def abort(reason: str) -> None:
            reasons.append(reason)

    writer = webrtc.WritableStream(Sink()).get_writer()
    first, second = writer.write(1), writer.write(2)
    await writer.abort('enough')
    await first
    with pytest.raises(asyncio.CancelledError):
        await second
    assert reasons == ['enough']


@pytest.mark.asyncio
async def test_pipe_through_transform() -> None:
    """A readable stream piped through a transform stream into a writable one."""
    written: list[int] = []

    class Double:
        @staticmethod
        def transform(chunk: int, controller: webrtc.TransformStreamDefaultController) -> None:
            controller.enqueue(chunk * 2)

    class Sink:
        @staticmethod
        def write(chunk: int, _controller: webrtc.WritableStreamDefaultController) -> None:
            written.append(chunk)

    readable = webrtc.ReadableStream(Chunks([1, 2, 3])).pipe_through(webrtc.TransformStream(Double()))
    await readable.pipe_to(webrtc.WritableStream(Sink()))
    assert written == [2, 4, 6]


@pytest.mark.asyncio
async def test_pipe_to_aborts_on_error() -> None:
    """An error of the source aborts the destination."""
    aborted: list[Exception] = []

    class Source:
        @staticmethod
        def pull(controller: webrtc.ReadableStreamDefaultController) -> None:
            controller.error(ValueError('source failed'))

    class Sink:
        @staticmethod
        def abort(reason: Exception) -> None:
            aborted.append(reason)

    with pytest.raises(ValueError, match='source failed'):
        await webrtc.ReadableStream(Source()).pipe_to(webrtc.WritableStream(Sink()))
    assert isinstance(aborted[0], ValueError)


def test_streams_need_a_loop() -> None:
    """Readers and writers use futures of the running loop."""
    with pytest.raises(RuntimeError):
        webrtc.ReadableStream(Chunks([])).get_reader()


class Woken:
    """An underlying source of 50 numbers, each pulled when what it waits for (known only weakly) is woken."""

    def __init__(self, waiting: weakref.WeakSet[asyncio.Future[None]]) -> None:
        self.waiting = waiting
        self.next = 0
        self.woken: asyncio.Future[None] | None = None

    def pull(self, controller: webrtc.ReadableStreamDefaultController) -> asyncio.Future[None]:
        # kept by the source, as a processor keeps its pending read
        woken = self.woken = asyncio.get_running_loop().create_future()
        self.waiting.add(woken)
        woken.add_done_callback(lambda _: self.deliver(controller))
        return woken

    def deliver(self, controller: webrtc.ReadableStreamDefaultController) -> None:
        if self.next == 50:
            controller.close()
        else:
            controller.enqueue(self.next)
            self.next += 1


def wake(waiting: weakref.WeakSet[asyncio.Future[None]]) -> None:
    for woken in list(waiting):
        if not woken.done():
            woken.set_result(None)


@pytest.mark.asyncio
async def test_pipe_goes_on_when_nothing_references_it() -> None:
    """A pipe nobody references goes on: a collected one errored its streams with GeneratorExit."""
    # what the source waits for, known only weakly, like a native object waking it
    waiting: weakref.WeakSet[asyncio.Future[None]] = weakref.WeakSet()
    written: list[int] = []

    def write(chunk: int, _controller: webrtc.WritableStreamDefaultController) -> None:
        written.append(chunk)

    def start() -> asyncio.Future[None]:
        # only the last pipe is referenced
        source = webrtc.ReadableStream(Woken(waiting), webrtc.QueuingStrategy(high_water_mark=0))
        sink = webrtc.WritableStream({'write': write})
        return source.pipe_through(webrtc.TransformStream()).pipe_to(sink)

    done = start()

    def collect_and_wake() -> int:
        gc.collect()
        wake(waiting)
        return len(written)

    await wait_progressing(collect_and_wake, done.done, 'the pipe', stall=5)
    await done
    assert written == list(range(50))


@pytest.mark.asyncio
async def test_sources_sinks_and_transformers_as_dictionaries() -> None:
    """As in browsers, methods may be members of a dictionary: they were ignored, a transform changed nothing."""
    written: list[int] = []

    def pull(controller: webrtc.ReadableStreamDefaultController) -> None:
        controller.enqueue(2)

    def transform(chunk: int, controller: webrtc.TransformStreamDefaultController) -> None:
        controller.enqueue(chunk * 10)

    def write(chunk: int, _controller: webrtc.WritableStreamDefaultController) -> None:
        written.append(chunk)

    source = webrtc.ReadableStream({'pull': pull})
    transform_stream = webrtc.TransformStream({'transform': transform})
    sink = webrtc.WritableStream({'write': write})
    pipe = source.pipe_through(transform_stream).pipe_to(sink)
    await wait_until(lambda: len(written) >= 3, 'chunks written')
    pipe.cancel()
    assert written[:3] == [20, 20, 20]


@pytest.mark.asyncio
async def test_strategy_size_counts_the_queue() -> None:
    """The size of the strategy counts the queue for the desired size, and an invalid one errors the stream."""
    source = Controlled()
    strategy: webrtc.QueuingStrategy[str] = webrtc.QueuingStrategy(high_water_mark=10, size=len)
    stream = webrtc.ReadableStream(source, strategy)
    await asyncio.sleep(0)
    source.controller.enqueue('abc')
    assert source.controller.desired_size == 7
    reader = stream.get_reader()
    assert (await reader.read()).value == 'abc'
    assert source.controller.desired_size == 10
    # what the size raises errors the stream
    with pytest.raises(TypeError):
        source.controller.enqueue(None)
    with pytest.raises(TypeError):
        await reader.read()
    with pytest.raises(webrtc.InvalidRangeError):
        webrtc.ReadableStream(strategy=webrtc.QueuingStrategy(high_water_mark=-1))


@pytest.mark.asyncio
async def test_writable_strategy_size() -> None:
    """A writable stream counts its queue with the size of its strategy."""
    sizes = {'small': 1.0, 'big': 5.0, 'bad': -1.0}

    class Sink:
        @staticmethod
        async def write(_chunk: str, _controller: webrtc.WritableStreamDefaultController) -> None:
            await asyncio.sleep(0.01)

    stream = webrtc.WritableStream(Sink(), webrtc.QueuingStrategy(high_water_mark=4, size=sizes.__getitem__))
    writer = stream.get_writer()
    await writer.ready
    first = writer.write('small')
    second = writer.write('big')
    assert writer.desired_size == -2
    await asyncio.gather(first, second)
    assert writer.desired_size == 4
    with pytest.raises(webrtc.InvalidRangeError):
        await writer.write('bad')


@pytest.mark.asyncio
async def test_tee() -> None:
    """Both branches read every chunk, and the stream is canceled once both branches are."""
    source = Chunks([1, 2, 3])
    stream = webrtc.ReadableStream(source)
    first, second = stream.tee()
    assert stream.locked
    assert [chunk async for chunk in first] == [1, 2, 3]
    assert [chunk async for chunk in second] == [1, 2, 3]

    source = Chunks(range(100))
    branches = webrtc.ReadableStream(source).tee()
    # canceling a branch is done once the other is canceled too
    first_canceled = branches[0].cancel('first')
    await asyncio.sleep(0.01)
    assert not first_canceled.done()
    assert source.canceled is None
    await asyncio.gather(first_canceled, branches[1].cancel('second'))
    assert source.canceled == ['first', 'second']


@pytest.mark.asyncio
async def test_tee_errors_both_branches() -> None:
    """An error of the stream errors both branches."""
    source = Controlled()
    branches = webrtc.ReadableStream(source).tee()
    readers = [branch.get_reader() for branch in branches]
    source.controller.error(ValueError('broken'))
    for reader in readers:
        with pytest.raises(ValueError, match='broken'):
            await reader.read()


@pytest.mark.asyncio
async def test_from_iterables() -> None:
    """A stream of the items of an iterable, asynchronous or not, which canceling closes."""
    assert [chunk async for chunk in webrtc.ReadableStream.from_([1, 2])] == [1, 2]

    closed: list[bool] = []

    async def numbers() -> AsyncIterator[int]:
        try:
            for i in range(100):
                await asyncio.sleep(0)
                yield i
        finally:
            closed.append(True)

    reader = webrtc.ReadableStream.from_(numbers()).get_reader()
    assert (await reader.read()).value == 0
    await reader.cancel()
    assert closed == [True]
    with pytest.raises(TypeError):
        webrtc.ReadableStream.from_(cast('Iterable[int]', 1))


@pytest.mark.asyncio
async def test_get_reader_options() -> None:
    """Only default readers exist: a BYOB one is for byte streams."""
    stream = webrtc.ReadableStream(Chunks([1]))
    with pytest.raises(TypeError):
        stream.get_reader(webrtc.ReadableStreamGetReaderOptions(mode='byob'))
    with pytest.raises(ValueError, match='nope'):
        webrtc.ReadableStreamGetReaderOptions.from_json({'mode': 'nope'})
    reader = stream.get_reader(webrtc.ReadableStreamGetReaderOptions())
    assert (await reader.read()).value == 1


@pytest.mark.asyncio
async def test_pipe_options_and_locked_pipe_through() -> None:
    """Pipe options leave the destination open, and piping through a locked transform raises."""
    stream = webrtc.WritableStream()
    await webrtc.ReadableStream(Chunks([1])).pipe_to(stream, webrtc.StreamPipeOptions(prevent_close=True))
    writer = stream.get_writer()
    await writer.write(2)
    transform = webrtc.TransformStream()
    _ = transform.writable.get_writer()
    with pytest.raises(TypeError):
        webrtc.ReadableStream(Chunks([1])).pipe_through(transform)


@pytest.mark.asyncio
async def test_pending_start_is_not_collected() -> None:
    """An unreferenced pending start survives gc."""

    class Source:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def start(self, _controller: webrtc.ReadableStreamDefaultController) -> None:
            self.started.set()
            await asyncio.get_running_loop().create_future()

    source = Source()
    stream = webrtc.ReadableStream(source)
    await source.started.wait()
    gc.collect()
    tasks = [t for t in asyncio.all_tasks() if getattr(t.get_coro(), '__qualname__', '').endswith('Source.start')]
    assert len(tasks) == 1
    tasks[0].cancel()
    assert stream is not None


@pytest.mark.asyncio
async def test_transform_write_settles_on_readable_cancel() -> None:
    """A blocked write rejects on cancel."""
    transform = webrtc.TransformStream()
    writer = transform.writable.get_writer()
    write = writer.write(1)
    await asyncio.sleep(0)
    await transform.readable.cancel(ValueError('stop'))
    with pytest.raises(ValueError, match='stop'):
        await asyncio.wait_for(write, 1)


@pytest.mark.asyncio
async def test_transform_async_start_runs() -> None:
    """An async transformer start runs."""

    class Transformer:
        @staticmethod
        async def start(controller: webrtc.TransformStreamDefaultController) -> None:
            controller.enqueue('hi')

    transform = webrtc.TransformStream(Transformer())
    result = await asyncio.wait_for(transform.readable.get_reader().read(), 1)
    assert result.value == 'hi'


@pytest.mark.asyncio
async def test_iterator_return_releases_on_cancel_error() -> None:
    """Closing the iterator unlocks despite a failing cancel."""

    class Source:
        @staticmethod
        def pull(controller: webrtc.ReadableStreamDefaultController) -> None:
            controller.enqueue(1)

        @staticmethod
        async def cancel(_reason: object) -> None:
            msg = 'cancel failed'
            raise ValueError(msg)

    stream = webrtc.ReadableStream(Source())
    iterator = stream.values()
    assert await iterator.__anext__() == 1
    with pytest.raises(ValueError, match='cancel failed'):
        await cast('AsyncGenerator[int, None]', iterator).aclose()
    assert not stream.locked


@pytest.mark.asyncio
async def test_cancel_rejects_when_source_cancel_raises() -> None:
    """A raising source cancel rejects the future."""

    def cancel(_reason: object) -> None:
        msg = 'cancel failed'
        raise ValueError(msg)

    future = webrtc.ReadableStream({'cancel': cancel}).cancel('x')
    with pytest.raises(ValueError, match='cancel failed'):
        await future


@pytest.mark.asyncio
async def test_abort_rejects_when_sink_abort_raises() -> None:
    """A raising sink abort rejects the future."""

    def abort(_reason: object) -> None:
        msg = 'abort failed'
        raise ValueError(msg)

    future = webrtc.WritableStream({'abort': abort}).abort('x')
    with pytest.raises(ValueError, match='abort failed'):
        await future


@pytest.mark.asyncio
async def test_failed_write_does_not_call_sink_abort() -> None:
    """A failed write doesn't abort the sink."""
    aborted: list[object] = []

    def write(_chunk: object, _controller: object) -> NoReturn:
        msg = 'write failed'
        raise ValueError(msg)

    writer = webrtc.WritableStream({'write': write, 'abort': aborted.append}).get_writer()
    with pytest.raises(ValueError, match='write failed'):
        await writer.write(1)
    assert aborted == []


@pytest.mark.asyncio
async def test_stream_belongs_to_the_open_loop_using_it() -> None:
    """Another loop can't write, close or read a stream while the loop using it is open."""
    writable: webrtc.WritableStream[int] = webrtc.WritableStream()
    readable: webrtc.ReadableStream[int] = webrtc.ReadableStream()
    writer = writable.get_writer()

    async def from_another_loop() -> None:  # ruff: ignore[unused-async]
        with pytest.raises(webrtc.InvalidStateError):
            _ = writer.write(1)
        with pytest.raises(webrtc.InvalidStateError):
            _ = writer.close()
        with pytest.raises(webrtc.InvalidStateError):
            _ = writable.abort()
        with pytest.raises(webrtc.InvalidStateError):
            _ = readable.get_reader()

    await asyncio.get_running_loop().run_in_executor(None, asyncio.run, from_another_loop())
    await writer.write(1)
    await writer.close()


def test_every_stream_method_checks_its_loop() -> None:
    """The public methods of streams, readers, writers and controllers raise from another loop."""
    classes = (
        webrtc.ReadableStream,
        webrtc.ReadableStreamDefaultController,
        webrtc.ReadableStreamDefaultReader,
        webrtc.WritableStream,
        webrtc.WritableStreamDefaultController,
        webrtc.WritableStreamDefaultWriter,
        webrtc.TransformStreamDefaultController,
    )
    unchecked = [
        f'{cls.__name__}.{name}'
        for cls in classes
        for name, member in vars(cls).items()
        if not name.startswith('_') and inspect.isfunction(member) and member not in streams.loop_checked
    ]
    assert unchecked == []


@pytest.mark.asyncio
async def test_readable_controller_after_close_and_error() -> None:
    """The desired size is 0 once closed and None once errored."""
    source = Controlled()
    stream = webrtc.ReadableStream(source)
    source.controller.close()
    assert source.controller.desired_size == 0
    with pytest.raises(TypeError):
        source.controller.enqueue(1)
    with pytest.raises(TypeError):
        source.controller.close()
    # erroring a closed stream does nothing
    source.controller.error(ValueError('late'))
    assert (await stream.get_reader().read()).done

    source = Controlled()
    stream = webrtc.ReadableStream(source)
    source.controller.error('broken')
    assert source.controller.desired_size is None
    with pytest.raises(TypeError, match='broken'):
        await stream.cancel()


@pytest.mark.asyncio
async def test_error_without_a_reason_is_a_type_error() -> None:
    """An error that isn't an exception is raised as a TypeError."""
    source = Controlled()
    reader = webrtc.ReadableStream(source).get_reader()
    source.controller.error()
    with pytest.raises(TypeError, match='The stream errored'):
        await reader.read()


@pytest.mark.asyncio
async def test_released_reader() -> None:
    """A released reader rejects reads and cancels with TypeError."""
    source = Chunks([1])
    stream = webrtc.ReadableStream(source)
    reader = stream.get_reader()
    reader.release_lock()
    reader.release_lock()
    with pytest.raises(TypeError):
        await reader.read()
    with pytest.raises(TypeError):
        await reader.cancel('x')
    assert source.canceled is None
    assert not stream.locked


@pytest.mark.asyncio
async def test_pipe_to_locked_streams_rejects() -> None:
    """Piping a locked stream or into a locked one rejects with TypeError."""
    readable = webrtc.ReadableStream(Chunks([1]))
    writable = webrtc.WritableStream()
    writer = writable.get_writer()
    with pytest.raises(TypeError):
        await readable.pipe_to(writable)
    writer.release_lock()
    reader = readable.get_reader()
    with pytest.raises(TypeError):
        await readable.pipe_to(writable)
    assert (await reader.read()).value == 1


@pytest.mark.asyncio
async def test_pipe_prevent_cancel_keeps_the_source() -> None:
    """A destination error leaves the source readable."""
    source = Chunks([1, 2])

    def write(_chunk: int, _controller: webrtc.WritableStreamDefaultController) -> NoReturn:
        msg = 'sink failed'
        raise ValueError(msg)

    readable = webrtc.ReadableStream(source)
    pipe = readable.pipe_to(webrtc.WritableStream({'write': write}), webrtc.StreamPipeOptions(prevent_cancel=True))
    with pytest.raises(ValueError, match='sink failed'):
        await pipe
    assert source.canceled is None
    assert not readable.locked
    assert not (await readable.get_reader().read()).done


@pytest.mark.asyncio
async def test_pipe_prevent_abort_keeps_the_destination() -> None:
    """A source error leaves the destination writable."""
    aborted: list[object] = []

    def pull(controller: webrtc.ReadableStreamDefaultController) -> None:
        controller.error(ValueError('source failed'))

    writable = webrtc.WritableStream({'abort': aborted.append})
    pipe = webrtc.ReadableStream({'pull': pull}).pipe_to(writable, webrtc.StreamPipeOptions(prevent_abort=True))
    with pytest.raises(ValueError, match='source failed'):
        await pipe
    assert aborted == []
    await writable.get_writer().write(1)


@pytest.mark.asyncio
async def test_tee_canceled_branches_with_a_pending_read() -> None:
    """The stream is canceled once."""
    source = Controlled()
    stream = webrtc.ReadableStream(source)
    first, second = stream.tee()
    await asyncio.gather(first.cancel('a'), second.cancel('b'))
    assert (await first.get_reader().read()).done
    assert (await second.get_reader().read()).done
    with pytest.raises(TypeError):
        source.controller.enqueue(1)


@pytest.mark.asyncio
async def test_tee_canceled_as_the_stream_errors() -> None:
    """Both branches get the stream's error from the cancel."""
    source = Controlled()
    first, second = webrtc.ReadableStream(source).tee()
    source.controller.error(ValueError('broken'))
    canceled = asyncio.gather(first.cancel(), second.cancel())
    with pytest.raises(ValueError, match='broken'):
        await canceled
    assert (await first.get_reader().read()).done


@pytest.mark.asyncio
async def test_from_iterators_closed_on_cancel() -> None:
    """A generator is closed; a plain iterator just stops."""
    closed: list[bool] = []

    def numbers() -> Iterator[int]:
        try:
            yield from range(100)
        finally:
            closed.append(True)

    reader = webrtc.ReadableStream.from_(numbers()).get_reader()
    assert (await reader.read()).value == 0
    await reader.cancel()
    assert closed == [True]

    items = iter([1, 2, 3])
    reader = webrtc.ReadableStream.from_(items).get_reader()
    assert (await reader.read()).value == 1
    await reader.cancel()
    assert (await reader.read()).done
    assert next(items) == 2


@pytest.mark.asyncio
async def test_sink_start_rejection_errors_the_stream() -> None:

    async def start(_controller: webrtc.WritableStreamDefaultController) -> None:  # ruff: ignore[unused-async]
        msg = 'start failed'
        raise ValueError(msg)

    writer = webrtc.WritableStream({'start': start}).get_writer()
    with pytest.raises(ValueError, match='start failed'):
        await writer.closed
    with pytest.raises(ValueError, match='start failed'):
        await writer.write(1)
    assert writer.desired_size is None


@pytest.mark.asyncio
async def test_error_during_a_write_errors_once_it_is_done() -> None:
    """The write finishes, then the queued ones fail."""
    controllers: list[webrtc.WritableStreamDefaultController] = []
    release: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def write(_chunk: int, controller: webrtc.WritableStreamDefaultController) -> None:
        controllers.append(controller)
        await release

    writer = webrtc.WritableStream({'write': write}).get_writer()
    first, second = writer.write(1), writer.write(2)
    await wait_until(lambda: len(controllers) == 1, 'the first write to start')
    controllers[0].error('stop')
    assert writer.desired_size is None
    # a second error is ignored
    controllers[0].error('ignored')
    release.set_result(None)
    await first
    with pytest.raises(TypeError, match='stop'):
        await second
    with pytest.raises(TypeError, match='stop'):
        await writer.closed


@pytest.mark.asyncio
async def test_writable_stream_close_and_abort() -> None:
    """Unlocked, it closes or aborts; locked, it rejects with TypeError."""
    closed: list[bool] = []
    stream: webrtc.WritableStream[int] = webrtc.WritableStream({'close': lambda: closed.append(True)})
    writer = stream.get_writer()
    with pytest.raises(TypeError):
        await stream.close()
    with pytest.raises(TypeError):
        await stream.abort()
    writer.release_lock()
    await stream.close()
    assert closed == [True]
    with pytest.raises(TypeError):
        await stream.close()
    # aborting a closed stream is done right away
    await stream.abort('late')
    writer = stream.get_writer()
    await writer.ready
    await writer.closed
    assert writer.desired_size == 0


@pytest.mark.asyncio
async def test_writable_controller_error_without_a_writer() -> None:
    """Erroring an unlocked stream fails a later writer."""
    controllers: list[webrtc.WritableStreamDefaultController] = []
    stream: webrtc.WritableStream[int] = webrtc.WritableStream({'start': controllers.append})
    controllers[0].error(ValueError('broken'))
    writer = stream.get_writer()
    with pytest.raises(TypeError):
        stream.get_writer()
    with pytest.raises(ValueError, match='broken'):
        await writer.ready
    with pytest.raises(ValueError, match='broken'):
        await writer.closed
    # aborting an errored stream is done right away
    await writer.abort()


@pytest.mark.asyncio
async def test_writer_without_room_waits_to_be_ready() -> None:
    """With a high water mark of 0, it's ready once a close is requested."""
    stream: webrtc.WritableStream[int] = webrtc.WritableStream(strategy=webrtc.QueuingStrategy(high_water_mark=0))
    writer = stream.get_writer()
    assert writer.desired_size == 0
    assert not writer.ready.done()
    writer.release_lock()
    close = stream.close()
    writer = stream.get_writer()
    await writer.ready
    await close


@pytest.mark.asyncio
async def test_released_writer() -> None:
    """A released writer rejects with TypeError."""
    stream: webrtc.WritableStream[int] = webrtc.WritableStream()
    writer = stream.get_writer()
    writer.release_lock()
    writer.release_lock()
    with pytest.raises(TypeError):
        _ = writer.desired_size
    with pytest.raises(TypeError):
        await writer.write(1)
    with pytest.raises(TypeError):
        await writer.close()
    with pytest.raises(TypeError):
        await writer.abort()
    with pytest.raises(TypeError):
        await writer.ready
    await stream.get_writer().write(1)


@pytest.mark.asyncio
async def test_transform_desired_size_follows_the_readable_queue() -> None:
    controllers: list[webrtc.TransformStreamDefaultController] = []
    transform = webrtc.TransformStream(
        {'start': controllers.append}, readable_strategy=webrtc.QueuingStrategy(high_water_mark=2)
    )
    controller = controllers[0]
    assert controller.desired_size == 2
    controller.enqueue('a')
    assert controller.desired_size == 1
    assert (await transform.readable.get_reader().read()).value == 'a'
    assert controller.desired_size == 2
    controller.terminate()
    assert controller.desired_size == 0


@pytest.mark.asyncio
async def test_terminate_closes_readable_and_errors_writable() -> None:
    """The readable side ends after its queue; writes fail with TypeError."""
    controllers: list[webrtc.TransformStreamDefaultController] = []
    transform = webrtc.TransformStream(
        {'start': controllers.append}, readable_strategy=webrtc.QueuingStrategy(high_water_mark=1)
    )
    controllers[0].enqueue('last')
    controllers[0].terminate()
    # terminating again does nothing more
    controllers[0].terminate()
    reader = transform.readable.get_reader()
    assert (await reader.read()).value == 'last'
    assert (await reader.read()).done
    writer = transform.writable.get_writer()
    with pytest.raises(TypeError):
        await writer.write(1)
    with pytest.raises(TypeError):
        await writer.closed


@pytest.mark.asyncio
async def test_terminate_unblocks_a_waiting_write() -> None:

    class Transformer:
        controller: webrtc.TransformStreamDefaultController

        def start(self, controller: webrtc.TransformStreamDefaultController) -> None:
            self.controller = controller

    transformer = Transformer()
    transform = webrtc.TransformStream(transformer)
    writer = transform.writable.get_writer()
    write = writer.write(1)
    await asyncio.sleep(0)
    transformer.controller.terminate()
    with pytest.raises(TypeError):
        await write
    assert (await transform.readable.get_reader().read()).done


@pytest.mark.asyncio
async def test_transform_async_start_rejection_errors_both_sides() -> None:

    async def start(_controller: webrtc.TransformStreamDefaultController) -> None:  # ruff: ignore[unused-async]
        msg = 'start failed'
        raise ValueError(msg)

    transform = webrtc.TransformStream({'start': start})
    with pytest.raises(ValueError, match='start failed'):
        await transform.readable.get_reader().read()
    with pytest.raises(ValueError, match='start failed'):
        await transform.writable.get_writer().closed


@pytest.mark.asyncio
async def test_async_transform_and_flush() -> None:
    """They run in order before the readable side closes."""

    async def transform(chunk: int, controller: webrtc.TransformStreamDefaultController) -> None:
        await asyncio.sleep(0)
        controller.enqueue(chunk + 1)

    async def flush(controller: webrtc.TransformStreamDefaultController) -> None:
        await asyncio.sleep(0)
        controller.enqueue('end')

    stream = webrtc.ReadableStream(Chunks([1, 2])).pipe_through(
        webrtc.TransformStream({'transform': transform, 'flush': flush})
    )
    assert [chunk async for chunk in stream] == [2, 3, 'end']


@pytest.mark.asyncio
async def test_flush_failure_errors_the_readable_side() -> None:
    """The close fails too."""

    def flush(_controller: webrtc.TransformStreamDefaultController) -> NoReturn:
        msg = 'flush failed'
        raise ValueError(msg)

    transform = webrtc.TransformStream({'flush': flush})
    reader = transform.readable.get_reader()
    with pytest.raises(ValueError, match='flush failed'):
        await transform.writable.get_writer().close()
    with pytest.raises(ValueError, match='flush failed'):
        await reader.read()


@pytest.mark.asyncio
async def test_flush_that_terminates_closes_once() -> None:

    def flush(controller: webrtc.TransformStreamDefaultController) -> None:
        controller.terminate()

    transform = webrtc.TransformStream({'flush': flush})
    reader = transform.readable.get_reader()
    await transform.writable.get_writer().close()
    assert (await reader.read()).done
