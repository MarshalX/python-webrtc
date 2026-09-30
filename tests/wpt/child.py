#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Runs one web-platform-tests case in this process and prints its result, for tests.wpt.runner."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import pythonmonkey as pm

from tests.wpt import bridge
from tests.wpt.loader import build_scripts, load, split_case
from tests.wpt.runner import (
    HARNESS_STATUSES,
    LONG_TIMEOUT,
    RESULT_PREFIX,
    TEST_STATUSES,
    TIMEOUT,
    CaseResult,
    harness_result,
)

logger = logging.getLogger(__name__)


def _text(value: object) -> str | None:
    # JS null and undefined arrive as PythonMonkey objects
    return value if isinstance(value, str) else None


def _log_unhandled_rejections(loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
    """Logs unhandled rejections instead of PythonMonkey's handler, which stops its timers.

    That would leave the rest of the file hanging. It also reports rejections that get handled later (as testharness
    does), so they are only logged. Any other exception goes to the default handler.
    """
    if isinstance(context.get('exception'), pm.SpiderMonkeyError):
        logger.warning('unhandled rejection: %s', context['exception'])
    else:
        loop.default_exception_handler(context)


async def run_in_process(case: str) -> CaseResult:
    path, variant = split_case(case)
    test_file = load(path)

    loop = asyncio.get_running_loop()
    completed = loop.create_future()
    unsupported: set[str] = set()

    def complete(result: dict) -> None:
        if not completed.done():
            completed.set_result(result)

    bridge.LOOP = loop
    loop.set_exception_handler(_log_unhandled_rejections)

    pm.eval('(env) => { globalThis.__wpt = env; }')({
        'bridge': bridge.EXPORTS,
        'unsupported': unsupported.add,
        'complete': complete,
    })
    pm.eval('(search, pathname) => { globalThis.location = {search, pathname, href: pathname + search}; }')(
        variant, '/' + case.partition('?')[0]
    )

    try:
        # one after another, without giving control to the loop in between
        for script in build_scripts(test_file):
            pm.eval(script)
    except pm.SpiderMonkeyError as e:
        return harness_result('ERROR', str(e))

    timeout = LONG_TIMEOUT if test_file.long_timeout else TIMEOUT
    try:
        result = await asyncio.wait_for(asyncio.shield(completed), timeout)
    except asyncio.TimeoutError:
        # marks unfinished tests as timed out and completes the harness
        pm.eval('timeout')()
        try:
            result = await asyncio.wait_for(completed, 5)
        except asyncio.TimeoutError:
            return harness_result('TIMEOUT', 'the harness did not complete after timing out')

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


def main() -> None:
    result = asyncio.run(run_in_process(sys.argv[1]))
    sys.stdout.write(RESULT_PREFIX + json.dumps(result) + '\n')
    sys.stdout.flush()


if __name__ == '__main__':
    main()
