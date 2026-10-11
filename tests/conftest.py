#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio
import gc
import os
import sys
import sysconfig
import threading
import types
import weakref
from collections import Counter
from typing import TYPE_CHECKING, TypeVar

import pytest

import webrtc
import wrtc
from tests.helpers import register_stack_dump, release_stranded_candidates, settled_alive
from webrtc.utils import loops

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from tests.helpers import CreatePC

#: native counts at the start of the call phase
_BASELINE = pytest.StashKey[tuple[dict[str, int], int]]()
#: the loop-close check only applies to passed tests
_PASSED = pytest.StashKey[bool]()

DESCRIBED_SURVIVORS = 3

_NativeT = TypeVar('_NativeT')


class _Created:
    """Wrappers created during the call phase."""

    def __init__(self) -> None:
        self.refs: set[weakref.ref[object]] = set()
        self.recording = False


_created = _Created()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--gc-on-emit',
        action='store_true',
        help='collect garbage before every record a loop drains, and on the Dispatcher thread on every wake',
    )
    parser.addoption('--stress', action='store_true', help='run the long stress tests too')


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption('--stress'):
        return
    skip = pytest.mark.skip(reason='a long stress test, run with --stress')
    for item in items:
        if 'stress' in item.keywords:
            item.add_marker(skip)


def pytest_configure(config: pytest.Config) -> None:
    register_stack_dump()
    if sysconfig.get_config_var('Py_GIL_DISABLED') == 1:
        # an extension not marked GIL-free silently re-enables the GIL on import
        gil_enabled = getattr(sys, '_is_gil_enabled', lambda: True)
        assert not gil_enabled(), 'the GIL was enabled by an import on a free-threaded build'
    config.addinivalue_line('markers', 'stress: a long stress test, run with --stress')
    config.addinivalue_line('markers', 'leaks(reason): the test leaks, the reason names the leak class')
    config.addinivalue_line('markers', 'roots(reason): the test fails a roots check, the reason names the class')
    # macOS may block the LAN without Local Network permission
    os.environ['WRTC_ALLOW_LOOPBACK'] = '1'
    webrtc.allow_loopback()
    _ = os.environ.setdefault('WRTC_CHECK_ROOTS', '1')
    _record_wrappers()
    if not config.getoption('--gc-on-emit'):
        return
    # gc can run on any thread with the GIL, Dispatcher wakes included: releases must block neither
    run = loops.LoopState._run
    collect = gc.collect
    # gc.collect() returns at once while another thread collects; re-entrant for gc callbacks
    collecting = threading.RLock()

    def locked_collect(generation: int = 2) -> int:
        with collecting:
            return collect(generation)

    def collecting_run(self: loops.LoopState) -> bool:
        _ = locked_collect()
        return run(self)

    def collecting_wake(mailbox_id: int) -> None:
        _ = locked_collect()
        loops._wake(mailbox_id)

    gc.collect = locked_collect
    loops.LoopState._run = collecting_run
    wrtc._set_wake(collecting_wake)


def _record_wrappers() -> None:
    init_native = webrtc.WebRTCObject._init_native

    def recording_init_native(self: webrtc.WebRTCObject[_NativeT], native_obj: _NativeT | None) -> None:
        init_native(self, native_obj)
        if _created.recording:
            _created.refs.add(weakref.ref(self))

    webrtc.WebRTCObject._init_native = recording_init_native


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    _created.refs.clear()
    loops.mismatches.clear()
    item.stash[_BASELINE] = wrtc._alive(), wrtc._alive_factories()
    _created.recording = True
    try:
        return (yield)
    finally:
        _created.recording = False


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if call.when == 'call':
        item.stash[_PASSED] = report.passed
    return report


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Generator[None, object, object]:
    # runs after the fixtures, including the loop, are torn down
    result = yield
    # a candidate arriving as the loop closed leaves a task holding its connections
    release_stranded_candidates()
    if item.stash.get(_PASSED, False) and item.get_closest_marker('leaks') is None:
        _check_released(item)
    # raised in a drain, a failed roots check only reaches the loop's exception handler
    if item.stash.get(_PASSED, False) and item.get_closest_marker('roots') is None and len(loops.mismatches) > 0:
        pytest.fail('the roots checks failed:\n' + '\n'.join(loops.mismatches), pytrace=False)
    return result


def _check_released(item: pytest.Item) -> None:
    """Fails if anything the test created outlives its fixtures."""
    if isinstance(item, pytest.Function):
        # pytest keeps fixture values until after this hook
        item.funcargs.clear()
    baseline, baseline_factories = item.stash[_BASELINE]
    refs = _created.refs

    def released(alive: dict[str, int], factories: int) -> bool:
        return _within(alive, baseline) and factories <= baseline_factories and all(ref() is None for ref in refs)

    alive, factories = settled_alive(released)
    if not released(alive, factories):
        pytest.fail(_leak_report((alive, factories), item.stash[_BASELINE]), pytrace=False)


def _within(alive: dict[str, int], baseline: dict[str, int]) -> bool:
    return all(count <= baseline.get(name, 0) for name, count in alive.items())


def _leak_report(current: tuple[dict[str, int], int], base: tuple[dict[str, int], int]) -> str:
    (alive, factories), (baseline, baseline_factories) = current, base
    over = [
        f'{name} {count} > {baseline.get(name, 0)}' for name, count in alive.items() if count > baseline.get(name, 0)
    ]
    lines = ['alive after the test:']
    if len(over) > 0:
        lines.append(f'  native objects above the baseline: {", ".join(over)}')
    if factories > baseline_factories:
        lines.append(f'  factories: {factories} > {baseline_factories}')
    survivors = [obj for ref in _created.refs if (obj := ref()) is not None]
    if len(survivors) > 0:
        by_type = Counter(type(obj).__name__ for obj in survivors)
        lines.append(f'  wrappers of the test: {", ".join(f"{name} x{n}" for name, n in by_type.items())}')
        lines.extend(
            f'    {type(obj).__name__} referred to by {_referrers(obj, survivors)}'
            for obj in survivors[:DESCRIBED_SURVIVORS]
        )
    return '\n'.join(lines)


def _referrers(obj: object, survivors: list[object]) -> str:
    """Referrer types of an object, one level deeper for dicts and cells."""
    names: list[str] = []
    for referrer in gc.get_referrers(obj):
        if referrer is survivors or isinstance(referrer, types.FrameType):
            continue
        name = type(referrer).__name__
        if isinstance(referrer, (dict, types.CellType)):
            owners = sorted({type(owner).__name__ for owner in gc.get_referrers(referrer)} - {'frame', 'list'})
            name += f' of {", ".join(owners)}'
        names.append(name)
    return ', '.join(names) if len(names) > 0 else 'nothing the collector tracks'


@pytest.fixture
def rtc_peer_connection() -> Iterator[webrtc.RTCPeerConnection]:
    pc = webrtc.RTCPeerConnection()
    yield pc
    pc.close()


pc = caller = callee = callee2 = rtc_peer_connection


@pytest.fixture
def create_pc(request: pytest.FixtureRequest) -> CreatePC:
    """Creates connections with a configuration, closed after the test."""

    def create(configuration: webrtc.RTCConfiguration | None = None) -> webrtc.RTCPeerConnection:
        pc = webrtc.RTCPeerConnection(configuration)
        request.addfinalizer(pc.close)
        return pc

    return create


def get_stream(constraints: dict[str, bool], request: pytest.FixtureRequest) -> webrtc.MediaStream:
    stream = asyncio.run(webrtc.media_devices.get_user_media(webrtc.MediaStreamConstraints(**constraints)))

    def stop_tracks() -> None:
        for track in stream.get_tracks():
            track.stop()

    request.addfinalizer(stop_tracks)

    return stream


@pytest.fixture
def audio_stream(request: pytest.FixtureRequest) -> webrtc.MediaStream:
    return get_stream({'audio': True}, request)


audio_stream2 = audio_stream


@pytest.fixture
def video_stream(request: pytest.FixtureRequest) -> webrtc.MediaStream:
    return get_stream({'audio': False, 'video': True}, request)
