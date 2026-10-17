# Benchmarks

Medians; % columns are of aiortc's. How: [README](README.md#method).

2026-10-17, 3 runs a case, Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.2, commit 908dd26 with uncommitted changes.

## Connection setup

- ms, p50 / p95, from `createOffer`; Create: the constructors.
- aiortc can't trickle: it connects without trickle in both.

### Trickle, warm (102 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.3 | 0.5 / 0.5 | 0.2 / 0.3 | 1.2 / 1.3 | 3.0 / 3.2 | 3.4 / 3.6 | 3.5 / 3.7 | 12% |
| aiortc 1.15.0 | 0.3 / 0.3 | 0.1 / 0.1 | 2.1 / 2.6 | 26.7 / 27.5 | 28.1 / 28.9 | 29.0 / 29.9 | 100% |
| pion v4.2.23 | 0.8 / 1.4 | 1.9 / 2.7 | 3.5 / 4.4 | 36.5 / 89.0 | 39.1 / 94.5 | 39.6 / 95.4 | 136% |
| libdatachannel 0.24.6 | 0.0 / 0.0 | 0.1 / 0.3 | 0.2 / 0.4 | 1.0 / 1.8 | 2.1 / 4.0 | 2.3 / 4.3 | 8% |
| webrtc-rs 0.21.1 | 1.2 / 1.4 | 0.1 / 0.1 | 0.3 / 0.4 | 206.0 / 225.8 | 223.1 / 426.5 | 420.6 / 822.3 | 1449% |

### Trickle, cold: fresh processes (10 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.3 | 2.3 / 4.0 | 0.3 / 0.3 | 1.3 / 1.5 | 3.7 / 4.0 | 4.3 / 4.8 | 4.3 / 4.8 | 13% |
| aiortc 1.15.0 | 3.6 / 15.8 | 0.1 / 0.1 | 2.2 / 2.6 | 27.4 / 27.5 | 32.8 / 37.8 | 33.9 / 38.7 | 100% |
| pion v4.2.23 | 0.4 / 0.8 | 0.8 / 1.6 | 1.5 / 2.8 | 18.6 / 78.7 | 20.1 / 82.7 | 20.6 / 84.2 | 60% |
| libdatachannel 0.24.6 | 1.5 / 11.5 | 4.8 / 6.2 | 4.9 / 6.2 | 7.7 / 9.2 | 10.5 / 11.7 | 10.9 / 11.9 | 32% |
| webrtc-rs 0.21.1 | 1.0 / 12.2 | 0.1 / 0.3 | 0.2 / 0.6 | 213.4 / 406.5 | 226.7 / 610.9 | 418.8 / 1012.4 | 1237% |

### Without trickle, warm (102 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.3 | 0.5 / 0.7 | 0.2 / 0.2 | 0.8 / 1.1 | 3.0 / 3.9 | 3.5 / 4.3 | 3.6 / 4.4 | 12% |
| aiortc 1.15.0 | 0.3 / 0.3 | 0.1 / 0.1 | 2.1 / 2.5 | 26.7 / 27.6 | 28.1 / 29.0 | 29.0 / 30.0 | 100% |
| pion v4.2.23 | 0.8 / 1.4 | 1.9 / 2.8 | 3.6 / 4.4 | 46.7 / 47.9 | 48.5 / 49.9 | 49.4 / 50.7 | 170% |
| libdatachannel 0.24.6 | 0.0 / 0.0 | 0.2 / 0.3 | 0.2 / 0.2 | 1.0 / 2.0 | 2.2 / 3.5 | 2.3 / 3.7 | 8% |
| webrtc-rs 0.21.1 | 1.1 / 1.3 | 0.0 / 0.1 | 0.2 / 0.2 | 5.5 / 79.9 | 15.8 / 107.9 | 212.2 / 303.6 | 730% |

### Without trickle, cold: fresh processes (10 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.3 | 2.3 / 2.4 | 0.3 / 0.3 | 1.1 / 1.1 | 4.0 / 4.4 | 4.4 / 4.9 | 4.6 / 5.0 | 13% |
| aiortc 1.15.0 | 3.5 / 3.7 | 0.1 / 0.1 | 2.2 / 2.3 | 27.4 / 27.5 | 32.7 / 33.0 | 33.7 / 34.0 | 100% |
| pion v4.2.23 | 0.4 / 3.9 | 0.7 / 4.6 | 1.2 / 8.2 | 20.9 / 36.6 | 22.3 / 37.9 | 22.7 / 38.6 | 67% |
| libdatachannel 0.24.6 | 0.8 / 1.5 | 2.7 / 5.4 | 2.6 / 5.3 | 4.3 / 8.0 | 5.8 / 10.6 | 6.1 / 11.0 | 18% |
| webrtc-rs 0.21.1 | 1.0 / 1.1 | 0.1 / 0.1 | 0.2 / 0.2 | 12.0 / 37.0 | 17.5 / 40.4 | 213.5 / 240.1 | 631% |

### Cost of a warm trial, trickle

| Library | CPU, both (ms) | Peak RSS, offerer (MB) | Loop lag p95 (ms) | Failed trials |
| --- | --- | --- | --- | --- |
| wrtc 0.0.3 | 10.8 | 55 | 0.3 | 0 |
| aiortc 1.15.0 | 11.7 | 71 | 0.8 | 0 |
| pion v4.2.23 | 98.3 | 23 | - | 0 |
| libdatachannel 0.24.6 | 4.7 | 10 | - | 0 |
| webrtc-rs 0.21.1 | 17.4 | 8 | - | 0 |

## Data channels

- Summed over the connections of a flood; % above 100 is faster.

### Throughput (Mbps)

| Flood | wrtc 0.0.3 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 758 | 90 | 517 | 478 | 684 | 844% | 575% | 532% | 762% |
| ordered 1 KB x10 | 738 | 95 | 1058 | 1039 | 1260 | 779% | 1117% | 1097% | 1330% |
| ordered 64 KB x1 | 1049 | 183 | 485 | 653 | 1618 | 573% | 265% | 357% | 885% |
| ordered 64 KB x10 | 1063 | 241 | 1135 | 1152 | 1307 | 440% | 470% | 477% | 541% |
| unordered 1 KB x1 | 821 | 89 | 464 | 472 | 1185 | 919% | 519% | 528% | 1326% |
| unordered 1 KB x10 | 755 | 95 | 1037 | 1046 | 808 | 796% | 1093% | 1103% | 852% |
| unordered 64 KB x1 | 1088 | 192 | 544 | 650 | 459 | 566% | 283% | 338% | 239% |
| unordered 64 KB x10 | 1050 | 241 | 1137 | 1164 | 720 | 435% | 471% | 482% | 298% |

### Message rate (messages/s)

| Flood | wrtc 0.0.3 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 92568 | 10964 | 63078 | 58348 | 83512 | 844% | 575% | 532% | 762% |
| ordered 1 KB x10 | 90030 | 11562 | 129161 | 126857 | 153778 | 779% | 1117% | 1097% | 1330% |
| ordered 64 KB x1 | 2000 | 349 | 926 | 1245 | 3087 | 573% | 265% | 357% | 885% |
| ordered 64 KB x10 | 2027 | 461 | 2165 | 2197 | 2492 | 440% | 470% | 477% | 541% |
| unordered 1 KB x1 | 100231 | 10904 | 56647 | 57566 | 144599 | 919% | 519% | 528% | 1326% |
| unordered 1 KB x10 | 92192 | 11578 | 126573 | 127670 | 98637 | 796% | 1093% | 1103% | 852% |
| unordered 64 KB x1 | 2075 | 367 | 1038 | 1240 | 876 | 566% | 283% | 338% | 239% |
| unordered 64 KB x10 | 2002 | 461 | 2169 | 2221 | 1374 | 435% | 471% | 482% | 298% |

### CPU per MB delivered, both processes (ms)

- % below 100 is cheaper.

| Flood | wrtc 0.0.3 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 31 | 132 | 82 | 62 | 13 | 23% | 62% | 47% | 10% |
| ordered 1 KB x10 | 31 | 127 | 54 | 52 | 34 | 25% | 43% | 41% | 27% |
| ordered 64 KB x1 | 15 | 78 | 83 | 41 | 10 | 20% | 107% | 52% | 12% |
| ordered 64 KB x10 | 15 | 85 | 51 | 46 | 31 | 18% | 60% | 54% | 37% |
| unordered 1 KB x1 | 28 | 131 | 90 | 64 | 15 | 21% | 68% | 49% | 11% |
| unordered 1 KB x10 | 31 | 126 | 56 | 49 | 53 | 24% | 44% | 38% | 42% |
| unordered 64 KB x1 | 15 | 76 | 75 | 40 | 23 | 19% | 99% | 53% | 30% |
| unordered 64 KB x10 | 15 | 86 | 50 | 46 | 66 | 18% | 58% | 54% | 76% |

### Round trip of 1 KB messages at 100 a second

| Library | RTT p50 / p95 (ms) | Lost | p50, % of aiortc |
| --- | --- | --- | --- |
| wrtc 0.0.3 | 0.7 / 1.2 | 0 | 62% |
| aiortc 1.15.0 | 1.2 / 1.7 | 0 | 100% |
| pion v4.2.23 | 0.5 / 0.9 | 0 | 46% |
| libdatachannel 0.24.6 | 0.5 / 0.7 | 0 | 39% |
| webrtc-rs 0.21.1 | 0.7 / 1.2 | 0 | 59% |

## Memory

- RSS of both processes after a garbage collection.
- Created: not negotiated. Data channel: open. Audio: plus a 48 kHz tone.

### Per connection

- Baseline: the library started. KB: the slope over the connection counts.

| Library | Baseline (MB) | Created (KB) | Data channel (KB) | Audio (KB) | Created, % of aiortc | Data channel, % of aiortc | Audio, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.3 | 92 | 146 | 814 | 1701 | 335% | 166% | 129% |
| aiortc 1.15.0 | 128 | 44 | 491 | 1322 | 100% | 100% | 100% |
| pion v4.2.23 | 28 | 94 | 3323 | 2795 | 216% | 677% | 212% |
| libdatachannel 0.24.6 | 5 | 22 | 771 | - | 51% | 157% | - |
| webrtc-rs 0.21.1 | 6 | 238 | 542 | - | 547% | 110% | - |

### Kept after closing every connection (MB over the baseline)

| Library | Created | Data channel | Audio |
| --- | --- | --- | --- |
| wrtc 0.0.3 | 36.7 | 195.1 | 376.1 |
| aiortc 1.15.0 | 14.2 | 108.3 | 227.9 |
| pion v4.2.23 | 22.6 | 680.3 | 594.2 |
| libdatachannel 0.24.6 | 13.8 | 168.9 | - |
| webrtc-rs 0.21.1 | 52.9 | 117.3 | - |

### RSS of both processes by connections (MB)

| Library | State | 1 | 10 | 50 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.3 | created | 99 | 100 | 106 | 113 | 128 |
| wrtc 0.0.3 | datachannel | 103 | 111 | 145 | 185 | 266 |
| wrtc 0.0.3 | audio | 105 | 123 | 192 | 276 | 445 |
| aiortc 1.15.0 | created | 134 | 135 | 136 | 138 | 143 |
| aiortc 1.15.0 | datachannel | 137 | 142 | 162 | 186 | 235 |
| aiortc 1.15.0 | audio | 141 | 154 | 208 | 277 | 403 |
| pion v4.2.23 | created | 30 | 33 | 38 | 43 | 50 |
| pion v4.2.23 | datachannel | 41 | 61 | 175 | 302 | 707 |
| pion v4.2.23 | audio | 42 | 63 | 150 | 291 | 597 |
| libdatachannel 0.24.6 | created | 14 | 14 | 16 | 17 | 18 |
| libdatachannel 0.24.6 | datachannel | 18 | 27 | 58 | 96 | 173 |
| webrtc-rs 0.21.1 | created | 10 | 14 | 24 | 36 | 58 |
| webrtc-rs 0.21.1 | datachannel | 15 | 21 | 43 | 70 | 123 |

### Most connections

- Steps of 10 until setup fails, its p95 > 5 s, RSS > 2 GB or free memory < 1.5 GB.

| Library | Last good | Stopped by | RSS at the last step (MB) | Setup p95 at the last step (ms) |
| --- | --- | --- | --- | --- |
| wrtc 0.0.3 | 1450 | setup failed: wrtc: no dc_open in 15.0 s | 1156 | 417.0 |
| aiortc 1.15.0 | 1100 | setup failed: aiortc: no dc_open in 15.0 s | 676 | 77.8 |
| pion v4.2.23 | 300 | setup failed: pion: no dc_open in 15.0 s | 896 | 4251.7 |
| libdatachannel 0.24.6 | 2000 | reached 2000 connections | 1546 | 221.0 |
| webrtc-rs 0.21.1 | 2000 | reached 2000 connections | 1084 | 700.6 |

## Media

- Pion is the peer. CPU of the measured process; % below 100 is cheaper.

### Video receive

- ffmpeg: decoding the same file on one thread, for reference.

| Case | ffmpeg CPU/frame (ms) | wrtc decoder | wrtc fps | wrtc kbps | wrtc CPU/frame (ms) | aiortc decoder | aiortc fps | aiortc kbps | aiortc CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VP8 720p30 2.5 Mbps | 1.1 | libvpx | 29.9 | 2387 | 6.9 | libvpx | 30.0 | 2391 | 7.2 | 96% |
| VP8 1080p30 5 Mbps | 2.3 | libvpx | 30.0 | 4786 | 9.7 | libvpx | 30.0 | 4793 | 10.5 | 92% |
| VP8 1080p60 8 Mbps | 2.1 | libvpx | 59.9 | 7654 | 6.9 | libvpx | 60.0 | 7669 | 7.2 | 97% |
| VP8 2160p30 20 Mbps | 7.7 | libvpx | 30.0 | 19193 | 12.7 | libvpx | 29.5 | 19217 | 14.8 | 86% |
| H264 720p30 2.5 Mbps | 0.7 | VideoToolbox | 30.0 | 2472 | 4.3 | FFmpeg h264 | 30.0 | 2475 | 6.2 | 71% |
| H264 1080p30 5 Mbps | 1.3 | VideoToolbox | 30.0 | 4957 | 6.1 | FFmpeg h264 | 30.0 | 4937 | 8.4 | 72% |
| H264 1080p60 8 Mbps | 1.4 | VideoToolbox | 59.9 | 7984 | 4.6 | FFmpeg h264 | 60.0 | 7985 | 6.2 | 74% |
| H264 2160p30 20 Mbps | 5.3 | VideoToolbox | 30.0 | 20020 | 9.9 | FFmpeg h264 | 0.0 | 20041 | - | - |
| H264-High 720p30 2.5 Mbps | 1.1 | VideoToolbox | 30.0 | 2477 | 4.3 | - | - | - | - | - |
| H264-High 1080p30 5 Mbps | 2.3 | VideoToolbox | 30.0 | 4917 | 6.2 | - | - | - | - | - |
| H264-High 1080p60 8 Mbps | 2.2 | VideoToolbox | 59.9 | 8042 | 4.5 | - | - | - | - | - |
| H264-High 2160p30 20 Mbps | 9.3 | VideoToolbox | 30.0 | 19842 | 9.8 | - | - | - | - | - |

### Video send

- Caps lowered to aiortc's maximum (1.5 Mbps VP8, 3 Mbps H.264); read CPU with fps and kbps.

| Case | wrtc encoder | wrtc fps | wrtc kbps | wrtc CPU/frame (ms) | aiortc encoder | aiortc fps | aiortc kbps | aiortc CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H264 720p30 2.5 Mbps | VideoToolbox | 30.0 | 2271 | 3.4 | libx264 | 30.0 | 2509 | 33.4 | 10% |
| VP8 720p30 1.5 Mbps | libvpx | 30.0 | 1330 | 14.8 | libvpx | 30.0 | 1509 | 13.9 | 107% |
| VP8 1080p30 1.5 Mbps | libvpx | 15.7 | 1084 | 29.5 | libvpx | 30.0 | 1787 | 21.9 | 135% |
| VP8 1080p60 1.5 Mbps | libvpx | 9.0 | 756 | 39.0 | libvpx | 60.0 | 3611 | 13.4 | 290% |
| VP8 2160p30 1.5 Mbps | libvpx | 3.2 | 894 | 102.9 | libvpx | 30.0 | 7482 | 34.5 | 298% |
| H264 1080p30 3 Mbps | VideoToolbox | 30.0 | 2713 | 4.1 | libx264 | 30.1 | 3031 | 38.2 | 11% |
| H264 1080p60 3 Mbps | VideoToolbox | 60.0 | 2609 | 3.1 | libx264 | 60.0 | 6003 | 27.5 | 11% |
| H264 2160p30 3 Mbps | VideoToolbox | 18.2 | 2757 | 7.7 | libx264 | 30.0 | 3001 | 64.4 | 12% |

### Video call

- Latency: a frame written to read. Each library sets its own bitrate: read CPU with kbps.

| Case | wrtc decoder | wrtc fps | wrtc kbps | wrtc latency p50 / p95 (ms) | wrtc receiver / sender CPU/frame (ms) | aiortc decoder | aiortc fps | aiortc kbps | aiortc latency p50 / p95 (ms) | aiortc receiver / sender CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VP8 720p30 2.5 Mbps | libvpx | 30.1 | 2500 | 22.4 / 24.9 | 5.8 / 11.4 | libvpx | 30.1 | 1466 | 43.5 / 45.4 | 4.5 / 11.5 | 130% |
| VP8 1080p30 5 Mbps | libvpx | 30.0 | 5006 | 23.1 / 25.2 | 6.0 / 14.0 | libvpx | 30.1 | 1789 | 44.4 / 46.0 | 4.8 / 15.9 | 126% |
| H264 720p30 2.5 Mbps | VideoToolbox | 30.0 | 2524 | 23.1 / 25.7 | 5.1 / 3.8 | FFmpeg h264 | 30.1 | 2387 | 44.4 / 45.7 | 3.5 / 30.7 | 145% |
| H264 1080p30 5 Mbps | VideoToolbox | 30.1 | 5008 | 28.4 / 31.9 | 6.3 / 4.2 | FFmpeg h264 | 30.0 | 2248 | 44.4 / 45.6 | 4.2 / 37.1 | 149% |
| VP9 720p30 2.5 Mbps | libvpx | 30.1 | 2502 | 21.1 / 23.2 | 6.1 / 19.1 | - | - | - | - | - | - |
| VP9 1080p30 5 Mbps | libvpx | 30.0 | 5012 | 24.3 / 26.6 | 9.9 / 21.0 | - | - | - | - | - | - |
| AV1 720p30 2.5 Mbps | dav1d | 30.0 | 2495 | 26.2 / 28.5 | 7.2 / 21.1 | - | - | - | - | - | - |
| AV1 1080p30 5 Mbps | dav1d | 30.0 | 4988 | 25.5 / 27.5 | 6.2 / 20.6 | - | - | - | - | - | - |

### Audio receive

- One Opus stream a connection; delivered: audio read over real time.

| Case | wrtc CPU per stream (% of a core) | wrtc delivered | wrtc loop lag p95 (ms) | aiortc CPU per stream (% of a core) | aiortc delivered | aiortc loop lag p95 (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 stream | 6.47 | 100% | 1.4 | 9.29 | 100% | 1.4 | 70% |
| 10 streams | 2.89 | 100% | 1.4 | 4.75 | 100% | 1.5 | 61% |
| 50 streams | 1.10 | 100% | 1.3 | 2.14 | 100% | 3.8 | 51% |

### Audio send

- One tone a connection; delivered: packets Pion got over 50 a second.

| Case | wrtc CPU per stream (% of a core) | wrtc delivered | wrtc loop lag p95 (ms) | aiortc CPU per stream (% of a core) | aiortc delivered | aiortc loop lag p95 (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 stream | 7.49 | 101% | 1.4 | 21.55 | 100% | 1.4 | 35% |
| 10 streams | 3.24 | 101% | 1.4 | 12.78 | 100% | 1.9 | 25% |
| 50 streams | 1.52 | 101% | 2.0 | 6.19 | 100% | 5.2 | 25% |

