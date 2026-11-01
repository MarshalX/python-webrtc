#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""A native peer shaped like the browser client of the bot framework."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import webrtc
from tests.helpers import wait_until

if TYPE_CHECKING:
    from webrtc.pipecat.connection import SmallWebRTCConnection

SENDRECV = webrtc.RTCRtpTransceiverInit(direction='sendrecv')
SENDONLY = webrtc.RTCRtpTransceiverInit(direction='sendonly')


class BrowserClient:
    """A microphone, a camera, a send-only screen share and a data channel; it offers before gathering.

    Args:
        video: Whether it has the camera and the screen share.
        channel: Whether it creates the data channel.
    """

    def __init__(self, *, video: bool = True, channel: bool = True) -> None:
        self.pc = webrtc.RTCPeerConnection()
        self.microphone = self.pc.add_transceiver('audio', SENDRECV)
        self.camera = self.pc.add_transceiver('video', SENDRECV) if video else None
        self.screen = self.pc.add_transceiver('video', SENDONLY) if video else None
        self.channel: webrtc.RTCDataChannel | None = None
        if channel:
            self.open_channel()

        #: The JSON messages received on the data channel
        self.messages: list[object] = []
        self.candidates: list[webrtc.RTCIceCandidate] = []
        self.pc.on('icecandidate', self._on_candidate)

    def open_channel(self) -> None:
        """Creates the data channel, which needs a negotiation once connected."""
        self.channel = self.pc.create_data_channel('chat')
        self.channel.on('message', self._on_message)

    def _on_candidate(self, event: webrtc.RTCPeerConnectionIceEvent) -> None:
        if event.candidate is not None:
            self.candidates.append(event.candidate)

    def _on_message(self, event: webrtc.MessageEvent) -> None:
        assert isinstance(event.data, str)
        self.messages.append(json.loads(event.data))

    async def offer(self) -> dict[str, str]:
        """A new offer, as the client posts it."""
        await self.pc.set_local_description()
        description = self.pc.local_description
        assert description is not None
        return {'sdp': description.sdp, 'type': str(description.type)}

    async def accept(self, answer: dict[str, str] | None) -> None:
        assert answer is not None
        description = webrtc.RTCSessionDescriptionInit(type=webrtc.RTCSdpType(answer['type']), sdp=answer['sdp'])
        await self.pc.set_remote_description(description)

    async def gathered_candidates(self) -> list[webrtc.RTCIceCandidate]:
        """The client's candidates, once it gathered them all."""
        await wait_until(lambda: self.pc.ice_gathering_state == 'complete', 'the client gathering')
        return self.candidates

    async def wait_connected(self) -> None:
        await wait_until(lambda: self.pc.connection_state == 'connected', 'the client connecting')

    async def wait_channel_open(self) -> None:
        assert self.channel is not None
        channel = self.channel
        await wait_until(lambda: channel.ready_state == 'open', 'the data channel opening')

    def send(self, message: object) -> None:
        self.send_text(json.dumps(message))

    def send_text(self, text: str) -> None:
        assert self.channel is not None
        self.channel.send(text)

    def ping(self) -> None:
        self.send_text('ping: 0')

    def close_channel(self) -> None:
        assert self.channel is not None
        self.channel.close()

    def close(self) -> None:
        self.pc.close()


def wire_candidate(candidate: webrtc.RTCIceCandidate) -> dict[str, object]:
    """A candidate as the client sends it to the bot."""
    return {
        'candidate': candidate.candidate,
        'sdp_mid': candidate.sdp_mid,
        'sdp_mline_index': candidate.sdp_m_line_index,
    }


async def add_candidates(connection: SmallWebRTCConnection, client: BrowserClient) -> None:
    """Adds the client's candidates to the connection."""
    for candidate in await client.gathered_candidates():
        init = webrtc.RTCIceCandidateInit(
            candidate=candidate.candidate, sdp_mid=candidate.sdp_mid, sdp_m_line_index=candidate.sdp_m_line_index
        )
        await connection.add_ice_candidate(init)


async def connect_client(connection: SmallWebRTCConnection, client: BrowserClient) -> None:
    """Answers the client's offer, sends its candidates, and waits until both are connected."""
    offer = await client.offer()
    await connection.initialize(sdp=offer['sdp'], type=offer['type'])
    await client.accept(connection.get_answer())
    await add_candidates(connection, client)

    await client.wait_connected()
    await wait_until(lambda: connection.pc.connection_state == 'connected', 'the bot connecting')
