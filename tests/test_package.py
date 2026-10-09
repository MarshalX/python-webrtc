#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The package facade."""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import random
import sys

from tests.isolation import isolated


@isolated
def test_facade_import_order_does_not_matter() -> None:
    """The facade works with its imports shuffled."""
    spec = importlib.util.find_spec('webrtc')
    assert spec is not None
    assert spec.origin is not None
    tree = ast.parse(pathlib.Path(spec.origin).read_text(encoding='utf-8'))
    submodules = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.level > 0]
    rest = [node for node in tree.body if node not in submodules]
    first = [node for node in rest if isinstance(node, (ast.Expr, ast.ImportFrom, ast.Import))]
    last = [node for node in rest if node not in first]

    for seed in range(20):
        for name in [name for name in sys.modules if name == 'webrtc' or name.startswith('webrtc.')]:
            del sys.modules[name]
        random.Random(seed).shuffle(submodules)
        module = importlib.util.module_from_spec(spec)
        sys.modules['webrtc'] = module
        code = compile(ast.Module([*first, *submodules, *last], type_ignores=[]), spec.origin, 'exec')
        try:
            exec(code, module.__dict__)
        except ImportError as e:
            msg = f'seed {seed}'
            raise AssertionError(msg) from e
        assert all(hasattr(module, name) for name in vars(module)['__all__'])
