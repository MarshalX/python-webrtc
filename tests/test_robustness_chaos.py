#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Random sequences of API calls (tests/chaos.py) in processes of their own: no crash, no deadlock.

A failure prints the seed and the steps, replayed with ``python -m tests.chaos --seed <seed> --steps <steps>``.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys

import pytest

import webrtc
from tests import chaos
from tests.helpers import ROOT
from tests.isolation import HUNTING
from tests.timing import seconds


def run_chaos(seed: int, steps: int, timeout: float, *, transforms: bool = False) -> None:
    command = [sys.executable, '-m', 'tests.chaos', '--seed', str(seed), '--steps', str(steps)]
    if transforms:
        command.append('--transforms')
    if HUNTING:
        command.append('--wait-when-stuck')
    try:
        # under make hunt, faulthandler's dump of a hang goes to the job's output
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=None if HUNTING else subprocess.PIPE,
            text=True,
            timeout=None if HUNTING else timeout,
            cwd=ROOT,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        pytest.fail(f'seed {seed} is stuck after:\n{(e.stdout if e.stdout is not None else b"")[-3000:]}')
    output = result.stdout + (result.stderr if result.stderr is not None else '')
    assert result.returncode == 0, f'seed {seed}, exit code {result.returncode}:\n{output[-5000:]}'
    assert 'done' in result.stdout, output[-3000:]


@pytest.mark.asyncio
@pytest.mark.parametrize('step', ['remove_track', 'replace_track', 'set_parameters'])
async def test_sender_steps_survive_a_close_from_another_worker(step: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sender step reads the senders once: another worker's close() between two reads would empty them."""
    get_senders = webrtc.RTCPeerConnection.get_senders

    def closing_get_senders(self: webrtc.RTCPeerConnection) -> list[webrtc.RTCRtpSender]:
        senders = get_senders(self)
        self.close()
        return senders

    state = chaos.Chaos(0)
    pc = webrtc.RTCPeerConnection()
    _ = pc.add_transceiver(webrtc.MediaType.audio)
    state.connections.append(pc)
    monkeypatch.setattr(webrtc.RTCPeerConnection, 'get_senders', closing_get_senders)
    with contextlib.suppress(*chaos.MISUSE):
        await getattr(state, step)()
    assert pc.connection_state == webrtc.RTCPeerConnectionState.closed


@pytest.mark.parametrize('seed', range(2))
def test_chaos(seed: int) -> None:
    run_chaos(seed, steps=150, timeout=seconds(120))


@pytest.mark.parametrize('seed', range(2))
def test_chaos_of_transforms(seed: int) -> None:
    """Transforms, SFrame keys and encoded frames, on connections sending media."""
    run_chaos(seed, steps=150, timeout=seconds(120), transforms=True)


@pytest.mark.stress
@pytest.mark.timeout(900)
@pytest.mark.parametrize('seed', range(100, 120))
def test_chaos_long(seed: int) -> None:
    run_chaos(seed, steps=1000, timeout=seconds(600))


@pytest.mark.stress
@pytest.mark.timeout(900)
@pytest.mark.parametrize('seed', range(200, 210))
def test_chaos_of_transforms_long(seed: int) -> None:
    run_chaos(seed, steps=1000, timeout=seconds(600), transforms=True)
