#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The task queues of the connections."""

from __future__ import annotations

import pytest

import wrtc


@pytest.mark.parametrize('by_captures', [False, True], ids=['body', 'captures'])
def test_a_task_deleting_its_queue_ends_it(*, by_captures: bool) -> None:
    """A queue deleted from its own task or its captures runs nothing after."""
    assert not wrtc._testing.delete_queue_from_its_task(by_captures)
