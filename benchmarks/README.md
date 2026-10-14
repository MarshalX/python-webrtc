# Benchmarks

python-webrtc against [aiortc](https://github.com/aiortc/aiortc) (the 1× baseline), [Pion](https://github.com/pion/webrtc),
[libdatachannel](https://github.com/paullouisageneau/libdatachannel) and [webrtc-rs](https://github.com/webrtc-rs/webrtc).
Results: `RESULTS.md` and `charts/`.

## Run

```sh
benchmarks/run.sh --quick                # smoke test
benchmarks/run.sh                        # full run
benchmarks/run.sh --suite media --libs wrtc,pion
```

Needs uv, Go, Rust, CMake, a C++17 compiler, OpenSSL, git, ffmpeg (libvpx, libx264, libopus) and `make dev`.
Run on an idle machine.

| Driver | Pinned |
| --- | --- |
| `drivers/wrtc/` | the working tree |
| `drivers/aiortc/` | `aiortc==1.15.0`, `run.sh` |
| `drivers/pion/` | v4.2.23, `go.sum` |
| `drivers/libdatachannel/` | v0.24.6, `runner.py` |
| `drivers/webrtc-rs/` | 0.21.1, `Cargo.lock` |

## Suites

| Suite | Measures | Libraries |
| --- | --- | --- |
| `setup` | time to an open data channel | all |
| `datachannel` | throughput, CPU per MB, round trip | all |
| `memory` | RSS per connection, after closing, most connections | all |
| `media` | video receive, send, call; audio | python-webrtc, aiortc |

## Method

- One process per peer; the runner relays signaling over JSON lines (`protocol.py`).
- CPU and RSS sampled from outside with psutil.
- Host candidates on loopback, no STUN or TURN; library defaults otherwise.
- Pion is the media peer: it sends pre-encoded files and counts what it receives.
- Each case runs 3 times in fresh processes, shuffled; tables show medians.
- `RESULTS.md` and the charts take each library's newest run, so `--libs wrtc` refreshes Python WebRTC alone.

## Caveats

- Both peers share one machine.
- aiortc can't trickle.
- aiortc can't cap its encoder: send caps are lowered to its maximum for both libraries.
- On macOS, a socket content filter (`sysctl net.cfil.active_count` > 0) can delay libdatachannel's close by 1 s.
- Linux: run in a VM or container with `ulimit -n 65536`.
