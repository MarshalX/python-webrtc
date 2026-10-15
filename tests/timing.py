#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Wait bounds of the tests, stretched on slow builds; without the library, for isolated children."""

from __future__ import annotations

import os

#: set by CI on slow builds (sanitizers, free threading)
SCALE = float(os.environ.get('WRTC_TEST_TIME_SCALE', '1'))


def seconds(value: float) -> float:
    """A wait bound in seconds, stretched on slow builds."""
    return value * SCALE
