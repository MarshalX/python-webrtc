# Benchmarks

Medians; % columns are of aiortc's. How: [README](README.md#method).

| Suite | Libraries | Date | Runs | Machine | Commit |
| --- | --- | --- | --- | --- | --- |
| setup | aiortc, pion, libdatachannel, webrtc-rs | 2026-10-13 | 3 | Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1 | 3ed4d51 with uncommitted changes |
| setup | wrtc | 2026-10-14 | 3 | Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1 | ab9ed88 with uncommitted changes |
| datachannel | aiortc, pion, libdatachannel, webrtc-rs | 2026-10-13 | 3 | Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1 | 3ed4d51 with uncommitted changes |
| datachannel | wrtc | 2026-10-13 | 3 | Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1 | ab9ed88 with uncommitted changes |
| memory | wrtc, aiortc, pion, libdatachannel, webrtc-rs | 2026-10-13 | 3 | Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1 | 3ed4d51 with uncommitted changes |
| media | aiortc | 2026-10-13 | 3 | Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1 | 3ed4d51 with uncommitted changes |
| media | wrtc | 2026-10-13 | 3 | Apple M1, 8 cores, Darwin 27.0.0 (arm64), Python 3.13.13, go1.27.1 | ab9ed88 with uncommitted changes |

## Connection setup

- ms, p50 / p95, from `createOffer`; Create: the constructors.
- aiortc can't trickle: it connects without trickle in both.

### Trickle, warm (102 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.2 | 0.6 / 0.6 | 0.2 / 0.3 | 1.3 / 1.5 | 2.7 / 3.7 | 4.1 / 4.6 | 4.3 / 4.8 | 15% |
| aiortc 1.15.0 | 0.3 / 0.3 | 0.1 / 0.1 | 2.1 / 2.6 | 26.8 / 27.6 | 28.2 / 28.9 | 29.1 / 30.0 | 100% |
| pion v4.2.23 | 0.8 / 1.2 | 1.9 / 2.7 | 3.7 / 4.6 | 37.5 / 117.9 | 40.3 / 121.1 | 40.9 / 122.0 | 140% |
| libdatachannel 0.24.6 | 0.0 / 0.0 | 0.2 / 0.2 | 0.2 / 0.3 | 1.0 / 1.4 | 2.1 / 2.6 | 2.2 / 2.8 | 8% |
| webrtc-rs 0.21.1 | 1.2 / 1.5 | 0.0 / 0.1 | 0.3 / 0.3 | 206.0 / 280.8 | 223.3 / 422.8 | 417.9 / 821.6 | 1437% |

### Trickle, cold: fresh processes (10 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.2 | 1.7 / 3.9 | 0.3 / 0.3 | 1.6 / 1.9 | 4.2 / 4.7 | 4.9 / 5.3 | 5.1 / 5.7 | 15% |
| aiortc 1.15.0 | 3.5 / 17.4 | 0.1 / 0.1 | 2.3 / 2.6 | 27.5 / 27.6 | 32.8 / 38.3 | 33.9 / 39.2 | 100% |
| pion v4.2.23 | 0.7 / 3.4 | 1.2 / 3.5 | 2.2 / 6.8 | 25.3 / 37.5 | 27.3 / 39.2 | 27.7 / 39.7 | 82% |
| libdatachannel 0.24.6 | 0.8 / 1.6 | 2.6 / 4.8 | 2.7 / 4.8 | 4.2 / 7.3 | 5.9 / 10.0 | 6.1 / 10.3 | 18% |
| webrtc-rs 0.21.1 | 0.5 / 1.1 | 0.0 / 0.1 | 0.1 / 0.3 | 205.9 / 220.6 | 242.3 / 421.6 | 423.0 / 823.9 | 1244% |

### Without trickle, warm (102 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.2 | 0.6 / 0.7 | 0.2 / 0.2 | 1.1 / 1.3 | 3.9 / 4.7 | 5.1 / 5.8 | 5.2 / 5.9 | 18% |
| aiortc 1.15.0 | 0.3 / 0.3 | 0.1 / 0.1 | 2.1 / 2.6 | 26.8 / 27.4 | 28.2 / 28.8 | 29.1 / 31.1 | 100% |
| pion v4.2.23 | 0.8 / 1.4 | 1.9 / 2.7 | 3.7 / 4.6 | 49.7 / 51.1 | 51.5 / 52.9 | 52.2 / 53.8 | 179% |
| libdatachannel 0.24.6 | 0.0 / 0.0 | 0.2 / 0.4 | 0.2 / 0.3 | 1.1 / 2.9 | 2.3 / 5.0 | 2.4 / 5.4 | 8% |
| webrtc-rs 0.21.1 | 0.9 / 1.3 | 0.0 / 0.1 | 0.1 / 0.2 | 5.2 / 86.0 | 15.7 / 104.6 | 211.5 / 300.4 | 724% |

### Without trickle, cold: fresh processes (10 trials)

| Library | Create | Offer created | Gathered | ICE connected | Connected | Data channel open | Open, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.2 | 1.7 / 2.2 | 0.3 / 0.3 | 1.5 / 1.7 | 5.0 / 5.7 | 6.1 / 6.9 | 6.3 / 7.0 | 19% |
| aiortc 1.15.0 | 3.5 / 3.6 | 0.1 / 0.1 | 2.3 / 2.3 | 27.3 / 27.6 | 32.5 / 33.0 | 33.5 / 34.0 | 100% |
| pion v4.2.23 | 0.4 / 0.8 | 0.8 / 1.5 | 1.3 / 2.5 | 25.7 / 35.1 | 26.6 / 36.3 | 27.3 / 36.9 | 80% |
| libdatachannel 0.24.6 | 0.8 / 1.6 | 2.7 / 5.2 | 2.7 / 5.2 | 4.3 / 7.8 | 5.9 / 10.4 | 6.1 / 10.7 | 18% |
| webrtc-rs 0.21.1 | 0.5 / 1.2 | 0.0 / 0.1 | 0.1 / 0.2 | 10.4 / 52.7 | 16.7 / 56.7 | 60.6 / 239.8 | 129% |

### Cost of a warm trial, trickle

| Library | CPU, both (ms) | Peak RSS, offerer (MB) | Loop lag p95 (ms) | Failed trials |
| --- | --- | --- | --- | --- |
| wrtc 0.0.2 | 14.5 | 55 | 0.5 | 0 |
| aiortc 1.15.0 | 11.6 | 70 | 0.7 | 0 |
| pion v4.2.23 | 96.2 | 23 | - | 0 |
| libdatachannel 0.24.6 | 4.3 | 11 | - | 0 |
| webrtc-rs 0.21.1 | 14.7 | 8 | - | 0 |

## Data channels

- Summed over the connections of a flood; % above 100 is faster.

### Throughput (Mbps)

| Flood | wrtc 0.0.2 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 812 | 91 | 490 | 448 | 1187 | 894% | 539% | 494% | 1307% |
| ordered 1 KB x10 | 745 | 93 | 990 | 1026 | 1261 | 801% | 1064% | 1103% | 1355% |
| ordered 64 KB x1 | 1084 | 197 | 532 | 622 | 705 | 551% | 271% | 317% | 358% |
| ordered 64 KB x10 | 1110 | 173 | 1135 | 1158 | 1429 | 642% | 657% | 670% | 827% |
| unordered 1 KB x1 | 759 | 89 | 492 | 441 | 818 | 853% | 553% | 495% | 920% |
| unordered 1 KB x10 | 727 | 93 | 1023 | 1035 | 721 | 780% | 1097% | 1111% | 774% |
| unordered 64 KB x1 | 1100 | 176 | 533 | 625 | 839 | 626% | 303% | 356% | 477% |
| unordered 64 KB x10 | 1105 | 245 | 1143 | 1194 | 680 | 451% | 466% | 487% | 277% |

### Message rate (messages/s)

| Flood | wrtc 0.0.2 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 99113 | 11086 | 59782 | 54721 | 144848 | 894% | 539% | 494% | 1307% |
| ordered 1 KB x10 | 90983 | 11361 | 120850 | 125260 | 153925 | 801% | 1064% | 1103% | 1355% |
| ordered 64 KB x1 | 2067 | 375 | 1015 | 1187 | 1344 | 551% | 271% | 317% | 358% |
| ordered 64 KB x10 | 2118 | 330 | 2165 | 2210 | 2725 | 642% | 657% | 670% | 827% |
| unordered 1 KB x1 | 92678 | 10864 | 60066 | 53800 | 99905 | 853% | 553% | 495% | 920% |
| unordered 1 KB x10 | 88691 | 11377 | 124819 | 126374 | 88016 | 780% | 1097% | 1111% | 774% |
| unordered 64 KB x1 | 2098 | 335 | 1017 | 1192 | 1600 | 626% | 303% | 356% | 477% |
| unordered 64 KB x10 | 2107 | 468 | 2179 | 2277 | 1298 | 451% | 466% | 487% | 277% |

### CPU per MB delivered, both processes (ms)

- % below 100 is cheaper.

| Flood | wrtc 0.0.2 | aiortc 1.15.0 | pion v4.2.23 | libdatachannel 0.24.6 | webrtc-rs 0.21.1 | wrtc, % of aiortc | pion, % of aiortc | libdatachannel, % of aiortc | webrtc-rs, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ordered 1 KB x1 | 30 | 130 | 85 | 67 | 12 | 23% | 65% | 52% | 9% |
| ordered 1 KB x10 | 32 | 131 | 55 | 53 | 34 | 24% | 42% | 41% | 26% |
| ordered 64 KB x1 | 15 | 74 | 74 | 44 | 10 | 21% | 101% | 60% | 14% |
| ordered 64 KB x10 | 15 | 81 | 51 | 46 | 31 | 18% | 62% | 56% | 38% |
| unordered 1 KB x1 | 32 | 132 | 86 | 69 | 14 | 24% | 65% | 53% | 11% |
| unordered 1 KB x10 | 33 | 130 | 54 | 53 | 59 | 25% | 41% | 40% | 45% |
| unordered 64 KB x1 | 15 | 80 | 75 | 43 | 12 | 19% | 94% | 53% | 15% |
| unordered 64 KB x10 | 15 | 92 | 50 | 44 | 72 | 16% | 54% | 48% | 78% |

### Round trip of 1 KB messages at 100 a second

| Library | RTT p50 / p95 (ms) | Lost | p50, % of aiortc |
| --- | --- | --- | --- |
| wrtc 0.0.2 | 0.7 / 1.3 | 0 | 73% |
| aiortc 1.15.0 | 1.0 / 1.3 | 0 | 100% |
| pion v4.2.23 | 0.4 / 0.7 | 0 | 44% |
| libdatachannel 0.24.6 | 0.4 / 0.5 | 0 | 38% |
| webrtc-rs 0.21.1 | 0.6 / 1.0 | 0 | 57% |

## Memory

- RSS of both processes after a garbage collection.
- Created: not negotiated. Data channel: open. Audio: plus a 48 kHz tone.

### Per connection

- Baseline: the library started. KB: the slope over the connection counts.

| Library | Baseline (MB) | Created (KB) | Data channel (KB) | Audio (KB) | Created, % of aiortc | Data channel, % of aiortc | Audio, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.2 | 91 | 144 | 805 | 1674 | 328% | 164% | 126% |
| aiortc 1.15.0 | 126 | 44 | 492 | 1325 | 100% | 100% | 100% |
| pion v4.2.23 | 28 | 94 | 2902 | 2715 | 214% | 590% | 205% |
| libdatachannel 0.24.6 | 5 | 23 | 772 | - | 52% | 157% | - |
| webrtc-rs 0.21.1 | 6 | 238 | 542 | - | 543% | 110% | - |

### Kept after closing every connection (MB over the baseline)

| Library | Created | Data channel | Audio |
| --- | --- | --- | --- |
| wrtc 0.0.2 | 37.7 | 193.9 | 369.6 |
| aiortc 1.15.0 | 14.1 | 108.2 | 228.4 |
| pion v4.2.23 | 22.3 | 592.1 | 575.5 |
| libdatachannel 0.24.6 | 14.1 | 169.6 | - |
| webrtc-rs 0.21.1 | 52.8 | 117.3 | - |

### RSS of both processes by connections (MB)

| Library | State | 1 | 10 | 50 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- |
| wrtc 0.0.2 | created | 100 | 101 | 107 | 114 | 128 |
| wrtc 0.0.2 | datachannel | 104 | 112 | 144 | 184 | 264 |
| wrtc 0.0.2 | audio | 106 | 123 | 189 | 272 | 440 |
| aiortc 1.15.0 | created | 132 | 132 | 134 | 136 | 140 |
| aiortc 1.15.0 | datachannel | 135 | 140 | 160 | 184 | 233 |
| aiortc 1.15.0 | audio | 138 | 151 | 206 | 276 | 402 |
| pion v4.2.23 | created | 31 | 33 | 39 | 42 | 50 |
| pion v4.2.23 | datachannel | 42 | 63 | 144 | 286 | 619 |
| pion v4.2.23 | audio | 42 | 63 | 156 | 284 | 583 |
| libdatachannel 0.24.6 | created | 14 | 15 | 16 | 17 | 19 |
| libdatachannel 0.24.6 | datachannel | 19 | 28 | 58 | 97 | 173 |
| webrtc-rs 0.21.1 | created | 10 | 14 | 24 | 36 | 59 |
| webrtc-rs 0.21.1 | datachannel | 15 | 21 | 43 | 69 | 123 |

### Most connections

- Steps of 10 until setup fails, its p95 > 5 s, RSS > 2 GB or free memory < 1.5 GB.

| Library | Last good | Stopped by | RSS at the last step (MB) | Setup p95 at the last step (ms) |
| --- | --- | --- | --- | --- |
| wrtc 0.0.2 | 1450 | setup failed: wrtc: no dc_open in 15.0 s | 1131 | 455.1 |
| aiortc 1.15.0 | 1100 | setup failed: aiortc: no dc_open in 15.0 s | 674 | 74.6 |
| pion v4.2.23 | 200 | setup failed: pion: no dc_open in 15.0 s | 490 | 1685.5 |
| libdatachannel 0.24.6 | 2000 | reached 2000 connections | 1526 | 161.7 |
| webrtc-rs 0.21.1 | 2000 | reached 2000 connections | 997 | 673.3 |

## Media

- Pion is the peer. CPU of the measured process; % below 100 is cheaper.

### Video receive

- ffmpeg: decoding the same file on one thread, for reference.

| Case | ffmpeg CPU/frame (ms) | wrtc decoder | wrtc fps | wrtc kbps | wrtc CPU/frame (ms) | aiortc decoder | aiortc fps | aiortc kbps | aiortc CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VP8 720p30 2.5 Mbps | 1.1 | libvpx | 29.9 | 2392 | 5.6 | libvpx | 30.0 | 2391 | 5.9 | 94% |
| VP8 1080p30 5 Mbps | 2.3 | libvpx | 30.0 | 4795 | 8.5 | libvpx | 30.0 | 4793 | 9.2 | 92% |
| VP8 1080p60 8 Mbps | 2.1 | libvpx | 60.0 | 7654 | 6.0 | libvpx | 60.0 | 7651 | 6.0 | 101% |
| VP8 2160p30 20 Mbps | 7.8 | libvpx | 29.9 | 19177 | 12.3 | libvpx | 29.5 | 19220 | 14.5 | 85% |
| H264 720p30 2.5 Mbps | 0.7 | VideoToolbox | 30.0 | 2476 | 4.9 | FFmpeg h264 | 30.1 | 2475 | 5.0 | 98% |
| H264 1080p30 5 Mbps | 1.4 | libopus | 30.0 | 4961 | 6.4 | FFmpeg h264 | 30.0 | 4942 | 7.4 | 86% |
| H264 1080p60 8 Mbps | 1.4 | VideoToolbox | 60.0 | 7986 | 4.3 | FFmpeg h264 | 60.0 | 7979 | 5.5 | 79% |
| H264 2160p30 20 Mbps | 5.5 | VideoToolbox | 29.9 | 20060 | 11.1 | FFmpeg h264 | 0.0 | 20043 | - | - |
| H264-High 720p30 2.5 Mbps | 1.2 | VideoToolbox | 30.0 | 2480 | 4.8 | - | - | - | - | - |
| H264-High 1080p30 5 Mbps | 2.4 | VideoToolbox | 30.0 | 4928 | 6.2 | - | - | - | - | - |
| H264-High 1080p60 8 Mbps | 2.2 | VideoToolbox | 60.0 | 8041 | 4.4 | - | - | - | - | - |
| H264-High 2160p30 20 Mbps | 9.3 | VideoToolbox | 29.9 | 19888 | 11.1 | - | - | - | - | - |

### Video send

- Caps lowered to aiortc's maximum (1.5 Mbps VP8, 3 Mbps H.264); read CPU with fps and kbps.

| Case | wrtc encoder | wrtc fps | wrtc kbps | wrtc CPU/frame (ms) | aiortc encoder | aiortc fps | aiortc kbps | aiortc CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H264 720p30 2.5 Mbps | VideoToolbox | 30.0 | 2254 | 2.9 | libx264 | 30.0 | 2509 | 29.5 | 10% |
| VP8 720p30 1.5 Mbps | libvpx | 30.0 | 1328 | 12.9 | libvpx | 30.0 | 1509 | 12.0 | 107% |
| VP8 1080p30 1.5 Mbps | libvpx | 16.0 | 1087 | 26.0 | libvpx | 30.0 | 1787 | 19.1 | 136% |
| VP8 1080p60 1.5 Mbps | libvpx | 8.8 | 740 | 34.7 | libvpx | 60.0 | 3610 | 12.5 | 277% |
| VP8 2160p30 1.5 Mbps | libvpx | 3.3 | 920 | 96.9 | libvpx | 30.0 | 7482 | 34.4 | 282% |
| H264 1080p30 3 Mbps | VideoToolbox | 30.0 | 2736 | 3.6 | libx264 | 30.0 | 3017 | 35.5 | 10% |
| H264 1080p60 3 Mbps | VideoToolbox | 60.0 | 2622 | 2.9 | libx264 | 60.0 | 6003 | 27.3 | 11% |
| H264 2160p30 3 Mbps | VideoToolbox | 18.2 | 2803 | 7.9 | libx264 | 30.0 | 3001 | 63.6 | 12% |

### Video call

- Latency: a frame written to read. Each library sets its own bitrate: read CPU with kbps.

| Case | wrtc decoder | wrtc fps | wrtc kbps | wrtc latency p50 / p95 (ms) | wrtc receiver / sender CPU/frame (ms) | aiortc decoder | aiortc fps | aiortc kbps | aiortc latency p50 / p95 (ms) | aiortc receiver / sender CPU/frame (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VP8 720p30 2.5 Mbps | libvpx | 30.0 | 2506 | 21.2 / 23.1 | 4.9 / 10.3 | libvpx | 30.0 | 1471 | 42.7 / 45.0 | 3.9 / 10.2 | 125% |
| VP8 1080p30 5 Mbps | libvpx | 30.1 | 5002 | 21.4 / 23.1 | 5.3 / 12.5 | libvpx | 30.1 | 1789 | 43.3 / 45.3 | 4.3 / 14.0 | 125% |
| H264 720p30 2.5 Mbps | VideoToolbox | 30.0 | 2520 | 24.0 / 25.7 | 5.2 / 3.0 | FFmpeg h264 | 30.0 | 2339 | 43.4 / 45.3 | 3.1 / 26.9 | 166% |
| H264 1080p30 5 Mbps | VideoToolbox | 30.0 | 5009 | 30.0 / 32.1 | 6.3 / 3.3 | FFmpeg h264 | 30.0 | 2264 | 43.5 / 45.2 | 3.9 / 33.3 | 162% |
| VP9 720p30 2.5 Mbps | libvpx | 30.0 | 2509 | 21.1 / 23.0 | 5.4 / 16.8 | - | - | - | - | - | - |
| VP9 1080p30 5 Mbps | libvpx | 30.0 | 5013 | 21.2 / 23.3 | 8.5 / 18.7 | - | - | - | - | - | - |
| AV1 720p30 2.5 Mbps | dav1d | 30.1 | 2500 | 24.2 / 26.5 | 6.2 / 18.0 | - | - | - | - | - | - |
| AV1 1080p30 5 Mbps | dav1d | 30.0 | 4988 | 26.2 / 28.2 | 6.0 / 20.4 | - | - | - | - | - | - |

### Audio receive

- One Opus stream a connection; delivered: audio read over real time.

| Case | wrtc CPU per stream (% of a core) | wrtc delivered | wrtc loop lag p95 (ms) | aiortc CPU per stream (% of a core) | aiortc delivered | aiortc loop lag p95 (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 stream | 5.26 | 100% | 0.7 | 6.98 | 100% | 1.4 | 75% |
| 10 streams | 2.31 | 100% | 0.7 | 4.13 | 100% | 1.4 | 56% |
| 50 streams | 0.96 | 100% | 0.8 | 1.95 | 100% | 3.5 | 49% |

### Audio send

- One tone a connection; delivered: packets Pion got over 50 a second.

| Case | wrtc CPU per stream (% of a core) | wrtc delivered | wrtc loop lag p95 (ms) | aiortc CPU per stream (% of a core) | aiortc delivered | aiortc loop lag p95 (ms) | wrtc, % of aiortc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 stream | 6.58 | 101% | 1.4 | 17.52 | 100% | 1.4 | 38% |
| 10 streams | 2.59 | 101% | 0.9 | 11.45 | 100% | 1.8 | 23% |
| 50 streams | 1.38 | 101% | 1.4 | 6.22 | 100% | 6.4 | 22% |

