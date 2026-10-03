#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Expected results of the WPT suite, stored in expectations.json.

The file has two sections:
    skip: test files that can't apply to a Python library, with the reason. Maintained by hand.
    results: every result other than PASS (or OK for the harness), per case. Written by `python -m tests.wpt update`.

A result is either one status or, for a flaky test, the list of statuses it is allowed to have, as in WPT
metadata. `update --repeat N` finds flaky tests by running every case several times.

Record them with Python 3.12 or later: before 3.12, async methods start one iteration of the loop later (see
bridge.call_async_method), which can change results that depend on the order of events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Union

from typing_extensions import TypedDict

if TYPE_CHECKING:
    from tests.wpt.runner import CaseResult

PATH = Path(__file__).with_name('expectations.json')

HARNESS_KEY = '[harness]'

# one status, or the statuses a flaky test may have
Expected = Union[str, list[str]]


class _File(TypedDict, total=False):
    skip: dict[str, str]
    results: dict[str, dict[str, Expected]]


def _allowed(expected: str | list[str]) -> list[str]:
    return expected if isinstance(expected, list) else [expected]


def _describe(expected: str | list[str]) -> str:
    return ' or '.join(_allowed(expected))


@dataclass
class Expectations:
    skip: dict[str, str] = field(default_factory=dict)
    results: dict[str, dict[str, str | list[str]]] = field(default_factory=dict)

    @classmethod
    def load(cls) -> Expectations:
        if not PATH.exists():
            return cls()
        data: _File = json.loads(PATH.read_text())
        return cls(skip=data.get('skip', {}), results=data.get('results', {}))

    def save(self) -> None:
        data = {'skip': dict(sorted(self.skip.items())), 'results': dict(sorted(self.results.items()))}
        PATH.write_text(json.dumps(data, indent=2) + '\n')

    def skip_reason(self, case: str) -> str | None:
        return self.skip.get(case.partition('?')[0])

    def record(self, case: str, results: list[CaseResult]) -> None:
        """Records the statuses seen over one or more runs of a case.

        Statuses that differ between runs are recorded as a list. An existing list is kept while it still covers
        every status seen, so a flaky test isn't marked stable just because it happened to behave this time.
        """
        seen: dict[str, set[str]] = {}
        for result in results:
            seen.setdefault(HARNESS_KEY, set()).add(result['harness']['status'])
            for test in result['tests']:
                seen.setdefault(test['name'], set()).add(test['status'])

        previous = self.results.get(case, {})
        entry: dict[str, Expected] = {}
        for name, statuses in seen.items():
            kept = previous.get(name)
            if isinstance(kept, list) and statuses <= set(kept):
                entry[name] = kept
            elif len(statuses) > 1:
                entry[name] = sorted(statuses)
            elif statuses.isdisjoint({'PASS', 'OK'}):
                entry[name] = statuses.pop()

        if len(entry) > 0:
            self.results[case] = dict(sorted(entry.items()))
        else:
            self.results.pop(case, None)

    def mismatches(self, case: str, result: CaseResult) -> list[str]:
        expected = dict(self.results.get(case, {}))
        expected_harness = expected.pop(HARNESS_KEY, 'OK')

        problems: list[str] = []
        harness = result['harness']
        if harness['status'] not in _allowed(expected_harness):
            problems.append(
                f'harness: expected {_describe(expected_harness)}, got {harness["status"]}: {harness["message"]}'
            )

        seen = set()
        for test in result['tests']:
            seen.add(test['name'])
            want = expected.get(test['name'], 'PASS')
            if test['status'] not in _allowed(want):
                problems.append(f'{test["name"]}: expected {_describe(want)}, got {test["status"]}: {test["message"]}')

        problems.extend(
            f'{name}: expected {_describe(expected[name])}, but the test did not run'
            for name in sorted(expected.keys() - seen)
        )
        return problems
