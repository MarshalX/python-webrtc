#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Runs the original web-platform-tests against python-webrtc and compares results with expectations.json.

A case fails when any result differs from its expectation in either direction, so a fixed test has to be
recorded as well: run `python -m tests.wpt update <case>` and commit the change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

pytest.importorskip('pythonmonkey')

from tests.wpt import runner
from tests.wpt.expectations import Expectations
from tests.wpt.loader import WPT_ROOT, discover

pytestmark = pytest.mark.skipif(not WPT_ROOT.is_dir(), reason='no wpt checkout, see tests/wpt/README.md')

expectations = Expectations.load()


def _cases() -> list[str | ParameterSet]:
    if not WPT_ROOT.is_dir():
        return []
    return [
        pytest.param(case, marks=pytest.mark.skip(reason=reason))
        if (reason := expectations.skip_reason(case))
        else case
        for case in discover()
    ]


@pytest.mark.parametrize('case', _cases())
def test_wpt(case: str) -> None:
    problems = expectations.mismatches(case, runner.run(case))
    if problems:
        pytest.fail('\n'.join(problems), pytrace=False)
