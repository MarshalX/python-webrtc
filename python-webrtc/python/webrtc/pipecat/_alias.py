#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

from webrtc.utils import module_alias


class _Finder(module_alias.ModuleAlias):
    source = 'pipecat.transports.smallwebrtc'
    target = 'webrtc.pipecat'


def install_alias() -> None:
    """Makes imports of the framework's own peer-to-peer transport give this package.

    Call it in every process before importing code that imports that transport.

    Raises:
        RuntimeError: If one of those modules is imported already.
    """
    module_alias.install(_Finder())
