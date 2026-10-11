#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The session description of one end of a connection."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import wrtc
from webrtc.base import WebRTCObject
from webrtc.models.rtc_session_description_init import RTCSessionDescriptionInit

if TYPE_CHECKING:
    import webrtc


class RTCSessionDescription(WebRTCObject[wrtc.RTCSessionDescription]):
    """A session description set on a connection, with its SDP and its role in the offer/answer exchange.

    :attr:`webrtc.RTCPeerConnection.local_description` and the other description properties return it. The
    methods that set a description take an :obj:`webrtc.RTCSessionDescriptionInit` as well, so creating one
    is rarely needed. The type is checked on creation, but the SDP is only parsed once the description is set.
    Both are writable; a description already set on a connection doesn't change.
    See :mdn:`RTCSessionDescription`.

    Args:
        type (:obj:`webrtc.RTCSdpType`): The type of the description, or its value (like ``'offer'``). An
            :obj:`webrtc.RTCSessionDescriptionInit` is taken too, in which case ``sdp`` is ignored.
        sdp (:obj:`str`, optional): The SDP of the description, empty by default.

    Raises:
        ValueError: If the type isn't a member of :obj:`webrtc.RTCSdpType`.
        TypeError: If the SDP is :obj:`None`.
    """

    __slots__ = ()

    _class = wrtc.RTCSessionDescription
    # a value: the setters replace the native object
    _canonical: ClassVar[bool] = False

    def __init__(
        self,
        type: webrtc.RTCSdpType | webrtc.RTCSdpTypeValue | webrtc.RTCSessionDescriptionInit,
        sdp: str = '',
    ) -> None:
        init = type if isinstance(type, RTCSessionDescriptionInit) else RTCSessionDescriptionInit(type, sdp)
        super().__init__(wrtc.RTCSessionDescription(init._to_native()))

    def to_json(self) -> dict[str, str]:
        """Returns the description as a JSON-serializable dictionary, to send to the remote peer.

        :meth:`webrtc.RTCSessionDescriptionInit.from_json` reads it back.
        See :mdn:`RTCSessionDescription/toJSON`.

        Returns:
            :obj:`dict`: ``type`` (like ``'offer'``) and ``sdp``.
        """
        return {'type': self.type.value, 'sdp': self.sdp}

    @property
    def type(self) -> webrtc.RTCSdpType:
        """:obj:`webrtc.RTCSdpType`: The role of the description in the offer/answer exchange.

        It can be set with a member or its value. See :mdn:`RTCSessionDescription/type`.
        """
        return self._native_obj.type

    @type.setter
    def type(self, value: webrtc.RTCSdpType | webrtc.RTCSdpTypeValue) -> None:
        self._replace(RTCSessionDescriptionInit(value, self.sdp))

    @property
    def sdp(self) -> str:
        """:obj:`str`: The SDP of the description, which may be empty (like for a ``rollback``).

        See :mdn:`RTCSessionDescription/sdp`.
        """
        return self._native_obj.sdp

    @sdp.setter
    def sdp(self, value: str) -> None:
        self._replace(RTCSessionDescriptionInit(self.type, value))

    def _replace(self, init: RTCSessionDescriptionInit) -> None:
        # the connection shares the native object
        self._init_native(wrtc.RTCSessionDescription(init._to_native()))

    #: Alias for :attr:`to_json`
    toJSON = to_json
