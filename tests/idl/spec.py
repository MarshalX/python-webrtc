#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The interfaces, dictionaries and enums of the specifications the library implements, merged from WPT IDL files."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

WPT_ROOT = Path(__file__).resolve().parents[2] / 'wpt'

# needs the WPT checkout, PythonMonkey to parse and inspect.get_annotations
AVAILABLE = sys.version_info >= (3, 10) and WPT_ROOT.is_dir() and find_spec('pythonmonkey') is not None

# IDL files under wpt/interfaces, with the definitions to take from them: None takes all of them. Dictionaries and
# enums the taken definitions use come along, typedefs always do.
FILES: dict[str, set[str] | None] = {
    'webrtc.idl': None,
    'webrtc-ice.idl': None,
    'webrtc-priority.idl': None,
    'webrtc-svc.idl': None,
    'webrtc-stats.idl': None,
    'webrtc-encoded-transform.idl': None,
    'mediacapture-streams.idl': None,
    'mediacapture-transform.idl': None,
    'webcodecs.idl': {'VideoFrame', 'AudioData'},
    'streams.idl': {
        'ReadableStream',
        'ReadableStreamDefaultReader',
        'ReadableStreamDefaultController',
        'WritableStream',
        'WritableStreamDefaultWriter',
        'WritableStreamDefaultController',
        'TransformStream',
        'TransformStreamDefaultController',
    },
    'FileAPI.idl': {'Blob'},
    'geometry.idl': {'DOMRectReadOnly'},
    'webcrypto.idl': set(),
}

Node = dict[str, Any]


@dataclass
class Definition:
    name: str
    kind: str  # interface, dictionary or enum
    parent: str | None = None
    members: list[Node] = field(default_factory=list)
    values: list[str] = field(default_factory=list)


@dataclass
class Spec:
    definitions: dict[str, Definition]
    typedefs: dict[str, Node]

    def lineage(self, name: str) -> list[Definition]:
        """The definition and its ancestors that are part of the spec, nearest first."""
        chain = []
        while name in self.definitions:
            chain.append(self.definitions[name])
            name = self.definitions[name].parent
        return chain

    def members(self, name: str) -> list[Node]:
        """The members of a definition, inherited ones included."""
        return [member for definition in self.lineage(name) for member in definition.members]

    def named_types(self, idl_type: Node | list[Node] | str, known: Callable[[str], bool] | None = None) -> set[str]:
        """The definitions a type refers to through unions, generics and typedefs, but not ``known`` typedefs."""
        if isinstance(idl_type, list):
            return set().union(*(self.named_types(item, known) for item in idl_type))
        if isinstance(idl_type, dict):
            return self.named_types(idl_type['idlType'], known)
        if idl_type in self.typedefs:
            return set() if known and known(idl_type) else self.named_types(self.typedefs[idl_type], known)
        return {idl_type} if idl_type in self.definitions else set()

    def dictionary(self, idl_type: Node) -> Definition | None:
        """The dictionary a type is, unless it's a union or a generic."""
        while not idl_type['union'] and not idl_type['generic'] and isinstance(idl_type['idlType'], str):
            name = idl_type['idlType']
            if name in self.typedefs:
                idl_type = self.typedefs[name]
                continue
            definition = self.definitions.get(name)
            return definition if definition and definition.kind == 'dictionary' else None
        return None


def load() -> Spec:
    """The spec of :data:`FILES`."""
    return parse({name: (WPT_ROOT / 'interfaces' / name).read_text() for name in FILES}, FILES)


def parse(texts: dict[str, str], files: dict[str, set[str] | None]) -> Spec:
    """Parses IDL texts by file name and keeps the definitions each file takes, as in :data:`FILES`."""
    nodes = json.loads(
        subprocess.run(
            [sys.executable, '-m', 'tests.idl.child'],
            input=json.dumps(texts),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    spec = Spec(_merge(nodes), {node['name']: node['idlType'] for node in nodes if node['type'] == 'typedef'})
    taken = {
        node['name']
        for node in nodes
        if node.get('name') in spec.definitions
        and not node.get('partial')
        and (files[node['file']] is None or node['name'] in files[node['file']])
    }
    return Spec({name: spec.definitions[name] for name in sorted(_used(spec, taken))}, spec.typedefs)


def _merge(nodes: list[Node]) -> dict[str, Definition]:
    """The interfaces, dictionaries and enums, with the members of their partials and mixins."""
    definitions = {
        node['name']: Definition(
            node['name'],
            node['type'],
            node.get('inheritance'),
            list(node.get('members', [])),
            [value['value'] for value in node.get('values', [])],
        )
        for node in nodes
        if node['type'] in {'interface', 'dictionary', 'enum'} and not node.get('partial')
    }
    mixins: dict[str, list[Node]] = {}
    for node in nodes:
        if node['type'] == 'interface mixin':
            mixins.setdefault(node['name'], []).extend(node['members'])
    # partials and mixins extend definitions of any file, but only those that exist
    for node in nodes:
        if node.get('partial') and node['name'] in definitions:
            definitions[node['name']].members.extend(node['members'])
        elif node['type'] == 'includes' and node['target'] in definitions:
            definitions[node['target']].members.extend(mixins.get(node['includes'], []))
    return definitions


def _used(spec: Spec, taken: set[str]) -> set[str]:
    """The taken definitions, their ancestors and the dictionaries and enums they use."""
    wanted = set(taken)
    queue = list(taken)
    while queue:
        definition = spec.definitions[queue.pop()]
        used = {definition.parent} & spec.definitions.keys()
        for member in definition.members:
            types = [member.get('idlType')] + [argument['idlType'] for argument in member.get('arguments') or []]
            used |= {
                name
                for idl_type in types
                if idl_type
                for name in spec.named_types(idl_type)
                if spec.definitions[name].kind != 'interface'
            }
        queue += used - wanted
        wanted |= used
    return wanted
