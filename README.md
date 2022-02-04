<p align="center">
    <a href="https://github.com/MarshalX/python-webrtc">
        <img src="https://github.com/MarshalX/python-webrtc/raw/main/.github/images/logo.png" alt="python-webrtc logo">
    </a>
    <br>
    <b>A Python extension that provides bindings to WebRTC M92</b>
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

> Stop making unstandard pure implementations of WebRTC and let's use the native library!

This project follows the [W3C specification](https://w3c.github.io/webrtc-pc/) with some modifications and additions to make it work better with Python applications, with useful APIs like programmatic audio and video.

## DISCLAIMER

This project is still under development and isn't ready for any serious use! In the current stage it's possible to establish connection and work with audio with a large number of segfaults and sigbuses. ✨

#### Snippet

```python
import asyncio
import webrtc


async def main():
    pc = webrtc.RTCPeerConnection()

    stream = webrtc.get_user_media()
    for track in stream.get_tracks():
        pc.add_track(track, stream)

    audio_source = webrtc.RTCAudioSource()
    track = audio_source.create_track()
    pc.add_track(track)

    local_sdp = await pc.create_offer()
    print(local_sdp.sdp)


if __name__ == '__main__':
    asyncio.run(main())
```

### Requirements

#### Pre-built wheels:

- Python 3.7 or higher
- pip 21 or higher
- And compatible platform: 

<table>
  <thead>
    <tr>
      <td colspan="2" rowspan="2"></td>
      <th colspan="3">Linux</th>
      <th colspan="2">macOS</th>
      <th>Windows</th>
    </tr>
    <tr>
      <th>armv7l</th>
      <th>arm64</th>
      <th>x86_64</th>
      <th>Intel</th>
      <th>Apple Silicon</th>
      <th>64bit</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th rowspan="4">Python</th>
      <th>3.7</th>
        <td align="center">N/A</td>
        <td align="center">N/A</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">N/A</td>
        <td align="center">✅</td>
    </tr>
    <tr>
      <th>3.8</th>
        <td align="center">N/A</td>
        <td align="center">N/A</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
    </tr>
    <tr>
      <th>3.9</th>
        <td align="center">N/A</td>
        <td align="center">N/A</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
    </tr>
    <tr>
      <th>3.10</th>
        <td align="center">N/A</td>
        <td align="center">N/A</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
    </tr>
  </tbody>
</table>

#### Building from sources (sdist):

- ~15 GB of free disk space
- CMake 3.14 or higher
- GCC 7.5 or higher
- glibc 2.18 or higher 
- ARM toolchain (ARM only)

_Full building instruction will be present later_

### Installing

Pre-built wheel:
``` bash
pip3 install --pre wrtc
```

Build from sources:
``` bash
pip3 install --pre wrtc --no-binary wrtc
```

### Documentation

The documentation is live at [readthedocs.io](https://wrtc.rtfd.io/).

### Getting help

You can get help in several ways:
- Report bugs, request new features by [creating an issue](https://github.com/MarshalX/python-webrtc/issues/new).
- Ask question by [starting a discussion](https://github.com/MarshalX/python-webrtc/discussions/new).

### Contributing

Contributions of any sizes are welcome.

### Special thanks to

- [Authors](https://github.com/node-webrtc/node-webrtc/blob/develop/AUTHORS) of [node-webrtc](https://github.com/node-webrtc/node-webrtc).

### License

The `python-webrtc` is published under the [BSD 3-Clause License](LICENSE.md).
