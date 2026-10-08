#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Loopback candidates."""

from __future__ import annotations

import asyncio

import pytest

import webrtc
from tests.helpers import isolated, wait_until


async def _candidate_addresses() -> set[str]:
    pc = webrtc.RTCPeerConnection()
    pc.create_data_channel('channel')
    await pc.set_local_description()
    await wait_until(lambda: pc.ice_gathering_state == webrtc.RTCIceGatheringState.complete, 'ICE gathering')
    assert pc.local_description is not None
    lines = pc.local_description.sdp.splitlines()
    pc.close()
    return {line.split()[4] for line in lines if line.startswith('a=candidate:')}


@isolated
def _gathers_loopback(*, allow: bool) -> bool:
    if allow:
        webrtc.allow_loopback()
    return '127.0.0.1' in asyncio.run(_candidate_addresses())


@pytest.mark.parametrize('allow', [False, True])
def test_allow_loopback(monkeypatch: pytest.MonkeyPatch, *, allow: bool) -> None:
    monkeypatch.delenv('WRTC_ALLOW_LOOPBACK')

    assert _gathers_loopback(allow=allow) is allow


def test_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('WRTC_ALLOW_LOOPBACK', '1')

    assert _gathers_loopback(allow=False)


@isolated
def test_fixed_once_a_connection_is_created() -> None:
    webrtc.RTCPeerConnection().close()

    with pytest.raises(webrtc.InvalidStateError):
        webrtc.allow_loopback()
