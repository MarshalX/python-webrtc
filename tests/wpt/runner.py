#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Runs web-platform-tests cases against python-webrtc in PythonMonkey.

PythonMonkey has one global object per process and WPT helpers declare top-level constants, so each case runs
in a child process: `python -m tests.wpt.runner <case>` prints a single ``WPT_RESULT <json>`` line.

A result looks like:
    {
        'harness': {'status': 'OK', 'message': None},
        'tests': [{'name': ..., 'status': 'PASS', 'message': None}, ...],
        'unsupported': ['RTCConfiguration.iceServers', ...],
    }
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from tests.wpt.loader import build_script, load, split_case

REPO_ROOT = Path(__file__).resolve().parents[2]

TEST_STATUSES = ('PASS', 'FAIL', 'TIMEOUT', 'NOTRUN', 'PRECONDITION_FAILED')
HARNESS_STATUSES = ('OK', 'ERROR', 'TIMEOUT', 'PRECONDITION_FAILED')

# Same as WPT in browsers
TIMEOUT = 10
LONG_TIMEOUT = 60

RESULT_PREFIX = 'WPT_RESULT '


def _harness_result(status: str, message: str) -> dict:
    return {'harness': {'status': status, 'message': message}, 'tests': [], 'unsupported': []}


def _text(value):
    # JS null and undefined arrive as PythonMonkey objects
    return value if isinstance(value, str) else None


async def run_in_process(case: str) -> dict:
    import pythonmonkey as pm

    from tests.wpt import bridge

    path, variant = split_case(case)
    test_file = load(path)

    loop = asyncio.get_running_loop()
    completed = loop.create_future()
    unsupported = set()

    def complete(result):
        if not completed.done():
            completed.set_result(result)

    pm.eval('(env) => { globalThis.__wpt = env; }')(
        {'bridge': bridge.EXPORTS, 'unsupported': unsupported.add, 'complete': complete}
    )
    pm.eval('(search, pathname) => { globalThis.location = {search, pathname, href: pathname + search}; }')(
        variant, '/' + case.partition('?')[0]
    )

    try:
        pm.eval(build_script(test_file))
    except pm.SpiderMonkeyError as e:
        return _harness_result('ERROR', str(e))

    timeout = LONG_TIMEOUT if test_file.long_timeout else TIMEOUT
    try:
        result = await asyncio.wait_for(asyncio.shield(completed), timeout)
    except asyncio.TimeoutError:
        # Marks unfinished tests as timed out and completes the harness, as a browser does
        pm.eval('timeout')()
        try:
            result = await asyncio.wait_for(completed, 5)
        except asyncio.TimeoutError:
            return _harness_result('TIMEOUT', 'the harness did not complete after timing out')

    return {
        'harness': {
            'status': HARNESS_STATUSES[int(result['harness']['status'])],
            'message': _text(result['harness']['message']),
        },
        'tests': [
            {'name': t['name'], 'status': TEST_STATUSES[int(t['status'])], 'message': _text(t['message'])}
            for t in result['tests']
        ],
        'unsupported': sorted(unsupported),
    }


def run(case: str) -> dict:
    """Runs a case in a child process. A crash or a hang of the child becomes the harness status."""
    path, _ = split_case(case)
    limit = (LONG_TIMEOUT if load(path).long_timeout else TIMEOUT) + 30
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'tests.wpt.runner', case],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=limit,
        )
    except subprocess.TimeoutExpired:
        return _harness_result('TIMEOUT', f'the runner did not finish in {limit} seconds')

    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            return json.loads(line[len(RESULT_PREFIX) :])
    return _harness_result('CRASH', f'exit code {proc.returncode}\n{proc.stderr[-2000:]}')


def main():
    result = asyncio.run(run_in_process(sys.argv[1]))
    print(RESULT_PREFIX + json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
