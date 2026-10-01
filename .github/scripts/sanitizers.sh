#!/usr/bin/env bash
#
# Builds the extension with AddressSanitizer and UndefinedBehaviorSanitizer and runs the Python tests against it.
#
# Runs in the image the Linux wheels are built in, the same way in CI and locally:
#   docker run --rm --platform linux/amd64 -v "$PWD:/src:ro" -w /src \
#       quay.io/pypa/manylinux_2_28_x86_64 .github/scripts/sanitizers.sh
#
# Extra arguments are passed to pytest.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${WRTC_SANITIZERS_BUILD_DIR:-/tmp/wrtc-sanitizers}"
PYTHON="${PYTHON:-/opt/python/cp313-cp313/bin/python}"

# libwebrtc for Linux is compiled against Chromium's libc++, which needs Clang; llvm provides the symbolizer
dnf install -y -q clang lld compiler-rt llvm

"$PYTHON" -m venv "$BUILD/venv"
# shellcheck disable=SC1091
source "$BUILD/venv/bin/activate"
python -m pip install -q cmake ninja "pybind11>=3.0" "typing_extensions>=4.10" pytest pytest-asyncio pytest-timeout

CC=clang CXX=clang++ cmake -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_UNITY_BUILD=ON \
    -DWRTC_SANITIZE=address,undefined \
    -Dpybind11_DIR="$(python -m pybind11 --cmakedir)"
cmake --build "$BUILD"

# The interpreter isn't instrumented: the runtime must be loaded before anything else
LD_PRELOAD="$(clang -print-runtime-dir)/libclang_rt.asan.so"
export LD_PRELOAD
# let ASan see the allocations of Python objects too
export PYTHONMALLOC=malloc
# CPython doesn't free everything at exit, which LeakSanitizer can't tell from real leaks.
# Leaks of the wrappers are covered by tests/test_lifetime.py.
export ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=0:strict_init_order=1:detect_stack_use_after_return=0"
export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
ASAN_SYMBOLIZER_PATH="$(command -v llvm-symbolizer)"
export ASAN_SYMBOLIZER_PATH
export PYTHONPATH="$BUILD/python-webrtc/cpp:$SRC/python-webrtc/python:$SRC"
export PYTHONDONTWRITEBYTECODE=1

cd "$SRC"
# tests/wpt runs JavaScript web-platform-tests through a shim, only the Python tests are run here
# sanitizers report to stderr and exit right away, so it must not be captured into a file (--capture=fd)
python -m pytest tests --ignore=tests/wpt -p no:cacheprovider --capture=sys -v "$@"
