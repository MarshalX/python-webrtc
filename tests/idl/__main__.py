#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Command line for the IDL comparison.

python -m tests.idl             print every difference, marking new (+) and gone (-) ones against expectations.json
python -m tests.idl update      record the current differences as expected
"""

from __future__ import annotations

import argparse
import logging

import webrtc
from tests.idl import expectations
from tests.idl.compare import compare
from tests.idl.spec import load

logger = logging.getLogger(__name__)


def _mark(item: str, changed: set[str]) -> str:
    """+ for a new difference, - for a gone one."""
    if f'+ {item}' in changed:
        return '+'
    if f'- {item}' in changed:
        return '-'
    return ' '


def report(differences: dict[str, list[str]]) -> None:
    expected = expectations.load()
    for name in sorted(differences.keys() | expected.keys()):
        found = differences.get(name, [])
        wanted = expected.get(name, [])
        changed = set(expectations.mismatches(wanted, found))
        logger.info(name)
        for item in sorted(set(found) | set(wanted)):
            logger.info('  %s %s', _mark(item, changed), item)

    total = sum(map(len, differences.values()))
    logger.info('%d differences in %d definitions', total, len(differences))


def main() -> None:
    parser = argparse.ArgumentParser(prog='python -m tests.idl')
    parser.add_argument('command', nargs='?', choices=['report', 'update'], default='report')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    differences = compare(load(), webrtc)
    if args.command == 'update':
        expectations.save(differences)
        logger.info('recorded %d differences', sum(map(len, differences.values())))
    else:
        report(differences)


if __name__ == '__main__':
    main()
