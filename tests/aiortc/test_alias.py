#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""``import aiortc`` served by the layer, each in a process of its own."""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types

import pytest

import webrtc.aiortc
from tests.isolation import isolated
from webrtc.aiortc import install_alias


def alias_finders() -> int:
    return sum(type(finder).__module__ == 'webrtc.aiortc._alias' for finder in sys.meta_path)


@isolated
def test_modules_are_the_layers() -> None:
    install_alias()

    package = importlib.import_module('aiortc')
    media = importlib.import_module('aiortc.contrib.media')
    jitterbuffer = importlib.import_module('aiortc.jitterbuffer')

    assert package is webrtc.aiortc
    assert media is importlib.import_module('webrtc.aiortc.contrib.media')
    assert jitterbuffer is importlib.import_module('webrtc.aiortc.jitterbuffer')
    assert sys.modules['aiortc.contrib.media'] is media
    assert media.__spec__ is not None
    assert media.__spec__.name == 'webrtc.aiortc.contrib.media'


@isolated
def test_found_without_importing() -> None:
    install_alias()

    spec = importlib.util.find_spec('aiortc')

    assert spec is not None
    assert spec.submodule_search_locations is not None
    assert 'aiortc' not in sys.modules


@isolated
def test_a_module_the_layer_lacks_is_not_found() -> None:
    install_alias()

    with pytest.raises(ModuleNotFoundError) as error:
        _ = importlib.import_module('aiortc.rate')

    assert error.value.name == 'aiortc.rate'


@isolated
def test_installing_again_does_nothing() -> None:
    install_alias()
    _ = importlib.import_module('aiortc')

    install_alias()

    assert alias_finders() == 1


@isolated
def test_fails_once_the_original_is_imported() -> None:
    sys.modules['aiortc'] = types.ModuleType('aiortc')

    with pytest.raises(RuntimeError, match='aiortc imported already'):
        install_alias()

    assert alias_finders() == 0


@isolated
def test_other_packages_are_left_alone() -> None:
    install_alias()

    assert importlib.util.find_spec('aiortc_extras') is None
