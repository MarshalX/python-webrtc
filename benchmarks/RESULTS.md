# Benchmarks

Medians; % columns are of aiortc's. How: [README](README.md#method).

2026-10-13, 3 runs a case, Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1, commit be4ae3e with uncommitted changes.

## Connection setup

- ms, p50 / p95, from `createOffer`; Create: the constructors.
- aiortc can't trickle: it connects without trickle in both.

### Trickle, warm (102 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.1 | 0.7 / 0.7 | 0.3 / 0.4 | 6.1 / 6.9 | 6.4 / 7.3 | 6.7 / 7.6 | 6.9 / 7.7 | 24% |
| aiortc 1.15.0 | 0.3 / 0.3 | 0.1 / 0.1 | 2.1 / 2.6 | 26.8 / 27.5 | 28.2 / 28.8 | 29.1 / 30.9 | 100% |
| pion v4.2.23 | 0.8 / 1.2 | 1.9 / 2.6 | 3.7 / 4.8 | 33.8 / 90.5 | 38.5 / 97.0 | 39.7 / 99.0 | 136% |
| libdatachannel 0.24.6 | 0.0 / 0.0 | 0.2 / 0.2 | 0.2 / 0.3 | 1.0 / 1.7 | 2.3 / 3.3 | 2.4 / 3.5 | 8% |
| webrtc-rs 0.21.1 | 1.2 / 1.5 | 0.1 / 0.1 | 0.3 / 0.3 | 205.8 / 224.2 | 223.6 / 419.5 | 418.9 / 807.7 | 1439% |

### Trickle, cold: fresh processes (10 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.1 | 1.7 / 2.0 | 0.4 / 0.5 | 7.1 / 8.6 | 7.4 / 9.5 | 7.6 / 9.7 | 7.8 / 10.0 | 23% |
| aiortc 1.15.0 | 3.6 / 3.7 | 0.1 / 0.1 | 2.3 / 2.4 | 27.3 / 27.9 | 32.7 / 33.2 | 33.7 / 34.2 | 100% |
| pion v4.2.23 | 0.4 / 5.4 | 0.7 / 4.2 | 1.4 / 6.4 | 26.7 / 84.1 | 28.9 / 87.7 | 29.6 / 88.2 | 83% |
| libdatachannel 0.24.6 | 0.8 / 1.6 | 2.6 / 4.9 | 2.7 / 4.9 | 4.2 / 7.7 | 5.8 / 10.4 | 6.1 / 10.7 | 18% |
| webrtc-rs 0.21.1 | 0.5 / 13.4 | 0.0 / 0.5 | 0.1 / 0.8 | 213.9 / 299.2 | 293.5 / 501.0 | 487.7 / 701.8 | 1385% |

### Without trickle, warm (102 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.1 | 1.7 / 1.8 | 0.8 / 0.9 | 107.9 / 109.9 | 124.3 / 126.7 | 124.8 / 127.2 | 125.1 / 127.6 | 430% |
| aiortc 1.15.0 | 0.3 / 0.3 | 0.1 / 0.1 | 2.1 / 2.6 | 26.8 / 27.6 | 28.2 / 28.9 | 29.1 / 29.9 | 100% |
| pion v4.2.23 | 0.8 / 1.0 | 1.8 / 2.5 | 3.6 / 4.5 | 49.2 / 51.0 | 51.0 / 53.0 | 51.9 / 53.9 | 178% |
| libdatachannel 0.24.6 | 0.0 / 0.0 | 0.2 / 0.4 | 0.2 / 0.3 | 1.1 / 2.1 | 2.2 / 3.9 | 2.3 / 4.2 | 8% |
| webrtc-rs 0.21.1 | 1.1 / 1.4 | 0.0 / 0.1 | 0.2 / 0.3 | 5.2 / 90.1 | 17.1 / 106.5 | 212.8 / 301.9 | 731% |

### Without trickle, cold: fresh processes (10 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.1 | 1.7 / 5.7 | 0.4 / 1.2 | 104.9 / 105.1 | 115.0 / 115.7 | 115.4 / 116.1 | 115.6 / 116.4 | 342% |
| aiortc 1.15.0 | 3.5 / 3.8 | 0.1 / 0.1 | 2.3 / 2.5 | 27.5 / 27.9 | 32.7 / 32.9 | 33.8 / 34.0 | 100% |
| pion v4.2.23 | 0.4 / 0.8 | 0.8 / 1.4 | 1.5 / 2.5 | 26.0 / 70.7 | 27.0 / 71.8 | 27.5 / 72.9 | 79% |
| libdatachannel 0.24.6 | 1.5 / 11.2 | 4.7 / 8.3 | 4.6 / 8.3 | 7.3 / 11.2 | 9.9 / 13.8 | 10.3 / 14.1 | 26% |
| webrtc-rs 0.21.1 | 0.5 / 1.0 | 0.0 / 0.1 | 0.1 / 0.2 | 10.1 / 60.9 | 16.3 / 66.6 | 21.4 / 162.8 | 62% |

### Cost of a warm trial, trickle

| Library | CPU, both (ms) | Peak RSS, offerer (MB) | Loop lag p95 (ms) | Failed trials |
| --- | --- | --- | --- | --- |
| wrtc 0.0.1 | 16.9 | 54 | 1.5 | 0 |
| aiortc 1.15.0 | 11.7 | 70 | 0.7 | 0 |
| pion v4.2.23 | 95.2 | 23 | - | 0 |
| libdatachannel 0.24.6 | 4.8 | 11 | - | 0 |
| webrtc-rs 0.21.1 | 15.1 | 8 | - | 0 |

## Data channels

- Summed over the connections of a flood; % above 100 is faster.

### Throughput (Mbps)

| Flood | wrtc 0.0.1 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 57 | 88 | 481 | 438 | 1352 | 65% | 544% | 495% | 1530% |
| ordered 1 KB x10 | 16 | 92 | 1004 | 993 | 1073 | 18% | 1087% | 1075% | 1162% |
| ordered 64 KB x1 | 257 | 187 | 565 | 632 | 1050 | 138% | 302% | 338% | 562% |
| ordered 64 KB x10 | 469 | 259 | 1140 | 1172 | 1539 | 181% | 440% | 453% | 594% |
| unordered 1 KB x1 | 58 | 91 | 495 | 438 | 985 | 63% | 546% | 483% | 1086% |
| unordered 1 KB x10 | 16 | 94 | 1030 | 1037 | 820 | 17% | 1100% | 1107% | 876% |
| unordered 64 KB x1 | 764 | 186 | 540 | 657 | 462 | 410% | 290% | 353% | 248% |
| unordered 64 KB x10 | 444 | 258 | 1144 | 1150 | 747 | 172% | 443% | 445% | 289% |

### Message rate (messages/s)

| Flood | wrtc 0.0.1 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 6984 | 10791 | 58744 | 53412 | 165072 | 65% | 544% | 495% | 1530% |
| ordered 1 KB x10 | 1998 | 11271 | 122557 | 121217 | 131004 | 18% | 1087% | 1075% | 1162% |
| ordered 64 KB x1 | 490 | 356 | 1077 | 1205 | 2002 | 138% | 302% | 338% | 562% |
| ordered 64 KB x10 | 895 | 494 | 2174 | 2236 | 2936 | 181% | 440% | 453% | 594% |
| unordered 1 KB x1 | 7023 | 11073 | 60429 | 53501 | 120273 | 63% | 546% | 483% | 1086% |
| unordered 1 KB x10 | 1979 | 11436 | 125752 | 126613 | 100149 | 17% | 1100% | 1107% | 876% |
| unordered 64 KB x1 | 1457 | 355 | 1029 | 1254 | 881 | 410% | 290% | 353% | 248% |
| unordered 64 KB x10 | 848 | 492 | 2183 | 2193 | 1424 | 172% | 443% | 445% | 289% |

### CPU per MB delivered, both processes (ms)

- % below 100 is cheaper.

| Flood | wrtc 0.0.1 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 256 | 132 | 85 | 69 | 12 | 194% | 65% | 53% | 9% |
| ordered 1 KB x10 | 856 | 133 | 56 | 56 | 38 | 643% | 42% | 42% | 28% |
| ordered 64 KB x1 | 22 | 79 | 72 | 43 | 12 | 29% | 91% | 55% | 15% |
| ordered 64 KB x10 | 39 | 80 | 49 | 45 | 30 | 48% | 61% | 56% | 38% |
| unordered 1 KB x1 | 256 | 130 | 85 | 71 | 17 | 197% | 65% | 54% | 13% |
| unordered 1 KB x10 | 855 | 130 | 55 | 55 | 58 | 660% | 43% | 42% | 45% |
| unordered 64 KB x1 | 23 | 76 | 76 | 39 | 24 | 30% | 100% | 52% | 31% |
| unordered 64 KB x10 | 41 | 86 | 48 | 46 | 67 | 47% | 56% | 54% | 78% |

### Round trip of 1 KB messages at 100 a second

| Library | RTT p50 / p95 (ms) | Lost | p50, % of aiortc |
| --- | --- | --- | --- |
| wrtc 0.0.1 | 1.4 / 1.9 | 0 | 138% |
| aiortc 1.15.0 | 1.0 / 1.4 | 0 | 100% |
| pion v4.2.23 | 0.4 / 0.7 | 0 | 44% |
| libdatachannel 0.24.6 | 0.4 / 0.6 | 0 | 37% |
| webrtc-rs 0.21.1 | 0.5 / 1.2 | 0 | 45% |

## Memory

- RSS of both processes after a garbage collection.
- Created: not negotiated. Data channel: open. Audio: plus a 48 kHz tone.

### Per connection

- Baseline: the library started. KB: the slope over the connection counts.

| Library | Baseline (MB) | Created (KB) | Data channel (KB) | Audio (KB) | Created, % of aiortc | Data channel, % of aiortc | Audio, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.1 | 91 | 144 | 1109 | 8325 | 329% | 226% | 626% |
| aiortc 1.15.0 | 127 | 44 | 492 | 1331 | 100% | 100% | 100% |
| pion v4.2.23 | 28 | 94 | 2927 | - | 214% | 596% | - |
| libdatachannel 0.24.6 | 5 | 23 | 772 | - | 52% | 157% | - |
| webrtc-rs 0.21.1 | 6 | 237 | 542 | - | 542% | 110% | - |

### Kept after closing every connection (MB over the baseline)

| Library | Created | Data channel | Audio |
| --- | --- | --- | --- |
| wrtc 0.0.1 | 37.9 | 244.1 | 1910.2 |
| aiortc 1.15.0 | 14.2 | 108.2 | 229.8 |
| pion v4.2.23 | 22.5 | 731.0 | - |
| libdatachannel 0.24.6 | 14.0 | 169.5 | - |
| webrtc-rs 0.21.1 | 52.9 | 117.4 | - |

### RSS of both processes by connections (MB)

| Library | State | 1 | 10 | 50 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.1 | created | 100 | 101 | 107 | 114 | 128 |
| wrtc 0.0.1 | datachannel | 104 | 113 | 158 | 218 | 323 |
| wrtc 0.0.1 | audio | 107 | 126 | 312 | 652 | 1762 |
| aiortc 1.15.0 | created | 132 | 132 | 134 | 136 | 141 |
| aiortc 1.15.0 | datachannel | 135 | 140 | 160 | 184 | 233 |
| aiortc 1.15.0 | audio | 138 | 151 | 206 | 276 | 403 |
| pion v4.2.23 | created | 31 | 32 | 39 | 42 | 50 |
| pion v4.2.23 | datachannel | 42 | 64 | 148 | 277 | 629 |
| libdatachannel 0.24.6 | created | 14 | 15 | 16 | 17 | 19 |
| libdatachannel 0.24.6 | datachannel | 19 | 28 | 59 | 97 | 173 |
| webrtc-rs 0.21.1 | created | 10 | 14 | 24 | 36 | 59 |
| webrtc-rs 0.21.1 | datachannel | 15 | 21 | 43 | 70 | 123 |

### Most connections

- Steps of 10 until setup fails, its p95 > 5 s, RSS > 2 GB or free memory < 1.5 GB.

| Library | Last good | Stopped by | RSS at the last step (MB) | Setup p95 at the last step (ms) |
| --- | --- | --- | --- | --- |
| wrtc 0.0.1 | 200 | setup p95 over 5 s | 375 | 5147.9 |
| aiortc 1.15.0 | 1100 | setup failed: aiortc: no dc_open in 15.0 s | 673 | 77.0 |
| pion v4.2.23 | 100 | setup failed: pion: no dc_open in 15.0 s | 299 | 677.6 |
| libdatachannel 0.24.6 | 2000 | reached 2000 connections | 1547 | 209.2 |
| webrtc-rs 0.21.1 | 2000 | reached 2000 connections | 1083 | 737.0 |

## Media

- Pion is the peer. CPU of the measured process; % below 100 is cheaper.

### Video receive

- ffmpeg: decoding the same file on one thread, for reference.

| Case | ffmpeg CPU/frame (ms) | wrtc decoder | wrtc fps | wrtc kbps | wrtc CPU/frame (ms) | aiortc decoder | aiortc fps | aiortc kbps | aiortc CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VP8 720p30 2.5 Mbps | 1.1 | libvpx | 29.9 | 2392 | 5.9 | libvpx | 30.0 | 2391 | 5.9 | 100% |
| VP8 1080p30 5 Mbps | 2.3 | libvpx | 29.9 | 4796 | 8.7 | libvpx | 30.0 | 4793 | 9.2 | 95% |
| VP8 1080p60 8 Mbps | 2.1 | libvpx | 60.0 | 7656 | 6.2 | libvpx | 60.0 | 7658 | 6.3 | 98% |
| VP8 2160p30 20 Mbps | 7.8 | libvpx | 29.9 | 19245 | 12.8 | libvpx | 29.5 | 19212 | 14.5 | 88% |
| H264 720p30 2.5 Mbps | 0.6 | VideoToolbox | 30.0 | 2477 | 5.1 | FFmpeg h264 | 30.0 | 2475 | 4.9 | 104% |
| H264 1080p30 5 Mbps | 1.3 | VideoToolbox | 30.0 | 4970 | 6.5 | FFmpeg h264 | 30.0 | 4943 | 7.3 | 90% |
| H264 1080p60 8 Mbps | 1.4 | VideoToolbox | 60.0 | 7989 | 4.6 | FFmpeg h264 | 60.0 | 7992 | 5.4 | 85% |
| H264 2160p30 20 Mbps | 5.3 | VideoToolbox | 29.9 | 20069 | 11.6 | FFmpeg h264 | 0.0 | 19982 | - | - |
| H264-High 720p30 2.5 Mbps | 1.1 | VideoToolbox | 30.0 | 2482 | 5.2 | - | - | - | - | - |
| H264-High 1080p30 5 Mbps | 2.3 | VideoToolbox | 30.0 | 4929 | 6.5 | - | - | - | - | - |
| H264-High 1080p60 8 Mbps | 2.2 | VideoToolbox | 60.0 | 8046 | 4.6 | - | - | - | - | - |
| H264-High 2160p30 20 Mbps | 9.3 | VideoToolbox | 29.9 | 19889 | 11.5 | - | - | - | - | - |

### Video send

- Caps lowered to aiortc's maximum (1.5 Mbps VP8, 3 Mbps H.264); read CPU with fps and kbps.

| Case | wrtc encoder | wrtc fps | wrtc kbps | wrtc CPU/frame (ms) | aiortc encoder | aiortc fps | aiortc kbps | aiortc CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H264 720p30 2.5 Mbps | VideoToolbox | 30.0 | 2264 | 3.0 | libx264 | 30.0 | 2499 | 29.3 | 10% |
| VP8 720p30 1.5 Mbps | libvpx | 30.0 | 1332 | 12.5 | libvpx | 30.0 | 1509 | 11.8 | 106% |
| VP8 1080p30 1.5 Mbps | libvpx | 15.8 | 1102 | 25.5 | libvpx | 30.0 | 1787 | 19.2 | 133% |
| VP8 1080p60 1.5 Mbps | libvpx | 9.1 | 750 | 34.4 | libvpx | 60.0 | 3611 | 12.4 | 277% |
| VP8 2160p30 1.5 Mbps | libvpx | 3.1 | 884 | 96.4 | libvpx | 30.0 | 7482 | 34.4 | 280% |
| H264 1080p30 3 Mbps | VideoToolbox | 30.0 | 2696 | 3.6 | libx264 | 30.1 | 3031 | 35.2 | 10% |
| H264 1080p60 3 Mbps | VideoToolbox | 60.0 | 2601 | 2.8 | libx264 | 60.0 | 6003 | 27.4 | 10% |
| H264 2160p30 3 Mbps | VideoToolbox | 18.8 | 2803 | 7.8 | libx264 | 30.0 | 3001 | 63.7 | 12% |

### Video call

- Latency: a frame written to read. Each library sets its own bitrate: read CPU with kbps.

| Case | wrtc decoder | wrtc fps | wrtc kbps | wrtc latency p50 / p95 (ms) | wrtc receiver / sender CPU/frame (ms) | aiortc decoder | aiortc fps | aiortc kbps | aiortc latency p50 / p95 (ms) | aiortc receiver / sender CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VP8 720p30 2.5 Mbps | libvpx | 30.0 | 2506 | 22.3 / 23.8 | 5.2 / 10.2 | libvpx | 30.1 | 1466 | 42.6 / 44.8 | 3.9 / 10.0 | 131% |
| VP8 1080p30 5 Mbps | libvpx | 30.0 | 5003 | 22.5 / 24.1 | 5.6 / 12.9 | libvpx | 30.0 | 1789 | 43.3 / 45.2 | 4.2 / 14.0 | 134% |
| H264 720p30 2.5 Mbps | VideoToolbox | 30.0 | 2511 | 24.5 / 26.6 | 5.6 / 3.1 | FFmpeg h264 | 30.0 | 2386 | 43.0 / 44.8 | 3.1 / 26.9 | 179% |
| H264 1080p30 5 Mbps | VideoToolbox | 30.0 | 4993 | 29.8 / 31.6 | 6.7 / 3.4 | FFmpeg h264 | 30.0 | 2304 | 43.6 / 45.3 | 3.9 / 33.6 | 169% |
| VP9 720p30 2.5 Mbps | libvpx | 30.0 | 2511 | 21.3 / 23.1 | 5.6 / 16.5 | - | - | - | - | - | - |
| VP9 1080p30 5 Mbps | libvpx | 30.0 | 5006 | 22.3 / 24.0 | 8.7 / 18.3 | - | - | - | - | - | - |
| AV1 720p30 2.5 Mbps | dav1d | 30.0 | 2501 | 24.7 / 27.3 | 6.5 / 18.3 | - | - | - | - | - | - |
| AV1 1080p30 5 Mbps | dav1d | 30.1 | 4996 | 25.0 / 27.4 | 6.3 / 20.3 | - | - | - | - | - | - |

### Audio receive

- One Opus stream a connection; delivered: audio read over real time.

| Case | wrtc CPU per stream (% of a core) | wrtc delivered | wrtc loop lag p95 (ms) | aiortc CPU per stream (% of a core) | aiortc delivered | aiortc loop lag p95 (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 stream | 6.68 | 100% | 1.4 | 6.80 | 100% | 1.4 | 98% |
| 10 streams | 4.65 | 100% | 1.4 | 4.09 | 100% | 1.4 | 114% |
| 50 streams | 1.62 | 100% | 1.3 | 2.00 | 100% | 3.4 | 81% |

### Audio send

- One tone a connection; delivered: packets Pion got over 50 a second.

| Case | wrtc CPU per stream (% of a core) | wrtc delivered | wrtc loop lag p95 (ms) | aiortc CPU per stream (% of a core) | aiortc delivered | aiortc loop lag p95 (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 stream | 6.53 | 101% | 1.4 | 17.79 | 100% | 1.4 | 37% |
| 10 streams | 5.76 | 101% | 1.3 | 11.46 | 100% | 1.7 | 50% |
| 50 streams | 2.58 | 101% | 1.3 | 6.24 | 100% | 6.1 | 41% |

