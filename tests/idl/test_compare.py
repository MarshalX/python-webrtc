#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The rules of the comparison, on small IDL and classes."""

from __future__ import annotations

import enum
from collections import UserDict
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from tests.idl.compare import compare, snake_case
from tests.idl.spec import AVAILABLE, parse

if TYPE_CHECKING:
    import asyncio

pytestmark = pytest.mark.skipif(not AVAILABLE, reason='needs Python 3.10+, the WPT checkout and PythonMonkey')

IDL = """
enum Color { "red", "green" };
dictionary Options { boolean loud = false; required DOMString name; };
dictionary Point { double x; double y; };
interface Base : EventTarget { readonly attribute Color color; };
interface Thing : Base {
  constructor(DOMString label, optional Options options = {});
  attribute unsigned long size;
  readonly attribute DOMString sharedName;
  attribute EventHandler onping;
  Promise<undefined> start(optional Options options = {});
  undefined move(Point point);
  undefined add(DOMString... items);
  undefined sendDTMF(DOMString tones);
  static Thing create();
  undefined stopAll();
};
interface Report { readonly maplike<DOMString, object>; };
interface Unused {};
"""


def differences(**classes: type) -> dict[str, list[str]]:
    return compare(parse({'test.idl': IDL}, {'test.idl': None}), SimpleNamespace(**classes))


class Color(str, enum.Enum):
    red = 'red'
    blue = 'blue'


@dataclass
class Options:
    name: str = ''
    loud: bool = False


class Thing:
    _events = ('ping', 'pong')
    color: Color

    def __init__(self, label: str, *, loud: bool = False) -> None:
        self._label = label
        self._loud = loud
        self.size = 0
        self.extra = 1

    @property
    def shared_name(self) -> str:
        return ''

    @shared_name.setter
    def shared_name(self, value: str) -> None: ...

    async def start(self, *, name: str, loud: bool = False) -> None: ...

    def stop_all(self) -> None: ...

    def move(self, point: dict[str, float], z: float = 0) -> None: ...

    def add(self, items: list[str]) -> None: ...

    def send_dtmf(self, tones: str) -> None: ...

    def create(self) -> Thing:
        raise NotImplementedError


Thing.sharedName = Thing.shared_name
Thing.sendDTMF = Thing.send_dtmf


class Report(UserDict[str, object]):
    pass


def test_snake_case() -> None:
    assert snake_case('insertDTMF') == 'insert_dtmf'
    assert snake_case('toJSON') == 'to_json'
    assert snake_case('sdpMLineIndex') == 'sdp_m_line_index'


def test_missing_definitions() -> None:
    found = differences()
    assert found['Unused'] == ['missing interface']
    assert found['Color'] == ['missing enum']
    assert found['Point'] == ['missing dictionary']


def test_enum_values() -> None:
    assert differences(Color=Color)['Color'] == ["extra value 'blue'", "missing value 'green'"]


def test_dictionary() -> None:
    assert differences(Options=Options)['Options'] == ['name: should be required']


def test_interface() -> None:
    assert differences(Thing=Thing, Color=Color)['Thing'] == [
        'add(items): should be optional',
        'add(items): should be variadic',
        'constructor(options.name): missing member',
        'create: should be static',
        'extra: extra member',
        'move(point): type lacks Point',
        'move(z): extra argument',
        'onpong: extra event',
        'sharedName: should be read-only',
        'stopAll: missing camelCase alias',
    ]


def test_type_and_rename() -> None:
    class Other:
        color: str

        def move(self, where: Options, /) -> None: ...

        async def create(self) -> None: ...

    found = differences(Base=Other, Thing=type('Thing', (Other,), {}))
    assert 'color: type lacks Color' in found['Base']
    assert 'move(point): named where' in found['Thing']
    assert 'create: should not be async' in found['Thing']
    assert 'create: should be static' in found['Thing']


def test_maplike() -> None:
    class Partial:
        def __getitem__(self, key: str) -> object: ...

    assert 'Report' not in differences(Report=Report, Color=Color)
    assert 'maplike: missing keys' in differences(Report=Partial)['Report']


def test_future_counts_as_async() -> None:
    class Thing:
        def start(self) -> asyncio.Future[None]:
            raise NotImplementedError

    assert 'start: should be async' not in differences(Thing=Thing)['Thing']
