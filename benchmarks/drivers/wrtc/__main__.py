#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#


"""The driver of python-webrtc."""

from __future__ import annotations

import asyncio
import importlib.metadata
import sys
from typing import TYPE_CHECKING

import webrtc
from benchmarks.drivers import base, frames
from benchmarks.drivers.wrtc import media
from benchmarks.drivers.wrtc.channel import Channel
from benchmarks.protocol import DATA_CHANNEL_LABEL, Answer, Created, Hello, Message, Offer, Server, now

if TYPE_CHECKING:
    from benchmarks.protocol import Candidate


class Driver(base.Driver):
    """Connections of python-webrtc."""

    def __init__(self, server: Server) -> None:
        super().__init__(server)
        self._peers: dict[int, webrtc.RTCPeerConnection] = {}
        self._trickle: dict[int, bool] = {}
        self._audio: media.ToneSource | None = None
        self._codecs: dict[int, str] = {}
        self._senders: dict[int, media.VideoSource] = {}
        self._readers: set[asyncio.Task[None]] = set()

    @staticmethod
    async def hello() -> Hello:
        """The library, its version, and that it trickles."""
        return {'library': 'wrtc', 'version': importlib.metadata.version('wrtc'), 'trickle': True}

    async def create(self, pc: int, role: str, *, trickle: bool, ordered: bool, audio: bool, codec: str) -> Created:
        """Creates a connection, and a data channel (and the audio track, if asked) for the offerer."""
        if codec.startswith('H264') and sys.platform != 'darwin':
            # VideoToolbox on macOS; elsewhere Cisco's OpenH264 binary, fetched once
            await webrtc.openh264.install(print_notice=False)
        self._codecs[pc] = codec

        t_start = now()
        peer = webrtc.RTCPeerConnection()
        self._peers[pc] = peer
        self._trickle[pc] = trickle
        self._watch(pc, peer)

        if role == 'offerer':
            init = webrtc.RTCDataChannelInit(ordered=ordered)
            self._watch_channel(pc, peer.create_data_channel(DATA_CHANNEL_LABEL, init))
            if audio:
                peer.add_track(self._audio_source().track)
        else:
            peer.on('datachannel', lambda event: self._watch_channel(pc, event.channel))

        return {'t_start': t_start, 't_end': now()}

    async def offer(self, pc: int) -> Offer:
        """Creates and sets an offer, with the candidates gathered unless they trickle."""
        peer = self._peers[pc]
        t_start = now()
        offer = await peer.create_offer()
        t_offer = now()
        return {'sdp': await self._set_local(pc, offer), 't_start': t_start, 't_offer': t_offer}

    async def answer(self, pc: int, sdp: str) -> Answer:
        """Sets an offer, then creates and sets an answer, with the candidates gathered unless they trickle."""
        peer = self._peers[pc]
        await peer.set_remote_description(webrtc.RTCSessionDescriptionInit(type='offer', sdp=sdp))
        return {'sdp': await self._set_local(pc, await peer.create_answer())}

    async def accept(self, pc: int, sdp: str) -> Message:
        """Sets an answer."""
        await self._peers[pc].set_remote_description(webrtc.RTCSessionDescriptionInit(type='answer', sdp=sdp))
        return {}

    async def add_candidate(self, pc: int, candidate: Candidate) -> Message:
        """Adds a remote candidate."""
        await self._peers[pc].add_ice_candidate(webrtc.RTCIceCandidateInit.from_json(candidate))
        return {}

    async def close(self, pc: int) -> Message:
        """Closes a connection."""
        sender = self._senders.pop(pc, None)
        if sender is not None:
            sender.stop()
        self._peers.pop(pc).close()
        self.channels.pop(pc, None)
        return {}

    async def video_send(
        self, pc: int, *, path: str, width: int, height: int, fps: float, bitrate: int, numbered: bool
    ) -> Message:
        """Sends the raw frames of a file, encoded in the connection's codec, at most at the bitrate."""
        raw = frames.load_raw(path, width, height)
        sender = self._senders[pc] = media.VideoSource(raw, size=(width, height), fps=fps, numbered=numbered)
        self.tallies[pc] = sender.tally

        encoding = webrtc.RTCRtpEncodingParameters(max_bitrate=bitrate)
        init = webrtc.RTCRtpTransceiverInit(direction='sendonly', send_encodings=[encoding])
        transceiver = self._peers[pc].add_transceiver(sender.generator.track, init)
        transceiver.set_codec_preferences(media.codecs(self._codecs[pc]))

        parameters = transceiver.sender.get_parameters()
        # the encoder keeps the size and drops frames instead, as fixed-size receivers compare better
        parameters.degradation_preference = 'maintain-resolution'
        await transceiver.sender.set_parameters(parameters)
        return {}

    async def audio_send(self, pc: int, *, path: str) -> Message:
        """Sends the process's tone."""
        del path
        self._peers[pc].add_track(self._audio_source().track)
        return {}

    async def sent_bytes(self, pc: int) -> int:
        """The bytes of the RTP streams sent, from the stats."""
        report = await self._peers[pc].get_stats()
        outbound = (s for s in report.values() if isinstance(s, webrtc.RTCOutboundRtpStreamStats))
        return sum(s.bytes_sent for s in outbound if s.bytes_sent is not None)

    async def implementation(self, pc: int) -> str:
        """The encoder of the video sent, or the decoder of the video received, from the stats."""
        report = await self._peers[pc].get_stats()
        for stats in report.values():
            if isinstance(stats, webrtc.RTCOutboundRtpStreamStats) and stats.encoder_implementation is not None:
                return stats.encoder_implementation
            if isinstance(stats, webrtc.RTCInboundRtpStreamStats) and stats.decoder_implementation is not None:
                return stats.decoder_implementation
        return 'libopus' if pc in self.tallies else '-'

    def _on_track(self, pc: int, event: webrtc.RTCTrackEvent) -> None:
        self.server.emit(pc, 'track')
        if pc in self.tallies:
            task = asyncio.ensure_future(self._read(pc, event.track))
            self._readers.add(task)
            task.add_done_callback(self._readers.discard)

    async def _read(self, pc: int, track: webrtc.MediaStreamTrack) -> None:
        tally, numbered = self.tallies[pc], self.numbered[pc]
        init = webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=2)
        reader = webrtc.MediaStreamTrackProcessor(init).readable.get_reader()

        while not (result := await reader.read()).done:
            item = result.value
            tally.frames += 1
            if isinstance(item, webrtc.AudioData):
                tally.audio_ms += item.number_of_frames / item.sample_rate * 1000
            elif isinstance(item, webrtc.VideoFrame) and numbered:
                read = now()
                tally.numbers[await media.read_number(item)] = read

            if isinstance(item, (webrtc.AudioData, webrtc.VideoFrame)):
                item.close()

    def _audio_source(self) -> media.ToneSource:
        if self._audio is None:
            self._audio = media.ToneSource()
        return self._audio

    async def _set_local(self, pc: int, description: webrtc.RTCSessionDescriptionInit) -> str:
        peer = self._peers[pc]
        await peer.set_local_description(description)
        if not self._trickle[pc]:
            await _gathered(peer)
        local = peer.local_description
        if local is None:
            msg = 'no local description'
            raise RuntimeError(msg)
        return local.sdp

    def _watch(self, pc: int, peer: webrtc.RTCPeerConnection) -> None:
        def on_state(_: webrtc.Event) -> None:
            self.server.emit_states(pc, peer.ice_connection_state, peer.connection_state)

        def on_gathering(_: webrtc.Event) -> None:
            if peer.ice_gathering_state == webrtc.RTCIceGatheringState.complete:
                self.server.emit(pc, 'gathered')

        def on_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
            if self._trickle[pc] and event.candidate is not None and event.candidate.candidate != '':
                self.server.emit_candidate(pc, event.candidate.to_json())

        peer.on('iceconnectionstatechange', on_state)
        peer.on('connectionstatechange', on_state)
        peer.on('icegatheringstatechange', on_gathering)
        peer.on('icecandidate', on_candidate)
        peer.on('track', lambda event: self._on_track(pc, event))

    def _watch_channel(self, pc: int, channel: webrtc.RTCDataChannel) -> None:
        wrapper = Channel(channel)
        if channel.ready_state == webrtc.RTCDataChannelState.open:
            self.opened(pc, wrapper)
        else:
            channel.on('open', lambda _: self.opened(pc, wrapper))


async def _gathered(peer: webrtc.RTCPeerConnection) -> None:
    """Waits until the connection gathered its candidates."""
    gathered = asyncio.get_running_loop().create_future()

    def on_change(_: webrtc.Event) -> None:
        if peer.ice_gathering_state == webrtc.RTCIceGatheringState.complete and not gathered.done():
            gathered.set_result(None)

    peer.on('icegatheringstatechange', on_change)
    if peer.ice_gathering_state != webrtc.RTCIceGatheringState.complete:
        await gathered
    peer.off('icegatheringstatechange', on_change)


if __name__ == '__main__':
    base.serve(Driver)
