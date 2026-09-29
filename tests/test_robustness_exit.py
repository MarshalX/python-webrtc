#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The interpreter exits while objects are alive and busy: no hang, no crash."""

import os

import pytest

from tests.helpers import run_isolated

BUSY_AT_EXIT = '''
    import asyncio
    import threading
    import webrtc
    from tests.helpers import connect

    async def main():
        stream = webrtc.get_user_media(audio=True, video=True)
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        for track in stream.get_tracks():
            caller.add_track(track, stream)
        channel = caller.create_data_channel('exit')
        await connect(caller, callee)

        def spin():
            while True:
                _ = caller.connection_state, caller.get_transceivers(), callee.get_receivers()
                try:
                    channel.send('busy')
                except Exception:
                    pass

        threading.Thread(target=spin, daemon=True).start()
        await asyncio.sleep(0.3)
        return caller, callee, channel

    # kept alive until the interpreter finalizes
    objects = asyncio.run(main())
    print('exiting')
'''


@pytest.mark.parametrize('attempt', range(5))
def test_exit_while_objects_are_busy(attempt):
    """Wrappers released by the last collection must not block on threads hung in the GIL"""
    assert 'exiting' in run_isolated(BUSY_AT_EXIT, timeout=30)


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='no fork')
def test_forked_child_leaves_the_objects_of_its_parent_alone():
    """The child of a fork doesn't block on its parent's threads; new objects work (raise on macOS)"""
    output = run_isolated(
        """
        import asyncio
        import gc
        import os
        import sys
        import time
        import warnings
        import webrtc
        from tests.helpers import connect

        warnings.simplefilter('ignore', DeprecationWarning)  # fork with threads

        async def use():
            caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
            track = webrtc.get_user_media(audio=False, video=True).get_tracks()[0]
            caller.add_track(track)
            await asyncio.wait_for(connect(caller, callee), 10)
            reader = webrtc.MediaStreamTrackProcessor(track).readable.get_reader()
            (await asyncio.wait_for(reader.read(), 5)).value.close()
            track.stop()
            caller.close()
            callee.close()

        parent = [webrtc.RTCPeerConnection(), webrtc.get_user_media(audio=True, video=True)]
        asyncio.run(use())
        pid = os.fork()
        if pid == 0:
            parent.clear()
            gc.collect()
            if sys.platform == 'darwin':
                try:
                    webrtc.RTCPeerConnection()
                except RuntimeError:
                    raise SystemExit(0)
                raise SystemExit(1)
            asyncio.run(use())
            raise SystemExit(0)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                print('child exited', os.waitstatus_to_exitcode(status))
                break
            time.sleep(0.05)
        else:
            os.kill(pid, 9)
            print('child is stuck')
        """,
        timeout=60,
    )
    assert 'child exited 0' in output, output
