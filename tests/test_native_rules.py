#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Grep-checkable cpp/NATIVE.md rules."""

from __future__ import annotations

import re

from tests.helpers import ROOT

CPP_SRC = ROOT / 'python-webrtc' / 'cpp' / 'src'

DISPATCHER = frozenset({'utils/dispatcher.h', 'utils/dispatcher.cpp'})


def _sources() -> list[tuple[str, str]]:
    """Native sources as (path under cpp/src, text)."""
    return [
        (path.relative_to(CPP_SRC).as_posix(), path.read_text(encoding='utf-8'))
        for path in sorted(CPP_SRC.rglob('*'))
        if path.suffix in {'.cpp', '.h', '.mm'}
    ]


def _lines_matching(pattern: str, *, allowed: frozenset[str] = frozenset()) -> list[str]:
    """Matching ``path:line: text`` lines outside the allowed files."""
    matching: list[str] = []
    for relative, text in _sources():
        if relative in allowed:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(pattern, line) is not None:
                matching.append(f'{relative}:{number}: {line.strip()}')
    return matching


def test_only_the_dispatcher_takes_the_gil() -> None:
    """Only the Dispatcher enters Python."""
    offending = _lines_matching(
        r'gil_scoped_acquire|PyGILState_Ensure|PyThreadState_Ensure', allowed=frozenset({'utils/dispatcher.cpp'})
    )
    assert offending == [], 'the GIL is taken outside the Dispatcher:\n' + '\n'.join(offending)


def test_the_gil_is_released_through_gil_release() -> None:
    """Detaches go through gil_release."""
    offending = _lines_matching(
        r'gil_scoped_release|PyEval_SaveThread', allowed=frozenset({'utils/gil.h', 'utils/dispatcher.cpp'})
    )
    assert offending == [], 'the GIL is released outside gil_release:\n' + '\n'.join(offending)


def test_no_python_object_is_held_natively() -> None:
    """No pybind11 members besides the Dispatcher's wake."""
    # a member: the type anywhere in a line ending `_name;`, optionally initialized
    typed = _lines_matching(r'pybind11::(object|function|handle|buffer)\b')
    members = [line for line in typed if re.search(r'\b_\w+\s*(\{[^;]*\})?\s*(=[^;]*)?;\s*$', line) is not None]
    offending = [line for line in members if not line.startswith('utils/dispatcher.h:') or not line.endswith(' _wake;')]
    assert offending == [], 'a Python object is a member of a native class:\n' + '\n'.join(offending)


def test_no_python_callable_is_held_natively() -> None:
    """Python callables stay out of native code."""
    offending = _lines_matching(r'(pybind11|py)::function\b', allowed=DISPATCHER)
    assert offending == [], 'a Python callable type is used outside the Dispatcher:\n' + '\n'.join(offending)


def test_no_native_callback_passes_a_python_object() -> None:
    """std::function never carries Python objects."""
    offending = _lines_matching(r'std::function<[^;]*pybind11::(object|function|handle)\b')
    assert offending == [], 'a std::function passes a Python object:\n' + '\n'.join(offending)


def test_wrappers_are_created_by_create_only() -> None:
    """NativeObjects come from NativeObject::Create."""
    derived = re.compile(r'public NativeObject<(\w+)>')
    classes: list[str] = sorted({name for _, text in _sources() for name in derived.findall(text)})
    assert len(classes) >= 20, classes
    names = '|'.join(classes)
    offending = _lines_matching(
        rf'std::make_shared<\s*({names})\s*>|std::shared_ptr<\s*({names})\s*>\s*\(\s*new\b',
        allowed=frozenset({'utils/native_object.h'}),
    )
    assert offending == [], 'a NativeObject is created outside NativeObject::Create:\n' + '\n'.join(offending)


def test_waits_on_libwebrtc_threads_go_through_blocking_call_on() -> None:
    """Waits go through BlockingCallOn."""
    offending = _lines_matching(r'\bBlockingCall\(', allowed=frozenset({'utils/libwebrtc_thread.h'}))
    assert offending == [], 'a libwebrtc thread is waited for outside BlockingCallOn:\n' + '\n'.join(offending)
