#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The streams media processing uses: readable, writable and transform streams of objects."""

import asyncio

import pytest

import webrtc
from tests.helpers import wait_until


class Chunks:
    """An underlying source of the given chunks, then closed"""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.pulls = 0
        self.canceled = None

    def pull(self, controller):
        self.pulls += 1
        if self.chunks:
            controller.enqueue(self.chunks.pop(0))
        else:
            controller.close()

    def cancel(self, reason):
        self.canceled = reason


class Controlled:
    """An underlying source keeping its controller, for the test to enqueue or error"""

    def start(self, controller):
        self.controller = controller


@pytest.mark.asyncio
async def test_read_until_done():
    """A reader reads each chunk, then done"""
    stream = webrtc.ReadableStream(Chunks([1, 2]))
    reader = stream.get_reader()
    assert stream.locked
    assert await reader.read() == webrtc.ReadableStreamReadResult(1, False)
    assert await reader.read() == webrtc.ReadableStreamReadResult(2, False)
    assert (await reader.read()).done
    assert await reader.closed is None


@pytest.mark.asyncio
async def test_reads_are_requested_when_called():
    """Reads are pending from the call on, like promises, and settled in order"""
    source = Controlled()
    reader = webrtc.ReadableStream(source, high_water_mark=0).get_reader()
    reads = [reader.read() for _ in range(3)]
    for i in range(3):
        source.controller.enqueue(i)
    assert [r.value for r in await asyncio.gather(*reads)] == [0, 1, 2]


@pytest.mark.asyncio
async def test_async_iteration_and_cancel():
    """async for reads every chunk, and breaking out of it cancels the stream"""
    source = Chunks(range(10))
    stream = webrtc.ReadableStream(source)
    seen = []
    async for chunk in stream:
        seen.append(chunk)
        if chunk == 2:
            break
    assert seen == [0, 1, 2]
    # the loop finalizes the iterator
    await wait_until(lambda: not stream.locked, 'the iterator to release the stream')
    assert (await stream.get_reader().read()).done


@pytest.mark.asyncio
async def test_cancel_reaches_source():
    """Canceling a stream calls the source and settles pending reads as done"""
    source = Chunks([])
    source.pull = lambda controller: None
    stream = webrtc.ReadableStream(source, high_water_mark=0)
    reader = stream.get_reader()
    read = reader.read()
    await reader.cancel('stop')
    assert (await read).done
    assert source.canceled == 'stop'


@pytest.mark.asyncio
async def test_errored_stream_rejects_reads():
    """An error of the source fails pending and later reads"""
    source = Controlled()
    reader = webrtc.ReadableStream(source).get_reader()
    read = reader.read()
    source.controller.error(ValueError('broken'))
    with pytest.raises(ValueError):
        await read
    with pytest.raises(ValueError):
        await reader.read()


@pytest.mark.asyncio
async def test_locked_stream():
    """A locked stream has no second reader until the first one is released"""
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
async def test_writer_backpressure_and_order():
    """Writes reach the sink in order, one at a time, and ready follows the queue"""
    written = []

    class Sink:
        async def write(self, chunk, controller):
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
async def test_failed_write_errors_the_stream():
    """A sink that fails a write errors the stream"""

    class Sink:
        def write(self, chunk, controller):
            raise TypeError('not this')

    writer = webrtc.WritableStream(Sink()).get_writer()
    with pytest.raises(TypeError):
        await writer.write(1)
    with pytest.raises(TypeError):
        await writer.write(2)
    with pytest.raises(TypeError):
        await writer.closed


@pytest.mark.asyncio
async def test_abort_drops_queued_writes():
    """Aborting fails the writes not done yet and tells the sink"""
    reasons = []

    class Sink:
        async def write(self, chunk, controller):
            await asyncio.sleep(0.05)

        def abort(self, reason):
            reasons.append(reason)

    writer = webrtc.WritableStream(Sink()).get_writer()
    first, second = writer.write(1), writer.write(2)
    await writer.abort('enough')
    await first
    with pytest.raises(asyncio.CancelledError):
        await second
    assert reasons == ['enough']


@pytest.mark.asyncio
async def test_pipe_through_transform():
    """A readable stream piped through a transform stream into a writable one"""
    written = []

    class Double:
        def transform(self, chunk, controller):
            controller.enqueue(chunk * 2)

    class Sink:
        def write(self, chunk, controller):
            written.append(chunk)

    readable = webrtc.ReadableStream(Chunks([1, 2, 3])).pipe_through(webrtc.TransformStream(Double()))
    await readable.pipe_to(webrtc.WritableStream(Sink()))
    assert written == [2, 4, 6]


@pytest.mark.asyncio
async def test_pipe_to_aborts_on_error():
    """An error of the source aborts the destination"""
    aborted = []

    class Source:
        def pull(self, controller):
            controller.error(ValueError('source failed'))

    class Sink:
        def abort(self, reason):
            aborted.append(reason)

    with pytest.raises(ValueError):
        await webrtc.ReadableStream(Source()).pipe_to(webrtc.WritableStream(Sink()))
    assert isinstance(aborted[0], ValueError)


def test_streams_need_a_loop():
    """Readers and writers use futures of the running loop"""
    with pytest.raises(RuntimeError):
        webrtc.ReadableStream(Chunks([])).get_reader()
