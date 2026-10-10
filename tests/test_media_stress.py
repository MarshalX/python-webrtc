#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Processors and generators under stress: races that could deadlock, and cycles that could leak."""

from __future__ import annotations

import asyncio
import gc
import time
import weakref

import pytest

import webrtc
from tests.helpers import SANITIZED, connect_track, rss_bytes, skip_if_sanitized, wait_until, write_video, writing
from webrtc.utils.loops import LoopState

TIMEOUT = 20


def frame(timestamp: int = 0, width: int = 16, height: int = 16) -> webrtc.VideoFrame:
    return webrtc.VideoFrame(
        bytes(width * height * 3 // 2),
        webrtc.VideoFrameBufferInit(format='I420', coded_width=width, coded_height=height, timestamp=timestamp),
    )


def close(media: object) -> None:
    """Closes media read from a processor."""
    assert isinstance(media, (webrtc.VideoFrame, webrtc.AudioData))
    media.close()


def collected(refs: list[weakref.ref[object]]) -> bool:
    gc.collect()
    return all(ref() is None for ref in refs)


@pytest.mark.asyncio
async def test_cancel_during_pending_reads(video_stream: webrtc.MediaStream) -> None:
    """Canceling while reads wait for frames settles them, over and over."""
    track = video_stream.get_tracks()[0]
    for _ in range(50):
        reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
        reads = [reader.read() for _ in range(3)]
        await asyncio.sleep(0)
        await reader.cancel()
        for result in await asyncio.wait_for(asyncio.gather(*reads), TIMEOUT):
            if not result.done:
                close(result.value)


@pytest.mark.asyncio
async def test_stop_track_while_reading(video_stream: webrtc.MediaStream, audio_stream: webrtc.MediaStream) -> None:
    """Tracks stopped while tasks read them close their streams."""
    tracks = [*video_stream.get_tracks(), *audio_stream.get_tracks()]

    read: list[webrtc.MediaStreamTrack] = []

    async def read_all(track: webrtc.MediaStreamTrack) -> int:
        count = 0
        async for media in webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable:
            close(media)
            count += 1
            if count == 1:
                read.append(track)
        return count

    tasks = [asyncio.ensure_future(read_all(track)) for track in tracks for _ in range(3)]
    # every task reads some media first (a fixed wait was too short on slow machines)
    await wait_until(lambda: len(read) == len(tasks), 'every task to read media', TIMEOUT)
    for track in tracks:
        track.stop()
    assert all(count > 0 for count in await asyncio.wait_for(asyncio.gather(*tasks), TIMEOUT))


@pytest.mark.asyncio
async def test_many_processors_of_one_track(video_stream: webrtc.MediaStream) -> None:
    """Every processor of a track gets its frames."""
    track = video_stream.get_tracks()[0]
    readers = [
        webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
        for _ in range(20)
    ]
    for result in await asyncio.wait_for(asyncio.gather(*(r.read() for r in readers)), TIMEOUT):
        close(result.value)
    track.stop()
    await asyncio.wait_for(asyncio.gather(*(r.closed for r in readers)), TIMEOUT)


@pytest.mark.asyncio
async def test_garbage_collected_with_pending_reads(video_stream: webrtc.MediaStream) -> None:
    """Processors dropped with reads pending are collected, while their track goes on."""
    track = video_stream.get_tracks()[0]
    refs: list[weakref.ref[object]] = []
    for _ in range(20):
        processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
        processor.readable.get_reader().read()
        refs.append(weakref.ref(processor))
        del processor
    await wait_until(lambda: collected(refs), 'the processors to be collected')
    reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track)).readable.get_reader()
    close((await asyncio.wait_for(reader.read(), TIMEOUT)).value)


@pytest.mark.asyncio
async def test_close_connection_while_reading(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Closing the connection closes the processors of its tracks, while frames still arrive."""
    generator = webrtc.VideoTrackGenerator()
    async with writing(write_video, generator, bytes(64 * 64 * 3 // 2), (64, 64), interval=0.01):
        remote = await connect_track(caller, callee, generator.track, timeout=TIMEOUT)
        readers = [
            webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(remote)).readable.get_reader()
            for _ in range(5)
        ]
        close((await asyncio.wait_for(readers[0].read(), TIMEOUT)).value)
        pending = [r.read() for r in readers]
        callee.close()
        caller.close()
        await asyncio.wait_for(asyncio.gather(*(r.closed for r in readers)), TIMEOUT)
        for result in await asyncio.gather(*pending):
            if not result.done:
                close(result.value)
    generator.track.stop()


def test_loop_closed_while_frames_arrive() -> None:
    """A processor whose loop is closed doesn't block the media threads, nor fail once collected."""
    stream = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True)))

    async def start() -> list[webrtc.MediaStreamTrackProcessor]:
        processors = [
            webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(t)) for t in stream.get_tracks()
        ]
        for p in processors:
            p.readable.get_reader().read()
        await asyncio.sleep(0.1)
        return processors

    loop = asyncio.new_event_loop()
    processors = loop.run_until_complete(start())
    loop.close()
    # frames keep arriving for the closed loop
    time.sleep(0.3)
    del processors
    gc.collect()
    for track in stream.get_tracks():
        track.stop()


@pytest.mark.asyncio
async def test_create_and_destroy_cycles_do_not_leak() -> None:
    """Thousands of processors, generators and frames leave nothing behind."""

    async def cycle() -> tuple[weakref.ref[object], weakref.ref[object]]:
        generator = webrtc.VideoTrackGenerator()
        processor = webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(generator.track, max_buffer_size=2)
        )
        reader = processor.readable.get_reader()
        await generator.writable.get_writer().write(frame())
        close((await reader.read()).value)
        await reader.cancel()
        generator.track.stop()
        return weakref.ref(processor), weakref.ref(generator)

    for _ in range(100):
        await cycle()
    gc.collect()
    before = rss_bytes()
    refs = [ref for _ in range(1000) for ref in await cycle()]
    # callbacks still queued on the loop hold the last objects
    await wait_until(lambda: collected(refs), 'every cycle to be collected')
    growth = rss_bytes() - before
    assert SANITIZED or growth < 20 * 1024 * 1024, f'{growth / 1e6:.1f} MB more after 1000 cycles'


@skip_if_sanitized
@pytest.mark.asyncio
async def test_unread_frames_do_not_grow_memory(video_stream: webrtc.MediaStream) -> None:
    """A processor nobody reads keeps at most its buffer: memory stays flat while frames keep coming."""
    processor = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(video_stream.get_tracks()[0], max_buffer_size=3)
    )
    reader = processor.readable.get_reader()
    # warm up, then measure for 2 s
    await asyncio.sleep(0.5)
    before = rss_bytes()
    await asyncio.sleep(2)
    assert rss_bytes() - before < 10 * 1024 * 1024
    assert processor.discarded_frames > 30
    await reader.cancel()


@pytest.mark.asyncio
async def test_reader_that_never_yields_queues_nothing() -> None:
    """Frames read as fast as they're written, without the loop running, leave no callbacks piling up for it."""
    generator = webrtc.VideoTrackGenerator()
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(generator.track, max_buffer_size=2)
    ).readable.get_reader()
    writer = generator.writable.get_writer()
    loop = asyncio.get_running_loop()
    for timestamp in range(2000):
        # both are done right away, so the loop never runs in between
        await writer.write(frame(timestamp))
        close((await reader.read()).value)
    state = LoopState.of(loop)
    assert len(state.mailbox) + len(state._markers) <= 2
    # the callbacks ready to run, private to the loop
    assert len(vars(loop)['_ready']) < 100
    generator.track.stop()
