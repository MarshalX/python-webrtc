#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Random sequences of API calls, to find crashes, deadlocks and leaks. Every step is printed before it runs, so the
output of a crash names the sequence; the same seed replays it.

    python -m tests.chaos --seed 7 --steps 500
"""

import argparse
import asyncio
import gc
import random
import sys
import threading
import time

import webrtc
import wrtc
from tests.helpers import connect

#: How long one step may take: longer is a deadlock
STEP_TIMEOUT = 20


class Chaos:
    def __init__(self, seed: int):
        self.random = random.Random(seed)
        self.connections = []
        self.channels = []
        self.tracks = []
        self.processors = []
        self.generators = []
        self.frames = []
        self.tasks = []

    def pick(self, pool):
        return self.random.choice(pool) if pool else None

    def drop(self, pool):
        if pool:
            pool.pop(self.random.randrange(len(pool)))

    def handler(self):
        """A handler doing something to a random object: closing, raising, referencing (a cycle), collecting"""
        target = self.pick(self.connections + self.channels + self.tracks)
        action = self.random.randrange(5)

        def handle(event):
            if action == 0 and target is not None:
                target.close() if hasattr(target, 'close') else target.stop()
            elif action == 1:
                raise RuntimeError('a handler raises')
            elif action == 2:
                gc.collect()
            elif action == 3:
                return repr(target)

        return handle

    # the steps, each with the objects it works on

    async def new_connection(self):
        self.connections.append(webrtc.RTCPeerConnection())

    async def close_connection(self):
        pc = self.pick(self.connections)
        if pc:
            pc.close()

    async def drop_connection(self):
        self.drop(self.connections)

    async def connect_two(self):
        if len(self.connections) >= 2:
            a, b = self.random.sample(self.connections, 2)
            await connect(a, b, timeout=5)

    async def add_track(self):
        pc, track = self.pick(self.connections), self.pick(self.tracks)
        if pc and track:
            pc.add_track(track)

    async def remove_track(self):
        pc = self.pick(self.connections)
        if pc and pc.get_senders():
            pc.remove_track(self.random.choice(pc.get_senders()))

    async def add_transceiver(self):
        pc = self.pick(self.connections)
        if pc:
            transceiver = pc.add_transceiver(self.random.choice(['audio', 'video']))
            if self.random.random() < 0.3:
                transceiver.stop()
            elif self.random.random() < 0.3:
                transceiver.direction = self.random.choice(list(webrtc.TransceiverDirection)[:4])

    async def negotiate(self):
        pc = self.pick(self.connections)
        if pc:
            await pc.set_local_description()

    async def create_channel(self):
        pc = self.pick(self.connections)
        if pc:
            channel = pc.create_data_channel(f'chaos{self.random.randrange(1000)}')
            channel.on(self.random.choice(['open', 'message', 'close']), self.handler())
            self.channels.append(channel)

    async def send(self):
        channel = self.pick(self.channels)
        if channel:
            channel.send(self.random.choice(['text', b'\x00' * self.random.randrange(70000), bytearray(10)]))

    async def close_channel(self):
        channel = self.pick(self.channels)
        if channel:
            channel.close()

    async def stats(self):
        pc = self.pick(self.connections)
        if pc:
            await pc.get_stats()

    async def restart_ice(self):
        pc = self.pick(self.connections)
        if pc:
            pc.restart_ice()

    async def handle_connection_event(self):
        pc = self.pick(self.connections)
        if pc:
            pc.on(self.random.choice(['connectionstatechange', 'icecandidate', 'track', 'datachannel']), self.handler())

    async def get_user_media(self):
        self.tracks.extend(webrtc.get_user_media(audio=True, video=True).get_tracks())

    async def stop_track(self):
        track = self.pick(self.tracks)
        if track:
            track.stop()

    async def clone_track(self):
        track = self.pick(self.tracks)
        if track:
            self.tracks.append(track.clone())

    async def toggle_track(self):
        track = self.pick(self.tracks)
        if track:
            track.enabled = not track.enabled

    async def drop_track(self):
        self.drop(self.tracks)

    async def new_processor(self):
        track = self.pick(self.tracks)
        if track:
            processor = webrtc.MediaStreamTrackProcessor(track, max_buffer_size=self.random.randrange(4))
            track.on('ended', self.handler())
            self.processors.append((processor, processor.readable.get_reader()))

    async def read(self):
        if self.processors:
            _, reader = self.pick(self.processors)
            try:
                result = await asyncio.wait_for(reader.read(), 0.2)
            except asyncio.TimeoutError:
                return
            if not result.done:
                result.value.close()

    async def cancel_processor(self):
        if self.processors:
            _, reader = self.pick(self.processors)
            await reader.cancel()

    async def drop_processor(self):
        self.drop(self.processors)

    async def new_generator(self):
        if self.random.random() < 0.5:
            generator = webrtc.VideoTrackGenerator()
            self.generators.append((generator.writable.get_writer(), 'video'))
            self.tracks.append(generator.track)
        else:
            generator = webrtc.MediaStreamTrackGenerator('audio')
            self.generators.append((generator.writable.get_writer(), 'audio'))
            self.tracks.append(generator)

    async def write(self):
        if not self.generators:
            return
        writer, kind = self.pick(self.generators)
        if kind == 'video':
            width, height = self.random.choice([(2, 2), (33, 17), (320, 240)])
            chunk = webrtc.VideoFrame(
                bytes(width * height * 4), format='RGBA', coded_width=width, coded_height=height, timestamp=0
            )
        else:
            rate, channels = self.random.choice([(48000, 2), (8000, 1), (44100, 1), (1000, 1), (48000, 20)])
            frames = rate // 100
            chunk = webrtc.AudioData(
                format='s16',
                sample_rate=rate,
                number_of_frames=frames,
                number_of_channels=channels,
                timestamp=0,
                data=bytes(frames * channels * 2),
            )
        await writer.write(chunk)

    async def close_generator(self):
        if self.generators:
            writer, _ = self.pick(self.generators)
            await writer.close()

    async def drop_generator(self):
        self.drop(self.generators)

    async def frame(self):
        fmt = self.random.choice(list(webrtc.VideoPixelFormat))
        width, height = self.random.randrange(1, 40), self.random.randrange(1, 40)
        frame = webrtc.VideoFrame(
            bytes(width * height * 8), format=fmt, coded_width=width, coded_height=height, timestamp=0
        )
        options = self.random.choice([None, {'format': 'RGBA'}, {'format': 'BGRX'}])
        await frame.copy_to(bytearray(frame.allocation_size(options)), options)
        self.frames.append(frame)

    async def use_frame(self):
        frame = self.pick(self.frames)
        if frame:
            self.random.choice([frame.close, lambda: self.frames.append(frame.clone())])()

    async def replace_track(self):
        pc = self.pick(self.connections)
        if pc and pc.get_senders():
            await self.random.choice(pc.get_senders()).replace_track(self.pick(self.tracks + [None]))

    async def set_parameters(self):
        pc = self.pick(self.connections)
        if pc and pc.get_senders():
            sender = self.random.choice(pc.get_senders())
            parameters = sender.get_parameters()
            for encoding in parameters.encodings:
                encoding.active = self.random.random() < 0.8
                encoding.max_bitrate = self.random.choice([None, 30000, 2**31])
            await sender.set_parameters(parameters)

    async def pipe(self):
        track = self.pick([track for track in self.tracks if track.kind == 'video'])
        if track:
            processor = webrtc.MediaStreamTrackProcessor(track)
            generator = webrtc.VideoTrackGenerator()
            self.tracks.append(generator.track)
            self.tasks.append(processor.readable.pipe_through(webrtc.TransformStream()).pipe_to(generator.writable))

    async def constraints(self):
        track = self.pick(self.tracks)
        if track:
            track.get_settings()
            track.apply_constraints(self.random.choice([{'width': 320}, {'frame_rate': 5}, {'width': {'exact': 7}}]))

    async def stream(self):
        tracks = self.random.sample(self.tracks, min(len(self.tracks), 2))
        stream = webrtc.MediaStream(tracks)
        if tracks and self.random.random() < 0.5:
            stream.remove_track(tracks[0])
        stream.get_tracks()

    async def reader_thread(self):
        """A thread reading the objects while the loop goes on"""
        connections, tracks = list(self.connections), list(self.tracks)

        def read():
            for _ in range(50):
                for pc in connections:
                    _ = pc.connection_state, pc.get_transceivers(), pc.sctp
                for track in tracks:
                    _ = track.ready_state, track.muted, track.enabled

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        self.tasks.append(thread)

    async def collect(self):
        gc.collect()

    async def pause(self):
        await asyncio.sleep(self.random.random() * 0.05)

    STEPS = [name for name in dir() if not name.startswith('_') and name not in ('pick', 'drop', 'handler')]

    async def run(self, steps: int):
        loop = asyncio.get_running_loop()
        # handlers raise on purpose
        loop.set_exception_handler(lambda loop, context: None)
        for index in range(steps):
            name = self.random.choice(self.STEPS)
            print(f'{index} {name}', flush=True)
            started = time.monotonic()
            try:
                await asyncio.wait_for(getattr(self, name)(), STEP_TIMEOUT)
            except asyncio.TimeoutError:
                if time.monotonic() - started >= STEP_TIMEOUT:
                    print(f'step {index} {name} is stuck', flush=True)
                    sys.exit(3)
            except Exception as e:  # noqa: BLE001 (misuse is expected, crashes and deadlocks aren't)
                print(f'  {type(e).__name__}: {str(e)[:80]}', flush=True)
        for pc in self.connections:
            pc.close()
        for track in self.tracks:
            track.stop()
        for task in self.tasks:
            if isinstance(task, threading.Thread):
                task.join(STEP_TIMEOUT)
                if task.is_alive():
                    print('a reader thread is stuck', flush=True)
                    sys.exit(3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--steps', type=int, default=300)
    args = parser.parse_args()
    print(f'seed {args.seed}, {args.steps} steps', flush=True)
    asyncio.run(Chaos(args.seed).run(args.steps))
    # the last references may be released on helper threads
    deadline = time.monotonic() + 1
    while wrtc._alive_factories() and time.monotonic() < deadline:
        gc.collect()
        time.sleep(0.05)
    alive = {name: count for name, count in wrtc._alive().items() if count}
    print(f'done, {wrtc._alive_factories()} factories alive, native objects alive: {alive}', flush=True)


if __name__ == '__main__':
    main()
