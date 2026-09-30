<p align="center">
    <a href="https://github.com/MarshalX/python-webrtc">
        <img src="https://github.com/MarshalX/python-webrtc/raw/main/.github/images/logo.png" alt="python-webrtc logo">
    </a>
    <br>
    <b>A Python extension that provides bindings to WebRTC M152</b>
    <br>
    <a href="https://github.com/MarshalX/python-webrtc/tree/main/examples">
        Examples
    </a>
    •
    <a href="https://wrtc.rtfd.io/">
        Documentation
    </a>
    •
    <a href="https://pypi.org/project/wrtc/">
        PyPI
    </a>
</p>

## Python WebRTC

> Let's use the native WebRTC with strict compatibility and fully implemented stuff!

This project follows the [W3C specification](https://w3c.github.io/webrtc-pc/) with some modifications and additions to make it work better with Python applications. Audio and video are read from tracks and written to them with the APIs of browsers: `MediaStreamTrackProcessor`, `VideoTrackGenerator` and `MediaStreamTrackGenerator`, with the `VideoFrame` and `AudioData` of WebCodecs.

## DISCLAIMER

This project is still under development and isn't ready for any serious use. In the current stage, it's possible to establish connection and work with audio, but many interfaces and methods not implemented yet.

You can easily check status of methods and interfaces availability [here](https://github.com/users/MarshalX/projects/1/views/1).

#### Snippet

```python
import asyncio
import webrtc


async def main():
    pc = webrtc.RTCPeerConnection()

    stream = webrtc.get_user_media()
    for track in stream.get_tracks():
        pc.add_track(track, stream)

    generator = webrtc.MediaStreamTrackGenerator('audio')
    pc.add_track(generator)

    local_sdp = await pc.create_offer()
    print(local_sdp.sdp)


if __name__ == '__main__':
    asyncio.run(main())
```

### Requirements

#### Pre-built wheels

Python 3.9 – 3.14 (CPython) on:

| Linux                                       | macOS                        | Windows |
|---------------------------------------------|------------------------------|---------|
| x86_64 and aarch64 (glibc 2.27+, manylinux) | 13+, Intel and Apple Silicon | x64     |

#### Building from sources (sdist)

- CMake 3.26 or higher
- A C++20 compiler: Clang on Linux (libwebrtc there is built against Chromium's libc++), Apple Clang on macOS, MSVC on Windows
- ~150 MB of free disk space

Nothing else has to be installed or configured manually: a prebuilt static libwebrtc for the target platform
(from [libwebrtc-bin](https://github.com/crow-misia/libwebrtc-bin)) is downloaded once, verified and unpacked
into a shared cache (`~/.cache/python-webrtc`, `%LOCALAPPDATA%\python-webrtc` on Windows or `$WRTC_CACHE_DIR`).
Only the headers in use are extracted and debug info is stripped, so it takes ~60 MB per platform.
Pass `-Ccmake.define.LIBWEBRTC_ROOT=/path/to/libwebrtc` to use your own libwebrtc build instead.

### Installing

Pre-built wheel:
``` bash
pip install --pre wrtc
```

Build from sources:
``` bash
pip install --pre wrtc --no-binary wrtc
```

### Development

Requires [uv](https://docs.astral.sh/uv/).

``` bash
make dev     # editable install into .venv, C++ is rebuilt on import when changed
make test    # run the test suite
make lint    # ruff
make stub    # regenerate type stubs of the native module
make wheels  # build wheels for the current platform the same way CI does
```

#### Releasing

1. Bump `version` in `pyproject.toml` and run `uv lock`.
2. Push a `v<version>` tag. CI builds the sdist and wheels for every platform and publishes them to PyPI.

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/): the PyPI project needs a
trusted publisher for this repository's `ci.yml` workflow, and the repository a `pypi` environment. No tokens needed.

#### Updating WebRTC

The libwebrtc version and archive hashes are pinned in `cmake/libwebrtc.cmake`:

1. Set `LIBWEBRTC_VERSION` to a [libwebrtc-bin release](https://github.com/crow-misia/libwebrtc-bin/releases)
   and update the `LIBWEBRTC_SHA256_*` values (the release page lists a SHA256 digest per asset).
2. Refresh the Linux libc++ pins as described in [`cmake/libcxx/README.md`](cmake/libcxx/README.md).
3. Build and run the tests. On Linux, check whether `cmake/libwebrtc_linux_fixups.cpp` is still needed:
   remove it and see whether the module imports (it is linked with `-z now`, so missing symbols fail on import).

### Documentation

The documentation is live at [readthedocs.io](https://wrtc.rtfd.io/).

### Getting help

You can get help in several ways:
- Report bugs, request new features by [creating an issue](https://github.com/MarshalX/python-webrtc/issues/new).
- Ask questions by [starting a discussion](https://github.com/MarshalX/python-webrtc/discussions/new).

### Contributing

Contributions of any sizes are welcome.

### Special thanks to

- [Authors](https://github.com/node-webrtc/node-webrtc/blob/develop/AUTHORS) of [node-webrtc](https://github.com/node-webrtc/node-webrtc).
- Authors of [web-platform-tests](https://github.com/web-platform-tests/wpt).

### License

The `python-webrtc` is published under the [BSD 3-Clause License](LICENSE.md).
