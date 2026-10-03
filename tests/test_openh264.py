#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import json
import sys

import pytest

import webrtc
from tests.helpers import ROOT, run_isolated

# loading OpenH264 can't be undone, so it happens in a process of its own
SCRIPT = """
import asyncio
import json

import webrtc
from tests.helpers import connect, stats_of_type, wait_for_event, write_video, writing

WIDTH, HEIGHT = 320, 240
chroma = (WIDTH // 2) * (HEIGHT // 2)
RED = bytes([81] * (WIDTH * HEIGHT) + [90] * chroma + [240] * chroma)


def h264():
    return [c for c in webrtc.RTCRtpSender.get_capabilities('video').codecs if c.mime_type == 'video/H264']


async def main():
    # the OS's H.264 (macOS), offered without OpenH264
    builtin = {c.sdp_fmtp_line for c in h264()}
    try:
        version = await webrtc.openh264.install()
    except RuntimeError as e:
        print(json.dumps({'skip': str(e)}))
        return

    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    generator = webrtc.VideoTrackGenerator()
    sender = caller.add_track(generator.track)
    transceiver = next(t for t in caller.get_transceivers() if t.sender == sender)
    transceiver.set_codec_preferences([c for c in h264() if c.sdp_fmtp_line not in builtin])

    async with writing(write_video, generator, RED, (WIDTH, HEIGHT)):
        track_event = wait_for_event(callee, 'track', 20)
        await connect(caller, callee, 20)
        remote = (await track_event).track
        reader = webrtc.MediaStreamTrackProcessor(
            webrtc.MediaStreamTrackProcessorInit(remote, max_buffer_size=5)
        ).readable.get_reader()
        for _ in range(10):
            frame = (await asyncio.wait_for(reader.read(), 20)).value
            size = (frame.coded_width, frame.coded_height)
            rgba = bytearray(frame.allocation_size(webrtc.VideoFrameCopyToOptions(format='RGBA')))
            await frame.copy_to(rgba, webrtc.VideoFrameCopyToOptions(format='RGBA'))
            frame.close()
        await reader.cancel()
        outbound = stats_of_type(await caller.get_stats(), 'outbound-rtp')[0]
        inbound = stats_of_type(await callee.get_stats(), 'inbound-rtp')[0]
        codec = (await callee.get_stats())[inbound.codec_id]
    generator.track.stop()
    caller.close()
    callee.close()

    center = (HEIGHT // 2 * WIDTH + WIDTH // 2) * 4
    print(json.dumps({
        'version': version,
        'size': size,
        'center': list(rgba[center : center + 4]),
        'codec': codec.mime_type,
        'fmtp': codec.sdp_fmtp_line,
        'encoder': outbound.encoder_implementation,
        'decoder': inbound.decoder_implementation,
        'decoded': inbound.frames_decoded,
    }))


asyncio.run(main())
"""


def test_h264_through_a_connection() -> None:
    """Frames encoded by Cisco's OpenH264 arrive in their color and size."""
    result: dict[str, object] = json.loads(run_isolated(SCRIPT, timeout=120).strip().splitlines()[-1])
    if 'skip' in result:
        pytest.skip(str(result['skip']))

    assert result['version'] == webrtc.openh264.VERSION
    assert result['codec'] == 'video/H264'
    assert result['encoder'] == 'OpenH264'
    # the OS's decoder takes every H.264 profile on macOS
    assert result['decoder'] == ('VideoToolbox' if sys.platform == 'darwin' else 'OpenH264')
    decoded = result['decoded']
    assert isinstance(decoded, int)
    assert decoded >= 10
    assert result['size'] == [320, 240]
    center = result['center']
    assert isinstance(center, list)
    r, g, b, a = center
    assert r > 230
    assert g < 25
    assert b < 25
    assert a == 255


TOGGLE_SCRIPT = """
import asyncio
import json

import webrtc


def h264():
    codecs = webrtc.RTCRtpSender.get_capabilities('video').codecs
    return {c.sdp_fmtp_line for c in codecs if c.mime_type == 'video/H264'}


# the OS's H.264 (macOS), offered without OpenH264
builtin = h264()


def offered():
    return bool(h264() - builtin)


states = [(webrtc.openh264.is_enabled(), offered())]



async def install_twice():
    return await asyncio.gather(webrtc.openh264.install(), webrtc.openh264.install())


try:
    versions = asyncio.run(install_twice())
except RuntimeError as e:
    print(json.dumps({'skip': str(e)}))
    raise SystemExit
states.append((webrtc.openh264.is_enabled(), offered()))
webrtc.openh264.disable()
states.append((webrtc.openh264.is_enabled(), offered()))
print('quiet install:', flush=True)
asyncio.run(webrtc.openh264.install(print_notice=False))
states.append((webrtc.openh264.is_enabled(), offered()))
print(json.dumps({'states': states, 'versions': versions}))
"""


def test_enable_disable_reenable() -> None:
    """OpenH264 is offered only between install() and disable(), as Cisco's license requires users can control it."""
    output = run_isolated(TOGGLE_SCRIPT).strip().splitlines()
    result: dict[str, object] = json.loads(output[-1])
    if 'skip' in result:
        pytest.skip(str(result['skip']))
    assert result['states'] == [[False, False], [True, True], [False, False], [True, True]]
    # printed by each of the two concurrent installs, not by the one with print_notice=False
    quiet = output.index('quiet install:')
    assert output[:quiet].count(webrtc.openh264.NOTICE) == 2
    assert webrtc.openh264.NOTICE not in output[quiet:]
    # concurrent installs share one download and load
    assert result['versions'] == [webrtc.openh264.VERSION, webrtc.openh264.VERSION]


def test_notice() -> None:
    assert webrtc.openh264.NOTICE == 'OpenH264 Video Codec provided by Cisco Systems, Inc.'


def test_license_is_the_one_in_third_party_licenses() -> None:
    """The constant and THIRD_PARTY_LICENSES.md carry the same text, and the notice in it."""
    text = (ROOT / 'THIRD_PARTY_LICENSES.md').read_text(encoding='utf-8')
    start = text.index('```\n' + '\n'.join(webrtc.openh264.LICENSE.splitlines()[:2])) + len('```\n')
    section = text[start : text.index('\n```', start)]
    assert section == webrtc.openh264.LICENSE.rstrip()
    assert webrtc.openh264.NOTICE in webrtc.openh264.LICENSE


@pytest.mark.parametrize(
    ('version', 'error'),
    [
        ('glibc 2.28', 'needs glibc 2.34 or newer, this system has glibc 2.28'),
        (None, 'this system has no glibc'),
        ('glibc 2.34', None),
        ('glibc 2.41', None),
    ],
)
def test_glibc_floor(monkeypatch: pytest.MonkeyPatch, version: str | None, error: str | None) -> None:
    """Cisco's Linux binaries need glibc 2.34, checked before anything is downloaded."""

    def confstr(name: str) -> str | None:
        assert name == 'CS_GNU_LIBC_VERSION'
        return version

    # os.confstr exists only on POSIX
    monkeypatch.setattr(webrtc.openh264.os, 'confstr', confstr, raising=False)
    if error is None:
        webrtc.openh264._check_glibc()
    else:
        with pytest.raises(RuntimeError, match=error):
            webrtc.openh264._check_glibc()
