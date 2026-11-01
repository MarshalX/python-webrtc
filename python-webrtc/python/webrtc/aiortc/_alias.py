#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

from webrtc.utils import module_alias


class _Finder(module_alias.ModuleAlias):
    source = 'aiortc'
    target = 'webrtc.aiortc'


def install_alias() -> None:
    """Makes ``import aiortc.x`` give ``webrtc.aiortc.x``, for libraries that import aiortc themselves.

    A module this package lacks raises :obj:`ModuleNotFoundError`. Call it before importing such a library, in each
    process. Calling it again does nothing.

    Raises:
        RuntimeError: If an ``aiortc`` module is imported already.
    """
    module_alias.install(_Finder())
