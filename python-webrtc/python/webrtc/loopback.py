#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Loopback candidates, skipped unless allowed, as in the browsers."""

from __future__ import annotations

import os

import wrtc

__all__ = ['allowLoopback', 'allow_loopback']


def allow_loopback() -> None:
    """Gathers loopback candidates too, for peers on one machine. Same as ``WRTC_ALLOW_LOOPBACK=1``.

    Raises:
        webrtc.InvalidStateError: If a connection or an ICE transport was created already.
    """
    wrtc._allow_loopback()


#: Alias for :func:`allow_loopback`
allowLoopback = allow_loopback

if os.environ.get('WRTC_ALLOW_LOOPBACK') == '1':
    allow_loopback()
