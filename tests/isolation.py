#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Tests in an interpreter of their own; apart from the helpers, which import the library."""

from __future__ import annotations

import functools
import multiprocessing
import multiprocessing.context
import os
import time
from typing import TYPE_CHECKING, Callable, Literal, TypeVar, Union, cast, overload
from unittest import mock

import pytest
from typing_extensions import ParamSpec

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

    from typing_extensions import TypeAlias

_T = TypeVar('_T')
_P = ParamSpec('_P')

_Outcome: TypeAlias = Union[tuple[Literal['returned'], object], tuple[Literal['skipped'], str]]


def _child(
    connection: Connection, *, function: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object]
) -> None:
    # an error is printed by multiprocessing and fails the exit code
    outcome: _Outcome
    try:
        outcome = ('returned', function(*args, **kwargs))
    except pytest.skip.Exception as e:
        outcome = ('skipped', str(e.msg))
    connection.send(outcome)
    connection.close()


def _run(
    function: Callable[..., object], args: tuple[object, ...], kwargs: dict[str, object], *, timeout: float
) -> object:
    receiver, sender = multiprocessing.Pipe(duplex=False)
    process = multiprocessing.context.SpawnProcess(
        target=_child, args=(sender,), kwargs={'function': function, 'args': args, 'kwargs': kwargs}
    )
    # a crash tells where: the Python stacks of every thread, and glibc's fatal errors, written to a tty otherwise
    with mock.patch.dict(os.environ, {'PYTHONFAULTHANDLER': '1', 'LIBC_FATAL_STDERR_': '1'}):
        process.start()
    sender.close()
    deadline = time.monotonic() + timeout
    outcome: _Outcome | None = None
    stuck = True
    try:
        try:
            if receiver.poll(timeout):
                outcome = receiver.recv()
        except EOFError:
            pass
        process.join(max(0.0, deadline - time.monotonic()))
        stuck = process.exitcode is None
    finally:
        if process.exitcode is None:
            process.kill()
            process.join()
        receiver.close()

    if stuck:
        pytest.fail(f'still running after {timeout} s', pytrace=False)
    if process.exitcode != 0:
        pytest.fail(f'exit code {process.exitcode}, see its output', pytrace=False)
    if outcome is not None and outcome[0] == 'skipped':
        pytest.skip(outcome[1])
    return outcome[1] if outcome is not None else None


@overload
def isolated(test: Callable[_P, _T], /) -> Callable[_P, _T]: ...


@overload
def isolated(*, timeout: float = 60) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]: ...


def isolated(
    test: Callable[_P, _T] | None = None, /, *, timeout: float = 60
) -> Callable[_P, _T] | Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Runs a function of the top of a module in a fresh interpreter, which must exit within the timeout."""

    def decorate(test: Callable[_P, _T]) -> Callable[_P, _T]:
        @functools.wraps(test)
        def run(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            if multiprocessing.parent_process() is not None:
                return test(*args, **kwargs)
            return cast('_T', _run(run, args, kwargs, timeout=timeout))

        return run

    return decorate(test) if test is not None else decorate
