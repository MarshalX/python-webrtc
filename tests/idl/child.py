#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Parses IDL with webidl2.js of the WPT checkout, the parser idlharness uses.

Reads ``{file name: IDL text}`` as JSON from stdin and writes the JSON AST of every definition, with its file name.
"""

from __future__ import annotations

import json
import sys

import pythonmonkey as pm

from tests.idl.spec import WPT_ROOT


def main() -> None:
    pm.eval((WPT_ROOT / 'resources' / 'webidl2' / 'lib' / 'webidl2.js').read_text())
    parse = pm.eval('(text) => JSON.stringify(globalThis.WebIDL2.parse(text))')
    definitions: list[dict[str, object]] = []
    for name, text in json.load(sys.stdin).items():
        ast: object = parse(text)
        if not isinstance(ast, str):
            msg = f'JSON.stringify returned {ast!r}'
            raise TypeError(msg)
        for definition in json.loads(ast):
            definition['file'] = name
            definitions.append(definition)
    json.dump(definitions, sys.stdout)


if __name__ == '__main__':
    main()
