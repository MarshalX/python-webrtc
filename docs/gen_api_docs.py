#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Generates the API reference pages of docs/source/api from the modules of the package."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / 'python-webrtc' / 'python' / 'webrtc'
OUT = Path(__file__).parent / 'source' / 'api'

SECTIONS = {
    'interfaces': 'Interfaces',
    'models': 'Models',
}
# the internals of the package, except the events every interface inherits
TOP_LEVEL = ['enums', 'exceptions', 'streams', 'utils.events', 'base', 'openh264', 'loopback']
# internal webrtc.utils modules, without a page
INTERNAL = ['utils.lifetime', 'utils.loops', 'utils.names', 'utils.operations', 'utils.strings', 'utils.transfer']

# modules of several public classes, or whose class name isn't the best title
TITLES = {
    'base': 'WebRTCObject',
    'enums': 'Enums',
    'exceptions': 'Exceptions',
    'streams': 'Streams',
    'openh264': 'OpenH264',
    'loopback': 'Loopback',
    'utils.events': 'EventTarget',
    'interfaces.media_devices': 'MediaDevices',
    'interfaces.media_stream_track_processor': 'MediaStreamTrackProcessor',
    'interfaces.rtc_data_channel': 'RTCDataChannel',
    'interfaces.rtc_rtp_script_transform': 'RTCRtpScriptTransform',
    'interfaces.sframe_transform': 'SFrame transforms',
    'interfaces.track_generator': 'Track generators',
    'models.audio_data': 'AudioData',
    'models.blob': 'Blob',
    'models.events': 'Event objects',
    'models.media_track_constraints': 'Track constraints',
    'models.rtc_certificate': 'RTCCertificate',
    'models.rtc_configuration': 'RTCConfiguration',
    'models.rtc_encoded_frame': 'Encoded frames',
    'models.rtc_ice_candidate': 'RTCIceCandidate',
    'models.rtc_offer_answer_options': 'Offer and answer options',
    'models.rtc_session_description_init': 'RTCSessionDescriptionInit',
    'models.rtc_stats': 'Stats',
    'models.rtp_parameters': 'RTP parameters',
    'models.rtp_source': 'RTP sources',
    'models.sframe_transform_options': 'SFrame options',
    'models.video_frame': 'VideoFrame',
}


def public_classes(path: Path) -> list[str]:
    """The public classes a module defines."""
    tree = ast.parse(path.read_text(encoding='UTF-8'))
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef) and not node.name.startswith('_')]


def title_of(module: str) -> str:
    """The title of the page of a module: its class, or a title of TITLES."""
    if module in TITLES:
        return TITLES[module]

    path = PACKAGE / f'{module.replace(".", "/")}.py'
    classes = public_classes(path)
    if len(classes) != 1:
        msg = f'add a title of webrtc.{module} to TITLES: it has the classes {classes}'
        raise SystemExit(msg)
    return classes[0]


def write_page(path: Path, module: str) -> None:
    """Writes the page of a module."""
    title = title_of(module)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{title}\n{"=" * len(title)}\n\n.. automodule:: webrtc.{module}\n', encoding='UTF-8')


def write_index(path: Path, title: str, docnames: list[str]) -> None:
    """Writes the page listing the pages of a section."""
    entries = '\n'.join(f'   {name}' for name in docnames)
    path.write_text(f'{title}\n{"=" * len(title)}\n\n.. toctree::\n   :maxdepth: 1\n\n{entries}\n', encoding='UTF-8')


def main() -> None:
    """Writes the pages of every documented module."""
    # the pages written by hand are Markdown
    for page in OUT.rglob('*.rst'):
        page.unlink()

    for section, title in SECTIONS.items():
        modules = sorted(p.stem for p in (PACKAGE / section).glob('*.py') if p.stem != '__init__')
        modules.sort(key=lambda name: title_of(f'{section}.{name}').lower())
        for name in modules:
            write_page(OUT / section / f'{name}.rst', f'{section}.{name}')
        write_index(OUT / section / 'index.rst', title, modules)

    for module in TOP_LEVEL:
        write_page(OUT / f'{module.rsplit(".", 1)[-1]}.rst', module)

    for path in (PACKAGE / 'utils').glob('*.py'):
        module = f'utils.{path.stem}'
        if path.stem != '__init__' and module not in TOP_LEVEL and module not in INTERNAL:
            msg = f'list webrtc.{module} in TOP_LEVEL or INTERNAL'
            raise SystemExit(msg)


if __name__ == '__main__':
    main()
