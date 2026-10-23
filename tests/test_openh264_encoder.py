#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The H.264 that OpenH264 sends, tapped by an encoded transform and checked with ffmpeg's own decoder."""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

import webrtc
from tests.h264 import HEIGHT, LUMA, SIZE, WIDTH, Encoded, Recorder, h264_codecs
from tests.helpers import connect, writing
from tests.isolation import isolated
from tests.timing import seconds

DECODED = 90
SAMPLES = range(10, DECODED, 10)


@dataclasses.dataclass
class _KeyFrames:
    before: int
    after: int
    first_after_request: int | None


@dataclasses.dataclass
class _Sent:
    profile: object
    size: tuple[object, object]
    decoded: int
    sent: int
    first_is_key: bool
    psnr: list[float]
    key_frames: _KeyFrames
    capped: float
    uncapped: float


def _key_frame_count(recorder: Recorder) -> int:
    return sum(encoded.key for encoded in recorder.encoded)


async def _key_frames(sender: webrtc.RTCRtpSender, recorder: Recorder) -> _KeyFrames:
    before = _key_frame_count(recorder)
    first = await recorder.key_frame_on_request(sender)
    return _KeyFrames(before, _key_frame_count(recorder), first)


async def _bitrate_capped_at(sender: webrtc.RTCRtpSender, recorder: Recorder, max_bitrate: int) -> float:
    parameters = sender.get_parameters()
    parameters.encodings[0].max_bitrate = max_bitrate
    await sender.set_parameters(parameters)
    return await recorder.bitrate(3)


@dataclasses.dataclass
class _Decoded:
    profile: object
    size: tuple[object, object]
    frames: bytes


def _probe(ffprobe: str, path: pathlib.Path) -> dict[str, object]:
    shown = ['-show_entries', 'stream=profile,width,height', '-of', 'json']
    probed = subprocess.run([ffprobe, '-v', 'error', *shown, path], capture_output=True, text=True, check=True)
    stream: dict[str, object] = json.loads(probed.stdout)['streams'][0]
    return stream


def _decode(ffmpeg: str, ffprobe: str, stream: list[Encoded]) -> _Decoded:
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / 'sent.h264'
        path.write_bytes(b''.join(encoded.data for encoded in stream))
        probe = _probe(ffprobe, path)
        decoding = [ffmpeg, '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-']
        frames = subprocess.run(decoding, capture_output=True, check=True).stdout

    size = (probe.get('width'), probe.get('height'))
    return _Decoded(probe.get('profile'), size, frames)


def _luma(frames: bytes, index: int) -> bytes:
    """The Y plane of a frame of raw I420 frames."""
    start = index * SIZE
    return frames[start : start + LUMA]


def _psnrs(recorder: Recorder, stream: list[Encoded], decoded: bytes) -> list[float]:
    values = [recorder.best_psnr(_luma(decoded, i), stream[i].written) for i in SAMPLES]
    return [min(value, 99.0) for value in values]


async def _install() -> set[str | None]:
    # the OS's H.264 (macOS), offered without OpenH264
    builtin = {c.sdp_fmtp_line for c in h264_codecs()}
    try:
        await webrtc.openh264.install()
    except RuntimeError as e:
        pytest.skip(str(e))
    return builtin


def _openh264_sender(
    caller: webrtc.RTCPeerConnection, recorder: Recorder, builtin: set[str | None]
) -> webrtc.RTCRtpSender:
    sender = caller.add_track(recorder.generator.track)
    transceiver = next(t for t in caller.get_transceivers() if t.sender == sender)
    openh264_codecs = [codec for codec in h264_codecs() if codec.sdp_fmtp_line not in builtin]
    transceiver.set_codec_preferences(openh264_codecs)
    sender.transform = webrtc.RTCRtpScriptTransform(recorder.tap)
    return sender


async def _send(ffmpeg: str, ffprobe: str) -> _Sent:
    builtin = await _install()
    recorder = Recorder(ffmpeg)
    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    sender = _openh264_sender(caller, recorder, builtin)

    async with writing(recorder.write):
        await connect(caller, callee, 20)
        await asyncio.wait_for(recorder.frames(DECODED), seconds(20))
        stream = recorder.encoded[:DECODED]

        key_frames = await _key_frames(sender, recorder)
        capped = await _bitrate_capped_at(sender, recorder, 100_000)
        uncapped = await _bitrate_capped_at(sender, recorder, 2_000_000)
    caller.close()
    callee.close()

    decoded = _decode(ffmpeg, ffprobe, stream)
    return _Sent(
        profile=decoded.profile,
        size=decoded.size,
        decoded=len(decoded.frames) // SIZE,
        sent=len(stream),
        first_is_key=stream[0].key,
        psnr=_psnrs(recorder, stream, decoded.frames),
        key_frames=key_frames,
        capped=capped,
        uncapped=uncapped,
    )


@isolated(timeout=seconds(180))
def _sent(ffmpeg: str, ffprobe: str) -> _Sent:
    return asyncio.run(_send(ffmpeg, ffprobe))


@functools.cache
def _result() -> _Sent | str:
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if ffmpeg is None or ffprobe is None:
        return 'no ffmpeg and ffprobe'
    try:
        return _sent(ffmpeg, ffprobe)
    except pytest.skip.Exception as e:
        return str(e.msg)


@pytest.fixture
def sent() -> _Sent:
    result = _result()
    if isinstance(result, str):
        pytest.skip(result)
    return result


def test_ffmpeg_decodes_what_openh264_sends(sent: _Sent) -> None:
    """The stream is Constrained Baseline at its size, starts with a key frame, and every frame decodes."""
    assert sent.profile == 'Constrained Baseline'
    assert sent.size == (WIDTH, HEIGHT)
    assert sent.first_is_key
    assert sent.decoded == sent.sent


def test_sent_frames_are_close_to_their_source(sent: _Sent) -> None:
    # encoding loses some, a broken stream or a wrong frame loses far more
    assert min(sent.psnr) > 30, sent.psnr


def test_key_frame_on_request(sent: _Sent) -> None:
    """set_parameters with key_frame makes the encoder send one within a few frames."""
    assert sent.key_frames.after > sent.key_frames.before
    assert sent.key_frames.first_after_request is not None
    assert sent.key_frames.first_after_request < 10


def test_max_bitrate_caps_the_stream(sent: _Sent) -> None:
    assert sent.capped < 100_000 * 1.3
    assert sent.uncapped > sent.capped * 2
