#!/usr/bin/env bash
#
# Builds the extension with libFuzzer coverage, AddressSanitizer and UndefinedBehaviorSanitizer and runs a fuzz
# target of tests/fuzz with Atheris. Linux only: Apple Clang has no libFuzzer. In the manylinux image:
#   docker run --rm --platform linux/amd64 -v "$PWD:/src" -w /src \
#       quay.io/pypa/manylinux_2_28_x86_64 .github/scripts/fuzz.sh video_frame -max_total_time=600
#
# The first argument is the target (fuzz_<target>.py), the rest are libFuzzer's. The corpus grows in
# tests/fuzz/corpus/<target>, crashes are written to tests/fuzz/crashes. Pass a crash file to replay it.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${WRTC_FUZZ_BUILD_DIR:-/tmp/wrtc-fuzz}"
PYTHON="${PYTHON:-/opt/python/cp313-cp313/bin/python}"
TARGET="${1:?usage: fuzz.sh <target> [libFuzzer arguments]}"
shift

if ! command -v clang > /dev/null; then
    dnf install -y -q clang lld compiler-rt llvm
fi

if [ ! -x "$BUILD/venv/bin/python" ]; then
    "$PYTHON" -m venv "$BUILD/venv"
    # built from source with this Clang, so its sanitizer runtime is the one the extension is instrumented for
    CLANG_BIN="$(command -v clang)" LIBFUZZER_LIB="$(clang -print-runtime-dir)/libclang_rt.fuzzer_no_main.a" \
        "$BUILD/venv/bin/pip" install -q --no-binary atheris atheris \
        cmake ninja "pybind11>=3.0" pytest
fi
# shellcheck disable=SC1091
source "$BUILD/venv/bin/activate"

CC=clang CXX=clang++ cmake -S "$SRC" -B "$BUILD/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_UNITY_BUILD=ON \
    -DWRTC_SANITIZE=fuzzer-no-link,address,undefined \
    -Dpybind11_DIR="$(python -m pybind11 --cmakedir)" > /dev/null
cmake --build "$BUILD/build"

# The interpreter isn't instrumented: libFuzzer and ASan must be loaded before anything else
LD_PRELOAD="$(python -c 'import atheris; print(atheris.path())')/asan_with_fuzzer.so"
export LD_PRELOAD
export PYTHONMALLOC=malloc
export ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=0:detect_stack_use_after_return=0"
export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
ASAN_SYMBOLIZER_PATH="$(command -v llvm-symbolizer)"
export ASAN_SYMBOLIZER_PATH
export PYTHONPATH="$BUILD/build/python-webrtc/cpp:$SRC/python-webrtc/python:$SRC/tests/fuzz"
export PYTHONDONTWRITEBYTECODE=1

CORPUS="$SRC/tests/fuzz/corpus/$TARGET"
mkdir -p "$CORPUS" "$SRC/tests/fuzz/crashes"
# a file argument replays it instead of fuzzing
if [ $# -gt 0 ] && [ -f "$1" ]; then
    CRASH="$(realpath "$1")"
    shift
    cd "$SRC/tests/fuzz"
    exec python "fuzz_$TARGET.py" "$CRASH" "$@"
fi
cd "$SRC/tests/fuzz"
exec python "fuzz_$TARGET.py" "$CORPUS" -artifact_prefix="$SRC/tests/fuzz/crashes/$TARGET-" \
    -max_len=4096 -timeout=30 -rss_limit_mb=4096 "$@"
