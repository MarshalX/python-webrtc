#!/usr/bin/env bash
#
# Runs clang-tidy (see .clang-tidy) over the extension sources, against a configured (not built) tree in build/tidy.
#
#   .github/scripts/tidy.sh [run-clang-tidy arguments, e.g. -fix or a file regex]
#
# The LLVM version is pinned to match clang-format in the Makefile.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${WRTC_TIDY_BUILD_DIR:-$SRC/build/tidy}"
LLVM_VERSION=22.1.8

if [ ! -x "$BUILD/venv/bin/python" ]; then
    uv venv -q "$BUILD/venv" --python 3.13
fi
uv pip install -q --python "$BUILD/venv/bin/python" cmake ninja "pybind11>=3.0" "clang-tidy==$LLVM_VERSION"
export PATH="$BUILD/venv/bin:$PATH"

# libwebrtc for Linux is compiled against Chromium's libc++, which needs Clang
if [ "$(uname)" = Linux ]; then
    export CC="${CC:-clang}" CXX="${CXX:-clang++}"
fi
cmake -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DPython_EXECUTABLE="$BUILD/venv/bin/python" \
    -Dpybind11_DIR="$("$BUILD/venv/bin/python" -m pybind11 --cmakedir)" > /dev/null

EXTRA=()
if [ "$(uname)" = Darwin ]; then
    # the wheel's clang doesn't know the SDK Apple Clang uses implicitly
    EXTRA+=(-extra-arg=-isysroot"$(xcrun --show-sdk-path)")
fi

cd "$SRC"
python "$BUILD/venv/bin/run-clang-tidy.py" -p "$BUILD" -quiet -j "$(getconf _NPROCESSORS_ONLN)" \
    ${EXTRA[@]+"${EXTRA[@]}"} "$@" "$SRC/python-webrtc/cpp/src/"
