#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Encoded transforms and SFrame used from many threads, and at exit, while media flows: no crash, no deadlock."""

from __future__ import annotations

import pytest

from tests.helpers import run_isolated

# Connections sending audio and video through script transforms and SFrame both ways, defined in the scripts
SETUP = """
    import asyncio
    import gc
    import random
    import threading
    import time
    import webrtc
    import wrtc
    from tests.helpers import connect

    KEY = bytes(range(16))
    SUITE = webrtc.SFrameCipherSuite.AES_128_CTR_HMAC_SHA256_80
    held = []

    def handled(future):
        future.add_done_callback(lambda f: f.cancelled() or f.exception())

    async def worker(event):
        # passes frames through late, holding the last ones
        reader = event.transformer.readable.get_reader()
        writer = event.transformer.writable.get_writer()
        mine = []
        while True:
            result = await reader.read()
            if result.done:
                return
            mine.append(result.value)
            held.append(result.value)
            del held[:-200]
            if len(mine) > 3:
                handled(writer.write(mine.pop(0)))

    def encryptor(key_id=1):
        encryptor = webrtc.RTCRtpSFrameEncryptor(webrtc.RTCRtpSFrameEncryptorOptions(SUITE))
        encryptor._native_obj.setEncryptionKey(KEY, key_id)
        return encryptor

    def decryptor(key_id=1):
        decryptor = webrtc.RTCRtpSFrameDecryptor(webrtc.SFrameTransformOptions(SUITE))
        decryptor._native_obj.addDecryptionKey(KEY, key_id)
        # handlers are registered on a loop
        if threading.current_thread() is threading.main_thread():
            decryptor.on('error', lambda event: held.append(event.frame))
        return decryptor

    async def call():
        stream = await webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(audio=True, video=True))
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        for track in stream.get_tracks():
            sender = caller.add_track(track)
            sender.transform = encryptor() if track.kind == 'audio' else webrtc.RTCRtpScriptTransform(worker)

        def on_track(event):
            kind = event.track.kind
            event.receiver.transform = decryptor() if kind == 'audio' else webrtc.RTCRtpScriptTransform(worker)

        callee.on('track', on_track)
        await connect(caller, callee)
        await asyncio.sleep(0.3)
        return caller, callee
"""


@pytest.mark.parametrize('_attempt', range(4))
def test_exit_while_frames_are_transformed(_attempt: int) -> None:
    """Frames in flight, queued and held, and threads using them, as the interpreter exits."""
    output = run_isolated(
        SETUP
        + """
    def spin():
        while True:
            for frame in list(held):
                native = frame._native
                if native is not None:
                    native.getData()
                    native.getMetadata()

    async def main():
        caller, callee = await call()
        threading.Thread(target=spin, daemon=True).start()
        await asyncio.sleep(0.2)
        return caller, callee

    # kept alive until the interpreter finalizes
    objects = asyncio.run(main())
    print('exiting')
    """,
        timeout=60,
    )
    assert 'exiting' in output


def test_exit_from_a_worker() -> None:
    """The interpreter exits while workers wait for frames and SFrame errors queue."""
    output = run_isolated(
        SETUP
        + """
    import os
    import sys

    async def main():
        caller, callee = await call()
        callee.get_receivers()[0].transform = decryptor(key_id=7)
        await asyncio.sleep(0.2)
        print('exiting', flush=True)
        sys.exit(0)

    asyncio.run(main())
    """,
        timeout=60,
    )
    assert 'exiting' in output


def test_threads_race_transforms_keys_and_frames() -> None:
    """Transforms set and removed, keys rotated, frames read and written and the connections closed, all at once."""
    output = run_isolated(
        SETUP
        + """
    stop = threading.Event()
    errors = []

    def guarded(function):
        def run():
            rng = random.Random(threading.get_ident())
            try:
                while not stop.is_set():
                    function(rng)
            except Exception as e:
                errors.append(repr(e))
        return run

    async def main():
        loop = asyncio.get_running_loop()
        caller, callee = await call()
        senders, receivers = caller.get_senders(), callee.get_receivers()
        # script transforms need the loop: made on it, set from the threads
        spare = [webrtc.RTCRtpScriptTransform(worker) for _ in range(200)]
        streams = [wrtc.SFrameTransform(1, True), wrtc.SFrameTransform(1, False)]
        natives = []

        def set_transforms(rng):
            part = rng.choice(senders + receivers)
            choice = rng.randrange(3)
            try:
                if choice == 0:
                    part.transform = None
                elif choice == 1 and spare:
                    part.transform = spare.pop()
                elif choice == 2:
                    part.transform = encryptor() if part in senders else decryptor(rng.randrange(3))
            except webrtc.InvalidStateError:
                pass
            time.sleep(0.005)

        def rotate_keys(rng):
            for part in senders + receivers:
                native = part._native_obj.transform
                if isinstance(native, wrtc.SFrameTransform):
                    key_id = rng.randrange(3)
                    if native.encrypting:
                        native.setEncryptionKey(KEY, key_id)
                    elif rng.random() < 0.5:
                        native.addDecryptionKey(KEY, key_id)
                    else:
                        native.removeDecryptionKey(key_id)
            for stream in streams:
                stream.setEncryptionKey(KEY, 1) if stream.encrypting else stream.addDecryptionKey(KEY, 1)
            time.sleep(0.001)

        def frames(rng):
            for part in senders + receivers:
                native = part._native_obj.transform
                if isinstance(native, wrtc.RTCRtpScriptTransform):
                    frame = native.read()
                    if frame is not None:
                        natives.append(frame)
                        del natives[:-100]
                    if natives:
                        data = rng.choice([None, b'', bytes(rng.randrange(3000))])
                        native.write(rng.choice(natives), data)
            for frame in [*natives[-10:], *(f._native for f in held[-10:] if f._native is not None)]:
                frame.getData()
                frame.getMetadata()
                streams[1].decrypt(streams[0].encrypt(frame.getData()) or b'')
            time.sleep(0.001)

        def collect(_rng):
            gc.collect()
            time.sleep(0.01)

        threads = [
            threading.Thread(target=guarded(f), daemon=True)
            for f in (set_transforms, set_transforms, rotate_keys, frames, frames, collect)
        ]
        for thread in threads:
            thread.start()
        await asyncio.sleep(3)
        await loop.run_in_executor(None, caller.close)
        callee.close()
        await asyncio.sleep(0.5)
        stop.set()
        for thread in threads:
            await loop.run_in_executor(None, thread.join, 20)
            assert not thread.is_alive(), 'stuck'
        assert not errors, errors
        assert natives, 'no frame was read'
        print('done')

    asyncio.run(main())
    """,
        timeout=90,
    )
    assert 'done' in output


def test_threads_race_frames_of_one_transformer() -> None:
    """The same frames read, copied and written from several threads: each is given back once at most."""
    output = run_isolated(
        SETUP
        + """
    async def main():
        loop = asyncio.get_running_loop()
        caller, callee = await call()
        native = caller.get_senders()[1]._native_obj.transform
        if not isinstance(native, wrtc.RTCRtpScriptTransform):
            native = caller.get_senders()[0]._native_obj.transform
        stop = threading.Event()
        frames = []
        written = []

        def read():
            while not stop.is_set():
                frame = native.read()
                if frame is not None:
                    frames.append(frame)
                    del frames[:-50]

        def use():
            while not stop.is_set():
                for frame in list(frames):
                    frame.getData()
                    frame.getMetadata()
                    if native.write(frame, None):
                        written.append(frame)

        threads = [threading.Thread(target=f, daemon=True) for f in (read, use, use, use)]
        for thread in threads:
            thread.start()
        await asyncio.sleep(3)
        stop.set()
        for thread in threads:
            await loop.run_in_executor(None, thread.join, 20)
            assert not thread.is_alive(), 'stuck'
        assert len(written) == len({id(frame) for frame in written}) > 0
        caller.close()
        callee.close()
        print('done')

    asyncio.run(main())
    """,
        timeout=60,
    )
    assert 'done' in output
