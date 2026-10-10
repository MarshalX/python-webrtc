#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Mailbox, completions, NativeObjects and the Dispatcher."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import warnings
from typing import Callable

import pytest

import webrtc
import wrtc
from tests.helpers import ROOT, exit_code_within
from tests.isolation import isolated

_Record = tuple['str | None', int, bool, 'tuple[object, ...] | None']

THREADS = 8
PER_THREAD = 100


def _records(mailbox: wrtc.Mailbox) -> list[_Record]:
    records: list[_Record] = []
    while (record := mailbox.take()) is not None:
        records.append(record)
    return records


def _start(*targets: Callable[[], object]) -> list[threading.Thread]:
    threads = [threading.Thread(target=target, daemon=True) for target in targets]
    for thread in threads:
        thread.start()
    return threads


def test_records_of_many_threads_all_arrive_in_the_order_of_each_thread() -> None:
    mailbox = wrtc.Mailbox()
    wrtc._testing.post_from_threads(mailbox, THREADS, PER_THREAD)
    assert len(mailbox) == THREADS * PER_THREAD

    records = _records(mailbox)
    by_thread: dict[object, list[object]] = {}
    for name, token, failed, args in records:
        assert (name, token, failed) == ('posted', 0, False)
        assert args is not None
        by_thread.setdefault(args[0], []).append(args[1])
    assert by_thread == {thread: list(range(PER_THREAD)) for thread in range(THREADS)}
    assert len(mailbox) == 0


def test_markers_and_completions_keep_their_order_with_events() -> None:
    mailbox = wrtc.Mailbox()
    mailbox.postMarker(1)
    wrtc._testing.post(mailbox, 'event', 5)
    wrtc._testing.complete(mailbox, 2, 42)
    wrtc._testing.fail(mailbox, 3)
    mailbox.postMarker(4)

    records = _records(mailbox)
    assert records[:3] == [(None, 1, False, None), ('event', 0, False, (5,)), (None, 2, False, (42,))]
    name, token, failed, args = records[3]
    assert (name, token, failed) == (None, 3, True)
    assert args is not None
    assert isinstance(args[0], webrtc.RTCException)
    assert args[0].message == 'The operation failed'
    assert records[4] == (None, 4, False, None)


def test_close_while_posting_drops_the_later_records() -> None:
    mailbox = wrtc.Mailbox()
    stop = threading.Event()

    def post() -> None:
        while not stop.is_set():
            wrtc._testing.post(mailbox, 'event', 1)

    threads = _start(post, post, post, post)
    time.sleep(0.05)
    mailbox.close()
    stop.set()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()

    assert mailbox.closed
    assert len(mailbox) == 0
    assert mailbox.take() is None
    dropped = mailbox.dropped
    wrtc._testing.post(mailbox, 'event', 2)
    assert mailbox.dropped == dropped + 1
    mailbox.close()
    assert mailbox.take() is None


def test_record_that_does_not_convert_is_reported_and_the_next_one_arrives(monkeypatch: pytest.MonkeyPatch) -> None:
    reported: list[tuple[str, object]] = []

    def hook(unraisable: sys.UnraisableHookArgs) -> None:
        reported.append((type(unraisable.exc_value).__name__, unraisable.object))

    monkeypatch.setattr(sys, 'unraisablehook', hook)
    mailbox = wrtc.Mailbox()
    wrtc._testing.post_unconvertible(mailbox)
    wrtc._testing.post(mailbox, 'event', 2)

    assert mailbox.take() == ('event', 0, False, (2,))
    assert reported == [('RuntimeError', 'Mailbox.take')]


def test_abandoned_completion_fails_with_invalid_state_error() -> None:
    mailbox = wrtc.Mailbox()
    wrtc._testing.abandon(mailbox, 7)

    record = mailbox.take()
    assert record is not None
    name, token, failed, args = record
    assert (name, token, failed) == (None, 7, True)
    assert args is not None
    assert isinstance(args[0], webrtc.InvalidStateError)
    assert args[0].message == 'The operation was abandoned'


def test_dispatcher_is_one_thread_that_idles() -> None:
    mailbox = wrtc.Mailbox()
    wrtc._testing.post(mailbox, 'event', 1)
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.dispatcher_threads() <= 1
    assert mailbox.take() == ('event', 0, False, (1,))


def test_native_objects_are_counted_and_destroyed_on_the_dispatcher() -> None:
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.alive_counts()['Counted'] == 0
    counted = wrtc._testing.Counted()
    other = wrtc._testing.Counted()
    assert wrtc._testing.alive_counts()['Counted'] == 2
    assert other.id > counted.id
    task = counted.guarded()
    task()
    assert task.ran == 1

    del counted, other
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.alive_counts()['Counted'] == 0
    # guarded by the life of its object
    task()
    assert task.ran == 1


def test_ids_are_never_reused() -> None:
    """NativeObject ids are process-unique."""
    ids = [cls().id for _ in range(50) for cls in (wrtc._testing.Counted, wrtc._testing.Emitting)]
    assert ids == sorted(set(ids))
    wrtc._testing.dispatcher_idle()


def test_registry_makes_one_wrapper_per_object_on_the_signaling_thread() -> None:
    identity = wrtc._testing.Identity()
    wrapper = wrtc._testing.registered(identity)
    assert wrtc._testing.registered(identity) is wrapper
    assert wrtc._testing.find_registered(identity) is wrapper
    assert wrapper.createdOnSignalingThread
    assert wrtc._testing.alive_counts()['Registered'] == 1

    del wrapper
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.find_registered(identity) is None
    assert wrtc._testing.alive_counts()['Registered'] == 0
    assert wrtc._testing.registered(identity).createdOnSignalingThread
    wrtc._testing.dispatcher_idle()


def test_emitter_posts_events_with_their_target_while_bound() -> None:
    mailbox = wrtc.Mailbox()
    emitting = wrtc._testing.Emitting()
    assert not emitting.bound
    emitting.emit(1)
    assert len(mailbox) == 0

    emitting.bind(mailbox)
    assert emitting.bound
    emitting.emit(2)
    record = mailbox.take()
    assert record is not None
    name, token, failed, args = record
    assert (name, token, failed) == ('value', 0, False)
    assert args is not None
    assert args[0] is emitting
    assert args[1] == 2

    del emitting, record, args
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.alive_counts()['Emitting'] == 0


def test_binding_is_kept_until_its_mailbox_closes() -> None:
    mailbox, other = wrtc.Mailbox(), wrtc.Mailbox()
    emitting = wrtc._testing.Emitting()
    emitting.bind(mailbox)
    emitting.bind(other)
    emitting.emit(1)
    assert (len(mailbox), len(other)) == (1, 0)
    child = wrtc._testing.Emitting()
    child.inherit(emitting)
    child.emit(2)
    assert len(mailbox) == 2

    mailbox.close()
    assert not emitting.bound
    emitting.emit(3)
    assert mailbox.dropped == 2
    emitting.bind(other)
    emitting.emit(4)
    assert len(other) == 1
    emitting.unbind()
    assert not emitting.bound
    emitting.emit(5)
    assert len(other) == 1

    # the queued record keeps its source until taken
    del emitting, child
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.alive_counts()['Emitting'] == 1
    other.close()
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.alive_counts()['Emitting'] == 0


def test_constructor_that_throws_leaves_no_object_behind() -> None:
    """A throwing constructor's cleanup isn't an escape."""
    wrtc._testing.dispatcher_idle()
    with pytest.raises(ValueError, match='The constructor failed'):
        wrtc._testing.Throwing(fail=True)
    assert wrtc._testing.alive_counts()['Throwing'] == 0

    made = wrtc._testing.Throwing(fail=False)
    assert wrtc._testing.alive_counts()['Throwing'] == 1
    del made
    wrtc._testing.dispatcher_idle()
    assert wrtc._testing.alive_counts()['Throwing'] == 0


@pytest.mark.skipif(not wrtc._sanitized, reason='checked in sanitizer builds only')
def test_destroyed_off_the_dispatcher_aborts() -> None:
    """Destroying off the Dispatcher aborts."""
    result = subprocess.run(
        [sys.executable, '-c', 'import wrtc; wrtc._testing.check_destroyed_off_dispatcher()'],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode != 0
    assert 'destroyed off the Dispatcher' in result.stderr, result.stderr


@pytest.mark.skipif(not wrtc._sanitized, reason='checked in sanitizer builds only')
def test_blocking_on_a_libwebrtc_thread_while_attached_aborts() -> None:
    """BlockingCallOn with the GIL attached aborts."""
    result = subprocess.run(
        [sys.executable, '-c', 'import wrtc; wrtc._testing.check_blocking_while_attached()'],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode != 0
    assert 'while attached to Python' in result.stderr, result.stderr


def test_parking_point_holds_a_posting_thread() -> None:
    mailbox = wrtc.Mailbox()
    wrtc._testing.park('mailbox.post')
    (thread,) = _start(lambda: wrtc._testing.post(mailbox, 'event', 1))
    try:
        assert wrtc._testing.parked('mailbox.post', 5)
        assert len(mailbox) == 0
    finally:
        wrtc._testing.release('mailbox.post')
    thread.join(5)
    assert not thread.is_alive()
    assert len(mailbox) == 1


def test_parking_point_holds_the_dispatcher_before_it_enters_python() -> None:
    mailbox = wrtc.Mailbox()
    wrtc._testing.park('dispatcher.wake')
    try:
        wrtc._testing.post(mailbox, 'event', 1)
        assert wrtc._testing.parked('dispatcher.wake', 5)
    finally:
        wrtc._testing.release('dispatcher.wake')
    wrtc._testing.dispatcher_idle()
    assert not wrtc._testing.parked('dispatcher.wake', 0)


def _child_restarts_the_dispatcher(parent: list[object]) -> bool:
    """Whether the child's Dispatcher works and spares pre-fork objects."""
    mailbox = wrtc.Mailbox()
    wrtc._testing.post(mailbox, 'child', 1)
    parent.clear()
    wrtc._testing.dispatcher_idle()
    return (
        mailbox.take() == ('child', 0, False, (1,))
        and wrtc._testing.dispatcher_threads() == 1
        and wrtc._testing.alive_counts()['Counted'] == 1
    )


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='no fork')
@pytest.mark.skipif(wrtc._thread_sanitized, reason='a thread started after a fork ends the child under ThreadSanitizer')
@isolated(timeout=60)
def test_forked_child_restarts_the_dispatcher_and_the_parent_goes_on() -> None:
    """A forked child gets its own Dispatcher."""
    warnings.simplefilter('ignore', DeprecationWarning)  # fork with threads
    mailbox = wrtc.Mailbox()
    wrtc._testing.post(mailbox, 'parent', 1)
    wrtc._testing.dispatcher_idle()
    counted: list[object] = [wrtc._testing.Counted()]
    pid = os.fork()
    if pid == 0:
        sys.exit(0 if _child_restarts_the_dispatcher(counted) else 1)

    assert exit_code_within(pid, 30) == 0
    wrtc._testing.post(mailbox, 'parent', 2)
    counted.clear()
    wrtc._testing.dispatcher_idle()
    assert [record[3] for record in _records(mailbox)] == [(1,), (2,)]
    assert wrtc._testing.alive_counts()['Counted'] == 0
