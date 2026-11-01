#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The framework's transport modules served by this package, each in a process of its own."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import pathlib
import sys
from unittest import mock

import fastapi
import pytest
from fastapi.routing import APIRoute

import webrtc.pipecat
from tests.isolation import isolated
from webrtc.pipecat import install_alias

TRANSPORT = 'pipecat.transports.smallwebrtc'


def framework_root() -> pathlib.Path:
    framework = importlib.import_module('pipecat')
    assert framework.__file__ is not None
    return pathlib.Path(framework.__file__).parent


def alias_finders() -> int:
    return sum(type(finder).__module__ == 'webrtc.pipecat._alias' for finder in sys.meta_path)


@isolated
def test_modules_are_ours() -> None:
    install_alias()

    package = importlib.import_module(TRANSPORT)

    assert package is webrtc.pipecat
    assert sys.modules[TRANSPORT] is package
    assert importlib.import_module('pipecat.transports').smallwebrtc is package
    assert package.__spec__ is not None
    assert package.__spec__.name == 'webrtc.pipecat'


@isolated
def test_found_without_importing() -> None:
    install_alias()

    spec = importlib.util.find_spec(TRANSPORT)

    assert spec is not None
    assert spec.submodule_search_locations is not None
    assert TRANSPORT not in sys.modules


@isolated
def test_a_module_we_lack_is_not_found() -> None:
    install_alias()

    with pytest.raises(ModuleNotFoundError) as error:
        _ = importlib.import_module(f'{TRANSPORT}.missing')

    assert error.value.name == f'{TRANSPORT}.missing'


@isolated
def test_installing_again_does_nothing() -> None:
    install_alias()
    _ = importlib.import_module(TRANSPORT)

    install_alias()

    assert alias_finders() == 1


@isolated
def test_fails_once_the_original_is_imported() -> None:
    _ = importlib.import_module(TRANSPORT)

    with pytest.raises(RuntimeError, match=f'{TRANSPORT} imported already'):
        install_alias()

    assert alias_finders() == 0


@isolated
def test_other_modules_are_left_alone() -> None:
    install_alias()

    sibling = importlib.util.find_spec('pipecat.transports.websocket')

    assert sibling is not None
    assert sibling.origin is not None
    assert pathlib.Path(sibling.origin).is_relative_to(framework_root())


@isolated
def test_the_compat_layer_stays_unimported() -> None:
    install_alias()

    _ = importlib.import_module(TRANSPORT)

    assert 'webrtc.aiortc' not in sys.modules
    assert 'aiortc' not in sys.modules


@isolated
def test_the_runners_routes_take_ours() -> None:
    install_alias()
    run = importlib.import_module('pipecat.runner.run')
    app = fastapi.FastAPI()
    args = argparse.Namespace(downloads_folder=None, ice_servers=[], esp32=False, host='localhost')

    # the routes are gated on a package the alias makes unneeded, which may be missing
    with mock.patch.object(run, '_transport_routes_enabled', return_value=True):
        run._setup_webrtc_routes(app, args, {})

    routes = {(route.path, method) for route in app.routes if isinstance(route, APIRoute) for method in route.methods}
    assert {('/api/offer', 'POST'), ('/api/offer', 'PATCH')} <= routes
    assert sys.modules[f'{TRANSPORT}.request_handler'] is importlib.import_module('webrtc.pipecat.request_handler')
    assert 'aiortc' not in sys.modules


@isolated
def test_the_whatsapp_client_takes_ours() -> None:
    install_alias()

    client = importlib.import_module('pipecat.transports.whatsapp.client')

    assert client.SmallWebRTCConnection is webrtc.pipecat.SmallWebRTCConnection
    assert client.IceServer is webrtc.pipecat.IceServer
    assert 'aiortc' not in sys.modules


@isolated
def test_the_transport_is_ours() -> None:
    """The module the runner creates its transport from."""
    install_alias()

    transport = importlib.import_module(f'{TRANSPORT}.transport')

    assert transport.SmallWebRTCTransport is webrtc.pipecat.SmallWebRTCTransport
    assert 'aiortc' not in sys.modules
