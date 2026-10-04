#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Every public class attribute, like a dataclass field or an enum member, is documented: ruff's D rules skip them."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1] / 'python-webrtc' / 'python' / 'webrtc'
MODULES = [
    '__init__',
    'base',
    'enums',
    'exceptions',
    'openh264',
    'streams',
    'utils/events',
    *sorted(
        f'{d}/{p.stem}' for d in ('interfaces', 'models') for p in (PACKAGE / d).glob('*.py') if p.stem != '__init__'
    ),
]


def _attribute_name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None


def _documented(cls: ast.ClassDef, i: int, lines: list[str]) -> bool:
    node = cls.body[i]
    # an attribute docstring after it
    after = cls.body[i + 1] if i + 1 < len(cls.body) else None
    if isinstance(after, ast.Expr) and isinstance(after.value, ast.Constant) and isinstance(after.value.value, str):
        return True
    # a doc comment above it or on its line
    if lines[node.lineno - 2].strip().startswith('#:') or '#:' in lines[node.lineno - 1]:
        return True
    # an entry in the Args or Attributes section of the class
    docstring, name = ast.get_docstring(cls), _attribute_name(node)
    if docstring is None or name is None:
        return False
    return re.search(rf'^\s+{re.escape(name)}\b.*:', docstring, re.MULTILINE) is not None


def _undocumented(module: str) -> list[str]:
    source = (PACKAGE / f'{module}.py').read_text(encoding='UTF-8')
    lines = source.splitlines()
    missing: list[str] = []
    for cls in ast.parse(source).body:
        if not isinstance(cls, ast.ClassDef) or cls.name.startswith('_'):
            continue
        for i, node in enumerate(cls.body):
            name = _attribute_name(node)
            if name is not None and not name.startswith('_') and not _documented(cls, i, lines):
                missing.append(f'{module}: {cls.name}.{name}')
    return missing


@pytest.mark.parametrize('module', MODULES)
def test_attributes_documented(module: str) -> None:
    assert _undocumented(module) == []
