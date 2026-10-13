#!/usr/bin/env bash
#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#
# Runs the benchmarks end to end: environments, the native drivers, the suites, the report and the charts.
#
#   benchmarks/run.sh                        # every suite, 3 runs each
#   benchmarks/run.sh --quick                # a smoke test of every suite
#   benchmarks/run.sh --suite media --libs wrtc,pion

set -euo pipefail

cd "$(dirname "$0")/.."

export WRTC_ALLOW_LOOPBACK=1
python() { uv run --no-sync python "$@"; }

for tool in uv go ffmpeg git cmake cargo; do
    command -v "$tool" >/dev/null || { echo "run.sh: $tool is needed" >&2; exit 1; }
done
[[ -d .venv ]] || { echo 'run.sh: no .venv, set up the development environment first (make dev)' >&2; exit 1; }

echo '== environments' >&2
uv pip install --quiet --python .venv -r benchmarks/requirements.txt
python -c 'import webrtc' >/dev/null
if [[ ! -d benchmarks/.venv-aiortc ]]; then
    uv venv --quiet --python "$(python -c 'import platform; print(platform.python_version())')" benchmarks/.venv-aiortc
fi
uv pip install --quiet --python benchmarks/.venv-aiortc -r benchmarks/requirements-aiortc.txt

echo '== native drivers' >&2
python -c 'from benchmarks.runner import build_drivers; build_drivers()'

echo '== suites' >&2
python -m benchmarks "$@"

echo '== charts' >&2
python -m benchmarks.charts
