#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Random sequences of API calls (tests/chaos.py) in processes of their own: no crash, no deadlock.

A failure prints the seed and the steps, replayed with ``python -m tests.chaos --seed <seed> --steps <steps>``.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.helpers import ROOT


def run_chaos(seed: int, steps: int, timeout: float, *, transforms: bool = False) -> None:
    command = [sys.executable, '-m', 'tests.chaos', '--seed', str(seed), '--steps', str(steps)]
    if transforms:
        command.append('--transforms')
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=ROOT, check=False)
    except subprocess.TimeoutExpired as e:
        pytest.fail(f'seed {seed} is stuck after:\n{(e.stdout if e.stdout is not None else b"")[-3000:]}')
    output = result.stdout + result.stderr
    assert result.returncode == 0, f'seed {seed}, exit code {result.returncode}:\n{output[-5000:]}'
    assert 'done' in result.stdout, output[-3000:]


@pytest.mark.parametrize('seed', range(2))
def test_chaos(seed: int) -> None:
    run_chaos(seed, steps=150, timeout=120)


@pytest.mark.parametrize('seed', range(2))
def test_chaos_of_transforms(seed: int) -> None:
    """Transforms, SFrame keys and encoded frames, on connections sending media."""
    run_chaos(seed, steps=150, timeout=120, transforms=True)


@pytest.mark.stress
@pytest.mark.timeout(900)
@pytest.mark.parametrize('seed', range(100, 120))
def test_chaos_long(seed: int) -> None:
    run_chaos(seed, steps=1000, timeout=600)


@pytest.mark.stress
@pytest.mark.timeout(900)
@pytest.mark.parametrize('seed', range(200, 210))
def test_chaos_of_transforms_long(seed: int) -> None:
    run_chaos(seed, steps=1000, timeout=600, transforms=True)
