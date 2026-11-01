#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

from importlib.util import find_spec

# the pipecat extra, on Python 3.11+; a skip here would fail a run of this directory alone
if find_spec('pipecat') is None:
    collect_ignore_glob = ['test_*.py']
