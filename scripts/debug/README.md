# Debugging tools

Tools for unattended bug hunts and for hangs. macOS and Linux; not Windows.

| Tool | What it does |
| --- | --- |
| `hunt.py` | Runs the jobs one at a time until a deadline, and keeps the evidence of every failure |
| `stacks.py` | Native stacks of a process and its children, and optionally its Python stacks |
| `triage.py` | Classifies a run and gives its signature; also prints the signature of a saved bundle |
| `synthetic.py` | Fake failures for `hunt --self-test`, without the library |
| `cover.py` | C++ and Python coverage of the suite and the hunt, and what never ran |

## The hunt

```sh
make hunt H=8                         # or O='--until 07:30', O='--jobs chaos,chaos-asan'
make hunt-report                      # build/hunt/REPORT.md
uv run --no-sync python -m scripts.debug.hunt --self-test
```

It builds once (the editable install, then the sanitizer builds the jobs need), then loops: it starts the job furthest
behind its share of time (`weight` in `JOBS`), with the next seed for chaos jobs, and watches it. A job hangs when
chaos says a step is stuck, when it prints nothing for `silence_s`, or when it runs longer than `wall_s`. It is
killed without stacks when its processes use more than `rss_gb`, and nothing starts while memory pressure is critical.

On a hang it takes the native stacks of every process of the job (lldb and `sample` on macOS, gdb on Linux), sends
SIGUSR1 for the Python stacks, then aborts for a core. Each failure gets a signature: the outcome (crash, hang, leak,
memory, failure) and its top frames without addresses, so the same bug gives the same text. A new signature sends a
notification. A job that hits the same signature 5 times in a row stops until the next hunt.

Ctrl-C stops the job and saves the state; the next `make hunt` continues the seeds. `rm -rf build/hunt` starts over.

### Before the first hunt

- `sudo chmod 1777 /cores`, or macOS writes no cores. Cores are kept only with 20 GB free.
- Run `--self-test` once: it checks that the debuggers can attach and that every outcome is filed.

### Before each hunt

- Plugged in, lid open: the hunt keeps the Mac awake, but a closed lid still sleeps it.
- Don't change C++ while it runs: jobs import the editable install, which rebuilds on import.

### Results

```
build/hunt/
  REPORT.md                 signatures, hits, first seen, a repro command; the time each job got
  hunt.log                  one line per run
  state.json                seeds and times to continue from
  <signature>/<time>-<job>-<seed>/
    info.json               command, environment, git HEAD and a hash of the working tree, cores
    output.txt              the end of the output, with the Python stacks
    stacks/                 <pid>-lldb.txt, <pid>-sample.txt, <pid>-gdb.txt, <pid>-py-spy.txt
    crash.ips, core.*       the macOS crash report, the cores
```

The first 3 runs of a signature get a bundle, the rest are counted. The repro command keeps `--wait-when-stuck`: a
stuck seed waits for `make stacks` or a debugger instead of exiting.

### Jobs

A job is a row of `JOBS` in `hunt.py`: its command, weight, and limits. `build` runs it in a build of
`.github/scripts/sanitizers-macos.sh --exec` (ASan, TSan, or the free-threaded one of `make ft`), `ecores` on the
efficiency cores (`taskpolicy -b`), which widens race windows. Both are macOS only; on Linux the other jobs run.
Efficiency cores reproduce races, they aren't a gate: the hunt turns pytest's timeouts off there.

## Coverage

```sh
make coverage                         # the suite once, then the report; O='tests/test_stats.py' or O='-k stats'
make coverage-report                  # everything collected so far: the suite, make asan and the hunt
```

C++ coverage comes from the ASan build (`build/asan` has coverage counters, which cost nothing next to ASan), so
`chaos-asan`, `suite-asan-gc-ecores` and `make asan` collect it too; macOS only. Python coverage costs up to a fifth of
the run time, so the hunt measures every 10th run of each job; `make coverage` always does.

The results are in `build/coverage`: `html/cpp`, `html/python`, and `NEVER.md`, the functions that never ran and those
the suite reaches but chaos never does. The hunt's REPORT.md gets the totals. The data starts over when the ASan build
or the package changes; `rm -rf build/coverage` starts over by hand. Chaos gets its C++ coverage from `chaos-asan`
only, which has no `--transforms`: the transform steps count only for Python. A process that crashes or aborts writes
no C++ profile, so code that only abort tests reach is listed as never executed.

## Stacks of a running process

```sh
make stacks PID=1234                  # O=--signal: also the Python stacks, on the process's stderr
```

The tests and chaos register SIGUSR1 for the Python stacks; without that, SIGUSR1 kills a Python process.

## Linux

In a container with gdb, e.g. the manylinux image with the repository mounted: `python -m scripts.debug.hunt
--self-test` needs no build. With `--privileged` or `SYS_PTRACE`, gdb can attach.
