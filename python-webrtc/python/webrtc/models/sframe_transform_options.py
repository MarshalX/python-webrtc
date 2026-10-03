#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The options of the SFrame transforms of WebRTC Encoded Transform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from webrtc.enums import SFrameCipherSuite, SFrameType
from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias

if TYPE_CHECKING:
    from webrtc.enums import SFrameCipherSuiteValue, SFrameTypeValue


@dataclass
class SFrameTransformOptions(Dictionary):
    """The options of an :obj:`webrtc.RTCRtpSFrameDecryptor` and of the SFrame streams.

    Args:
        cipher_suite (:obj:`webrtc.SFrameCipherSuite`): The cipher suite, or its value.

    Raises:
        ValueError: If the cipher suite isn't a member of :obj:`webrtc.SFrameCipherSuite`.
    """

    cipher_suite: SFrameCipherSuite | SFrameCipherSuiteValue

    def __post_init__(self) -> None:
        self.cipher_suite = SFrameCipherSuite(self.cipher_suite)

    #: Alias for :attr:`cipher_suite`
    cipherSuite: ClassVar[Alias[SFrameCipherSuite | SFrameCipherSuiteValue]] = alias('cipher_suite')


@dataclass
class RTCRtpSFrameEncryptorOptions(SFrameTransformOptions):
    """The options of an :obj:`webrtc.RTCRtpSFrameEncryptor`.

    Args:
        cipher_suite (:obj:`webrtc.SFrameCipherSuite`): The cipher suite, or its value.
        type (:obj:`webrtc.SFrameType`, optional): Whether whole frames or RTP packets are encrypted, or its value.
            Only ``'per-frame'`` is supported.

    Raises:
        ValueError: If the cipher suite or the type isn't a member of its enum.
    """

    type: SFrameType | SFrameTypeValue = SFrameType.per_frame

    def __post_init__(self) -> None:
        super().__post_init__()
        self.type = SFrameType(self.type)
