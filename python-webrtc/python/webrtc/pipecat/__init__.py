#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""A peer-to-peer transport for voice and video bot pipelines, see https://wrtc.marshal.dev/guides/pipecat/."""

from __future__ import annotations

import importlib.util

if importlib.util.find_spec('pipecat') is None:
    msg = 'webrtc.pipecat needs its extra, on Python 3.11+: pip install "wrtc[pipecat]"'
    raise ModuleNotFoundError(msg, name='pipecat')

from webrtc.pipecat._alias import install_alias as install_alias
from webrtc.pipecat.connection import IceServer as IceServer, SmallWebRTCConnection as SmallWebRTCConnection
from webrtc.pipecat.transport import SmallWebRTCTransport as SmallWebRTCTransport

__all__ = ['IceServer', 'SmallWebRTCConnection', 'SmallWebRTCTransport', 'install_alias']
