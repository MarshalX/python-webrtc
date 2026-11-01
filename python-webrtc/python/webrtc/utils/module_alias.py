#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Serves the imports of one package from another."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from typing import TYPE_CHECKING, ClassVar

from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Sequence
    from importlib.machinery import ModuleSpec
    from types import ModuleType


def _in_package(name: str, package: str) -> bool:
    return name == package or name.startswith(package + '.')


class _Loader(importlib.abc.Loader):
    def __init__(self, target: str) -> None:
        self._target = target
        self._spec: ModuleSpec | None = None

    @override
    def create_module(self, spec: ModuleSpec) -> ModuleType:
        module = importlib.import_module(self._target)
        self._spec = module.__spec__
        return module

    @override
    def exec_module(self, module: ModuleType) -> None:
        # its relative imports read its own spec
        module.__spec__ = self._spec


class ModuleAlias(importlib.abc.MetaPathFinder):
    """Gives ``target.x`` for ``source.x``, never the source's own module; a subclass sets both."""

    source: ClassVar[str]
    target: ClassVar[str]

    @override
    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> ModuleSpec | None:
        if not _in_package(fullname, self.source):
            return None

        target_name = self.target + fullname[len(self.source) :]
        found = importlib.util.find_spec(target_name)
        if found is None:
            return None

        is_package = found.submodule_search_locations is not None
        return importlib.util.spec_from_loader(fullname, _Loader(target_name), is_package=is_package)

    def imported_originals(self) -> list[str]:
        """The source's own modules imported already."""
        imported = list(sys.modules.items())
        return [
            name
            for name, module in imported
            if _in_package(name, self.source) and not _in_package(getattr(module, '__name__', ''), self.target)
        ]


def install(alias: ModuleAlias) -> None:
    """Puts the alias first on :data:`sys.meta_path`; one of the same type again does nothing.

    Raises:
        RuntimeError: If a module of the source is imported already.
    """
    if any(isinstance(finder, type(alias)) for finder in sys.meta_path):
        return

    imported = alias.imported_originals()
    if len(imported) > 0:
        msg = f'{", ".join(imported)} imported already: call install_alias() before anything imports {alias.source}'
        raise RuntimeError(msg)

    sys.meta_path.insert(0, alias)
