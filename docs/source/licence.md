# Licence

BSD 3-Clause License. File in repository: [LICENSE.md](https://github.com/MarshalX/python-webrtc/blob/main/LICENSE.md)

The licences of the bundled third-party code: [THIRD_PARTY_LICENSES.md](https://github.com/MarshalX/python-webrtc/blob/main/THIRD_PARTY_LICENSES.md)

```{include} ../../LICENSE.md
:end-before: Binary distributions
```

## OpenH264

OpenH264 Video Codec provided by Cisco Systems, Inc.

H.264 uses Cisco's OpenH264 binary, downloaded separately by {func}`webrtc.openh264.install` (see
[H.264](guides/h264.md)). Its license, and the license of the OpenH264 headers compiled into python-webrtc:

```{include} ../../THIRD_PARTY_LICENSES.md
:start-after: "# openh264"
:end-before: "# opus"
```
