#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Compares the public API with the WebIDL of the WPT checkout and the differences with expectations.json.

A definition fails when its differences change in either direction: run `python -m tests.idl update` after an
intended change and commit expectations.json with it.
"""

from __future__ import annotations

import pytest

import webrtc
from tests.idl import expectations
from tests.idl.compare import compare
from tests.idl.spec import AVAILABLE, load

pytestmark = pytest.mark.skipif(not AVAILABLE, reason='needs Python 3.10+, the WPT checkout and PythonMonkey')

SPEC = load() if AVAILABLE else None
EXPECTED = expectations.load()


@pytest.fixture(scope='module')
def differences() -> dict[str, list[str]]:
    return compare(SPEC, webrtc)


@pytest.mark.parametrize('name', sorted(set(SPEC.definitions) | set(EXPECTED)) if SPEC else [])
def test_definition(name: str, differences: dict[str, list[str]]) -> None:
    problems = expectations.mismatches(EXPECTED.get(name, []), differences.get(name, []))
    assert not problems, '\n'.join([*problems, 'run `python -m tests.idl update` if the change is intended'])
