"""Regenerates the libc++ pins used by Linux builds (maintainer tool, needs the `gh` CLI).

The Linux libwebrtc prebuilt ships only the *.h headers of Chromium's libc++. This script
- finds the llvm-project commit whose libcxx/include matches them byte for byte and writes the SHA256 of
  every remaining (extensionless) header to headers.sha256;
- writes the SHA256 of Chromium's build-generated libc++ config (__config_site, __assertion_handler)
  at the given Chromium tag to config.sha256.
Then set LIBCXX_LLVM_COMMIT and LIBCXX_CHROMIUM_TAG in cmake/libwebrtc.cmake to the printed values.

usage: python cmake/libcxx/update.py <unpacked libwebrtc-linux-x64>/include/third_party/libc++/src/include \\
           --chromium-tag 152.0.7977.0 --since 2026-04-01 --until 2026-06-01
"""

import argparse
import base64
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = 'repos/llvm/llvm-project'
CHROMIUM_CONFIG = ('__config_site', '__assertion_handler')


def gh(path):
    return json.loads(subprocess.check_output(['gh', 'api', path]))


def blob_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def include_tree(commit):
    tree = gh(f'{REPO}/git/commits/{commit}')['tree']['sha']
    for part in ('libcxx', 'include'):
        tree = next(e['sha'] for e in gh(f'{REPO}/git/trees/{tree}')['tree'] if e['path'] == part)
    return [e for e in gh(f'{REPO}/git/trees/{tree}?recursive=1')['tree'] if e['type'] == 'blob']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('headers', type=Path, help='libc++ include dir of the unpacked Linux prebuilt')
    parser.add_argument('--chromium-tag', required=True, help='Chromium tag matching the WebRTC branch')
    parser.add_argument('--since', required=True, help='search window start, YYYY-MM-DD')
    parser.add_argument('--until', required=True, help='search window end, YYYY-MM-DD')
    args = parser.parse_args()

    local = {str(p.relative_to(args.headers)): blob_sha(p.read_bytes()) for p in args.headers.rglob('*') if p.is_file()}

    commits = subprocess.check_output(
        [
            'gh', 'api', '--paginate', '--jq', '.[].sha',
            f'{REPO}/commits?path=libcxx/include&since={args.since}T00:00:00Z&until={args.until}T00:00:00Z',
        ],
        text=True,
    ).split()  # fmt: skip

    for commit in commits:
        tree = include_tree(commit)
        remote = {e['path']: e['sha'] for e in tree}
        mismatches = sum(remote.get(path) != sha for path, sha in local.items())
        print(commit, mismatches, flush=True)
        if not mismatches:
            break
    else:
        raise SystemExit('no matching commit in the window, widen it')

    missing = [e for e in tree if e['path'] not in local and '.' not in e['path'].rsplit('/', 1)[-1]]

    def sha256(entry):
        data = base64.b64decode(gh(f'{REPO}/git/blobs/{entry["sha"]}')['content'])
        return f'{hashlib.sha256(data).hexdigest()}  {entry["path"]}\n'

    with ThreadPoolExecutor(8) as pool:
        lines = sorted(pool.map(sha256, missing), key=lambda line: line.split()[1])
    (Path(__file__).parent / 'headers.sha256').write_text(''.join(lines))
    print(f'LIBCXX_LLVM_COMMIT {commit}: {len(lines)} headers pinned')

    config = []
    for name in CHROMIUM_CONFIG:
        data = subprocess.check_output(
            [
                'gh', 'api', '-H', 'Accept: application/vnd.github.raw',
                f'repos/chromium/chromium/contents/buildtools/third_party/libc%2B%2B/{name}?ref={args.chromium_tag}',
            ]
        )  # fmt: skip
        config.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    (Path(__file__).parent / 'config.sha256').write_text(''.join(config))
    print(f'LIBCXX_CHROMIUM_TAG {args.chromium_tag}: {len(config)} config headers pinned')


if __name__ == '__main__':
    main()
