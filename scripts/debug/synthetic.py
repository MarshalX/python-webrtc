#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""A failure of each kind the hunt tells apart, for ``hunt --self-test``; doesn't import the library.

python -m scripts.debug.synthetic {deadlock,segfault,failure,leak,memory} --seed N
"""

from __future__ import annotations

import argparse
import ctypes
import faulthandler
import signal
import sys
import threading
import time

#: More than the self-test's memory limit
MEMORY_MB = 300


def deadlock(_seed: int) -> None:
    """Blocks forever in native code."""
    lock = threading.Lock()
    lock.acquire()
    lock.acquire()


def segfault(_seed: int) -> None:
    ctypes.string_at(0)


def failure(seed: int) -> None:
    print(f'FAILED tests/test_fake.py::test_fake[{seed}] - AssertionError')
    sys.exit(1)


def leak(_seed: int) -> None:
    print("done, 0 factories alive, native objects alive: {'RTCPeerConnection': 1}")


def memory(_seed: int) -> None:
    """Keeps more memory than allowed, and keeps talking so it isn't a hang."""
    block = b'x' * (MEMORY_MB << 20)
    while True:
        print(f'holding {len(block)} bytes')
        time.sleep(1)


def main() -> None:
    failures = {function.__name__: function for function in (deadlock, segfault, failure, leak, memory)}
    parser = argparse.ArgumentParser()
    parser.add_argument('failure', choices=sorted(failures))
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    if sys.platform != 'win32':
        faulthandler.register(signal.SIGUSR1, all_threads=True)
    failures[args.failure](args.seed)


if __name__ == '__main__':
    main()
