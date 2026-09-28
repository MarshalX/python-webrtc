#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
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
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PATH = Path(__file__).with_name('expectations.json')

HARNESS_KEY = '[harness]'


def _allowed(expected) -> list[str]:
    return expected if isinstance(expected, list) else [expected]


def _describe(expected) -> str:
    return ' or '.join(_allowed(expected))


@dataclass
class Expectations:
    skip: dict[str, str] = field(default_factory=dict)
    results: dict[str, dict[str, str | list[str]]] = field(default_factory=dict)

    @classmethod
    def load(cls) -> Expectations:
        if not PATH.exists():
            return cls()
        data = json.loads(PATH.read_text())
        return cls(skip=data.get('skip', {}), results=data.get('results', {}))

    def save(self):
        data = {'skip': dict(sorted(self.skip.items())), 'results': dict(sorted(self.results.items()))}
        PATH.write_text(json.dumps(data, indent=2) + '\n')

    def skip_reason(self, case: str) -> str | None:
        return self.skip.get(case.partition('?')[0])

    def record(self, case: str, results: list[dict]):
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
        entry = {}
        for name, statuses in seen.items():
            kept = previous.get(name)
            if isinstance(kept, list) and statuses <= set(kept):
                entry[name] = kept
            elif len(statuses) > 1:
                entry[name] = sorted(statuses)
            elif statuses.isdisjoint({'PASS', 'OK'}):
                entry[name] = statuses.pop()

        if entry:
            self.results[case] = dict(sorted(entry.items()))
        else:
            self.results.pop(case, None)

    def mismatches(self, case: str, result: dict) -> list[str]:
        expected = dict(self.results.get(case, {}))
        expected_harness = expected.pop(HARNESS_KEY, 'OK')

        problems = []
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

        for name in sorted(expected.keys() - seen):
            problems.append(f'{name}: expected {_describe(expected[name])}, but the test did not run')
        return problems
