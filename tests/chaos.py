#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Random sequences of API calls, to find crashes, deadlocks and leaks.

Every step is logged before it runs, so the output of a crash names the sequence; the same seed replays it.

    python -m tests.chaos --seed 7 --steps 500
    python -m tests.chaos --seed 7 --steps 500 --transforms
    python -m tests.chaos --seed 7 --steps 500 --workers 4
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import contextlib
import gc
import logging
import random
import sys
import threading
import time
from typing import TYPE_CHECKING, ClassVar, Literal, NoReturn, TypeVar

import webrtc
from tests.helpers import connect, copy_frame, register_stack_dump, settled_alive
from webrtc.utils import loops

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

log = logging.getLogger('chaos')

#: How long one step may take: longer is a deadlock
STEP_TIMEOUT = 20

#: What misusing the API raises
MISUSE = (webrtc.PythonWebRTCExceptionBase, ValueError, TypeError, RuntimeError)

T = TypeVar('T')


class State:
    """The objects the steps work on, and what the steps share."""

    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)
        # guards the pools below, shared by --workers
        self.lock = threading.Lock()
        self.connections: list[webrtc.RTCPeerConnection] = []
        self.channels: list[webrtc.RTCDataChannel] = []
        self.tracks: list[webrtc.MediaStreamTrack] = []
        self.processors: list[
            tuple[
                webrtc.MediaStreamTrackProcessor,
                webrtc.ReadableStreamDefaultReader[webrtc.VideoFrame | webrtc.AudioData],
            ]
        ] = []
        self.generators: list[tuple[webrtc.WritableStreamDefaultWriter, str]] = []
        self.frames: list[webrtc.VideoFrame] = []
        self.tasks: list[threading.Thread | asyncio.Future[None]] = []
        self.transformers: list[webrtc.RTCRtpScriptTransformer] = []
        self.encoded: list[webrtc.RTCEncodedVideoFrame | webrtc.RTCEncodedAudioFrame] = []

    def pick(self, pool: list[T]) -> T | None:
        with self.lock:
            return self.random.choice(pool) if len(pool) > 0 else None

    def drop(self, pool: list[T]) -> None:
        with self.lock:
            if len(pool) > 0:
                pool.pop(self.random.randrange(len(pool)))

    def handler(self) -> Callable[[webrtc.Event], str | None]:
        """A handler doing something to a random object: closing, raising, referencing (a cycle), collecting."""
        target = self.pick([*self.connections, *self.channels, *self.tracks])
        action = self.random.randrange(5)
        collected = [float('-inf')]

        def handle(_event: webrtc.Event) -> str | None:
            if action == 0 and target is not None:
                target.stop() if isinstance(target, webrtc.MediaStreamTrack) else target.close()
            elif action == 1:
                msg = 'a handler raises'
                raise RuntimeError(msg)
            # at most once a second: per event, as SFrame errors come for every frame, it would starve the loop
            elif action == 2 and time.monotonic() - collected[0] > 1:
                collected[0] = time.monotonic()
                gc.collect()
            elif action == 3:
                return repr(target)
            return None

        return handle


def steps(cls: type) -> list[str]:
    return [name for name in vars(cls) if not name.startswith('_')]


class ConnectionSteps(State):
    """Steps of connections and channels."""

    async def new_connection(self) -> None:
        self.connections.append(webrtc.RTCPeerConnection())

    async def close_connection(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None:
            pc.close()

    async def drop_connection(self) -> None:
        self.drop(self.connections)

    async def connect_two(self) -> None:
        with self.lock:
            pair = self.random.sample(self.connections, 2) if len(self.connections) >= 2 else None
        if pair is not None:
            await connect(pair[0], pair[1], timeout=5)

    async def add_track(self) -> None:
        pc, track = self.pick(self.connections), self.pick(self.tracks)
        if pc is not None and track is not None:
            pc.add_track(track)

    async def remove_track(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None and len(pc.get_senders()) > 0:
            pc.remove_track(self.random.choice(pc.get_senders()))

    async def add_transceiver(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None:
            transceiver = pc.add_transceiver(self.random.choice(['audio', 'video']))
            if self.random.random() < 0.3:
                transceiver.stop()
            elif self.random.random() < 0.3:
                transceiver.direction = self.random.choice(list(webrtc.RTCRtpTransceiverDirection)[:4])

    async def negotiate(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None:
            await pc.set_local_description()

    async def create_channel(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None:
            channel = pc.create_data_channel(f'chaos{self.random.randrange(1000)}')
            names: list[Literal['open', 'message', 'close']] = ['open', 'message', 'close']
            _ = channel.on(self.random.choice(names), self.handler())
            self.channels.append(channel)

    async def send(self) -> None:
        channel = self.pick(self.channels)
        if channel is not None:
            channel.send(self.random.choice(['text', b'\x00' * self.random.randrange(70000), bytearray(10)]))

    async def close_channel(self) -> None:
        channel = self.pick(self.channels)
        if channel is not None:
            channel.close()

    async def stats(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None:
            await pc.get_stats()

    async def restart_ice(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None:
            pc.restart_ice()

    async def handle_connection_event(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None:
            names: list[Literal['connectionstatechange', 'icecandidate', 'track', 'datachannel']] = [
                'connectionstatechange',
                'icecandidate',
                'track',
                'datachannel',
            ]
            _ = pc.on(self.random.choice(names), self.handler())

    async def replace_track(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None and len(pc.get_senders()) > 0:
            await self.random.choice(pc.get_senders()).replace_track(self.pick([*self.tracks, None]))

    async def set_parameters(self) -> None:
        pc = self.pick(self.connections)
        if pc is not None and len(pc.get_senders()) > 0:
            sender = self.random.choice(pc.get_senders())
            parameters = sender.get_parameters()
            for encoding in parameters.encodings:
                encoding.active = self.random.random() < 0.8
                encoding.max_bitrate = self.random.choice([None, 30000, 2**31])
            await sender.set_parameters(parameters)


class MediaSteps(State):
    """Steps of tracks, processors, generators and frames."""

    async def get_user_media(self) -> None:
        self.tracks.extend(
            (
                await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
            ).get_tracks()
        )

    async def stop_track(self) -> None:
        track = self.pick(self.tracks)
        if track is not None:
            track.stop()

    async def clone_track(self) -> None:
        track = self.pick(self.tracks)
        if track is not None:
            self.tracks.append(track.clone())

    async def toggle_track(self) -> None:
        track = self.pick(self.tracks)
        if track is not None:
            track.enabled = not track.enabled

    async def drop_track(self) -> None:
        self.drop(self.tracks)

    async def new_processor(self) -> None:
        track = self.pick(self.tracks)
        if track is not None:
            processor = webrtc.MediaStreamTrackProcessor(
                webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=self.random.randrange(4))
            )
            track.on('ended', self.handler())
            self.processors.append((processor, processor.readable.get_reader()))

    async def read(self) -> None:
        processor = self.pick(self.processors)
        if processor is None:
            return
        try:
            result = await asyncio.wait_for(processor[1].read(), 0.2)
        except asyncio.TimeoutError:
            return
        if not result.done:
            # the processor's readable is typed ReadableStream[object]
            assert isinstance(result.value, (webrtc.VideoFrame, webrtc.AudioData))
            result.value.close()

    async def cancel_processor(self) -> None:
        processor = self.pick(self.processors)
        if processor is not None:
            await processor[1].cancel()

    async def drop_processor(self) -> None:
        self.drop(self.processors)

    async def new_generator(self) -> None:
        if self.random.random() < 0.5:
            generator = webrtc.VideoTrackGenerator()
            self.generators.append((generator.writable.get_writer(), 'video'))
            self.tracks.append(generator.track)
        else:
            generator = webrtc.MediaStreamTrackGenerator('audio')
            self.generators.append((generator.writable.get_writer(), 'audio'))
            self.tracks.append(generator)

    async def write(self) -> None:
        generator = self.pick(self.generators)
        if generator is None:
            return
        writer, kind = generator
        if kind == 'video':
            width, height = self.random.choice([(2, 2), (33, 17), (320, 240)])
            chunk = webrtc.VideoFrame(
                bytes(width * height * 4),
                webrtc.VideoFrameBufferInit(format='RGBA', coded_width=width, coded_height=height, timestamp=0),
            )
        else:
            rate, channels = self.random.choice([(48000, 2), (8000, 1), (44100, 1), (1000, 1), (48000, 20)])
            frames = rate // 100
            chunk = webrtc.AudioData(
                webrtc.AudioDataInit(
                    format='s16',
                    sample_rate=rate,
                    number_of_frames=frames,
                    number_of_channels=channels,
                    timestamp=0,
                    data=bytes(frames * channels * 2),
                )
            )
        await writer.write(chunk)

    async def close_generator(self) -> None:
        generator = self.pick(self.generators)
        if generator is not None:
            await generator[0].close()

    async def drop_generator(self) -> None:
        self.drop(self.generators)

    async def frame(self) -> None:
        fmt = self.random.choice(list(webrtc.VideoPixelFormat))
        width, height = self.random.randrange(1, 40), self.random.randrange(1, 40)
        frame = webrtc.VideoFrame(
            bytes(width * height * 8),
            webrtc.VideoFrameBufferInit(format=fmt, coded_width=width, coded_height=height, timestamp=0),
        )
        options = self.random.choice([None, *(webrtc.VideoFrameCopyToOptions(format=f) for f in ('RGBA', 'BGRX'))])
        await frame.copy_to(bytearray(frame.allocation_size(options)), options)
        self.frames.append(frame)

    async def use_frame(self) -> None:
        frame = self.pick(self.frames)
        if frame is not None:
            self.random.choice([frame.close, lambda: self.frames.append(frame.clone())])()

    async def pipe(self) -> None:
        track = self.pick([video for video in self.tracks if video.kind == 'video'])
        if track is not None:
            processor = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
            generator = webrtc.VideoTrackGenerator()
            self.tracks.append(generator.track)
            self.tasks.append(processor.readable.pipe_through(webrtc.TransformStream()).pipe_to(generator.writable))

    async def constraints(self) -> None:
        track = self.pick(self.tracks)
        if track is not None:
            track.get_settings()
            track.apply_constraints(
                self.random.choice([
                    webrtc.MediaTrackConstraints(width=320),
                    webrtc.MediaTrackConstraints(frame_rate=5),
                    webrtc.MediaTrackConstraints(width=webrtc.ConstrainULongRange(exact=7)),
                ])
            )

    async def stream(self) -> None:
        with self.lock:
            tracks = self.random.sample(self.tracks, min(len(self.tracks), 2))
        stream = webrtc.MediaStream(tracks)
        if len(tracks) > 0 and self.random.random() < 0.5:
            stream.remove_track(tracks[0])
        stream.get_tracks()


class TransformSteps(State):
    """Steps of encoded transforms, SFrame and encoded frames."""

    def _parts(self) -> list[webrtc.RTCRtpSender | webrtc.RTCRtpReceiver]:
        return [part for pc in self.connections for part in (*pc.get_senders(), *pc.get_receivers())]

    def _worker(self) -> Callable[[webrtc.RTCTransformEvent], Coroutine[object, object, None]]:
        """Passes frames through, drops them, holds them or never reads."""
        mode = self.random.choice(['pass', 'drop', 'hold', 'idle'])

        async def worker(event: webrtc.RTCTransformEvent) -> None:
            transformer = event.transformer
            self.transformers.append(transformer)
            if mode == 'idle':
                return
            reader = transformer.readable.get_reader()
            writer = transformer.writable.get_writer()
            while True:
                result = await reader.read()
                if result.done or result.value is None:
                    return
                if mode == 'hold' and len(self.encoded) < 200:
                    self.encoded.append(result.value)
                elif mode == 'pass':
                    # rejected once the transform is removed
                    writer.write(result.value).add_done_callback(lambda f: f.cancelled() or f.exception())

        return worker

    async def script_transform(self) -> None:
        part = self.pick(self._parts())
        if part is not None:
            part.transform = webrtc.RTCRtpScriptTransform(self._worker())

    async def sframe_transform(self) -> None:
        part = self.pick(self._parts())
        if part is None:
            return
        suite = self.random.choice(list(webrtc.SFrameCipherSuite))
        key = bytes(self.random.randrange(256) for _ in range(self.random.choice([0, 16, 32])))
        if isinstance(part, webrtc.RTCRtpSender):
            encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(suite))
            if self.random.random() < 0.8:
                await encryptor.set_encryption_key(key, self.random.randrange(4))
            part.transform = encryptor
        else:
            decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(suite))
            await decryptor.add_decryption_key(key, self.random.randrange(4))
            decryptor.on('error', self.random.choice([self.handler(), self._keep_frame]))
            part.transform = decryptor

    def _keep_frame(self, event: webrtc.SFrameTransformErrorEvent) -> None:
        if isinstance(event.frame, (webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame)):
            self.encoded.append(event.frame)

    async def remove_transform(self) -> None:
        part = self.pick(self._parts())
        if part is not None:
            part.transform = None

    async def rotate_key(self) -> None:
        part = self.pick(self._parts())
        transform = part.transform if part is not None else None
        key, key_id = bytes(range(self.random.choice([1, 16]))), self.random.randrange(4)
        if isinstance(transform, webrtc.RTCRtpSFrameEncryptor):
            await transform.set_encryption_key(key, key_id)
        elif isinstance(transform, webrtc.RTCRtpSFrameDecryptor):
            if self.random.random() < 0.5:
                await transform.add_decryption_key(key, key_id)
            else:
                await transform.remove_decryption_key(key_id)

    async def write_frame(self) -> None:
        """Writes a held frame, or a copy, to any transformer: frames of others are dropped."""
        frame, transformer = self.pick(self.encoded), self.pick(self.transformers)
        if frame is None or transformer is None:
            return
        if self.random.random() < 0.3:
            frame = copy_frame(frame)
        if self.random.random() < 0.5:
            frame.data = bytearray(self.random.randrange(2000))
        if self.random.random() < 0.5 and frame._native is not None:
            # natively, past the checks of Python
            transformer._native_obj.write(frame._native, None)
            return
        if not transformer.writable.locked:
            writer = transformer.writable.get_writer()
            writer.write(frame).add_done_callback(lambda f: f.cancelled() or f.exception())
            writer.release_lock()

    async def use_encoded_frame(self) -> None:
        frame = self.pick(self.encoded)
        if frame is not None:
            _ = frame.data, frame.get_metadata()
            if self.random.random() < 0.3:
                self.encoded.append(copy_frame(frame))
            if self.random.random() < 0.3:
                self.drop(self.encoded)

    async def key_frame(self) -> None:
        transformer = self.pick(self.transformers)
        if transformer is not None:
            request = self.random.choice([transformer.generate_key_frame, transformer.send_key_frame_request])
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(request(), 0.2)

    async def sframe_stream(self) -> None:
        suite = self.random.choice(list(webrtc.SFrameCipherSuite))
        encryptor = webrtc.SFrameEncryptorStream(webrtc.SFrameTransformOptions(suite))
        decryptor = webrtc.SFrameDecryptorStream(webrtc.SFrameTransformOptions(suite))
        decryptor.on('error', self.handler())
        await encryptor.set_encryption_key(b'key', 5)
        await decryptor.add_decryption_key(b'key', self.random.choice([5, 6]))
        writer = encryptor.writable.get_writer()
        chunks = [bytes(self.random.randrange(100)), *(f for f in self.encoded[-3:] if self.random.random() < 0.5)]
        for chunk in chunks:
            writer.write(chunk).add_done_callback(lambda f: f.cancelled() or f.exception())
        if self.random.random() < 0.5:
            reader = encryptor.readable.pipe_through(decryptor).get_reader()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(reader.read(), 0.2)

    async def drop_transformer(self) -> None:
        self.drop(self.transformers)


class LoopSteps(State):
    """Steps of threads, the garbage collector and the loop."""

    async def reader_thread(self) -> None:
        """A thread reading the objects while the loop goes on."""
        connections, tracks = list(self.connections), list(self.tracks)

        def read() -> None:
            for _ in range(50):
                for pc in connections:
                    _ = pc.connection_state, pc.get_transceivers(), pc.sctp
                for track in tracks:
                    _ = track.ready_state, track.muted, track.enabled

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        self.tasks.append(thread)

    @staticmethod
    async def collect() -> None:
        gc.collect()

    async def pause(self) -> None:
        await asyncio.sleep(self.random.random() * 0.05)


class Chaos(ConnectionSteps, MediaSteps, TransformSteps, LoopSteps):
    """Every step, run in a random sequence."""

    STEPS: ClassVar[list[str]] = sorted([
        *steps(ConnectionSteps),
        *steps(MediaSteps),
        *steps(TransformSteps),
        *steps(LoopSteps),
    ])
    #: The steps of transforms, and those getting media to flow through them
    TRANSFORM_STEPS: ClassVar[list[str]] = sorted([
        *steps(TransformSteps),
        *('new_connection', 'close_connection', 'drop_connection', 'connect_two', 'add_track', 'get_user_media'),
        *steps(LoopSteps),
    ])

    def __init__(self, seed: int, *, transforms: bool = False, wait_when_stuck: bool = False, workers: int = 1) -> None:
        super().__init__(seed)
        self.steps = self.TRANSFORM_STEPS if transforms else self.STEPS
        self.wait_when_stuck = wait_when_stuck
        self.workers = workers
        self._finished = 0

    async def run(self, count: int, worker: int = 0) -> None:
        """Runs count steps; the last worker to finish cleans up."""
        # handlers raise on purpose
        asyncio.get_running_loop().set_exception_handler(lambda _loop, _context: None)
        for index in range(count):
            await self.step(index, self.random.choice(self.steps), worker)
        with self.lock:
            self._finished += 1
            last = self._finished == self.workers
        if last:
            self._finish()

    def _finish(self) -> None:
        for pc in self.connections:
            pc.close()
        for track in self.tracks:
            track.stop()
        for task in self.tasks:
            if isinstance(task, threading.Thread):
                task.join(STEP_TIMEOUT)
                if task.is_alive():
                    self._stuck('a reader thread')

    async def step(self, index: int, name: str, worker: int = 0) -> None:
        log.info('%s%d %s', f'worker {worker} ' if self.workers > 1 else '', index, name)
        started = time.monotonic()
        try:
            run: Callable[[], Coroutine[object, object, None]] = getattr(self, name)
            await asyncio.wait_for(run(), STEP_TIMEOUT)
        # a step timing out, or connect_two's wait (a builtin TimeoutError before 3.11)
        except (asyncio.TimeoutError, TimeoutError):
            if time.monotonic() - started >= STEP_TIMEOUT:
                self._stuck(f'step {index} {name}')
        # misuse is expected, crashes and deadlocks aren't
        except MISUSE as e:
            log.info('  %s: %s', type(e).__name__, str(e)[:80])
        # an operation on a connection another step closed is aborted, neither resolved nor rejected
        except asyncio.CancelledError:
            log.info('  CancelledError: closed meanwhile')

    def _stuck(self, what: str) -> NoReturn:
        log.info('%s is stuck', what)
        if not self.wait_when_stuck:
            sys.exit(3)
        # until the runner has taken the stacks and aborts
        while True:
            time.sleep(60)


def _run(args: argparse.Namespace) -> None:
    """Runs the steps here, or on --workers threads with a loop each."""
    chaos = Chaos(args.seed, transforms=args.transforms, wait_when_stuck=args.wait_when_stuck, workers=args.workers)
    if args.workers == 1:
        asyncio.run(chaos.run(args.steps))
        return

    def work(worker: int, count: int) -> None:
        asyncio.run(chaos.run(count, worker))

    workers: int = args.workers
    share, extra = divmod(int(args.steps), workers)
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        runs = [pool.submit(work, worker, share + (1 if worker < extra else 0)) for worker in range(workers)]
        # a failed or exited worker (stuck step) ends the run too
        for run in runs:
            run.result()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--steps', type=int, default=300)
    parser.add_argument('--transforms', action='store_true', help='the steps of transforms only, and media for them')
    parser.add_argument(
        '--workers', type=int, default=1, help='threads with an event loop each, running steps over the same objects'
    )
    parser.add_argument(
        '--wait-when-stuck',
        action='store_true',
        help='on a deadlock, wait to be inspected (make hunt) instead of exiting',
    )
    args = parser.parse_args()
    register_stack_dump()
    logging.basicConfig(stream=sys.stdout, format='%(message)s', level=logging.INFO)
    log.info('seed %d, %d steps', args.seed, args.steps)
    if args.workers > 1:
        log.info('%d workers', args.workers)
    _run(args)
    # the last references may be released on helper threads
    alive, factories = settled_alive(lambda alive, factories: factories == 0 and not any(alive.values()))
    alive = {name: count for name, count in alive.items() if count != 0}
    log.info('done, %d factories alive, native objects alive: %s', factories, alive)
    # a closed loop releases everything; make hunt files this as a leak
    if factories != 0 or len(alive) > 0:
        sys.exit(1)
    if len(loops.mismatches) > 0:
        log.info('the roots checks failed:\n%s', '\n'.join(loops.mismatches))
        sys.exit(1)


if __name__ == '__main__':
    main()
