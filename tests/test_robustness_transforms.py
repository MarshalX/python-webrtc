#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Encoded transforms and SFrame used from many threads, and at exit, while media flows: no crash, no deadlock."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import random
import sys
import threading
import time
from typing import Callable, Union

import pytest

import webrtc
import wrtc
from tests.helpers import connect
from tests.isolation import isolated

KEY = bytes(range(16))
SUITE = webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_80

Frame = Union[webrtc.RTCEncodedVideoFrame, webrtc.RTCEncodedAudioFrame]
Part = Union[webrtc.RTCRtpSender, webrtc.RTCRtpReceiver]

_held: list[Frame | bytes] = []
# kept alive until the interpreter finalizes
_kept: list[object] = []


def _retrieve(future: asyncio.Future[None]) -> None:
    future.add_done_callback(lambda f: f.cancelled() or f.exception())


async def _worker(event: webrtc.RTCTransformEvent) -> None:
    # passes frames through late, holding the last ones
    reader = event.transformer.readable.get_reader()
    writer = event.transformer.writable.get_writer()
    mine: list[Frame] = []
    while not (result := await reader.read()).done:
        assert result.value is not None
        mine.append(result.value)
        _held.append(result.value)
        del _held[:-200]
        if len(mine) > 3:
            _retrieve(writer.write(mine.pop(0)))


def _encryptor(key_id: int = 1) -> webrtc.RTCRtpSFrameEncryptor:
    encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(SUITE))
    encryptor._native_obj.setEncryptionKey(KEY, key_id)
    return encryptor


def _decryptor(key_id: int = 1) -> webrtc.RTCRtpSFrameDecryptor:
    decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(SUITE))
    decryptor._native_obj.addDecryptionKey(KEY, key_id)
    # handlers are registered on a loop
    if threading.current_thread() is threading.main_thread():
        decryptor.on('error', lambda event: _held.append(event.frame))
    return decryptor


async def _call() -> tuple[webrtc.RTCPeerConnection, webrtc.RTCPeerConnection]:
    stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    for track in stream.get_tracks():
        sender = caller.add_track(track)
        sender.transform = _encryptor() if track.kind == 'audio' else webrtc.RTCRtpScriptTransform(_worker)

    def on_track(event: webrtc.RTCTrackEvent) -> None:
        if event.track.kind == 'audio':
            event.receiver.transform = _decryptor()
        else:
            event.receiver.transform = webrtc.RTCRtpScriptTransform(_worker)

    callee.on('track', on_track)
    await connect(caller, callee)
    await asyncio.sleep(0.3)
    return caller, callee


def _start(*targets: Callable[[], None]) -> list[threading.Thread]:
    threads = [threading.Thread(target=target, daemon=True) for target in targets]
    for thread in threads:
        thread.start()
    return threads


async def _join(threads: list[threading.Thread]) -> None:
    loop = asyncio.get_running_loop()
    for thread in threads:
        await loop.run_in_executor(None, thread.join, 20)
        assert not thread.is_alive(), 'stuck'


def _held_natives() -> list[wrtc.RTCEncodedFrame]:
    return [f._native for f in _held.copy() if not isinstance(f, bytes) and f._native is not None]


def _use_held_frames() -> None:
    while True:
        for native in _held_natives():
            native.getData()
            native.getMetadata()


async def _transform_while_frames_are_used() -> None:
    _kept.extend(await _call())
    _start(_use_held_frames)
    await asyncio.sleep(0.2)


@pytest.mark.parametrize('_attempt', range(4))
@isolated
def test_exit_while_frames_are_transformed(_attempt: int) -> None:
    """Frames in flight, queued and held, and threads using them, as the interpreter exits."""
    asyncio.run(_transform_while_frames_are_used())


async def _exit_while_errors_queue() -> None:
    caller, callee = await _call()
    callee.get_receivers()[0].transform = _decryptor(key_id=7)
    await asyncio.sleep(0.2)
    _kept.extend((caller, callee))
    sys.exit(0)


@isolated
def test_exit_from_a_worker() -> None:
    """The interpreter exits while workers wait for frames and SFrame errors queue."""
    asyncio.run(_exit_while_errors_queue())


class _Race:
    def __init__(self, senders: list[webrtc.RTCRtpSender], receivers: list[webrtc.RTCRtpReceiver]) -> None:
        self.parts: list[Part] = [*senders, *receivers]
        self.stop = threading.Event()
        # script transforms need the loop: made on it, set from the threads
        self.spare = [webrtc.RTCRtpScriptTransform(_worker) for _ in range(200)]
        self.streams = [wrtc.SFrameTransform(1, encrypting=True), wrtc.SFrameTransform(1, encrypting=False)]
        self.natives: list[wrtc.RTCEncodedFrame] = []

    def run(self, step: Callable[[random.Random], None]) -> threading.Thread:
        def repeat() -> None:
            rng = random.Random(threading.get_ident())
            while not self.stop.is_set():
                step(rng)

        return _start(repeat)[0]

    def set_transforms(self, rng: random.Random) -> None:
        with contextlib.suppress(webrtc.InvalidStateError):
            self._set_transform(rng.choice(self.parts), rng)
        time.sleep(0.005)

    def _set_transform(self, part: Part, rng: random.Random) -> None:
        choice = rng.randrange(3)
        if choice == 0:
            part.transform = None
        elif choice == 2:
            if isinstance(part, webrtc.RTCRtpSender):
                part.transform = _encryptor()
            else:
                part.transform = _decryptor(rng.randrange(3))
        elif len(self.spare) > 0:
            part.transform = self.spare.pop()

    def rotate_keys(self, rng: random.Random) -> None:
        for part in self.parts:
            native = part._native_obj.transform
            if isinstance(native, wrtc.SFrameTransform):
                key_id = rng.randrange(3)
                if native.encrypting:
                    native.setEncryptionKey(KEY, key_id)
                elif rng.random() < 0.5:
                    native.addDecryptionKey(KEY, key_id)
                else:
                    native.removeDecryptionKey(key_id)
        self.streams[0].setEncryptionKey(KEY, 1)
        self.streams[1].addDecryptionKey(KEY, 1)
        time.sleep(0.001)

    def use_frames(self, rng: random.Random) -> None:
        for part in self.parts:
            native = part._native_obj.transform
            if isinstance(native, wrtc.RTCRtpScriptTransform):
                frame = native.read()
                if frame is not None:
                    self.natives.append(frame)
                    del self.natives[:-100]
                if len(self.natives) > 0:
                    data = rng.choice([None, b'', bytes(rng.randrange(3000))])
                    native.write(rng.choice(self.natives), data)
        for frame in [*self.natives[-10:], *_held_natives()[-10:]]:
            frame.getData()
            frame.getMetadata()
            encrypted = self.streams[0].encrypt(frame.getData())
            self.streams[1].decrypt(encrypted if encrypted is not None else b'')
        time.sleep(0.001)


def _collect(_rng: random.Random) -> None:
    gc.collect()
    time.sleep(0.01)


async def _race() -> None:
    loop = asyncio.get_running_loop()
    caller, callee = await _call()
    race = _Race(caller.get_senders(), callee.get_receivers())
    errors: list[str] = []
    threading.excepthook = lambda args: errors.append(repr(args.exc_value))
    steps = (race.set_transforms, race.set_transforms, race.rotate_keys, race.use_frames, race.use_frames, _collect)
    threads = [race.run(step) for step in steps]
    await asyncio.sleep(3)
    await loop.run_in_executor(None, caller.close)
    callee.close()
    await asyncio.sleep(0.5)
    race.stop.set()
    await _join(threads)
    assert errors == []
    assert len(race.natives) > 0, 'no frame was read'


@isolated(timeout=90)
def test_threads_race_transforms_keys_and_frames() -> None:
    """Transforms set and removed, keys rotated, frames read and written and the connections closed, all at once."""
    asyncio.run(_race())


def _script_transform(pc: webrtc.RTCPeerConnection) -> wrtc.RTCRtpScriptTransform:
    (native,) = [
        sender._native_obj.transform
        for sender in pc.get_senders()
        if isinstance(sender._native_obj.transform, wrtc.RTCRtpScriptTransform)
    ]
    assert isinstance(native, wrtc.RTCRtpScriptTransform)
    return native


async def _share_frames() -> None:
    caller, callee = await _call()
    native = _script_transform(caller)
    stop = threading.Event()
    frames: list[wrtc.RTCEncodedFrame] = []
    written: list[wrtc.RTCEncodedFrame] = []

    def read() -> None:
        while not stop.is_set():
            frame = native.read()
            if frame is not None:
                frames.append(frame)
                del frames[:-50]

    def use() -> None:
        while not stop.is_set():
            for frame in frames.copy():
                frame.getData()
                frame.getMetadata()
                if native.write(frame, None):
                    written.append(frame)

    threads = _start(read, use, use, use)
    await asyncio.sleep(3)
    stop.set()
    await _join(threads)
    assert len(written) == len({id(frame) for frame in written}) > 0
    caller.close()
    callee.close()


@isolated
def test_threads_race_frames_of_one_transformer() -> None:
    """The same frames read, copied and written from several threads: each is given back once at most."""
    asyncio.run(_share_frames())
