#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""DTMF tones sent over an audio sender."""

from __future__ import annotations

import re
from typing import Literal, cast

from typing_extensions import override

import webrtc
import wrtc
from webrtc.base import WebRTCObject
from webrtc.models.events import RTCDTMFToneChangeEvent, RTCDTMFToneChangeEventInit
from webrtc.utils.events import UniformEventTarget

_TONES = re.compile(r'[0-9A-Da-d#*,]*')


class RTCDTMFSender(
    WebRTCObject[wrtc.RTCDTMFSender], UniformEventTarget[Literal['tonechange'], RTCDTMFToneChangeEvent]
):
    """Sends DTMF (telephone keypad) tones over an audio sender, from :attr:`webrtc.RTCRtpSender.dtmf`.

    See :mdn:`RTCDTMFSender`.

    Events:
        tonechange (:obj:`webrtc.RTCDTMFToneChangeEvent`): A tone started playing, or the last one ended
            (with an empty ``tone``).
    """

    _class = wrtc.RTCDTMFSender

    @override
    def _on_event(self, name: str, *args: object) -> None:
        _, tone_buffer, insertion = cast('tuple[str, str, int]', args)
        # the tone buffer is shortened along with the event
        self._native_obj._surfaceBuffer(tone_buffer, insertion)

    @override
    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        tone, _, _ = cast('tuple[str, str, int]', args)
        return RTCDTMFToneChangeEvent(name, RTCDTMFToneChangeEventInit(tone))

    def insert_dtmf(self, tones: str, duration: int = 100, inter_tone_gap: int = 70) -> None:
        """Queues tones to play, replacing the ones not played yet.

        Durations and gaps out of range are clamped to the nearest limit.

        See :mdn:`RTCDTMFSender/insertDTMF`.

        Args:
            tones (:obj:`str`): The tones: ``0`` to ``9``, ``A`` to ``D`` (any case), ``#``, ``*``, and ``,`` for a
                2-second pause. An empty string cancels the tones not played yet.
            duration (:obj:`int`, optional): The length of each tone in milliseconds, clamped to 40 to 6000.
            inter_tone_gap (:obj:`int`, optional): The pause after each tone in milliseconds, clamped to 30 to 6000.

        Raises:
            webrtc.InvalidCharacterError: If ``tones`` has another character.
            webrtc.InvalidStateError: If the transceiver of the sender is stopped or doesn't send.
        """
        if _TONES.fullmatch(tones) is None:
            msg = f'{tones!r} has characters that are not DTMF tones'
            raise webrtc.InvalidCharacterError(msg)
        duration = min(max(int(duration), 40), 6000)
        inter_tone_gap = min(max(int(inter_tone_gap), 30), 6000)
        self._native_obj.insertDTMF(tones.upper(), duration, inter_tone_gap)

    @property
    def tone_buffer(self) -> str:
        """:obj:`str`: The tones not played yet, in upper case.

        See :mdn:`RTCDTMFSender/toneBuffer`.
        """
        return self._native_obj.toneBuffer

    @property
    def can_insert_dtmf(self) -> bool:
        """:obj:`bool`: Whether tones can be sent.

        That needs the sender to be negotiated to send with a telephone-event codec.
        See :mdn:`RTCDTMFSender/canInsertDTMF`.
        """
        return self._native_obj.canInsertDTMF

    #: Alias for :attr:`insert_dtmf`
    insertDTMF = insert_dtmf
    #: Alias for :attr:`tone_buffer`
    toneBuffer = tone_buffer
    #: Alias for :attr:`can_insert_dtmf`
    canInsertDTMF = can_insert_dtmf
