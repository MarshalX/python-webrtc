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
from typing import TYPE_CHECKING, Literal, Union

from typing_extensions import TypedDict, TypeGuard

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


# the JSON AST of webidl2.js, as far as the comparison reads it
class IdlType(TypedDict):
    type: str | None
    generic: str
    nullable: bool
    union: bool
    idlType: str | list[IdlType]


class Argument(TypedDict):
    type: Literal['argument']
    name: str
    idlType: IdlType
    optional: bool
    variadic: bool


class Attribute(TypedDict):
    type: Literal['attribute']
    name: str
    idlType: IdlType
    special: str
    readonly: bool


class Operation(TypedDict):
    type: Literal['operation']
    name: str
    idlType: IdlType
    arguments: list[Argument]
    special: str


class Constructor(TypedDict):
    type: Literal['constructor']
    arguments: list[Argument]


class Const(TypedDict):
    type: Literal['const']
    name: str
    idlType: IdlType


class Field(TypedDict):
    type: Literal['field']
    name: str
    idlType: IdlType
    required: bool


class Declaration(TypedDict):
    type: Literal['iterable', 'async_iterable', 'maplike', 'setlike']
    idlType: list[IdlType]
    arguments: list[Argument]
    readonly: bool


Member = Union[Attribute, Operation, Constructor, Const, Field, Declaration]


class Container(TypedDict):
    type: Literal['interface', 'interface mixin', 'dictionary', 'namespace', 'callback interface']
    name: str
    inheritance: str | None
    members: list[Member]
    partial: bool
    file: str


class EnumValue(TypedDict):
    type: Literal['enum-value']
    value: str


class Enum(TypedDict):
    type: Literal['enum']
    name: str
    values: list[EnumValue]
    file: str


class Typedef(TypedDict):
    type: Literal['typedef']
    name: str
    idlType: IdlType
    file: str


class Callback(TypedDict):
    type: Literal['callback']
    name: str
    idlType: IdlType
    arguments: list[Argument]
    file: str


class Includes(TypedDict):
    type: Literal['includes']
    target: str
    includes: str
    file: str


Node = Union[Container, Enum, Typedef, Callback, Includes]


@dataclass
class Definition:
    name: str
    kind: str  # interface, dictionary or enum
    parent: str | None = None
    members: list[Member] = field(default_factory=list)
    values: list[str] = field(default_factory=list)


@dataclass
class Spec:
    definitions: dict[str, Definition]
    typedefs: dict[str, IdlType]

    def lineage(self, name: str) -> list[Definition]:
        """The definition and its ancestors that are part of the spec, nearest first."""
        chain: list[Definition] = []
        current: str | None = name
        while current is not None and current in self.definitions:
            chain.append(self.definitions[current])
            current = self.definitions[current].parent
        return chain

    def members(self, name: str) -> list[Member]:
        """The members of a definition, inherited ones included."""
        return [member for definition in self.lineage(name) for member in definition.members]

    def fields(self, name: str) -> list[Field]:
        """The members of a dictionary, inherited ones included."""
        return [member for member in self.members(name) if member['type'] == 'field']

    def named_types(
        self, idl_type: IdlType | list[IdlType] | str, known: Callable[[str], bool] | None = None
    ) -> set[str]:
        """The definitions a type refers to through unions, generics and typedefs, but not ``known`` typedefs."""
        if isinstance(idl_type, list):
            none: set[str] = set()
            return none.union(*(self.named_types(item, known) for item in idl_type))
        if isinstance(idl_type, dict):
            return self.named_types(idl_type['idlType'], known)
        if idl_type in self.typedefs:
            skip = known is not None and known(idl_type)
            return set() if skip else self.named_types(self.typedefs[idl_type], known)
        return {idl_type} if idl_type in self.definitions else set()

    def dictionary(self, idl_type: IdlType) -> Definition | None:
        """The dictionary a type is, unless it's a union or a generic."""
        while not idl_type['union'] and idl_type['generic'] == '' and isinstance(idl_type['idlType'], str):
            name = idl_type['idlType']
            if name in self.typedefs:
                idl_type = self.typedefs[name]
                continue
            definition = self.definitions.get(name)
            return definition if definition is not None and definition.kind == 'dictionary' else None
        return None


def load() -> Spec:
    """The spec of :data:`FILES`."""
    return parse({name: (WPT_ROOT / 'interfaces' / name).read_text() for name in FILES}, FILES)


def parse(texts: dict[str, str], files: dict[str, set[str] | None]) -> Spec:
    """Parses IDL texts by file name and keeps the definitions each file takes, as in :data:`FILES`."""
    nodes: list[Node] = json.loads(
        subprocess.run(
            [sys.executable, '-m', 'tests.idl.child'],
            input=json.dumps(texts),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    spec = Spec(_merge(nodes), {node['name']: node['idlType'] for node in nodes if node['type'] == 'typedef'})
    taken: set[str] = set()
    for node in nodes:
        if node['type'] == 'includes' or node['name'] not in spec.definitions or _is_partial(node):
            continue
        wanted = files[node['file']]
        if wanted is None or node['name'] in wanted:
            taken.add(node['name'])
    return Spec({name: spec.definitions[name] for name in sorted(_used(spec, taken))}, spec.typedefs)


def _is_partial(node: Node) -> TypeGuard[Container]:
    return (
        node['type'] in {'interface', 'interface mixin', 'dictionary', 'namespace', 'callback interface'}
        and node['partial']
    )


def _definitions(nodes: list[Node]) -> dict[str, Definition]:
    """The interfaces, dictionaries and enums, without their partials."""
    definitions: dict[str, Definition] = {}
    for node in nodes:
        if node['type'] in {'interface', 'dictionary'} and not node['partial']:
            definitions[node['name']] = Definition(
                node['name'], node['type'], node['inheritance'], list(node['members'])
            )
        elif node['type'] == 'enum':
            values = [value['value'] for value in node['values']]
            definitions[node['name']] = Definition(node['name'], node['type'], values=values)
    return definitions


def _merge(nodes: list[Node]) -> dict[str, Definition]:
    """The interfaces, dictionaries and enums, with the members of their partials and mixins."""
    definitions = _definitions(nodes)
    mixins: dict[str, list[Member]] = {}
    for node in nodes:
        if node['type'] == 'interface mixin':
            mixins.setdefault(node['name'], []).extend(node['members'])
    # partials and mixins extend definitions of any file, but only those that exist
    for node in nodes:
        if node['type'] == 'includes':
            if node['target'] in definitions:
                definitions[node['target']].members.extend(mixins.get(node['includes'], []))
        elif node['name'] in definitions and _is_partial(node):
            definitions[node['name']].members.extend(node['members'])
    return definitions


def _types(member: Member) -> list[IdlType | list[IdlType]]:
    """The type of a member and of its arguments."""
    types: list[IdlType | list[IdlType]] = [] if member['type'] == 'constructor' else [member['idlType']]
    if member['type'] not in {'attribute', 'const', 'field'}:
        types += [argument['idlType'] for argument in member['arguments']]
    return types


def _used(spec: Spec, taken: set[str]) -> set[str]:
    """The taken definitions, their ancestors and the dictionaries and enums they use."""
    wanted = set(taken)
    queue = list(taken)
    while len(queue) > 0:
        definition = spec.definitions[queue.pop()]
        used: set[str] = set()
        if definition.parent is not None and definition.parent in spec.definitions:
            used.add(definition.parent)
        for member in definition.members:
            used |= {
                name
                for idl_type in _types(member)
                for name in spec.named_types(idl_type)
                if spec.definitions[name].kind != 'interface'
            }
        queue += used - wanted
        wanted |= used
    return wanted
