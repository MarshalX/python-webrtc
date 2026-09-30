#!/usr/bin/env python3
#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

r"""Regenerates the libc++ pins used by Linux builds (maintainer tool, needs `git` and the `gh` CLI).

The Linux libwebrtc prebuilt ships only the *.h headers of Chromium's libc++. This script
- resolves the libc++, libc++abi and llvm-libc revisions of WebRTC's DEPS to llvm-project commits, and checks
  that the prebuilt's *.h headers match the libc++ one byte for byte;
- writes the SHA256 of every remaining (extensionless) libc++ header to headers.sha256;
- writes the SHA256 of Chromium's build-generated libc++ config (__config_site, __assertion_handler)
  at the given Chromium tag to config.sha256;
- writes the SHA256 of the libc++ and libc++abi sources Chromium builds, plus every file they include, to
  runtime.sha256 (the linux-arm64 prebuilt lacks the compiled runtime).
Then set the printed variables in cmake/libwebrtc.cmake.

usage: python cmake/libcxx/update.py <unpacked libwebrtc-linux-x64>/include/third_party/libc++/src/include \\
           --webrtc-branch 7977 --chromium-tag 152.0.7977.0
"""

from __future__ import annotations

import argparse
import base64
import datetime
import functools
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

REPO = 'repos/llvm/llvm-project'
CHROMIUM_CONFIG = ('__config_site', '__assertion_handler')
# llvm-project dir -> (its DEPS path in WebRTC, CMake variable of its commit)
LLVM_DIRS = {
    'libcxx': ('src/third_party/libc++/src', 'LIBCXX_LLVM_COMMIT'),
    'libcxxabi': ('src/third_party/libc++abi/src', 'LIBCXXABI_LLVM_COMMIT'),
    'libc': ('src/third_party/llvm-libc/src', 'LLVM_LIBC_COMMIT'),
}
# llvm-project dirs the runtime sources include from: their own trees, and llvm-libc (-I libc)
RUNTIME_TREES = ('libcxx/src', 'libcxxabi/src', 'libc')
INCLUDE = re.compile(rb'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.MULTILINE)


class TreeEntry(TypedDict):
    """An entry of a git tree of the GitHub API."""

    path: str
    sha: str
    type: str


class Commit(TypedDict):
    """A commit of the GitHub API."""

    sha: str


class Tree(TypedDict):
    """A git tree of the GitHub API."""

    tree: list[TreeEntry]
    truncated: bool


@functools.cache
def tool(name: str) -> str:
    """The full path of an executable on PATH."""
    path = shutil.which(name)
    if path is None:
        msg = f'{name} is not on PATH'
        raise SystemExit(msg)
    return path


def gh(path: str) -> bytes:
    """A response of the GitHub API."""
    return subprocess.check_output([tool('gh'), 'api', path])


def git_tree(sha: str, *, recursive: bool = False) -> Tree:
    """A git tree of llvm-project."""
    tree: Tree = json.loads(gh(f'{REPO}/git/trees/{sha}' + ('?recursive=1' if recursive else '')))
    return tree


def blob_sha(data: bytes) -> str:
    """The git object hash of a blob."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data, usedforsecurity=False).hexdigest()


def tree_sha(commit: str, path: str) -> str:
    """The git tree hash of a directory of llvm-project at a commit."""
    tree: str = json.loads(gh(f'{REPO}/git/commits/{commit}'))['tree']['sha']
    for part in path.split('/'):
        tree = next(e['sha'] for e in git_tree(tree)['tree'] if e['path'] == part)
    return tree


def subtree(commit: str, path: str) -> list[TreeEntry]:
    """The files of a directory of llvm-project at a commit, recursively."""
    listing = git_tree(tree_sha(commit, path), recursive=True)
    if listing['truncated']:
        msg = f'{path} tree listing is truncated'
        raise SystemExit(msg)
    return [e for e in listing['tree'] if e['type'] == 'blob']


def blob(sha: str) -> bytes:
    """The content of a blob of llvm-project."""
    content: str = json.loads(gh(f'{REPO}/git/blobs/{sha}'))['content']
    return base64.b64decode(content)


def chromium(path: str, tag: str) -> bytes:
    """A file of Chromium at a tag."""
    return subprocess.check_output([
        tool('gh'),
        'api',
        '-H',
        'Accept: application/vnd.github.raw',
        f'repos/chromium/chromium/contents/{path}?ref={tag}',
    ])


def git_fetch(url: str, ref: str, repo: str) -> str:
    """Fetches only the commit object of <ref>, returns its hash."""
    git = tool('git')
    subprocess.run([git, 'init', '-q', repo], check=True)
    subprocess.run([git, '-C', repo, 'fetch', '-q', '--depth=1', '--filter=tree:0', url, ref], check=True)
    return subprocess.check_output([git, '-C', repo, 'rev-parse', 'FETCH_HEAD'], text=True).strip()


def resolve_llvm(deps: str, name: str) -> str:
    """Chromium mirrors each llvm-project dir as its own repo: finds the llvm-project commit with the same tree."""
    match = re.search(rf"'{re.escape(LLVM_DIRS[name][0])}':\s*'([^'@]+)@([0-9a-f]+)'", deps)
    if not match:
        msg = f'{LLVM_DIRS[name][0]} is not in the WebRTC DEPS'
        raise SystemExit(msg)
    url, revision = match.groups()
    with tempfile.TemporaryDirectory() as repo:
        git_fetch(url, revision, repo)
        tree, committed = subprocess.check_output(
            [tool('git'), '-C', repo, 'log', '-1', '--format=%T %cI', 'FETCH_HEAD'], text=True
        ).split()
    date = datetime.datetime.fromisoformat(committed).astimezone(datetime.timezone.utc)
    since, until = ((date + datetime.timedelta(days=d)).strftime('%Y-%m-%dT%H:%M:%SZ') for d in (-1, 1))
    commits: list[Commit] = json.loads(gh(f'{REPO}/commits?path={name}&since={since}&until={until}&per_page=100'))
    for commit in commits:
        if tree_sha(commit['sha'], name) == tree:
            return str(commit['sha'])
    msg = f'no llvm-project commit has the {name} tree of {url}@{revision}'
    raise SystemExit(msg)


def runtime_sources(tag: str) -> list[str]:
    """The libc++ and libc++abi sources of Chromium's Linux build, as llvm-project paths."""
    sources = []
    for gn, llvm in (('libc%2B%2B', 'libcxx'), ('libc%2B%2Babi', 'libcxxabi')):
        for line in chromium(f'buildtools/third_party/{gn}/BUILD.gn', tag).decode().splitlines():
            match = re.search(r'"//third_party/libc\+\+(?:abi)?/src/src/([^"]+\.cpp)"', line)
            if match and not line.lstrip().startswith('#') and 'win32' not in match[1]:
                sources.append(f'{llvm}/src/{match[1]}')
    return sorted(set(sources))


def includes(path: str, data: bytes) -> set[str]:
    """The llvm-project paths a file may include: next to it, or from libcxx/src and llvm-libc."""
    found = set()
    for include in INCLUDE.findall(data):
        name = include.decode()
        found.add(posixpath.normpath(posixpath.join(posixpath.dirname(path), name)))
        found.update(f'{root}/{name}' for root in ('libcxx/src', 'libc'))
    return found


def pin_runtime(commits: dict[str, str], tag: str) -> None:
    """Pins the runtime sources and, transitively, every file they include from RUNTIME_TREES."""
    tree: dict[str, str] = {}
    for root in RUNTIME_TREES:
        tree.update({f'{root}/{e["path"]}': e['sha'] for e in subtree(commits[root.split('/')[0]], root)})
    sources = runtime_sources(tag)
    pinned: dict[str, bytes] = {}
    queue = list(sources)
    with ThreadPoolExecutor(8) as pool:
        while queue:
            pinned.update(zip(queue, pool.map(blob, [tree[p] for p in queue])))
            found = set().union(*(includes(path, pinned[path]) for path in queue))
            queue = sorted(c for c in found if c in tree and c not in pinned)
    # CMake compiles every pinned libcxx/libcxxabi .cpp, so only the sources may be among them
    stray = [p for p in pinned if p.endswith('.cpp') and p not in sources and not p.startswith('libc/')]
    if stray:
        msg = f'sources include other .cpp files: {stray}'
        raise SystemExit(msg)
    lines = [f'{hashlib.sha256(data).hexdigest()}  {path}\n' for path, data in sorted(pinned.items())]
    (Path(__file__).parent / 'runtime.sha256').write_text(''.join(lines))
    print(f'{len(sources)} runtime sources, {len(lines)} files pinned')


def resolve_commits(webrtc_branch: str) -> dict[str, str]:
    """The llvm-project commits of the LLVM_DIRS the WebRTC branch pins."""
    with tempfile.TemporaryDirectory() as repo:
        webrtc = git_fetch('https://webrtc.googlesource.com/src', f'refs/branch-heads/{webrtc_branch}', repo)
        deps = subprocess.check_output([tool('git'), '-C', repo, 'show', 'FETCH_HEAD:DEPS'], text=True)
    print(f'WebRTC branch-heads/{webrtc_branch} at {webrtc}')
    return {name: resolve_llvm(deps, name) for name in LLVM_DIRS}


def pin_headers(commit: str, headers: Path) -> None:
    """Checks the prebuilt *.h headers against libc++ and pins the extensionless ones it lacks."""
    tree = subtree(commit, 'libcxx/include')
    remote = {e['path']: e['sha'] for e in tree}
    local = {str(p.relative_to(headers)): blob_sha(p.read_bytes()) for p in headers.rglob('*') if p.is_file()}
    mismatches = [path for path, sha in local.items() if remote.get(path) != sha]
    if mismatches:
        msg = f'the prebuilt headers differ from llvm-project@{commit}: {mismatches[:10]}'
        raise SystemExit(msg)

    missing = [e for e in tree if e['path'] not in local and '.' not in e['path'].rsplit('/', 1)[-1]]

    def sha256(entry: TreeEntry) -> str:
        data = blob(entry['sha'])
        return f'{hashlib.sha256(data).hexdigest()}  {entry["path"]}\n'

    with ThreadPoolExecutor(8) as pool:
        lines = sorted(pool.map(sha256, missing), key=lambda line: line.split()[1])
    (Path(__file__).parent / 'headers.sha256').write_text(''.join(lines))
    print(f'{len(lines)} headers pinned')


def pin_config(tag: str) -> None:
    """Pins Chromium's build-generated libc++ config."""
    config = []
    for name in CHROMIUM_CONFIG:
        data = chromium(f'buildtools/third_party/libc%2B%2B/{name}', tag)
        config.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    (Path(__file__).parent / 'config.sha256').write_text(''.join(config))
    print(f'{len(config)} config headers pinned')


def main() -> None:
    """Regenerates the pins and prints the CMake variables."""
    parser = argparse.ArgumentParser()
    parser.add_argument('headers', type=Path, help='libc++ include dir of the unpacked Linux prebuilt')
    parser.add_argument('--webrtc-branch', required=True, help='WebRTC branch number of the prebuilt, e.g. 7977')
    parser.add_argument('--chromium-tag', required=True, help='Chromium tag matching the WebRTC branch')
    args = parser.parse_args()

    commits = resolve_commits(args.webrtc_branch)
    pin_headers(commits['libcxx'], args.headers)
    pin_config(args.chromium_tag)
    pin_runtime(commits, args.chromium_tag)

    for name, (_, variable) in LLVM_DIRS.items():
        print(f'set({variable} {commits[name]})')
    print(f'set(LIBCXX_CHROMIUM_TAG {args.chromium_tag})')


if __name__ == '__main__':
    main()
