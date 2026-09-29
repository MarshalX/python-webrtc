# Benchmarks

2026-09-29, Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, commit 0809341 with uncommitted changes. Written by `python -m benchmarks`.

Both peers run in one process on the machine, so encoding, decoding and Python share its cores. CPU is of one core (100% is a core busy).

## VideoFrame.copy_to

The cost of a copy of the planes (I420) or of a conversion to RGB.

| Size | Format | ms per frame | Megapixels/s |
| --- | --- | --- | --- |
| 320x240 | I420 | 0.010 | 7570 |
| 320x240 | RGBA | 0.036 | 2108 |
| 320x240 | BGRA | 0.036 | 2105 |
| 640x480 | I420 | 0.016 | 18875 |
| 640x480 | RGBA | 0.125 | 2463 |
| 640x480 | BGRA | 0.124 | 2471 |
| 1280x720 | I420 | 0.037 | 24831 |
| 1280x720 | RGBA | 0.364 | 2534 |
| 1280x720 | BGRA | 0.365 | 2527 |
| 1920x1080 | I420 | 0.084 | 24656 |
| 1920x1080 | RGBA | 0.864 | 2399 |
| 1920x1080 | BGRA | 0.889 | 2332 |

Creating a 1920x1080 I420 VideoFrame from bytes (a copy of them): 0.104 ms.

## Video through a connection

Frames written to a VideoTrackGenerator at 30 fps for 30 s (after a warmup), sent over VP8, read from a MediaStreamTrackProcessor of the remote track (buffer of 1 frame). Latency is from the write to the read, matched by a frame number drawn in the pixels. Lag is how late the event loop runs a 5 ms timer.

| Size | Delivered fps | Sent | Received | Received sizes | Dropped by the processor | Latency p50 / p95 (ms) | Loop lag p95 / max (ms) | CPU | RSS start / end (MB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 320x240 | 30.0 | 901 | 901 | 320x240 | 0 | 17 / 19 | 1.4 / 21.8 | 15% | 88 / 64 |
| 640x480 | 30.0 | 901 | 901 | 640x480 | 0 | 20 / 22 | 1.4 / 2.0 | 23% | 83 / 87 |
| 1280x720 | 30.0 | 901 | 900 | 1280x720 | 0 | 25 / 27 | 1.3 / 3.9 | 43% | 138 / 147 |
| 1920x1080 | 30.0 | 901 | 900 | 1920x1080 | 0 | 30 / 31 | 1.3 / 7.9 | 54% | 299 / 314 |

## Audio through a connection

10 ms chunks of 48 kHz stereo written to a MediaStreamTrackGenerator in real time for 60 s, sent over Opus, read from a MediaStreamTrackProcessor of the remote track.

| Written | Received | Chunks/s | Frames received | Dropped | Loop lag p95 (ms) | CPU | RSS start / end (MB) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6003 | 6003 | 100.0 | 2881440 | 0 | 1.3 | 12% | 135 / 142 |

## Slow consumer

720p at 30 fps read by a consumer that takes 100 ms per frame, for 30 s: the processor drops the frames it can't deliver, so memory stays flat.

| Delivered fps | Dropped by the processor | RSS start / end (MB) | RSS slope (MB/min) |
| --- | --- | --- | --- |
| 9.9 | 603 | 178 / 142 | -82.84 |

## Soak

720p at 30 fps through a connection for 10 minutes, the resident memory sampled every 10 s.

| Delivered fps | Latency p95 (ms) | CPU | RSS start / end (MB) | RSS slope (MB/min) | RSS slope, second half (MB/min) |
| --- | --- | --- | --- | --- | --- |
| 30.0 | 23 | 40% | 168 / 169 | -0.18 | -0.81 |

RSS samples (s, MB): 0: 168, 10: 168, 20: 168, 30: 169, 40: 169, 50: 169, 60: 170, 70: 170, 80: 170, 90: 170, 100: 170, 110: 170, 120: 171, 130: 172, 140: 172, 150: 173, 160: 173, 170: 172, 180: 172, 190: 172, 200: 172, 210: 172, 220: 172, 230: 172, 240: 173, 250: 173, 260: 173, 270: 173, 280: 173, 290: 173, 300: 173, 310: 173, 320: 173, 330: 173, 340: 173, 350: 173, 360: 173, 370: 173, 380: 168, 390: 166, 401: 166, 411: 167, 421: 167, 431: 168, 441: 168, 451: 168, 461: 169, 471: 169, 481: 169, 491: 169, 501: 169, 511: 169, 521: 169, 531: 169, 541: 169, 551: 169, 561: 169, 571: 169, 581: 169, 591: 169

