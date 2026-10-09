#!/usr/bin/env bash
#
# Builds the extension with AddressSanitizer and UndefinedBehaviorSanitizer on macOS (Apple Clang, natively), or
# ThreadSanitizer with SANITIZE=thread, and runs the Python tests against it. The Linux counterpart is sanitizers.sh.
#
#   .github/scripts/sanitizers-macos.sh [pytest arguments]
#   .github/scripts/sanitizers-macos.sh --build-only
#   .github/scripts/sanitizers-macos.sh --exec python -m tests.chaos --seed 7   # a command against the existing build
#
# The build and a venv without the editable install (whose import hook would load the regular build) are kept
# in build/asan (build/tsan).

set -euo pipefail

# physical: scripts/debug/cover.py matches the paths CMake records
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
SANITIZE="${SANITIZE:-address,undefined}"
if [ "$SANITIZE" = thread ]; then
    BUILD="${WRTC_SANITIZERS_BUILD_DIR:-$SRC/build/tsan}"
    COVERAGE=OFF
else
    BUILD="${WRTC_SANITIZERS_BUILD_DIR:-$SRC/build/asan}"
    COVERAGE=ON
    if [ -n "${CI:-}" ] || [ -n "${WRTC_SANITIZERS_BUILD_DIR:-}" ]; then
        COVERAGE=OFF
    fi
fi
MODE=test
case "${1:-}" in
    --build-only) MODE=build; shift ;;
    --exec) MODE=exec; shift ;;
esac

export PATH="$BUILD/venv/bin:$PATH"
if [ "$MODE" != exec ]; then
    if [ -z "${PYTHON:-}" ]; then
        uv python install -q 3.13
        PYTHON="$(uv python find 3.13)"
    fi

    if [ ! -x "$BUILD/venv/bin/python" ]; then
        uv venv -q "$BUILD/venv" --python "$PYTHON"
    fi
    uv pip install -q --python "$BUILD/venv/bin/python" cmake ninja "pybind11>=3.0" "typing_extensions>=4.10" \
        pytest pytest-asyncio pytest-timeout
    if [ "$COVERAGE" = ON ]; then
        uv pip install -q --python "$BUILD/venv/bin/python" "coverage>=7.10"
    fi

    cmake -S "$SRC" -B "$BUILD" -G Ninja \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DWRTC_SANITIZE="$SANITIZE" \
        -DWRTC_COVERAGE="$COVERAGE" \
        -DPython_EXECUTABLE="$BUILD/venv/bin/python" \
        -Dpybind11_DIR="$("$BUILD/venv/bin/python" -m pybind11 --cmakedir)" > /dev/null
    cmake --build "$BUILD"
    if [ "$COVERAGE" = ON ]; then
        # profiles of the previous build no longer match
        (cd "$SRC" && "$BUILD/venv/bin/python" -m scripts.debug.cover collect)
    fi
fi
if [ "$MODE" = build ]; then
    exit 0
fi

# The interpreter isn't instrumented: the runtime must be loaded before anything else
if [ "$SANITIZE" = thread ]; then
    DYLD_INSERT_LIBRARIES="$(clang -print-runtime-dir)/libclang_rt.tsan_osx_dynamic.dylib"
    # libwebrtc isn't instrumented: races of its own aren't reported
    export TSAN_OPTIONS="halt_on_error=1:report_signal_unsafe=0:strip_env=0"
else
    DYLD_INSERT_LIBRARIES="$(clang -print-runtime-dir)/libclang_rt.asan_osx_dynamic.dylib"
    export PYTHONMALLOC=malloc
    # LeakSanitizer isn't supported on macOS; strip_env=0 keeps the runtime in subprocesses of the tests;
    # container annotations can't match libwebrtc's libc++, whose code the linker may fold with ours
    export ASAN_OPTIONS="detect_leaks=0:detect_container_overflow=0:halt_on_error=1:abort_on_error=0:strict_init_order=1:strip_env=0"
    export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
fi
export DYLD_INSERT_LIBRARIES
export PYTHONPATH="$BUILD/python-webrtc/cpp:$SRC/python-webrtc/python:$SRC"
export PYTHONDONTWRITEBYTECODE=1
export LLVM_PROFILE_FILE="${LLVM_PROFILE_FILE:-$SRC/build/coverage/native/suite-%4m.profraw}"

cd "$SRC"
if [ "$MODE" = exec ]; then
    exec "$@"
fi
"$BUILD/venv/bin/python" -m pytest --ignore=tests/wpt -p no:cacheprovider --capture=sys "$@"
