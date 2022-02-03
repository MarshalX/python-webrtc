from typing import TYPE_CHECKING

from webrtc import wrtc, WebRTCObject


if TYPE_CHECKING:
    import webrtc


class RTCSessionDescriptionInit(WebRTCObject):
    """An object providing the default values for the session description."""
    _class = wrtc.RTCSessionDescriptionInit

    def __init__(self, type: 'webrtc.RTCSdpType', sdp=''):
        self._set_native_obj(self._class(type, sdp))

    @property
    def type(self) -> 'webrtc.RTCSdpType':
        """:obj:`webrtc.RTCSdpType`: A member of the :obj:`webrtc.RTCSdpType` enum."""
        return self._native_obj.type

    @type.setter
    def type(self, value: 'webrtc.RTCSdpType'):
        self._native_obj.type = value

    @property
    def sdp(self) -> str:
        """:obj:`str`: A string containing a SDP message describing the session.
        This value is an empty string ('') by default and may not be None."""
        return self._native_obj.sdp

    @sdp.setter
    def sdp(self, value: str):
        self._native_obj.sdp = value
