#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Runs web-platform-tests cases against python-webrtc in PythonMonkey.

PythonMonkey has one global object per process and WPT helpers declare top-level constants, so each case runs
in a child process: `python -m tests.wpt.child <case>` prints a single ``WPT_RESULT <json>`` line.

A result looks like:
    {
        'harness': {'status': 'OK', 'message': None},
        'tests': [{'name': ..., 'status': 'PASS', 'message': None}, ...],
        'unsupported': ['RTCConfiguration.iceServers', ...],
    }
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

from tests.wpt.loader import load, split_case

REPO_ROOT = Path(__file__).resolve().parents[2]

TEST_STATUSES = ('PASS', 'FAIL', 'TIMEOUT', 'NOTRUN', 'PRECONDITION_FAILED')
HARNESS_STATUSES = ('OK', 'ERROR', 'TIMEOUT', 'PRECONDITION_FAILED')

# Same as WPT in browsers
TIMEOUT = 10
LONG_TIMEOUT = 60

RESULT_PREFIX = 'WPT_RESULT '


class HarnessResult(TypedDict):
    status: str
    message: str | None


class TestResult(TypedDict):
    name: str
    status: str
    message: str | None


class CaseResult(TypedDict):
    harness: HarnessResult
    tests: list[TestResult]
    unsupported: list[str]


def harness_result(status: str, message: str) -> CaseResult:
    return {'harness': {'status': status, 'message': message}, 'tests': [], 'unsupported': []}


def run(case: str) -> CaseResult:
    """Runs a case in a child process. A crash or a hang of the child becomes the harness status."""
    path, _ = split_case(case)
    limit = (LONG_TIMEOUT if load(path).long_timeout else TIMEOUT) + 30
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'tests.wpt.child', case],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=limit,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return harness_result('TIMEOUT', f'the runner did not finish in {limit} seconds')

    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            result: CaseResult = json.loads(line[len(RESULT_PREFIX) :])
            return result
    return harness_result('CRASH', f'exit code {proc.returncode}\n{proc.stderr[-2000:]}')
