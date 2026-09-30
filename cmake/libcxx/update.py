"""Regenerates the libc++ pins used by Linux builds (maintainer tool, needs `git` and the `gh` CLI).

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

import argparse
import base64
import datetime
import hashlib
import json
import posixpath
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Set

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


def gh(path: str) -> Any:
    return json.loads(subprocess.check_output(['gh', 'api', path]))


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def tree_sha(commit: str, path: str) -> str:
    tree: str = gh(f'{REPO}/git/commits/{commit}')['tree']['sha']
    for part in path.split('/'):
        tree = next(e['sha'] for e in gh(f'{REPO}/git/trees/{tree}')['tree'] if e['path'] == part)
    return tree


def subtree(commit: str, path: str) -> List[Dict[str, Any]]:
    listing = gh(f'{REPO}/git/trees/{tree_sha(commit, path)}?recursive=1')
    if listing['truncated']:
        raise SystemExit(f'{path} tree listing is truncated')
    return [e for e in listing['tree'] if e['type'] == 'blob']


def blob(sha: str) -> bytes:
    return base64.b64decode(gh(f'{REPO}/git/blobs/{sha}')['content'])


def chromium(path: str, tag: str) -> bytes:
    return subprocess.check_output(
        ['gh', 'api', '-H', 'Accept: application/vnd.github.raw', f'repos/chromium/chromium/contents/{path}?ref={tag}']
    )


def git_fetch(url: str, ref: str, repo: str) -> str:
    """Fetches only the commit object of <ref>, returns its hash."""
    subprocess.run(['git', 'init', '-q', repo], check=True)
    subprocess.run(['git', '-C', repo, 'fetch', '-q', '--depth=1', '--filter=tree:0', url, ref], check=True)
    return subprocess.check_output(['git', '-C', repo, 'rev-parse', 'FETCH_HEAD'], text=True).strip()


def resolve_llvm(deps: str, name: str) -> str:
    """Chromium mirrors each llvm-project dir as its own repo: finds the llvm-project commit with the same tree."""
    match = re.search(rf"'{re.escape(LLVM_DIRS[name][0])}':\s*'([^'@]+)@([0-9a-f]+)'", deps)
    if not match:
        raise SystemExit(f'{LLVM_DIRS[name][0]} is not in the WebRTC DEPS')
    url, revision = match.groups()
    with tempfile.TemporaryDirectory() as repo:
        git_fetch(url, revision, repo)
        tree, committed = subprocess.check_output(
            ['git', '-C', repo, 'log', '-1', '--format=%T %cI', 'FETCH_HEAD'], text=True
        ).split()
    date = datetime.datetime.fromisoformat(committed).astimezone(datetime.timezone.utc)
    since, until = ((date + datetime.timedelta(days=d)).strftime('%Y-%m-%dT%H:%M:%SZ') for d in (-1, 1))
    for commit in gh(f'{REPO}/commits?path={name}&since={since}&until={until}&per_page=100'):
        if tree_sha(commit['sha'], name) == tree:
            return str(commit['sha'])
    raise SystemExit(f'no llvm-project commit has the {name} tree of {url}@{revision}')


def runtime_sources(tag: str) -> List[str]:
    """The libc++ and libc++abi sources of Chromium's Linux build, as llvm-project paths."""
    sources = []
    for gn, llvm in (('libc%2B%2B', 'libcxx'), ('libc%2B%2Babi', 'libcxxabi')):
        for line in chromium(f'buildtools/third_party/{gn}/BUILD.gn', tag).decode().splitlines():
            match = re.search(r'"//third_party/libc\+\+(?:abi)?/src/src/([^"]+\.cpp)"', line)
            if match and not line.lstrip().startswith('#') and 'win32' not in match[1]:
                sources.append(f'{llvm}/src/{match[1]}')
    return sorted(set(sources))


def pin_runtime(commits: Dict[str, str], tag: str) -> None:
    """Pins the runtime sources and, transitively, every file they include from RUNTIME_TREES."""
    tree: Dict[str, str] = {}
    for root in RUNTIME_TREES:
        tree.update({f'{root}/{e["path"]}': e['sha'] for e in subtree(commits[root.split('/')[0]], root)})
    sources = runtime_sources(tag)
    pinned: Dict[str, bytes] = {}
    queue = list(sources)
    with ThreadPoolExecutor(8) as pool:
        while queue:
            for path, data in zip(queue, pool.map(blob, [tree[p] for p in queue])):
                pinned[path] = data
            found: Set[str] = set()
            for path in queue:
                for include in INCLUDE.findall(pinned[path]):
                    name = include.decode()
                    candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(path), name))]
                    candidates += [f'{root}/{name}' for root in ('libcxx/src', 'libc')]
                    found.update(c for c in candidates if c in tree and c not in pinned)
            queue = sorted(found)
    # CMake compiles every pinned libcxx/libcxxabi .cpp, so only the sources may be among them
    stray = [p for p in pinned if p.endswith('.cpp') and p not in sources and not p.startswith('libc/')]
    if stray:
        raise SystemExit(f'sources include other .cpp files: {stray}')
    lines = [f'{hashlib.sha256(data).hexdigest()}  {path}\n' for path, data in sorted(pinned.items())]
    (Path(__file__).parent / 'runtime.sha256').write_text(''.join(lines))
    print(f'{len(sources)} runtime sources, {len(lines)} files pinned')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('headers', type=Path, help='libc++ include dir of the unpacked Linux prebuilt')
    parser.add_argument('--webrtc-branch', required=True, help='WebRTC branch number of the prebuilt, e.g. 7977')
    parser.add_argument('--chromium-tag', required=True, help='Chromium tag matching the WebRTC branch')
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as repo:
        webrtc = git_fetch('https://webrtc.googlesource.com/src', f'refs/branch-heads/{args.webrtc_branch}', repo)
        deps = subprocess.check_output(['git', '-C', repo, 'show', 'FETCH_HEAD:DEPS'], text=True)
    print(f'WebRTC branch-heads/{args.webrtc_branch} at {webrtc}')
    commits = {name: resolve_llvm(deps, name) for name in LLVM_DIRS}

    tree = subtree(commits['libcxx'], 'libcxx/include')
    remote = {e['path']: e['sha'] for e in tree}
    local = {str(p.relative_to(args.headers)): blob_sha(p.read_bytes()) for p in args.headers.rglob('*') if p.is_file()}
    mismatches = [path for path, sha in local.items() if remote.get(path) != sha]
    if mismatches:
        raise SystemExit(f'the prebuilt headers differ from llvm-project@{commits["libcxx"]}: {mismatches[:10]}')

    missing = [e for e in tree if e['path'] not in local and '.' not in e['path'].rsplit('/', 1)[-1]]

    def sha256(entry: Dict[str, Any]) -> str:
        data = blob(entry['sha'])
        return f'{hashlib.sha256(data).hexdigest()}  {entry["path"]}\n'

    with ThreadPoolExecutor(8) as pool:
        lines = sorted(pool.map(sha256, missing), key=lambda line: line.split()[1])
    (Path(__file__).parent / 'headers.sha256').write_text(''.join(lines))
    print(f'{len(lines)} headers pinned')

    config = []
    for name in CHROMIUM_CONFIG:
        data = chromium(f'buildtools/third_party/libc%2B%2B/{name}', args.chromium_tag)
        config.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    (Path(__file__).parent / 'config.sha256').write_text(''.join(config))
    print(f'{len(config)} config headers pinned')

    pin_runtime(commits, args.chromium_tag)

    for name, (_, variable) in LLVM_DIRS.items():
        print(f'set({variable} {commits[name]})')
    print(f'set(LIBCXX_CHROMIUM_TAG {args.chromium_tag})')


if __name__ == '__main__':
    main()
