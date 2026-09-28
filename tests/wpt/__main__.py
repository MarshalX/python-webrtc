#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Command line for the WPT suite.

python -m tests.wpt run <case>              run one case and print every result
python -m tests.wpt update [case ...]       run cases in parallel and record their results as expected
python -m tests.wpt update --repeat 3       the same, running each case 3 times to find flaky tests
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from tests.wpt import runner
from tests.wpt.expectations import Expectations
from tests.wpt.loader import discover


def _print_result(case: str, result: dict):
    harness = result['harness']
    print(f'{case}: harness {harness["status"]}' + (f' ({harness["message"]})' if harness['message'] else ''))
    for test in result['tests']:
        print(f'  {test["status"]:<8} {test["name"]}')
        if test['status'] != 'PASS' and test['message']:
            print(f'           {test["message"]}')
    if result['unsupported']:
        print('  unsupported: ' + ', '.join(result['unsupported']))


def run(args):
    for case in args.cases:
        _print_result(case, runner.run(case))


def update(args):
    expectations = Expectations.load()
    cases = [c for c in args.cases or discover() if not expectations.skip_reason(c)]

    tests = Counter()
    harness = Counter()
    unsupported = Counter()

    def run_repeatedly(case):
        return [runner.run(case) for _ in range(args.repeat)]

    with ThreadPoolExecutor(args.jobs) as pool:
        for done, (case, results) in enumerate(zip(cases, pool.map(run_repeatedly, cases)), 1):
            expectations.record(case, results)
            first = results[0]
            harness[first['harness']['status']] += 1
            tests.update(t['status'] for t in first['tests'])
            unsupported.update(first['unsupported'])
            statuses = '/'.join(sorted({r['harness']['status'] for r in results}))
            print(f'[{done}/{len(cases)}] {statuses:<8} {case}', flush=True)

    expectations.save()

    print(f'\nfiles: {dict(harness)}')
    print(f'tests: {dict(tests)}')
    if unsupported:
        print('unsupported members used by tests:')
        for name, count in unsupported.most_common():
            print(f'  {count:>4}  {name}')


def main():
    parser = argparse.ArgumentParser(prog='python -m tests.wpt')
    commands = parser.add_subparsers(required=True)

    run_parser = commands.add_parser('run', help='run cases and print every result')
    run_parser.add_argument('cases', nargs='+')
    run_parser.set_defaults(func=run)

    update_parser = commands.add_parser('update', help='run cases and record their results in expectations.json')
    update_parser.add_argument('cases', nargs='*', help='defaults to every case not skipped')
    update_parser.add_argument('--jobs', type=int, default=os.cpu_count())
    update_parser.add_argument('--repeat', type=int, default=1, help='runs of each case, to find flaky tests')
    update_parser.set_defaults(func=update)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
