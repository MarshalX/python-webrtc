#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Grep-checkable cpp/NATIVE.md rules."""

from __future__ import annotations

import re
from typing import NamedTuple

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


def _is_dispatcher_wake(line: str) -> bool:
    return line.startswith('utils/dispatcher.h:') and line.endswith(' _wake;')


def test_no_python_object_is_held_natively() -> None:
    """No pybind11 members besides the Dispatcher's wake."""
    typed = _lines_matching(r'pybind11::(object|function|handle|buffer)\b')
    # a member: the type anywhere in a line ending `_name;`, optionally initialized
    members = [line for line in typed if re.search(r'\b_\w+\s*(\{[^;]*\})?\s*(=[^;]*)?;\s*$', line) is not None]
    offending = [line for line in members if not _is_dispatcher_wake(line)]
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


LEAVES = frozenset({'EncodedFrame'})

# member types a leaf may have, each freeing only memory or an atomic count
LEAF_MEMBERS = {
    'const bool': 'a value',
    'const uint64_t': 'a value',
    'std::mutex': 'unlocked once nothing references the leaf',
    'std::unique_ptr<webrtc::TransformableFrameInterface>': "libwebrtc's frames have implicit destructors over buffers",
}

LEAF_FORBIDDEN = r'BlockingCall|PostTask|Guard\(|Disarm\(|Dispatcher::|Emit\(|Registry<'

FIXTURES = frozenset({'testing.cpp'})

LEAF_MARKER = 'static constexpr bool kLeaf = true;'


class Leaf(NamedTuple):
    path: str
    bases: str
    body: str


def _class_body(text: str, start: int) -> str:
    """The text between a class's braces, from just past its opening brace."""
    depth = 1
    end = start
    while depth > 0:
        if text[end] == '{':
            depth += 1
        elif text[end] == '}':
            depth -= 1
        end += 1

    return text[start : end - 1]


def _leaves() -> dict[str, Leaf]:
    """Leaf classes by name."""
    leaves: dict[str, Leaf] = {}
    for relative, text in _sources():
        if relative in FIXTURES:
            continue

        for marker in re.finditer(re.escape(LEAF_MARKER), text):
            # the marker's class is the last one opened before it
            head = list(re.finditer(r'\bclass (\w+)\b([^;{]*)\{', text[: marker.start()]))[-1]
            name = head.group(1)
            bases = ' '.join(head.group(2).split())
            leaves[name] = Leaf(relative, bases, _class_body(text, head.end()))

    return leaves


def _declarations(body: str) -> list[str]:
    """A class body's declarations, without comments, inline bodies, initializers or access specifiers."""
    code = re.sub(r'//[^\n]*|/\*.*?\*/', '', body, flags=re.DOTALL)
    while (inner := re.sub(r'\{[^{}]*\}', ';', code)) != code:
        code = inner

    statements = (re.sub(r'\b(public|protected|private)\s*:', '', statement) for statement in code.split(';'))
    # up to an initializer: = default, = delete or a member's value
    declarations = (re.split(r'(?<!operator)=(?!=)', statement, maxsplit=1)[0] for statement in statements)

    return [' '.join(declaration.split()) for declaration in declarations if declaration.strip() != '']


def _member_types(body: str) -> list[str]:
    """The types of a class body's instance data members, whatever their names."""
    members: list[str] = []
    for declaration in _declarations(body):
        if re.match(r'(static|using|friend|typedef|template)\b', declaration) is not None:
            continue

        # a function: its parameters close the declarator, then qualifiers
        if re.search(r'\)( ?(const|noexcept|override|final|&&?))*$', declaration) is not None:
            continue

        member = re.fullmatch(r'(.+?[\s*&])(\w+)(\[[^\]]*\])?', declaration)
        assert member is not None, f'not parsed as a member: {declaration}'
        members.append(' '.join(member.group(1).split()))

    return members


def test_leaves_are_known() -> None:
    """Every kLeaf class is listed, marked the one way the tests find."""
    markers = _lines_matching(r'\bkLeaf\b', allowed=FIXTURES | {'utils/native_object.h'})
    offending = [line for line in markers if not line.endswith(f': {LEAF_MARKER}')]
    assert offending == [], f'kLeaf set otherwise than `{LEAF_MARKER}`:\n' + '\n'.join(offending)
    assert set(_leaves()) == LEAVES


def test_leaves_hold_only_values() -> None:
    """A leaf's implicit destructor frees memory only."""
    used: set[str] = set()
    for name, leaf in _leaves().items():
        assert leaf.bases == f': public NativeObject<{name}>', f'{leaf.path}: the leaf {name} derives from {leaf.bases}'
        assert re.search(rf'~{name}\s*\(', leaf.body) is None, f'{leaf.path}: the leaf {name} declares a destructor'

        members = _member_types(leaf.body)
        unknown = [member for member in members if member not in LEAF_MEMBERS]
        assert unknown == [], f'{leaf.path}: the leaf {name} holds members not known to only free memory: {unknown}'
        used.update(members)

    # a parse that finds nothing can't pass
    assert used == set(LEAF_MEMBERS)


def _without_suffix(path: str) -> str:
    return path.rsplit('.', 1)[0]


def test_leaves_dont_wait_or_post() -> None:
    """A leaf's sources don't wait, post, emit or register."""
    sources = _sources()
    for name, leaf in _leaves().items():
        stem = _without_suffix(leaf.path)
        for path, text in sources:
            if _without_suffix(path) == stem:
                matching = re.findall(LEAF_FORBIDDEN, text)
                assert matching == [], f'{path}: the leaf {name} waits, posts or registers: {matching}'


def test_waits_on_libwebrtc_threads_go_through_blocking_call_on() -> None:
    """Waits go through BlockingCallOn."""
    offending = _lines_matching(r'\bBlockingCall\(', allowed=frozenset({'utils/libwebrtc_thread.h'}))
    assert offending == [], 'a libwebrtc thread is waited for outside BlockingCallOn:\n' + '\n'.join(offending)
