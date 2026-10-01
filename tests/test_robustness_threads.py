#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The same objects used from many Python threads at once: no crash, no deadlock, no corruption."""

from __future__ import annotations

import pytest

from tests.helpers import run_isolated


def test_constructors_from_many_threads() -> None:
    """Constructors register their Python object with the GIL: pybind11's registry was corrupted."""
    output = run_isolated(
        """
        import gc
        import threading
        import time
        import webrtc

        track = webrtc.get_user_media(audio=False, video=True).get_tracks()[0]
        stop = threading.Event()
        errors = []

        def construct():
            try:
                while not stop.is_set():
                    webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(track))
                    webrtc.RTCPeerConnection().close()
                    webrtc.RTCIceTransport().stop()
                    gc.collect()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=construct) for _ in range(6)]
        for thread in threads:
            thread.start()
        time.sleep(3)
        stop.set()
        for thread in threads:
            thread.join(30)
            assert not thread.is_alive(), 'stuck'
        track.stop()
        assert not errors, errors
        print('constructed')
        """,
        timeout=90,
    )
    assert 'constructed' in output


@pytest.mark.parametrize('kind', ['video generator', 'audio generator', 'processor'])
def test_released_while_libwebrtc_threads_wait_for_the_gil(kind: str) -> None:
    """A track's proxy released with the GIL deadlocked with the signaling thread."""
    output = run_isolated(
        f"""
        import asyncio
        import gc
        import sys
        import time
        import webrtc
        from tests.helpers import connect

        async def main():
            caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
            channel = caller.create_data_channel('busy')
            opened = asyncio.get_running_loop().create_future()
            channel.on('open', lambda event: opened.done() or opened.set_result(None))
            callee.on('datachannel', lambda event: event.channel.on('message', lambda message: None))
            await connect(caller, callee)
            await opened
            if {kind!r} == 'video generator':
                released = webrtc.VideoTrackGenerator()._native
            elif {kind!r} == 'audio generator':
                released = webrtc.MediaStreamTrackGenerator('audio')
            else:
                init = webrtc.MediaStreamTrackProcessorInit(webrtc.VideoTrackGenerator().track)
                released = webrtc.MediaStreamTrackProcessor(init)
            gc.collect()
            # the signaling thread delivers the messages, waiting for the GIL this thread keeps
            sys.setswitchinterval(1000)
            for _ in range(200):
                channel.send(b'busy')
            end = time.perf_counter() + 0.3
            while time.perf_counter() < end:
                pass
            del released
            gc.collect()
            sys.setswitchinterval(0.005)
            caller.close()
            callee.close()
            print('released')

        asyncio.run(main())
        """,
        timeout=30,
    )
    assert 'released' in output


def test_wrappers_created_and_released_on_many_threads() -> None:
    """Releasing a wrapper with the GIL waited for a holder lock held across a BlockingCall."""
    output = run_isolated(
        """
        import asyncio
        import threading
        import time
        import webrtc
        from tests.helpers import connect

        async def main():
            caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
            channel = caller.create_data_channel('busy')
            opened = asyncio.get_running_loop().create_future()
            channel.on('open', lambda event: opened.done() or opened.set_result(None))
            callee.on('datachannel', lambda event: event.channel.on('message', lambda message: None))
            await connect(caller, callee)
            await opened
            stop = threading.Event()

            def create():
                while not stop.is_set():
                    for track in webrtc.get_user_media(audio=True, video=True).get_tracks():
                        track.stop()

            def release():
                while not stop.is_set():
                    tracks = [webrtc.get_user_media(audio=True, video=False).get_tracks()[0] for _ in range(5)]
                    del tracks

            threads = [threading.Thread(target=f, daemon=True) for f in (create, create, release, release)]
            for thread in threads:
                thread.start()
            end = time.monotonic() + 4
            while time.monotonic() < end:
                for _ in range(100):
                    channel.send(b'busy')
                await asyncio.sleep(0.001)
            stop.set()
            for thread in threads:
                thread.join(20)
                assert not thread.is_alive(), 'stuck'
            caller.close()
            callee.close()
            print('done')

        asyncio.run(main())
        """,
        timeout=60,
    )
    assert 'done' in output


def test_wrappers_created_while_a_description_wraps_them() -> None:
    """A thread creating a wrapper held the holder's lock waiting for the signaling thread, which waited for it."""
    output = run_isolated(
        """
        import asyncio
        import threading
        import time
        import webrtc
        from tests.helpers import exchange_offer_answer

        async def main():
            stream = webrtc.get_user_media(audio=True, video=True)
            stop = threading.Event()

            def create():
                # new transceivers, wrapped on this thread
                while not stop.is_set():
                    pc = webrtc.RTCPeerConnection()
                    for track in stream.get_tracks():
                        pc.add_transceiver(track)
                    pc.get_transceivers()
                    pc.close()

            threads = [threading.Thread(target=create, daemon=True) for _ in range(3)]
            for thread in threads:
                thread.start()
            end = time.monotonic() + 4
            while time.monotonic() < end:
                # new transceivers of the callee, wrapped on the signaling thread by its track events
                caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
                for track in stream.get_tracks():
                    caller.add_transceiver(track)
                await asyncio.wait_for(exchange_offer_answer(caller, callee), 10)
                caller.close()
                callee.close()
            stop.set()
            for thread in threads:
                thread.join(20)
                assert not thread.is_alive(), 'stuck'
            print('done')

        asyncio.run(main())
        """,
        timeout=60,
    )
    assert 'done' in output


def test_objects_of_connections_read_while_they_connect() -> None:
    """Wrapping under a lock of the connection (its SCTP transport, its tracks) waited for the signaling thread."""
    output = run_isolated(
        """
        import asyncio
        import threading
        import time
        import webrtc
        from tests.helpers import connect

        async def main():
            stream = webrtc.get_user_media(audio=True, video=True)
            connections = []
            stop = threading.Event()

            def read():
                while not stop.is_set():
                    for pc in list(connections):
                        _ = pc.sctp, pc.get_transceivers(), pc.get_senders()
                        for receiver in pc.get_receivers():
                            _ = receiver.transport, receiver.track.ready_state
                    stream.get_tracks()

            threads = [threading.Thread(target=read, daemon=True) for _ in range(3)]
            for thread in threads:
                thread.start()
            end = time.monotonic() + 4
            while time.monotonic() < end:
                caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
                connections[:] = [caller, callee]
                for track in stream.get_tracks():
                    caller.add_track(track, stream)
                caller.create_data_channel('read')
                await connect(caller, callee)
                caller.close()
                callee.close()
            stop.set()
            for thread in threads:
                thread.join(20)
                assert not thread.is_alive(), 'stuck'
            print('done')

        asyncio.run(main())
        """,
        timeout=60,
    )
    assert 'done' in output
