#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Tests in an interpreter of their own."""

from __future__ import annotations

import faulthandler
import os
import sys
import threading

import pytest

from tests.isolation import isolated


@isolated
def _process_and_value() -> tuple[int, bool, str]:
    return os.getpid(), faulthandler.is_enabled(), 'value'


@isolated
def _failing() -> None:
    msg = 'failed in the child'
    raise AssertionError(msg)


@isolated
def _crashing() -> None:
    os.abort()


@isolated(timeout=5)
def _hanging_at_exit() -> None:
    threading.Thread(target=threading.Event().wait).start()


@isolated
def _exiting() -> None:
    sys.exit(0)


@isolated
def _skipping() -> None:
    pytest.skip('skipped in the child')


def test_returns_from_another_process() -> None:
    process, crashes_dump_stacks, value = _process_and_value()

    assert process != os.getpid()
    assert crashes_dump_stacks
    assert value == 'value'


def test_error_fails() -> None:
    with pytest.raises(pytest.fail.Exception, match='exit code 1'):
        _failing()


@pytest.mark.skipif(sys.platform == 'win32', reason='Windows Error Reporting may wait on a crash')
def test_crash_fails() -> None:
    with pytest.raises(pytest.fail.Exception, match='exit code'):
        _crashing()


def test_hang_at_exit_fails() -> None:
    with pytest.raises(pytest.fail.Exception, match='still running after 5 s'):
        _hanging_at_exit()


def test_exit_without_returning_passes() -> None:
    _exiting()


def test_skip_skips() -> None:
    with pytest.raises(pytest.skip.Exception, match='skipped in the child'):
        _skipping()
