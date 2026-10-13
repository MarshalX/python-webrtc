#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#


"""The driver of aiortc."""

from __future__ import annotations

import asyncio

import aioice.ice
import aiortc
from aiortc.contrib.media import MediaRelay

from benchmarks.drivers import base, frames
from benchmarks.drivers.aiortc import media
from benchmarks.drivers.aiortc.channel import Channel
from benchmarks.protocol import DATA_CHANNEL_LABEL, Answer, Created, Hello, Message, Offer, Server, now

_host_addresses = aioice.ice.get_host_addresses


def _with_loopback(*, use_ipv4: bool, use_ipv6: bool) -> list[str]:
    """The addresses aioice gathers on, and loopback, as the other drivers gather on it too."""
    loopback: list[str] = ['127.0.0.1'] if use_ipv4 else []
    return [*loopback, *_host_addresses(use_ipv4=use_ipv4, use_ipv6=use_ipv6)]


class Driver(base.Driver):
    """Connections of aiortc."""

    def __init__(self, server: Server) -> None:
        super().__init__(server)
        self._peers: dict[int, aiortc.RTCPeerConnection] = {}
        self._relay = MediaRelay()
        self._audio: media.ToneTrack | None = None
        self._readers: set[asyncio.Task[None]] = set()
        self._codecs: dict[int, str] = {}

    @staticmethod
    async def hello() -> Hello:
        """The library, its version, and that it doesn't trickle."""
        return {'library': 'aiortc', 'version': aiortc.__version__, 'trickle': False}

    async def create(self, pc: int, role: str, *, trickle: bool, ordered: bool, audio: bool, codec: str) -> Created:
        """Creates a connection, a data channel (and the audio track, if asked) for the offerer; never trickles."""
        del trickle
        self._codecs[pc] = codec

        t_start = now()
        # no STUN server, as for the other libraries
        peer = aiortc.RTCPeerConnection(aiortc.RTCConfiguration(iceServers=[]))
        self._peers[pc] = peer
        self._watch(pc, peer)

        if role == 'offerer':
            self._watch_channel(pc, peer.createDataChannel(DATA_CHANNEL_LABEL, ordered=ordered))
            if audio:
                peer.addTrack(self._relay.subscribe(self._audio_source()))
        else:

            def on_channel(channel: aiortc.RTCDataChannel) -> None:
                self._watch_channel(pc, channel)

            peer.on('datachannel', on_channel)

        def on_track(track: aiortc.MediaStreamTrack) -> None:
            self._receive(pc, track)

        peer.on('track', on_track)

        return {'t_start': t_start, 't_end': now()}

    async def offer(self, pc: int) -> Offer:
        """Creates and sets an offer, with the candidates gathered."""
        peer = self._peers[pc]
        t_start = now()
        offer = await peer.createOffer()
        t_offer = now()
        return {'sdp': await self._set_local(pc, offer), 't_start': t_start, 't_offer': t_offer}

    async def answer(self, pc: int, sdp: str) -> Answer:
        """Sets an offer, then creates and sets an answer, with the candidates gathered."""
        peer = self._peers[pc]
        await peer.setRemoteDescription(aiortc.RTCSessionDescription(sdp=sdp, type='offer'))
        return {'sdp': await self._set_local(pc, await peer.createAnswer())}

    async def accept(self, pc: int, sdp: str) -> Message:
        """Sets an answer."""
        await self._peers[pc].setRemoteDescription(aiortc.RTCSessionDescription(sdp=sdp, type='answer'))
        return {}

    async def close(self, pc: int) -> Message:
        """Closes a connection."""
        await self._peers.pop(pc).close()
        self.channels.pop(pc, None)
        return {}

    async def video_send(
        self, pc: int, *, path: str, width: int, height: int, fps: float, bitrate: int, numbered: bool
    ) -> Message:
        """Sends the raw frames of a file, encoded in the connection's codec; aiortc takes the bitrate from REMB."""
        del bitrate
        track = media.VideoTrack(frames.load_raw(path, width, height), size=(width, height), fps=fps, numbered=numbered)
        self.tallies[pc] = track.tally
        transceiver = self._peers[pc].addTransceiver(track, direction='sendonly')
        transceiver.setCodecPreferences(media.codecs(self._codecs[pc]))
        return {}

    async def audio_send(self, pc: int, *, path: str) -> Message:
        """Sends the process's tone."""
        del path
        self._peers[pc].addTrack(self._relay.subscribe(self._audio_source()))
        return {}

    async def sent_bytes(self, pc: int) -> int:
        """The bytes of the RTP streams sent, from the stats."""
        report = await self._peers[pc].getStats()
        return sum(s.bytesSent for s in report.values() if s.type == 'outbound-rtp')

    async def implementation(self, pc: int) -> str:
        """The PyAV codec aiortc encodes or decodes the connection's video with."""
        encoder, decoder = media.IMPLEMENTATIONS.get(self._codecs[pc], ('libopus', 'libopus'))
        sending = any(t.sender.track is not None for t in self._peers[pc].getTransceivers())
        return encoder if sending else decoder

    def _audio_source(self) -> media.ToneTrack:
        """The tone, relayed to every connection."""
        if self._audio is None:
            self._audio = media.ToneTrack()
        return self._audio

    def _receive(self, pc: int, track: aiortc.MediaStreamTrack) -> None:
        self.server.emit(pc, 'track')
        tally = self.tallies.get(pc, frames.Tally())
        task = asyncio.ensure_future(media.read(track, tally, numbered=self.numbered.get(pc, False)))
        self._readers.add(task)
        task.add_done_callback(self._readers.discard)

    async def _set_local(self, pc: int, description: aiortc.RTCSessionDescription) -> str:
        peer = self._peers[pc]
        await peer.setLocalDescription(description)
        self.server.emit(pc, 'gathered')
        return peer.localDescription.sdp

    def _watch(self, pc: int, peer: aiortc.RTCPeerConnection) -> None:
        def on_state() -> None:
            self.server.emit_states(pc, peer.iceConnectionState, peer.connectionState)

        peer.on('iceconnectionstatechange', on_state)
        peer.on('connectionstatechange', on_state)

    def _watch_channel(self, pc: int, channel: aiortc.RTCDataChannel) -> None:
        wrapper = Channel(channel)
        if channel.readyState == 'open':
            self.opened(pc, wrapper)
        else:
            channel.on('open', lambda: self.opened(pc, wrapper))


if __name__ == '__main__':
    # between processes, checks on LAN addresses alone often stall, as python-webrtc's do without loopback
    aioice.ice.get_host_addresses = _with_loopback
    base.serve(Driver)
