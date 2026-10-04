#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""H.264 through Cisco's OpenH264 binary, downloaded on request.

OpenH264 Video Codec provided by Cisco Systems, Inc.

:func:`install` downloads Cisco's prebuilt binary for macOS (x64, arm64), Linux (x64, arm64, glibc 2.34 or newer)
or Windows (x64), checks its SHA-256 and loads it.

Cisco's patent license covers the binary only under the conditions of its license (see THIRD_PARTY_LICENSES.md).
The application must let its users enable and disable it, show :data:`NOTICE` where they do, and reproduce
:data:`LICENSE` where it presents licensing information.
"""

from __future__ import annotations

import asyncio
import bz2
import hashlib
import importlib.resources
import os
import platform
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

import webrtc

__all__ = ['LICENSE', 'NOTICE', 'VERSION', 'disable', 'install', 'isEnabled', 'is_enabled']

#: The OpenH264 release the extension is built against, and that :func:`install` downloads
VERSION = '2.6.0'

#: The text Cisco's license requires where users enable or disable H.264
NOTICE = 'OpenH264 Video Codec provided by Cisco Systems, Inc.'

#: Cisco's license of the binary, which applications must reproduce where they present licensing information
LICENSE = importlib.resources.files('webrtc').joinpath('openh264_license.txt').read_text(encoding='utf-8')

_URL = 'http://ciscobinary.openh264.org/'

# Cisco serves plain http, so these pins are the integrity check
_BINARIES = {
    ('darwin', 'arm64'): (
        'libopenh264-2.6.0-mac-arm64.dylib',
        '6db362ee5abdab572311aeadb96d3f44b0617d9a4a4b9f4db4cb5ac4d968da71',
    ),
    ('darwin', 'x64'): (
        'libopenh264-2.6.0-mac-x64.dylib',
        '38b2ed6d1d45b6a3e408c734173f2d67ab44a10d0e154ff3489b89877cd60e7e',
    ),
    ('linux', 'x64'): (
        'libopenh264-2.6.0-linux64.8.so',
        '27ab53323c110b76214c1c72222f459d17febbcd1e252136cadc292b0308d75b',
    ),
    ('linux', 'arm64'): (
        'libopenh264-2.6.0-linux-arm64.8.so',
        'a78aea7970150f46bcd3bb7994c9e6dd90bd7a9ea785920f5a73f6964e3fcda7',
    ),
    ('win32', 'x64'): (
        'openh264-2.6.0-win64.dll',
        'dab5f2a872777f9a58b69bfa9fbcf20d9f82f2d6ec91383fd70bff49bd34ac9f',
    ),
}

# Cisco builds its Linux binaries against glibc 2.34
_GLIBC = (2, 34)

# one download and unpack at a time, from any event loop
_lock = threading.Lock()


def _platform() -> tuple[str, str]:
    machine = platform.machine().lower()
    if machine in {'x86_64', 'amd64'}:
        machine = 'x64'
    elif machine == 'aarch64':
        machine = 'arm64'
    return 'linux' if sys.platform.startswith('linux') else sys.platform, machine


def _glibc() -> tuple[int, int] | None:
    try:
        version = os.confstr('CS_GNU_LIBC_VERSION')
    except (ValueError, OSError):
        return None
    if version is None or not version.startswith('glibc '):
        return None
    major, minor = version.split()[1].split('.')[:2]
    return int(major), int(minor)


def _check_glibc() -> None:
    glibc = _glibc()
    if glibc is None or glibc < _GLIBC:
        found = f'glibc {glibc[0]}.{glibc[1]}' if glibc is not None else 'no glibc'
        msg = f"Cisco's OpenH264 binary needs glibc {_GLIBC[0]}.{_GLIBC[1]} or newer, this system has {found}"
        raise RuntimeError(msg)


def _cache_dir() -> Path:
    # the same directory the build caches libwebrtc in
    variables = (('WRTC_CACHE_DIR', ''), ('LOCALAPPDATA', 'python-webrtc'), ('XDG_CACHE_HOME', 'python-webrtc'))
    for variable, suffix in variables:
        value = os.environ.get(variable)
        if value is not None and value != '':
            return Path(value, suffix)
    return Path.home() / '.cache' / 'python-webrtc'


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as file:
            _ = file.write(data)
        temporary.chmod(0o644)  # mkstemp's 0600 would keep a shared cache from others
        _ = temporary.replace(path)
    except BaseException:
        temporary.unlink()
        raise


async def install(cache_dir: str | os.PathLike[str] | None = None, *, print_notice: bool = True) -> str:
    """Enables H.264, downloading Cisco's OpenH264 binary first if it isn't cached.

    OpenH264 Video Codec provided by Cisco Systems, Inc.

    Calling it is the opt-in Cisco's license requires, and it re-enables H.264 after :func:`disable`. Call it before
    creating peer connections, because the codecs of a connection are fixed when it's created. The download runs in a
    thread, so the event loop keeps running. It's skipped when the binary is already in the cache.

    Args:
        cache_dir (:obj:`str`, optional): The directory the binary is kept in. Defaults to ``openh264-<VERSION>`` in
            the cache directory. That is ``WRTC_CACHE_DIR``, else ``python-webrtc`` in ``LOCALAPPDATA`` or
            ``XDG_CACHE_HOME``, else ``~/.cache/python-webrtc``.
        print_notice (:obj:`bool`, optional): Whether to print :data:`NOTICE`. Pass :obj:`False` only when the
            application shows :data:`NOTICE` itself where its users enable and disable H.264, as Cisco's license
            requires.

    Returns:
        :obj:`str`: The version of the loaded binary.

    Raises:
        RuntimeError: If Cisco has no binary for this platform (on Linux, it needs glibc 2.34 or newer), or it can't
            be downloaded, doesn't match its SHA-256, or can't be loaded.
    """
    version = await asyncio.to_thread(_load, Path(cache_dir) if cache_dir is not None else None)
    if print_notice:
        print(NOTICE)  # ruff: ignore[print]
    return version


def _load(cache_dir: Path | None) -> str:
    binary = _BINARIES.get(_platform())
    if binary is None:
        msg = f'Cisco provides no OpenH264 binary for {"-".join(_platform())}'
        raise RuntimeError(msg)
    name, sha256 = binary
    if _platform()[0] == 'linux':
        _check_glibc()

    directory = cache_dir if cache_dir is not None else _cache_dir() / f'openh264-{VERSION}'
    library = directory / name
    with _lock:
        if not library.exists():
            data = _archive(directory / f'{name}.bz2')
            actual = hashlib.sha256(data).hexdigest()
            if actual != sha256:
                msg = f'{name}.bz2 has SHA-256 {actual}, expected {sha256}'
                raise RuntimeError(msg)
            _atomic_write(library, bz2.decompress(data))
        return webrtc.wrtc.loadOpenH264(str(library))


def _archive(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    url = f'{_URL}{path.name}'
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # ruff: ignore[suspicious-url-open-usage]
            data: bytes = response.read()
            return data
    except OSError as e:
        msg = f"Can't download {url}: {e}"
        raise RuntimeError(msg) from e


def disable() -> None:
    """Stops offering H.264, until :func:`install` is called again.

    OpenH264 Video Codec provided by Cisco Systems, Inc.

    Connections created earlier keep their codecs. The binary stays in the cache.
    """
    webrtc.wrtc.disableOpenH264()


def is_enabled() -> bool:
    """Whether H.264 through OpenH264 is offered to new connections.

    Returns:
        :obj:`bool`: :obj:`True` after :func:`install`, until :func:`disable`.
    """
    return webrtc.wrtc.openH264Enabled()


#: Alias for :func:`is_enabled`
isEnabled = is_enabled
