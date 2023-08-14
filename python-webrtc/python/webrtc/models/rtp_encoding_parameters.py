#
#  Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from typing import Optional

from webrtc import wrtc, WebRTCObject


class RtpEncodingParameters(WebRTCObject):
    """Model describes a single configuration of a codec for an :obj:`webrtc.RTCRtpSender`."""

    _class = wrtc.RtpEncodingParameters

    def __init__(
        self,
        active: Optional[bool] = True,
        max_bitrate: Optional[int] = None,
        max_framerate: Optional[float] = None,
        rid: Optional[str] = None,
        scale_resolution_down_by: Optional[float] = None,
    ):
        # TODO so hacky ;d need to be able to wrap already created native objects
        if isinstance(active, self._class):
            super().__init__(active)
            return

        super().__init__()

        self.active = active
        self.max_bitrate = max_bitrate
        self.max_framerate = max_framerate
        self.rid = rid
        self.scale_resolution_down_by = scale_resolution_down_by

    @property
    def active(self) -> bool:
        """:obj:`bool`: If true, the described encoding is currently actively being used. That is, for RTP senders,
        the encoding is currently being used to send data, while for receivers, the encoding is being used to decode
        received data. The default value is true."""
        return self._native_obj.active

    @active.setter
    def active(self, value: bool):
        self._native_obj.active = value

    @property
    def max_bitrate(self) -> Optional[int]:
        """:obj:`int`, optional: An unsigned long integer indicating the maximum number of bits per second to allow
        for this encoding. Other parameters may further constrain the bit rate, such as the value
        of :attr:`max_framerate` or transport or physical network limitations."""
        return self._native_obj.maxBitrate

    @max_bitrate.setter
    def max_bitrate(self, value: Optional[int]):
        self._native_obj.maxBitrate = value

    @property
    def max_framerate(self) -> Optional[int]:
        """:obj:`int`, optional: A double-precision floating-point value specifying the maximum number
        of frames per second to allow for this encoding."""
        return self._native_obj.maxFramerate

    @max_framerate.setter
    def max_framerate(self, value: Optional[float]):
        self._native_obj.maxFramerate = value

    @property
    def rid(self) -> Optional[str]:
        """:obj:`str`, optional: A string which, if set, specifies an RTP stream ID (RID) to be sent using
        the RID header extension. This parameter cannot be modified using :attr:`webrtc.RTCRtpSender.set_parameters`.
        Its value can only be set when the transceiver is first created."""
        return self._native_obj.rid

    @rid.setter
    def rid(self, value: Optional[str]):
        if value is None:
            value = ''

        self._native_obj.rid = value

    @property
    def scale_resolution_down_by(self) -> Optional[float]:
        """:obj:`float`, optional: Only used for senders whose track's kind is video, this is a double-precision
        floating-point value specifying a factor by which to scale down the video during encoding.
        The default value, 1.0, means that the sent video's size will be the same as the original.
        A value of 2.0 scales the video frames down by a factor of 2 in each dimension,
        resulting in a video 1/4 the size of the original.
        The value must not be less than 1.0 (you can't use this to scale the video up)."""
        return self._native_obj.scaleResolutionDownBy

    @scale_resolution_down_by.setter
    def scale_resolution_down_by(self, value: Optional[float]):
        self._native_obj.scaleResolutionDownBy = value

    #: Alias for :attr:`max_bitrate`
    maxBitrate = max_bitrate
    #: Alias for :attr:`max_framerate`
    maxFramerate = max_framerate
    #: Alias for :attr:`scale_resolution_down_by`
    scaleResolutionDownBy = scale_resolution_down_by
