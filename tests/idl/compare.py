#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Finds the differences between the IDL definitions and the public API of the webrtc package.

Every definition maps to the object of the same name in the package. Members and arguments map by their snake_case
name, and members need their camelCase alias too. A dictionary argument is either one parameter or keyword
parameters for its members, like ``create_offer(*, ice_restart=False)``.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import functools
import inspect
import keyword
import re
import textwrap
from typing import TYPE_CHECKING

from typing_extensions import TypeGuard

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from tests.idl.spec import (
        Argument,
        Attribute,
        Constructor,
        Definition,
        Field,
        IdlType,
        Member,
        Operation,
        Spec,
    )

_BOUNDARY = re.compile(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')
_AWAITABLE = re.compile(r'\b(Future|Awaitable|Coroutine|Task)\b')
_P = inspect.Parameter

# the Python protocol for maplike, setlike and iterable declarations
_PROTOCOLS = {
    'maplike': ('__getitem__', '__iter__', '__len__', '__contains__', 'get', 'keys', 'values', 'items'),
    'setlike': ('__iter__', '__len__', '__contains__'),
    'iterable': ('__iter__',),
    'async_iterable': ('__aiter__', 'values'),
}
# toJSON returns the JSON form of its dictionary, which is a dict in Python
_JSON = re.compile(r'\b(dict|Mapping)\b')


def snake_case(name: str) -> str:
    """``'insertDTMF'`` -> ``'insert_dtmf'``, the way the package names acronyms."""
    return _BOUNDARY.sub('_', name).lower()


def python_name(name: str) -> str:
    """``'from'`` -> ``'from_'``: a keyword takes a trailing underscore, which Python names can't do without."""
    return f'{name}_' if keyword.iskeyword(name) else name


@functools.cache
def _assigned(cls: type) -> frozenset[str]:
    """The attributes the methods of a class assign to ``self``."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    except (OSError, TypeError):
        return frozenset()
    names = set()
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, 'target', None)]
        names.update(
            target.attr
            for target in targets
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self'
        )
    return frozenset(names)


def _names(cls: type) -> set[str]:
    """The public names of a class and its instances."""
    names = set(dir(cls))
    for klass in cls.__mro__:
        names |= set(inspect.get_annotations(klass)) | _assigned(klass)
    return {name for name in names if not name.startswith('_')}


def _text(annotation: object) -> str | None:
    """An annotation as text, the way ``from __future__ import annotations`` keeps it."""
    if annotation is _P.empty:
        return None
    return annotation if isinstance(annotation, str) else getattr(annotation, '__name__', str(annotation))


def _mentions(pattern: str | re.Pattern[str], annotation: object) -> bool:
    """Whether the text of an annotation matches a pattern."""
    text = _text(annotation)
    return re.search(pattern, text if text is not None else '') is not None


def _is_async(function: Callable[..., object]) -> bool:
    """Whether a function is a coroutine function or returns an awaitable, like a future."""
    if inspect.iscoroutinefunction(function):
        return True
    return _mentions(_AWAITABLE, inspect.signature(function).return_annotation)


def _type_names(idl_type: IdlType) -> str:
    inner = idl_type['idlType']
    return inner if isinstance(inner, str) else ' '.join(_type_names(item) for item in inner)


def _is_handler(member: Member) -> TypeGuard[Attribute]:
    """Whether a member is an event handler attribute, which the package replaces with ``on(name)``."""
    return (
        member['type'] == 'attribute'
        and member['name'].startswith('on')
        and 'EventHandler' in _type_names(member['idlType'])
    )


def _default(label: str, *, required: bool, has_default: bool) -> list[str]:
    if required and has_default:
        return [f'{label}: should be required']
    if not required and not has_default:
        return [f'{label}: should be optional']
    return []


class _Types:
    def __init__(self, spec: Spec) -> None:
        self.spec = spec

    def lacks(self, label: str, idl_type: IdlType, annotation: object) -> list[str]:
        """Checks that an annotation names the definitions the IDL type refers to."""
        text = _text(annotation)
        if text is None:
            return []

        def named(name: str) -> bool:
            return re.search(rf'\b{name}\b', text) is not None

        missing = sorted(name for name in self.spec.named_types(idl_type, named) if not named(name))
        return [f'{label}: type lacks {", ".join(missing)}'] if len(missing) > 0 else []


class _Arguments(_Types):
    """Matches the arguments of one overload with the parameters of a signature."""

    def __init__(self, spec: Spec, label: str, parameters: list[inspect.Parameter], *, span: int = 0) -> None:
        super().__init__(spec)
        self.label = label
        self.parameters = parameters
        # the arguments other overloads take: optional parameters in their positions merge those overloads
        self.span = span
        self.unused = {parameter.name: parameter for parameter in parameters}
        self.order: list[int] = []
        self.found: list[str] = []

    def check(self, arguments: list[Argument]) -> list[str]:
        for index, argument in enumerate(arguments):
            self.argument(index, argument)
        if self.order != sorted(self.order):
            self.found.append(f'{self.label}: arguments out of order')
        for parameter in self.unused.values():
            if self.merged(parameter):
                continue
            prefix = '*' if parameter.kind is _P.VAR_POSITIONAL else '**' if parameter.kind is _P.VAR_KEYWORD else ''
            self.found.append(f'{self.label}({prefix}{parameter.name}): extra argument')
        return self.found

    def merged(self, parameter: inspect.Parameter) -> bool:
        """Whether an optional parameter takes an argument of another overload, like ``MediaStream(tracks=None)``."""
        positional = parameter.kind in {_P.POSITIONAL_ONLY, _P.POSITIONAL_OR_KEYWORD}
        return positional and parameter.default is not _P.empty and self.parameters.index(parameter) < self.span

    def take(self, name: str) -> inspect.Parameter | None:
        parameter = self.unused.pop(python_name(snake_case(name)), None)
        return parameter if parameter is not None else self.unused.pop(python_name(name), None)

    def argument(self, index: int, argument: Argument) -> None:
        path = f'{self.label}({argument["name"]})'
        parameter = self.take(argument['name'])
        if parameter is None:
            members = self.flattened(argument)
            if members is not None:
                self.members(f'{self.label}({argument["name"]}', members)
                return
            parameter = self.positional(index)
            if parameter is None:
                self.found.append(f'{path}: missing argument')
                return
            # a positional-only parameter has no name callers use
            if parameter.kind is not _P.POSITIONAL_ONLY:
                self.found.append(f'{path}: named {parameter.name}')

        if argument['variadic'] != (parameter.kind is _P.VAR_POSITIONAL):
            self.found.append(f'{path}: should {"" if argument["variadic"] else "not "}be variadic')
        elif parameter.kind is _P.KEYWORD_ONLY:
            self.found.append(f'{path}: should be positional')
        else:
            self.order.append(self.parameters.index(parameter))
        has_default = parameter.default is not _P.empty or parameter.kind is _P.VAR_POSITIONAL
        optional = argument['optional'] or argument['variadic']
        self.found += _default(path, required=not optional, has_default=has_default)
        self.found += self.lacks(path, argument['idlType'], parameter.annotation)

    def positional(self, index: int) -> inspect.Parameter | None:
        """The unused parameter at the position of an argument, which has another name then."""
        if index >= len(self.parameters):
            return None
        parameter = self.parameters[index]
        if parameter.name not in self.unused or parameter.kind in {_P.KEYWORD_ONLY, _P.VAR_KEYWORD}:
            return None
        return self.unused.pop(parameter.name)

    def flattened(self, argument: Argument) -> list[Field] | None:
        """The members of a dictionary argument, if the signature takes them as parameters of their own."""
        dictionary = self.spec.dictionary(argument['idlType'])
        if dictionary is None:
            return None
        members = self.spec.fields(dictionary.name)
        matched = [
            self.unused[name]
            for member in members
            for name in {member['name'], snake_case(member['name'])} & self.unused.keys()
        ]
        # a lone positional parameter named like a member but annotated as a dictionary is the argument, renamed
        lone = len(matched) == 1 and matched[0].kind is not _P.KEYWORD_ONLY
        if len(matched) == 0 or (lone and _mentions(rf'\b(dict|Mapping|{dictionary.name})\b', matched[0].annotation)):
            return None
        return members

    def members(self, prefix: str, members: list[Field]) -> None:
        for member in members:
            path = f'{prefix}.{member["name"]})'
            parameter = self.take(member['name'])
            if parameter is None:
                self.found.append(f'{path}: missing member')
                continue
            has_default: bool = parameter.default is not _P.empty
            self.found += _default(path, required=member['required'], has_default=has_default)
            self.found += self.lacks(path, member['idlType'], parameter.annotation)


class _Class(_Types):
    """The differences of one class from its definition."""

    def __init__(self, spec: Spec, definition: Definition, cls: type) -> None:
        super().__init__(spec)
        self.definition = definition
        self.cls = cls
        self.names = _names(cls)
        self.expected: set[str] = set()
        self.found: list[str] = []

    def resolve(self, idl_name: str, kind: str) -> str | None:
        """Checks the snake_case name and the camelCase alias of a member, returning the one to inspect."""
        snake, camel = python_name(snake_case(idl_name)), python_name(idl_name)
        self.expected |= {camel, snake}
        if snake not in self.names and camel not in self.names:
            self.found.append(f'{idl_name}: missing {kind}')
            return None
        if snake not in self.names:
            self.found.append(f'{idl_name}: missing snake_case name {snake}')
        elif camel not in self.names:
            self.found.append(f'{idl_name}: missing camelCase alias')
        return snake if snake in self.names else camel

    def annotation(self, name: str) -> object:
        for klass in self.cls.__mro__:
            annotations = inspect.get_annotations(klass)
            if name in annotations:
                return annotations[name]
        return _P.empty

    def extras(self) -> list[str]:
        # the names of bases are infrastructure, or the extras of a base definition, reported once for it
        inherited = set()
        for base in self.cls.__mro__[1:]:
            inherited |= _names(base)
        extra = self.names - self.expected - inherited
        # a snake_case name and its camelCase alias are one member
        return [f'{name}: extra member' for name in extra if snake_case(name) == name or snake_case(name) not in extra]

    def check_enum(self) -> list[str]:
        if not issubclass(self.cls, enum.Enum):
            return ['is not an enum']
        values = {member.value for member in self.cls}
        wanted = self.definition.values
        return [f'missing value {value!r}' for value in wanted if value not in values] + [
            f'extra value {value!r}' for value in values - set(wanted)
        ]

    def check_dictionary(self) -> list[str]:
        fields: dict[str, dataclasses.Field[object]] = (
            {field.name: field for field in dataclasses.fields(self.cls)} if dataclasses.is_dataclass(self.cls) else {}
        )
        for member in self.spec.fields(self.definition.name):
            name = self.resolve(member['name'], 'member')
            if name is None:
                continue
            if name in fields:
                field = fields[name]
                has_default = (
                    field.default is not dataclasses.MISSING or field.default_factory is not dataclasses.MISSING
                )
                self.found += _default(member['name'], required=member['required'], has_default=has_default)
            self.found += self.lacks(member['name'], member['idlType'], self.annotation(name))
        return self.found + self.extras()

    def check_interface(self) -> list[str]:
        members = self.spec.members(self.definition.name)
        operations: dict[str, list[Operation]] = {}
        for member in members:
            if member['type'] == 'operation' and member['name'] != '':
                operations.setdefault(member['name'], []).append(member)
            else:
                self.check_member(member)

        self.check_events({member['name'][2:] for member in members if _is_handler(member)})
        constructors = [member for member in members if member['type'] == 'constructor']
        if len(constructors) > 0:
            self.check_overloads('constructor', constructors, lambda: inspect.signature(self.cls))
        for name, overloads in operations.items():
            self.check_operation(name, overloads)
        return self.found + self.extras()

    def check_member(self, member: Member) -> None:
        kind = member['type']
        if kind in _PROTOCOLS:
            self.expected |= set(_PROTOCOLS[kind])
            self.found += [f'{kind}: missing {method}' for method in _PROTOCOLS[kind] if not hasattr(self.cls, method)]
        elif member['type'] == 'const':
            name = member['name']
            self.expected.add(name)
            if name not in self.names:
                self.found.append(f'{name}: missing constant')
        elif _is_handler(member):
            self.expected |= {member['name'], snake_case(member['name'])}
        elif member['type'] == 'attribute':
            self.check_attribute(member)

    def check_events(self, events: set[str]) -> None:
        actual = set(getattr(self.cls, '_events', ()))
        self.found += [f'on{event}: missing event' for event in events - actual]
        self.found += [f'on{event}: extra event' for event in actual - events]

    def check_attribute(self, member: Attribute) -> None:
        idl_name = member['name']
        name = self.resolve(idl_name, 'attribute')
        if name is None:
            return
        attribute = inspect.getattr_static(self.cls, name, None)
        if inspect.isfunction(attribute):
            self.found.append(f'{idl_name}: should be an attribute, not a method')
            return
        annotation = self.annotation(name)
        if isinstance(attribute, property):
            if member['readonly'] and attribute.fset is not None:
                self.found.append(f'{idl_name}: should be read-only')
            elif not member['readonly'] and attribute.fset is None:
                self.found.append(f'{idl_name}: should be writable')
            assert attribute.fget is not None  # a property without a getter has no type
            annotation = inspect.get_annotations(attribute.fget).get('return', _P.empty)
        self.found += self.lacks(idl_name, member['idlType'], annotation)

    def check_operation(self, idl_name: str, overloads: list[Operation]) -> None:
        name = self.resolve(idl_name, 'method')
        if name is None:
            return
        attribute = inspect.getattr_static(self.cls, name)
        is_static = isinstance(attribute, (staticmethod, classmethod))
        function = attribute.__func__ if is_static else attribute
        if not callable(function) or isinstance(attribute, property):
            self.found.append(f'{idl_name}: should be a method')
            return
        static = overloads[0]['special'] == 'static'
        if static != is_static:
            self.found.append(f'{idl_name}: should {"" if static else "not "}be static')
        promise = overloads[0]['idlType']['generic'] == 'Promise'
        if promise != _is_async(function):
            self.found.append(f'{idl_name}: should {"" if promise else "not "}be async')

        def signature() -> inspect.Signature:
            result = inspect.signature(function)
            if isinstance(attribute, staticmethod):
                return result
            return result.replace(parameters=list(result.parameters.values())[1:])  # self or cls

        self.check_overloads(idl_name, overloads, signature)
        self.check_return(idl_name, overloads[0], signature().return_annotation)

    def check_return(self, idl_name: str, operation: Operation, returned: object) -> None:
        if idl_name != 'toJSON':
            self.found += self.lacks(f'{idl_name}()', operation['idlType'], returned)
        elif not _mentions(_JSON, returned):
            self.found.append(f'{idl_name}(): should return a dict')

    def check_overloads(
        self, label: str, overloads: Sequence[Operation | Constructor], signature: Callable[[], inspect.Signature]
    ) -> None:
        """Checks the arguments against the overload the signature matches best."""
        try:
            parameters = list(signature().parameters.values())
        except (TypeError, ValueError):
            return
        span = max(len(overload['arguments']) for overload in overloads) if len(overloads) > 1 else 0
        results = [
            _Arguments(self.spec, label, parameters, span=span).check(overload['arguments']) for overload in overloads
        ]
        self.found += min(results, key=len)


def _differences(spec: Spec, definition: Definition, module: object) -> list[str]:
    obj = getattr(module, definition.name, None)
    if obj is None:
        return [f'missing {definition.kind}']
    if not isinstance(obj, type):
        return ['is not a class']
    checker = _Class(spec, definition, obj)
    checks = {'enum': checker.check_enum, 'dictionary': checker.check_dictionary}
    return checks.get(definition.kind, checker.check_interface)()


def compare(spec: Spec, module: object) -> dict[str, list[str]]:
    """The differences of every definition that has some, by the name of the definition."""
    differences: dict[str, list[str]] = {}
    for name, definition in spec.definitions.items():
        found = sorted(set(_differences(spec, definition, module)))
        if len(found) > 0:
            differences[name] = found
    return differences
