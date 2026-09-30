#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""RTCDTMFSender of WebRTC."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from webrtc import InvalidCharacterError, RTCDTMFToneChangeEvent, WebRTCObject, wrtc
from webrtc.utils.events import EventTarget

if TYPE_CHECKING:
    import webrtc

_TONES = re.compile(r'[0-9A-Da-d#*,]*')


class RTCDTMFSender(WebRTCObject[wrtc.RTCDTMFSender], EventTarget):
    """Sends DTMF tones on an audio sender (:attr:`webrtc.RTCRtpSender.dtmf`).

    Events (see :meth:`on`):
        ``tonechange`` (:obj:`webrtc.RTCDTMFToneChangeEvent`): A tone started playing, or all tones were played
        (with an empty ``tone``).
    """

    _class = wrtc.RTCDTMFSender
    _events = ('tonechange',)

    def _on_event(self, _name: str, *args: object) -> None:
        _, tone_buffer, insertion = args
        # the tone buffer is shortened along with the event
        self._native_obj._surfaceBuffer(tone_buffer, insertion)

    def _create_event(self, name: str, *args: object) -> webrtc.Event | None:
        tone, _, _ = args
        return RTCDTMFToneChangeEvent(name, tone, target=self)

    def insert_dtmf(self, tones: str, duration: int = 100, inter_tone_gap: int = 70) -> None:
        """Plays tones, replacing the ones not played yet.

        Args:
            tones (:obj:`str`): The tones: ``0`` to ``9``, ``A`` to ``D``, ``#`` and ``*``, and ``,`` for a pause
                of 2 seconds. An empty string cancels the tones not played yet.
            duration (:obj:`int`, optional): The duration of a tone in milliseconds, from 40 to 6000.
            inter_tone_gap (:obj:`int`, optional): The pause between tones in milliseconds, at least 30.

        Raises:
            webrtc.InvalidCharacterError: If ``tones`` has another character.
            webrtc.InvalidStateError: If the transceiver of the sender is stopped or doesn't send.
        """
        if not _TONES.fullmatch(tones):
            msg = f'{tones!r} has characters that are not DTMF tones'
            raise InvalidCharacterError(msg)
        duration = min(max(int(duration), 40), 6000)
        inter_tone_gap = min(max(int(inter_tone_gap), 30), 6000)
        self._native_obj.insertDTMF(tones.upper(), duration, inter_tone_gap)

    @property
    def tone_buffer(self) -> str:
        """:obj:`str`: The tones not played yet."""
        return self._native_obj.toneBuffer

    @property
    def can_insert_dtmf(self) -> bool:
        """:obj:`bool`: Whether tones can be sent, once the sender is negotiated to send."""
        return self._native_obj.canInsertDTMF

    #: Alias for :attr:`insert_dtmf`
    insertDTMF = insert_dtmf
    #: Alias for :attr:`tone_buffer`
    toneBuffer = tone_buffer
    #: Alias for :attr:`can_insert_dtmf`
    canInsertDTMF = can_insert_dtmf
