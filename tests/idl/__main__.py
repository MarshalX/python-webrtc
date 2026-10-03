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


def report(differences: dict[str, list[str]]) -> None:
    expected = expectations.load()
    for name in sorted(differences.keys() | expected.keys()):
        changed = set(expectations.mismatches(expected.get(name, []), differences.get(name, [])))
        items = sorted(set(differences.get(name, [])) | set(expected.get(name, [])))
        logger.info(name)
        for item in items:
            mark = '+' if f'+ {item}' in changed else '-' if f'- {item}' in changed else ' '
            logger.info('  %s %s', mark, item)
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
