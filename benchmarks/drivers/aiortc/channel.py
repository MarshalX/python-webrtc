#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#


"""A data channel of aiortc."""

from __future__ import annotations

from typing import TYPE_CHECKING

from benchmarks.drivers import base

if TYPE_CHECKING:
    import aiortc


class Channel(base.Channel):
    """A data channel of aiortc."""

    def __init__(self, channel: aiortc.RTCDataChannel) -> None:
        super().__init__()
        self._channel = channel
        channel.on('message', self._on_message)
        channel.on('bufferedamountlow', self.on_low)

    def send(self, data: bytes) -> None:
        """Sends a binary message."""
        self._channel.send(data)

    @property
    def buffered_amount(self) -> int:
        """The bytes queued to send."""
        return self._channel.bufferedAmount

    def set_low_threshold(self, value: int) -> None:
        """Sets the buffered amount at or below which ``bufferedamountlow`` fires."""
        self._channel.bufferedAmountLowThreshold = value

    def _on_message(self, data: bytes | str) -> None:
        if isinstance(data, bytes):
            self.on_message(data)
