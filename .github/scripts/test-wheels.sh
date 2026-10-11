#!/usr/bin/env bash
#
# Tests the wheels built in one job all at once: a pytest process per wheel, on the wheel's own interpreter.
#
#   .github/scripts/test-wheels.sh sdist/wrtc-0.0.1.tar.gz wheelhouse [--gc-on-emit]
#
# With --gc-on-emit, the free-threaded wheel also runs the suite with it, at the same time.
set -euo pipefail
SDIST="$1"
WHEELS="$(cd "$2" && pwd)"
GC_ON_EMIT="${3:-}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# the tests from the sdist, as cibuildwheel runs them
tar -xzf "$SDIST" -C "$WORK"
cd "$WORK"/wrtc-*

names=()
pids=()
# in the background, into a log of its own: run NAME PYTHON [PYTEST ARGS...]
run() {
    local name="$1" python="$2"
    shift 2
    "$python" -m pytest tests "$@" > "$WORK/$name.log" 2>&1 &
    names+=("$name")
    pids+=($!)
}

for wheel in "$WHEELS"/*.whl; do
    # wrtc-0.0.1-cp315-cp315t-macosx_13_0_arm64.whl: cp315t, Python 3.15t
    abi="$(basename "$wheel" | cut -d- -f4)"
    digits="${abi#cp}"
    venv="$WORK/$abi"
    uv venv -q --python "${digits:0:1}.${digits:1}" "$venv"
    uv pip install -q --python "$venv/bin/python" "$wheel" --group pyproject.toml:test
    run "$abi" "$venv/bin/python"
    if [ "$GC_ON_EMIT" = --gc-on-emit ] && [[ "$abi" == *t ]]; then
        run "$abi-gc-on-emit" "$venv/bin/python" --gc-on-emit
    fi
done

status=0
for i in "${!pids[@]}"; do
    name="${names[$i]}"
    # a failed run stays expanded
    if wait "${pids[$i]}"; then
        echo "::group::$name passed"
        cat "$WORK/$name.log"
        echo "::endgroup::"
    else
        status=1
        echo "$name failed:"
        cat "$WORK/$name.log"
    fi
done
exit "$status"
