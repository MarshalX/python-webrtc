#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Finds web-platform-tests files and turns each one into a single script that runs outside a browser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from typing_extensions import override

WPT_ROOT = Path(__file__).resolve().parents[2] / 'wpt'
# Platform globals the shell lacks, then the WebRTC API
POLYFILLS = Path(__file__).with_name('polyfills.js')
SHIM = Path(__file__).with_name('shim.js')

# Directories of tests, or glob patterns of test files in a directory
TEST_DIRS = (
    'webrtc',
    'webrtc-encoded-transform',
    'webrtc-extensions',
    'webrtc-ice',
    'webrtc-identity',
    'webrtc-priority',
    'webrtc-stats',
    'mediacapture-insertable-streams',
    # the frames of WebCodecs, which media processing reads and writes, not its codecs
    'webcodecs/audio-data*',
    'webcodecs/videoFrame-*',
    'webcodecs/video-frame-*',
    'webcodecs/videoColorSpace*',
)

# Directories holding helpers rather than tests, as in the WPT manifest
HELPER_DIRS = {'resources', 'support', 'tools', 'third_party', 'coverage'}

HARNESS = '/resources/testharness.js'

# Browser integration scripts; the shim provides what tests need from them
REPLACED_SCRIPTS = {'/resources/testharnessreport.js', '/resources/testdriver.js', '/resources/testdriver-vendor.js'}

# Runs after the helper scripts. Tests get media from python-webrtc instead of Web Audio and canvas.
HELPER_OVERRIDES = 'getNoiseStream = async (caps = {}) => navigator.mediaDevices.getUserMedia(caps);'

HARNESS_HOOKS = """
add_completion_callback((tests, status) => {
  globalThis.__wpt.complete({
    harness: {status: status.status, message: status.message},
    tests: tests.map((t) => ({name: t.name, status: t.status, message: t.message})),
  });
});
"""

_META = re.compile(r'^//\s*META:\s*(\w+)=(.*)$')


@dataclass
class TestFile:
    path: Path
    # ('src', url) or ('inline', code), in document order
    scripts: list[tuple[str, str]] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    title: str = ''
    long_timeout: bool = False


class _HtmlCollector(HTMLParser):
    def __init__(self, test_file: TestFile) -> None:
        super().__init__()
        self.test_file = test_file
        self._inline: list[str] | None = None
        self._in_title = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, dict(attrs))

    def _start(self, tag: str, attrs: dict[str, str | None]) -> None:
        if tag == 'script':
            src = attrs.get('src')
            if src is not None and src != '':
                self.test_file.scripts.append(('src', src))
            else:
                self._inline = []
        elif tag == 'meta' and attrs.get('name') == 'variant':
            content = attrs.get('content')
            self.test_file.variants.append(content if content is not None else '')
        elif tag == 'meta' and attrs.get('name') == 'timeout':
            self.test_file.long_timeout = attrs.get('content') == 'long'
        elif tag == 'title':
            self._in_title = True

    @override
    def handle_data(self, data: str) -> None:
        if self._inline is not None:
            self._inline.append(data)
        elif self._in_title:
            self.test_file.title += data

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == 'script' and self._inline is not None:
            self.test_file.scripts.append(('inline', ''.join(self._inline)))
            self._inline = None
        elif tag == 'title':
            self._in_title = False


def _load_html(path: Path) -> TestFile:
    test_file = TestFile(path)
    _HtmlCollector(test_file).feed(path.read_text(encoding='utf-8'))
    return test_file


def _load_js(path: Path) -> TestFile:
    """Loads a .window.js or .any.js test, which WPT would wrap into a generated HTML page."""
    test_file = TestFile(path, scripts=[('src', HARNESS)])
    for line in path.read_text(encoding='utf-8').splitlines():
        match = _META.match(line.strip())
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip()
        if key == 'script':
            test_file.scripts.append(('src', value))
        elif key == 'variant':
            test_file.variants.append(value)
        elif key == 'title':
            test_file.title = value
        elif key == 'timeout':
            test_file.long_timeout = value == 'long'
    test_file.scripts.append(('src', '/' + path.relative_to(WPT_ROOT).as_posix()))
    return test_file


def load(path: Path) -> TestFile:
    test_file = _load_js(path) if path.name.endswith('.js') else _load_html(path)
    if len(test_file.variants) == 0:
        test_file.variants = ['']
    title = test_file.title.strip()
    test_file.title = title if title != '' else path.name
    return test_file


def _is_test(path: Path) -> bool:
    parts = path.relative_to(WPT_ROOT).parts
    if len(HELPER_DIRS.intersection(parts[:-1])) > 0:
        return False
    name = path.name
    if '-manual.' in name or name.endswith(('-ref.html', '-notref.html')):
        return False
    # .any.js can also run in workers, but only its window scope applies here
    return name.endswith(('.html', '.htm', '.xhtml', '.window.js', '.any.js'))


def discover() -> list[str]:
    """Returns every test case as a path relative to the WPT root, followed by its variant, if any."""
    cases: list[str] = []
    for test_dir in TEST_DIRS:
        paths = WPT_ROOT.glob(test_dir) if '*' in test_dir else (WPT_ROOT / test_dir).rglob('*')
        for path in sorted(paths):
            if path.is_file() and _is_test(path):
                cases.extend(case_id(path, variant) for variant in load(path).variants)
    return cases


def case_id(path: Path, variant: str = '') -> str:
    return path.relative_to(WPT_ROOT).as_posix() + variant


def split_case(case: str) -> tuple[Path, str]:
    path, _, variant = case.partition('?')
    return WPT_ROOT / path, '?' + variant if variant != '' else ''


def _resolve(src: str, test_path: Path) -> Path:
    # Resolved as a URL, so that ../ never leaves the WPT root
    page_url = '/' + test_path.relative_to(WPT_ROOT).as_posix()
    return WPT_ROOT / urlsplit(urljoin(page_url, src)).path.lstrip('/')


def build_scripts(test_file: TestFile) -> list[str]:
    """The polyfills, the shim, the harness, the helpers and the test, as the scripts of the page.

    They are evaluated separately, like the scripts of a page (so a "use strict" directive applies to its own
    script), but all at once: in a shell, the harness considers the page loaded after the first microtask.

    Returns:
        The source of each script, in the order of the page.
    """
    parts = [POLYFILLS.read_text(), SHIM.read_text()]
    test_src = '/' + test_file.path.relative_to(WPT_ROOT).as_posix()
    overrides_added = False
    for kind, value in test_file.scripts:
        is_test_code = kind == 'inline' or value == test_src
        if is_test_code and not overrides_added:
            parts.append(HELPER_OVERRIDES)
            overrides_added = True
        if kind == 'inline':
            parts.append(value)
            continue
        if value in REPLACED_SCRIPTS:
            continue
        script = _resolve(value, test_file.path)
        if not script.is_file():
            # A browser gets a 404 for it and runs the page anyway
            continue
        parts.append(script.read_text())
        if value == HARNESS:
            parts.append(HARNESS_HOOKS)
    return parts
