<p align="center">
    <a href="https://github.com/MarshalX/python-webrtc">
        <img src=".github/images/logo.png" alt="python-webrtc">
    </a>
    <br>
    <b>Python Extension that provides bindings to WebRTC M92 </b>
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

This project tries to be like [W3C](https://w3c.github.io/webrtc-pc/) specification, but there is some edits out of
specification. The changes were applied to make library more Pythonic and add useful API like programmatic audio and
video.

## DISCLAIMER

This project under development and doesn't redy for any serious use! In the current stage it's possible to establish
connection and working with audio. The project has segfaults and sigbuse in large numbers ✨

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
- Pip 21+
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
      <th>x64</th>
      <th>x64</th>
      <th>M1</th>
      <th>x64</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th rowspan="6">Python</th>
      <th>3.7</th>
        <td align="center">❌</td>
        <td align="center">❌</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">❌</td>
        <td align="center">✅</td>
    </tr>
    <tr>
      <th>3.8</th>
        <td align="center">❌</td>
        <td align="center">❌</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
    </tr>
    <tr>
      <th>3.9</th>
        <td align="center">❌</td>
        <td align="center">❌</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
    </tr>
    <tr>
      <th>3.10</th>
        <td align="center">❌</td>
        <td align="center">❌</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
        <td align="center">✅</td>
    </tr>
  </tbody>
</table>

#### Building from sources (sdist):

- ~15 GB of free disk space
- CMake 3.14+
- GCC 7.5+
- glibc 2.18+ 
- ARM toolchain (ARM only)

_Full building instruction will be present later_

### Installing

❗️ Nothing was published on PyPi for now!

Pre-built wheel:
``` bash
pip3 install wrtc
```

Build from sources:
``` bash
pip3 install wrtc --no-binary
```

### Documentation

`wrtc`'s documentation lives at [readthedocs.io](https://wrtc.rtfd.io/).

### Getting help

You can get help in several ways:
- Report bugs, request new features by creating [an issue](https://github.com/MarshalX/python-webrtc/issues/new).
- Ask questions by creation [a discussion](https://github.com/MarshalX/python-webrtc/discussions/new).

### Contributing

Contributions of all sizes are welcome.

### Special thanks to

- [Authors](https://github.com/node-webrtc/node-webrtc/blob/develop/AUTHORS) for [node-webrtc](https://github.com/node-webrtc/node-webrtc).

### License

The `python-webrtc` licence is [BSD 3-Clause License](LICENSE.md).
