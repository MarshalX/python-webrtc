#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

from __future__ import annotations

import asyncio
import bz2
import contextlib
import ctypes.util
import dataclasses
import io
import re
import shutil
import sys
from typing import TYPE_CHECKING, NoReturn

import pytest

import webrtc
import wrtc
from tests.helpers import ROOT, connect, stats_of_type, wait_for_event, write_video, writing
from tests.isolation import isolated
from tests.timing import seconds

if TYPE_CHECKING:
    from pathlib import Path

# loading OpenH264 can't be undone, so it happens in a process of its own

WIDTH, HEIGHT = 320, 240
_CHROMA = (WIDTH // 2) * (HEIGHT // 2)
RED = bytes([81] * (WIDTH * HEIGHT) + [90] * _CHROMA + [240] * _CHROMA)


def _h264() -> list[webrtc.RTCRtpCodec]:
    capabilities = webrtc.RTCRtpSender.get_capabilities('video')
    assert capabilities is not None
    return [c for c in capabilities.codecs if c.mime_type == 'video/H264']


def _h264_fmtps() -> set[str | None]:
    return {c.sdp_fmtp_line for c in _h264()}


#: Why install() can't get a binary on this machine; any other failure is a bug
_UNAVAILABLE = re.compile(
    r"Can't download |Cisco provides no OpenH264 binary for |Cisco's OpenH264 binary needs glibc "
)


def _skip_if_unavailable(error: RuntimeError) -> NoReturn:
    if _UNAVAILABLE.match(str(error)) is None:
        raise error
    pytest.skip(str(error))


async def _install() -> str:
    try:
        return await webrtc.openh264.install()
    except RuntimeError as e:
        _skip_if_unavailable(e)


@dataclasses.dataclass
class _Received:
    version: str
    size: tuple[int, int]
    center: bytes
    codec: str
    encoder: str | None
    decoder: str | None
    decoded: int | None


def _track(event: webrtc.Event) -> webrtc.MediaStreamTrack:
    assert isinstance(event, webrtc.RTCTrackEvent)
    return event.track


async def _center_pixel(frame: webrtc.VideoFrame) -> bytes:
    options = webrtc.VideoFrameCopyToOptions(format='RGBA')
    rgba = bytearray(frame.allocation_size(options))
    await frame.copy_to(rgba, options)
    center = (HEIGHT // 2 * WIDTH + WIDTH // 2) * 4
    return bytes(rgba[center : center + 4])


async def _last_of_ten(track: webrtc.MediaStreamTrack) -> tuple[tuple[int, int], bytes]:
    reader = webrtc.MediaStreamTrackProcessor(
        webrtc.MediaStreamTrackProcessorInit(track, max_buffer_size=5)
    ).readable.get_reader()
    # every frame converts, the last one is checked
    for _ in range(10):
        frame = (await asyncio.wait_for(reader.read(), seconds(20))).value
        assert isinstance(frame, webrtc.VideoFrame)
        size, center = (frame.coded_width, frame.coded_height), await _center_pixel(frame)
        frame.close()
    await reader.cancel()
    return size, center


async def _received(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    version: str,
    track: webrtc.MediaStreamTrack,
) -> _Received:
    size, center = await _last_of_ten(track)
    outbound = stats_of_type(await caller.get_stats(), 'outbound-rtp')[0]
    stats = await callee.get_stats()
    inbound = stats_of_type(stats, 'inbound-rtp')[0]
    assert isinstance(outbound, webrtc.RTCOutboundRtpStreamStats)
    assert isinstance(inbound, webrtc.RTCInboundRtpStreamStats)
    assert inbound.codec_id is not None
    codec = stats[inbound.codec_id]
    assert isinstance(codec, webrtc.RTCCodecStats)
    return _Received(
        version=version,
        size=size,
        center=center,
        codec=codec.mime_type,
        encoder=outbound.encoder_implementation,
        decoder=inbound.decoder_implementation,
        decoded=inbound.frames_decoded,
    )


async def _send_red() -> _Received:
    # the OS's H.264 (macOS), offered without OpenH264
    builtin = _h264_fmtps()
    version = await _install()

    caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
    generator = webrtc.VideoTrackGenerator()
    sender = caller.add_track(generator.track)
    transceiver = next(t for t in caller.get_transceivers() if t.sender == sender)
    transceiver.set_codec_preferences([c for c in _h264() if c.sdp_fmtp_line not in builtin])

    async with writing(write_video, generator, RED, (WIDTH, HEIGHT)):
        track_event = wait_for_event(callee, 'track', 20)
        await connect(caller, callee, 20)
        received = await _received(caller, callee, version=version, track=_track(await track_event))
    generator.track.stop()
    caller.close()
    callee.close()
    return received


@isolated(timeout=seconds(120))
def _received_red() -> _Received:
    return asyncio.run(_send_red())


def test_h264_through_a_connection() -> None:
    """Frames encoded by Cisco's OpenH264 arrive in their color and size."""
    result = _received_red()

    assert result.version == webrtc.openh264.VERSION
    assert result.codec == 'video/H264'
    assert result.encoder == 'OpenH264'
    # the OS's decoder takes every H.264 profile on macOS
    assert result.decoder == ('VideoToolbox' if sys.platform == 'darwin' else 'OpenH264')
    assert result.decoded is not None
    assert result.decoded >= 10
    assert result.size == (320, 240)
    r, g, b, a = result.center
    assert r > 230
    assert g < 25
    assert b < 25
    assert a == 255


@dataclasses.dataclass
class _Toggled:
    states: list[tuple[bool, bool]]
    versions: list[str]
    printed: str
    printed_quietly: str


async def _install_twice() -> list[str]:
    return list(await asyncio.gather(_install(), _install()))


@isolated
def _toggled() -> _Toggled:
    # the OS's H.264 (macOS), offered without OpenH264
    builtin = _h264_fmtps()

    def state() -> tuple[bool, bool]:
        return webrtc.openh264.is_enabled(), len(_h264_fmtps() - builtin) > 0

    states = [state()]
    printed, printed_quietly = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(printed):
        versions = asyncio.run(_install_twice())
    states.append(state())
    webrtc.openh264.disable()
    states.append(state())
    with contextlib.redirect_stdout(printed_quietly):
        asyncio.run(webrtc.openh264.install(print_notice=False))
    states.append(state())
    return _Toggled(states, versions, printed.getvalue(), printed_quietly.getvalue())


def test_enable_disable_reenable() -> None:
    """OpenH264 is offered only between install() and disable(), as Cisco's license requires users can control it."""
    result = _toggled()

    assert result.states == [(False, False), (True, True), (False, False), (True, True)]
    # printed by each of the two concurrent installs, not by the one with print_notice=False
    assert result.printed.count(webrtc.openh264.NOTICE) == 2
    assert webrtc.openh264.NOTICE not in result.printed_quietly
    # concurrent installs share one download and load
    assert result.versions == [webrtc.openh264.VERSION, webrtc.openh264.VERSION]


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


def test_glibc_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """A system that can't tell its C library counts as having no glibc."""

    def confstr(_name: str) -> str:
        msg = 'unrecognized configuration name'
        raise ValueError(msg)

    monkeypatch.setattr(webrtc.openh264.os, 'confstr', confstr, raising=False)
    with pytest.raises(RuntimeError, match='this system has no glibc'):
        webrtc.openh264._check_glibc()


def _binary() -> tuple[str, str]:
    binary = webrtc.openh264._BINARIES.get(webrtc.openh264._platform())
    if binary is None:
        pytest.skip('Cisco provides no OpenH264 binary for this platform')
    return binary


@pytest.fixture
def mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty stand-in for Cisco's server, so the tests download nothing."""
    directory = tmp_path / 'mirror'
    directory.mkdir()
    monkeypatch.setattr(webrtc.openh264, '_URL', directory.as_uri() + '/')

    def confstr(_name: str) -> str:
        return 'glibc 2.34'

    # Cisco's Linux binaries need glibc 2.34
    monkeypatch.setattr(webrtc.openh264.os, 'confstr', confstr, raising=False)
    return directory


@pytest.mark.parametrize(
    ('machine', 'name'), [('AMD64', 'x64'), ('x86_64', 'x64'), ('aarch64', 'arm64'), ('arm64', 'arm64')]
)
def test_machines_named_as_cisco_does(monkeypatch: pytest.MonkeyPatch, machine: str, name: str) -> None:
    """Windows, Linux and macOS name the same machines differently."""
    monkeypatch.setattr(webrtc.openh264.platform, 'machine', lambda: machine)
    assert webrtc.openh264._platform()[1] == name


@pytest.mark.asyncio
async def test_install_on_a_machine_cisco_has_no_binary_for(monkeypatch: pytest.MonkeyPatch, mirror: Path) -> None:
    monkeypatch.setattr(webrtc.openh264.platform, 'machine', lambda: 'riscv64')
    with pytest.raises(RuntimeError, match=r'Cisco provides no OpenH264 binary for \w+-riscv64'):
        await webrtc.openh264.install(mirror.parent / 'cache')
    assert not webrtc.openh264.is_enabled()


def _junk_archive(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(bz2.compress(b'not OpenH264'))


@pytest.mark.asyncio
@pytest.mark.usefixtures('mirror')
async def test_install_rejects_an_archive_of_another_sha256(tmp_path: Path) -> None:
    """A cached archive is checked like a downloaded one."""
    name, sha256 = _binary()
    cache = tmp_path / 'cache'
    _junk_archive(cache / f'{name}.bz2')
    with pytest.raises(RuntimeError, match=rf'{re.escape(name)}\.bz2 has SHA-256 [0-9a-f]{{64}}, expected {sha256}'):
        await webrtc.openh264.install(cache, print_notice=False)
    assert [p.name for p in cache.iterdir()] == [f'{name}.bz2']
    assert not webrtc.openh264.is_enabled()


@pytest.mark.asyncio
async def test_install_downloads_a_missing_archive(tmp_path: Path, mirror: Path) -> None:
    """An error to get the archive says from where."""
    name, _ = _binary()
    url = re.escape(f'{mirror.as_uri()}/{name}.bz2')
    with pytest.raises(RuntimeError, match=f"Can't download {url}: "):
        await webrtc.openh264.install(tmp_path / 'cache', print_notice=False)

    _junk_archive(mirror / f'{name}.bz2')
    with pytest.raises(RuntimeError, match='has SHA-256'):
        await webrtc.openh264.install(tmp_path / 'cache', print_notice=False)
    assert not (tmp_path / 'cache' / name).exists()


@pytest.mark.asyncio
@pytest.mark.usefixtures('mirror')
@pytest.mark.parametrize(
    'location', [('WRTC_CACHE_DIR', ''), ('LOCALAPPDATA', 'python-webrtc'), ('XDG_CACHE_HOME', 'python-webrtc')]
)
async def test_install_caches_in_the_cache_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: tuple[str, str]
) -> None:
    """Without a directory, the binary goes where libwebrtc is cached."""
    variable, suffix = location
    name, _ = _binary()
    for other in ('WRTC_CACHE_DIR', 'LOCALAPPDATA', 'XDG_CACHE_HOME'):
        monkeypatch.delenv(other, raising=False)
    monkeypatch.setenv(variable, str(tmp_path))
    _junk_archive(tmp_path / suffix / f'openh264-{webrtc.openh264.VERSION}' / f'{name}.bz2')
    # read from there, not downloaded from the empty mirror
    with pytest.raises(RuntimeError, match='has SHA-256'):
        await webrtc.openh264.install(print_notice=False)


@pytest.mark.asyncio
@pytest.mark.usefixtures('mirror')
async def test_install_rejects_a_file_that_isnt_a_library(tmp_path: Path) -> None:
    name, _ = _binary()
    library = tmp_path / name
    _ = library.write_bytes(b'not a library')
    with pytest.raises(RuntimeError, match=f"Can't load {re.escape(str(library))}: "):
        await webrtc.openh264.install(tmp_path, print_notice=False)
    assert not webrtc.openh264.is_enabled()


def test_load_rejects_a_library_without_openh264() -> None:
    """A library needs the OpenH264 entry points."""
    # a library every process has loaded already
    library = 'kernel32.dll' if sys.platform == 'win32' else ctypes.util.find_library('c')
    if library is None:
        pytest.skip('no C library found')
    with pytest.raises(RuntimeError, match='Not an OpenH264 library, no WelsCreateSVCEncoder'):
        wrtc.loadOpenH264(library)
    assert not webrtc.openh264.is_enabled()


@dataclasses.dataclass
class _Downloaded:
    version: str
    files: list[str]
    mode: int
    elsewhere: str


@isolated(timeout=seconds(120))
def _downloaded(directory: Path) -> _Downloaded:
    try:
        version = asyncio.run(webrtc.openh264.install(directory, print_notice=False))
    except RuntimeError as e:
        _skip_if_unavailable(e)
    name, _ = _binary()
    files = sorted(p.name for p in directory.iterdir())
    mode = (directory / name).stat().st_mode & 0o777
    copy = directory / 'copy'
    copy.mkdir()
    _ = shutil.copy(directory / name, copy / name)
    with pytest.raises(RuntimeError) as elsewhere:
        asyncio.run(webrtc.openh264.install(copy, print_notice=False))
    return _Downloaded(version, files, mode, str(elsewhere.value))


def test_install_downloads_and_unpacks(tmp_path: Path) -> None:
    """Only the library stays, readable by every user."""
    result = _downloaded(tmp_path)

    assert result.version == webrtc.openh264.VERSION
    name, _ = _binary()
    assert result.files == [name]
    if sys.platform != 'win32':
        assert result.mode == 0o644
    # the loaded binary can't be swapped for another
    assert result.elsewhere == f'OpenH264 is already loaded from {tmp_path / name}'
