#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The options of creating an offer or an answer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from webrtc.models.dictionary import Dictionary
from webrtc.utils.names import Alias, alias


@dataclass
class RTCOfferAnswerOptions(Dictionary):
    """The options of :meth:`webrtc.RTCPeerConnection.create_offer` and :meth:`webrtc.RTCPeerConnection.create_answer`.

    Args:
        voice_activity_detection (:obj:`bool`, optional): Whether audio codecs may use voice activity detection.
    """

    voice_activity_detection: bool = True

    #: Alias for :attr:`voice_activity_detection`
    voiceActivityDetection: ClassVar[Alias[bool]] = alias('voice_activity_detection')


@dataclass
class RTCOfferOptions(RTCOfferAnswerOptions):
    """The options of :meth:`webrtc.RTCPeerConnection.create_offer`.

    Args:
        voice_activity_detection (:obj:`bool`, optional): Whether audio codecs may use voice activity detection.
        ice_restart (:obj:`bool`, optional): Whether to restart ICE, gathering new credentials and candidates.
            :meth:`webrtc.RTCPeerConnection.restart_ice` is the preferred way.
        offer_to_receive_audio (:obj:`bool`, optional): Legacy: :obj:`True` adds a receiving audio transceiver
            if there's none, :obj:`False` stops receiving audio on the existing ones.
            :meth:`webrtc.RTCPeerConnection.add_transceiver` is the preferred way.
        offer_to_receive_video (:obj:`bool`, optional): The same for video.
    """

    ice_restart: bool = False
    offer_to_receive_audio: bool | None = None
    offer_to_receive_video: bool | None = None

    #: Alias for :attr:`ice_restart`
    iceRestart: ClassVar[Alias[bool]] = alias('ice_restart')
    #: Alias for :attr:`offer_to_receive_audio`
    offerToReceiveAudio: ClassVar[Alias[bool | None]] = alias('offer_to_receive_audio')
    #: Alias for :attr:`offer_to_receive_video`
    offerToReceiveVideo: ClassVar[Alias[bool | None]] = alias('offer_to_receive_video')


@dataclass
class RTCAnswerOptions(RTCOfferAnswerOptions):
    """The options of :meth:`webrtc.RTCPeerConnection.create_answer`.

    Args:
        voice_activity_detection (:obj:`bool`, optional): Whether audio codecs may use voice activity detection.
    """
