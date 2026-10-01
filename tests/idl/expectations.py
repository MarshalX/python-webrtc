#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The known differences between the IDL and the package, stored in expectations.json by definition name.

Written by `python -m tests.idl update`. A test fails when the differences of a definition change in either
direction, so a fixed difference has to be recorded as well as a new one.
"""

from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).with_name('expectations.json')


def load() -> dict[str, list[str]]:
    return json.loads(PATH.read_text()) if PATH.exists() else {}


def save(differences: dict[str, list[str]]) -> None:
    PATH.write_text(json.dumps(dict(sorted(differences.items())), indent=2) + '\n')


def mismatches(expected: list[str], actual: list[str]) -> list[str]:
    """The differences that are new, marked with +, and those that are gone, marked with -."""
    return [f'+ {item}' for item in sorted(set(actual) - set(expected))] + [
        f'- {item}' for item in sorted(set(expected) - set(actual))
    ]
