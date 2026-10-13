#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#


"""A data channel of python-webrtc."""

from __future__ import annotations

from typing import TYPE_CHECKING

from benchmarks.drivers import base

if TYPE_CHECKING:
    import webrtc


class Channel(base.Channel):
    """A data channel of python-webrtc."""

    def __init__(self, channel: webrtc.RTCDataChannel) -> None:
        super().__init__()
        self._channel = channel
        channel.on('message', self._on_message)
        channel.on('bufferedamountlow', lambda _: self.on_low())

    def send(self, data: bytes) -> None:
        """Sends a binary message."""
        self._channel.send(data)

    @property
    def buffered_amount(self) -> int:
        """The bytes queued to send."""
        return self._channel.buffered_amount

    def set_low_threshold(self, value: int) -> None:
        """Sets the buffered amount at or below which ``bufferedamountlow`` fires."""
        self._channel.buffered_amount_low_threshold = value

    def _on_message(self, event: webrtc.MessageEvent) -> None:
        if isinstance(event.data, bytes):
            self.on_message(event.data)
