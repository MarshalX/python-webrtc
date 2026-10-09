#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Modified SDP set as the local description, and the effect of common changes."""

from __future__ import annotations

import array
import asyncio
import math
from collections.abc import Callable

import pytest

import webrtc
from tests.helpers import exchange_ice_candidates, stats_of_type, wait_until, write_video, writing

TIMEOUT = 20
OPUS = 'opus/48000/2'
VP8 = 'VP8/90000'

#: A change to the SDP of a description
Munge = Callable[[str], str]


def unchanged(sdp: str) -> str:
    return sdp


def payload_types(lines: list[str], codec: str) -> set[str]:
    """The payload types of a codec, like ``VP8/90000``."""
    return {
        line.split()[0].removeprefix('a=rtpmap:')
        for line in lines
        if line.startswith('a=rtpmap:') and line.split()[1] == codec
    }


def add_fmtp(sdp: str, codec: str, parameters: str) -> str:
    """Adds format parameters to every payload type of a codec."""
    lines = sdp.split('\r\n')
    for payload_type in payload_types(lines, codec):
        fmtp = f'a=fmtp:{payload_type} '
        index = next((i for i, line in enumerate(lines) if line.startswith(fmtp)), None)
        if index is None:
            lines.insert(lines.index(f'a=rtpmap:{payload_type} {codec}') + 1, fmtp + parameters)
        else:
            lines[index] += ';' + parameters
    return '\r\n'.join(lines)


def stereo(sdp: str) -> str:
    """Asks for Opus in stereo, and says it sends stereo."""
    return add_fmtp(sdp, OPUS, 'stereo=1;sprop-stereo=1')


def remove_codec(sdp: str, codec: str) -> str:
    """Removes a codec, and the retransmission of it, from every media section."""
    lines = sdp.split('\r\n')
    removed = payload_types(lines, codec)
    retransmissions = {f'apt={payload_type}' for payload_type in removed}
    removed |= {
        line.split()[0].removeprefix('a=fmtp:')
        for line in lines
        if line.startswith('a=fmtp:') and line.split()[-1] in retransmissions
    }
    prefixes = tuple(
        f'a={attribute}:{payload_type} ' for attribute in ('rtpmap', 'fmtp', 'rtcp-fb') for payload_type in removed
    )
    kept: list[str] = []
    for line in lines:
        if line.startswith('m='):
            # m=<media> <port> <proto> <payload type>...
            fields = line.split()
            kept.append(' '.join(fields[:3] + [field for field in fields[3:] if field not in removed]))
        elif not line.startswith(prefixes):
            kept.append(line)
    return '\r\n'.join(kept)


def replace_attribute(sdp: str, name: str, value: str) -> str:
    """Sets every line of an attribute to a value."""
    return '\r\n'.join(f'a={name}:{value}' if line.startswith(f'a={name}:') else line for line in sdp.split('\r\n'))


async def negotiate(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    munge_offer: Munge = unchanged,
    munge_answer: Munge = unchanged,
) -> None:
    """Exchanges an offer and an answer, each changed before it's set as the local description."""
    offer = await caller.create_offer()
    offer.sdp = munge_offer(offer.sdp)
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)
    answer = await callee.create_answer()
    answer.sdp = munge_answer(answer.sdp)
    await callee.set_local_description(answer)
    await caller.set_remote_description(answer)


async def connect(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    munge_offer: Munge = unchanged,
    munge_answer: Munge = unchanged,
) -> None:
    """Negotiates with changed descriptions and waits until both connections are connected."""
    exchange_ice_candidates(caller, callee)
    await negotiate(caller, callee, munge_offer=munge_offer, munge_answer=munge_answer)

    def connected() -> bool:
        return all(pc.connection_state == webrtc.RTCPeerConnectionState.connected for pc in (caller, callee))

    await wait_until(connected, 'both connections to connect', TIMEOUT)


async def outbound_rtp(pc: webrtc.RTCPeerConnection) -> webrtc.RTCOutboundRtpStreamStats:
    (stats,) = stats_of_type(await pc.get_stats(), 'outbound-rtp')
    assert isinstance(stats, webrtc.RTCOutboundRtpStreamStats)
    return stats


async def target_bitrate(pc: webrtc.RTCPeerConnection) -> float | None:
    return (await outbound_rtp(pc)).target_bitrate


async def available_outgoing_bitrate(pc: webrtc.RTCPeerConnection) -> float | None:
    """The bandwidth estimate of the selected candidate pair, the only one that has it."""
    report = await pc.get_stats()
    for transport in stats_of_type(report, 'transport'):
        assert isinstance(transport, webrtc.RTCTransportStats)
        if transport.selected_candidate_pair_id is None:
            continue
        pair = report[transport.selected_candidate_pair_id]
        assert isinstance(pair, webrtc.RTCIceCandidatePairStats)
        return pair.available_outgoing_bitrate
    return None


async def write_stereo(generator: webrtc.MediaStreamTrackGenerator, *, stop: asyncio.Event) -> None:
    """Writes 48 kHz stereo in real time, a different tone in each channel."""
    writer = generator.writable.get_writer()
    loop = asyncio.get_running_loop()
    start = loop.time()
    written = 0
    while not stop.is_set():
        samples = array.array('h')
        for i in range(480):
            time = (written + i) / 48000
            samples.extend(int(12000 * math.sin(2 * math.pi * tone * time)) for tone in (440, 660))
        init = webrtc.AudioDataInit(
            format='s16',
            sample_rate=48000,
            number_of_frames=480,
            number_of_channels=2,
            timestamp=written * 1_000_000 // 48000,
            data=samples.tobytes(),
        )
        await writer.write(webrtc.AudioData(init))
        written += 480
        await asyncio.sleep(max(0.0, start + written / 48000 - loop.time()))


def plane(audio: webrtc.AudioData, index: int) -> array.array[float]:
    samples = array.array('f', [0.0] * audio.number_of_frames)
    audio.copy_to(memoryview(samples).cast('B'), webrtc.AudioDataCopyToOptions(plane_index=index, format='f32-planar'))
    return samples


async def first_sound(
    reader: webrtc.ReadableStreamDefaultReader[webrtc.AudioData | webrtc.VideoFrame],
) -> webrtc.AudioData:
    """The first frame with the tones, after the initial silence."""
    while True:
        audio = (await reader.read()).value
        assert isinstance(audio, webrtc.AudioData)
        if max(plane(audio, 0)) > 0.1:
            return audio
        audio.close()


@pytest.mark.asyncio
async def test_munged_offer_and_answer_are_set(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    caller.add_transceiver('audio')
    await negotiate(caller, callee, munge_offer=stereo, munge_answer=stereo)

    for pc in (caller, callee):
        assert pc.local_description is not None
        assert ';stereo=1' in pc.local_description.sdp


@pytest.mark.asyncio
async def test_offer_of_another_connection_is_rejected(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A description with another connection's fingerprint is rejected."""
    caller.add_transceiver('audio')
    offer = await caller.create_offer()

    with pytest.raises(webrtc.InvalidModificationError):
        await callee.set_local_description(offer)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('munge', 'channels'),
    [
        pytest.param(unchanged, 1, id='mono'),
        pytest.param(stereo, 2, id='stereo'),
    ],
)
async def test_opus_stereo(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, munge: Munge, *, channels: int
) -> None:
    """Stereo arrives in two channels when the answer asks for it, and in one otherwise."""
    generator = webrtc.MediaStreamTrackGenerator('audio')
    caller.add_track(generator)
    tracks: list[webrtc.MediaStreamTrack] = []
    callee.on('track', lambda event: tracks.append(event.track))
    async with writing(write_stereo, generator):
        await connect(caller, callee, munge_answer=munge)
        reader = webrtc.MediaStreamTrackProcessor(webrtc.MediaStreamTrackProcessorInit(tracks[0])).readable.get_reader()
        audio = await asyncio.wait_for(first_sound(reader), TIMEOUT)
        await reader.cancel()
    generator.stop()

    assert audio.number_of_channels == channels
    planes = [plane(audio, index) for index in range(channels)]
    audio.close()
    assert len({samples.tobytes() for samples in planes}) == channels, 'each channel has its own tone'


@pytest.mark.asyncio
@pytest.mark.parametrize('parameters', ['maxaveragebitrate=12000', 'stereo=1;sprop-stereo=1;maxaveragebitrate=96000'])
async def test_opus_max_average_bitrate(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, parameters: str
) -> None:
    """The encoder targets the bitrate the answer asks for."""
    bitrate = int(parameters.rpartition('maxaveragebitrate=')[2])
    generator = webrtc.MediaStreamTrackGenerator('audio')
    caller.add_track(generator)
    async with writing(write_stereo, generator):
        await connect(caller, callee, munge_answer=lambda sdp: add_fmtp(sdp, OPUS, parameters))
        await wait_until(lambda: target_bitrate(caller), 'the encoder', TIMEOUT)
        target = await target_bitrate(caller)
    generator.stop()

    assert target == bitrate


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('parameter', 'kbps'),
    # around libwebrtc's default start of 300 kbps
    [('x-google-start-bitrate', 1000), ('x-google-min-bitrate', 800), ('x-google-max-bitrate', 150)],
)
async def test_vp8_bitrate_sets_the_initial_estimate(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, parameter: str, *, kbps: int
) -> None:
    """Until media flows, the estimate is the start bitrate, clamped to the minimum and maximum."""
    caller.add_transceiver('video')
    await connect(caller, callee, munge_answer=lambda sdp: add_fmtp(sdp, VP8, f'{parameter}={kbps}'))
    await wait_until(lambda: available_outgoing_bitrate(caller), 'a bandwidth estimate', TIMEOUT)

    assert await available_outgoing_bitrate(caller) == kbps * 1000


@pytest.mark.asyncio
async def test_vp8_max_bitrate_caps_the_encoder(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The encoder never targets more than the maximum the answer sets."""
    kbps = 150
    width, height = 320, 240
    generator = webrtc.VideoTrackGenerator()
    caller.add_track(generator.track)
    async with writing(write_video, generator, bytes(width * height * 3 // 2), (width, height)):
        await connect(caller, callee, munge_answer=lambda sdp: add_fmtp(sdp, VP8, f'x-google-max-bitrate={kbps}'))
        await wait_until(lambda: target_bitrate(caller), 'the encoder', TIMEOUT)
        targets: list[float | None] = []
        for _ in range(5):
            targets.append(await target_bitrate(caller))
            await asyncio.sleep(0.2)
    generator.track.stop()

    assert all(target is not None and target <= kbps * 1000 for target in targets), targets


@pytest.mark.asyncio
async def test_munged_ice_credentials(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Changed ICE credentials in the offer are used by both peers."""
    ufrag, pwd = 'mungedufrag', 'mungedpasswordmungedpassword'
    caller.add_transceiver('audio')
    await connect(
        caller,
        callee,
        munge_offer=lambda sdp: replace_attribute(replace_attribute(sdp, 'ice-ufrag', ufrag), 'ice-pwd', pwd),
    )

    assert callee.remote_description is not None
    assert f'a=ice-ufrag:{ufrag}\r\na=ice-pwd:{pwd}\r\n' in callee.remote_description.sdp
    local_transport = caller.get_senders()[0].transport
    remote_transport = callee.get_receivers()[0].transport
    assert local_transport is not None
    assert remote_transport is not None
    local = local_transport.ice_transport.get_local_parameters()
    remote = remote_transport.ice_transport.get_remote_parameters()
    assert local is not None
    assert remote is not None
    assert (local.username_fragment, local.password) == (ufrag, pwd)
    assert (remote.username_fragment, remote.password) == (ufrag, pwd)


@pytest.mark.asyncio
async def test_removed_codec_is_not_negotiated(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    capabilities = webrtc.RTCRtpSender.get_capabilities('video')
    assert capabilities is not None
    assert 'video/VP8' in {codec.mime_type for codec in capabilities.codecs}
    caller.add_transceiver('video')
    await negotiate(caller, callee, munge_offer=lambda sdp: remove_codec(sdp, VP8))

    assert callee.remote_description is not None
    assert VP8 not in callee.remote_description.sdp
    codecs = {codec.mime_type for codec in caller.get_senders()[0].get_parameters().codecs}
    assert len(codecs) > 0
    assert 'video/VP8' not in codecs
