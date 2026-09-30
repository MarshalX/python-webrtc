#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCSessionDescription, created as in the specification: a type is required, the SDP is optional."""

from __future__ import annotations

import pytest

import webrtc


def test_type_is_required() -> None:
    """The init of a description needs its type, as its WebIDL dictionary does."""
    with pytest.raises(TypeError):
        webrtc.RTCSessionDescription()
    with pytest.raises(TypeError):
        webrtc.RTCSessionDescription({'sdp': ''})
    with pytest.raises(TypeError):
        webrtc.RTCSessionDescription({'type': 'offer', 'sdp': None})


@pytest.mark.parametrize(
    'init', [{'type': 'rollback'}, webrtc.RTCSessionDescriptionInit('rollback'), webrtc.RTCSdpType.rollback]
)
def test_sdp_is_empty_by_default(
    init: dict[str, str] | webrtc.RTCSessionDescriptionInit | webrtc.RTCSdpType,
) -> None:
    """A description from a dictionary, an init or a type has an empty SDP."""
    description = webrtc.RTCSessionDescription(init)
    assert description.type == webrtc.RTCSdpType.rollback
    assert not description.sdp
    assert description.to_json() == {'type': 'rollback', 'sdp': ''}
