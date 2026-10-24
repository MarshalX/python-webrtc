---
description: "Python WebRTC against aiortc, Pion, libdatachannel and webrtc-rs: connection setup, data channels, memory and media"
---

# Benchmarks

Python WebRTC against [aiortc](https://github.com/aiortc/aiortc), the other WebRTC library for Python, and three
compiled ones: [Pion](https://github.com/pion/webrtc) (Go), [libdatachannel](https://github.com/paullouisageneau/libdatachannel)
(C++) and [webrtc-rs](https://github.com/webrtc-rs/webrtc) (Rust).

Every chart is relative to aiortc (the dashed line at 1x), and **higher is better**. The suites and drivers
are in [`benchmarks/`](https://github.com/MarshalX/python-webrtc/tree/main/benchmarks): run
`benchmarks/run.sh` to measure your own machine. Every number on this page is in
[RESULTS.md](https://github.com/MarshalX/python-webrtc/blob/main/benchmarks/RESULTS.md).

The charts are from an Apple M1 with 8 cores, both peers on one machine over loopback. Each case runs 3 times in fresh
processes, and the charts show the medians of each library's newest run.

## At a glance

Against aiortc, Python WebRTC:

- opens a connection **7–8x faster**;
- moves **7.7–14.6x more data** through a data channel, with **7–10x less CPU** per megabyte;
- spends **less CPU on audio** at every stream count, up to 4x less when sending;
- encodes H.264 in hardware on macOS, at **a tenth of the CPU** per frame;
- delivers call video with **about half the latency**;
- holds **more connections** in one process (1450 against 1100).

It also does more work for each connection. It runs the full engine browsers use, so congestion control, pacing,
retransmission, jitter buffers and statistics stay on even when nobody looks at them. A few charts
read worse because of that, and the sections below explain each one.

## Connection setup

![Connection setup](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/setup.png)

The time from creating a connection to an open data channel: about 3.5 ms, against 29 ms for aiortc. Cold runs start
fresh processes. The benchmark keeps the defaults: DTLS 1.3 is on, while SNAP and SPED, the other parts of
[WARP](guides/field-trials.md#warp), are off and would save more round trips.

## Data channels

![Data channel throughput](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/datachannel-throughput.png)

![Data channel CPU per MB](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/datachannel-cpu.png)

SCTP, DTLS and the network stay in native threads, so Python only sees the messages. That puts Python WebRTC alongside
the compiled libraries in throughput rather than near aiortc.

![Data channel round trip](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/datachannel-rtt.png)

The round trip of 1 KB messages, sent 100 times a second. Every message is handed to your asyncio code, on the event
loop, in both directions. The compiled libraries deliver to native code, and aiortc does the whole protocol stack in
Python on the loop.

## Memory

![Memory per connection](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/memory.png)

This chart favors aiortc, for two reasons that come from the engine rather than from Python WebRTC's code:

- **A bare connection** keeps the state of a full browser engine: the codec tables it negotiates with, a congestion
  controller and its transport. The Python objects on top take under 1 KB.
- **A connected data channel** is mostly ICE: the engine keeps every candidate pair it checked, about 8 KB each, to
  switch networks without reconnecting. The benchmark Mac has 10 addresses (Wi-Fi, VPN, virtual machine bridges and
  loopback), each over UDP and TCP, so 50 pairs a connection. aiortc gathers UDP only and skips loopback. In the same
  test on Linux with one interface, a connected pair takes a third of the memory it takes on that Mac.

Memory stays reserved after connections close, because the allocator keeps it for reuse: opening and closing 100
connections over and over doesn't grow the process past the first round.

The process itself starts smaller, 92 MB against 128 MB, and holds 1450 connections where aiortc stops at 1100.

## Media

### Video receive

![Video receive](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/media-video-receive.png)

CPU for each frame received, decoded and read in Python. VP8 decodes with the same library in both, so the bars stay
close. H.264 is cheaper at every resolution, decoded by VideoToolbox on macOS.

### Video send

![Video send](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/media-video-send.png)

Both libraries send under the same bitrate cap. Read the two panels under the bars before the bars:

- **Bitrate over the cap.** Python WebRTC stays under the cap. aiortc's VP8 ignores it as the picture grows: twice the
  cap at 1080p60 and five times at 2160p. Sent to a real network, that is packet loss.
- **Frame rate over the source.** To fit 1080p and 4K into 1.5 Mbps, the engine keeps the resolution and drops
  frames, as browsers do with that setting. It encodes fewer, much larger frames, so the CPU per frame goes up.

So the VP8 bars compare different work: one library respects the cap, the other doesn't. H.264 uses the hardware
encoder on macOS and costs a tenth of the CPU per frame.

### Video call

![Video call](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/media-video-call.png)

Two peers of the same library call each other, and each library's congestion control picks the bitrate. Python WebRTC
reaches the bitrate the video asks for, 2.5 or 5 Mbps, while aiortc stays near 1.5–2.4 Mbps. The panel under the bars
shows it: Python WebRTC receives up to three times the bits for every frame, so a better picture, and decoding more
bits costs more CPU per frame.

![Video call latency](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/media-video-latency.png)

From writing a frame on one side to reading it on the other: 22–28 ms against aiortc's 44 ms, at the higher
bitrate.

### Audio

![Audio](https://raw.githubusercontent.com/MarshalX/python-webrtc/main/benchmarks/charts/media-audio.png)

CPU per Opus stream. Packets, encoding and decoding stay native, so the cost per stream drops as streams are
added.

## Caveats

- Both peers run on one machine, so a library that uses more threads competes with its own peer.
- aiortc can't trickle ICE candidates, and can't cap its encoder: the send caps are aiortc's own maximum.
- Media compares the two Python libraries only. Pion is the peer that sends and receives the encoded files.
- The results are of one machine. Run `benchmarks/run.sh` on yours.
