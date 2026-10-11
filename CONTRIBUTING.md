# Contributing

Contributions of any size are welcome. For bugs and features, [open an issue](https://github.com/MarshalX/python-webrtc/issues/new);
for questions, [start a discussion](https://github.com/MarshalX/python-webrtc/discussions/new).

## Development

Requires [uv](https://docs.astral.sh/uv/).

``` bash
make dev     # editable install into .venv, C++ is rebuilt on import when changed
make test    # run the test suite
make lint    # ruff
make stub    # regenerate type stubs of the native module
make wheels  # build wheels for the current platform the same way CI does
```

## Building from sources (sdist)

- CMake 3.26 or higher
- A C++20 compiler: Clang on Linux (libwebrtc there is built against Chromium's libc++), Apple Clang on macOS, MSVC on Windows
- ~150 MB of free disk space

Nothing else has to be installed or configured manually: a prebuilt static libwebrtc for the target platform
(from [libwebrtc-bin](https://github.com/crow-misia/libwebrtc-bin)) is downloaded once, verified and unpacked
into a shared cache (`~/.cache/python-webrtc`, `%LOCALAPPDATA%\python-webrtc` on Windows or `$WRTC_CACHE_DIR`).
Only the headers in use are extracted and debug info is stripped, so it takes ~60 MB per platform.
Pass `-Ccmake.define.LIBWEBRTC_ROOT=/path/to/libwebrtc` to use your own libwebrtc build instead.

## Releasing

1. Bump `version` in `pyproject.toml` and run `uv lock`.
2. Push a `v<version>` tag. CI builds the sdist and wheels for every platform and publishes them to PyPI.

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/): the PyPI project needs a
trusted publisher for this repository's `ci.yml` workflow, and the repository a `pypi` environment. No tokens needed.

## Updating WebRTC

The libwebrtc version and archive hashes are pinned in `cmake/libwebrtc.cmake`:

1. Set `LIBWEBRTC_VERSION` to a [libwebrtc-bin release](https://github.com/crow-misia/libwebrtc-bin/releases)
   and update the `LIBWEBRTC_SHA256_*` values (the release page lists a SHA256 digest per asset).
2. Refresh the Linux libc++ pins as described in [`cmake/libcxx/README.md`](cmake/libcxx/README.md).
3. Build and run the tests. On Linux, check whether `cmake/libwebrtc_linux_fixups.cpp` is still needed:
   remove it and see whether the module imports (it is linked with `-z now`, so missing symbols fail on import).
