#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Native stacks of every thread of a process and its descendants, for debugging hangs.

python -m scripts.debug.stacks PID             # or make stacks PID=...
python -m scripts.debug.stacks PID --out DIR   # a file per process and tool
python -m scripts.debug.stacks PID --signal    # then Python stacks too, on the process's stderr

macOS: lldb and sample. Linux: gdb, and py-spy when installed.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

MAX_PROCESSES = 8
PYTHON_STACKS_WAIT = 2
GDB = ['gdb', '-nx', '-batch', '-ex', 'set pagination off']


@dataclass(frozen=True)
class Process:
    """A row of ``ps``."""

    pid: int
    ppid: int
    pgid: int
    rss_kb: int
    stat: str
    comm: str


def _processes() -> list[Process]:
    ps = ['ps', '-A', '-o', 'pid=,ppid=,pgid=,rss=,stat=,comm=']
    output = subprocess.run(ps, capture_output=True, text=True, errors='replace', check=True).stdout
    rows: list[Process] = []
    for line in output.splitlines():
        try:
            pid, ppid, pgid, rss, stat, comm = line.split(None, 5)
        except ValueError:
            continue
        # macOS shows the path of the executable
        rows.append(Process(int(pid), int(ppid), int(pgid), int(rss), stat, pathlib.PurePath(comm).name))
    return rows


def tree(root: int) -> list[Process]:
    """The live processes of a tree, the root first: its descendants, and the members of its process group."""
    alive = [process for process in _processes() if not process.stat.startswith('Z')]
    # a descendant may have left the group with setsid, an orphan is reparented to init but stays in the group
    members = {root} | {process.pid for process in alive if process.pgid == root}
    parents = list(members)
    while parents != []:
        parent = parents.pop()
        for process in alive:
            if process.ppid == parent and process.pid not in members:
                members.add(process.pid)
                parents.append(process.pid)
    return sorted((process for process in alive if process.pid in members), key=lambda p: (p.pid != root, p.pid))


def _commands(pid: int, out_dir: pathlib.Path) -> list[tuple[list[str], pathlib.Path, int]]:
    def path(tool: str) -> pathlib.Path:
        return out_dir / f'{pid}-{tool}.txt'

    if sys.platform == 'darwin':
        batch = ['-o', 'thread backtrace all', '-o', 'process detach']
        lldb = ['lldb', '--no-lldbinit', '--batch', '-p', str(pid), *batch]
        sample = ['sample', str(pid), '2', '-mayDie', '-file', str(path('sample'))]
        return [(lldb, path('lldb'), 90), (sample, path('sample'), 60)]
    commands = [([*GDB, '-p', str(pid), '-ex', 'thread apply all bt'], path('gdb'), 120)]
    if shutil.which('py-spy') is not None:
        commands.append((['py-spy', 'dump', '--native', '--pid', str(pid)], path('py-spy'), 60))
    return commands


def _run(command: list[str], path: pathlib.Path, timeout: int) -> bool:
    # the sanitizer runtimes break debuggers they are preloaded into
    env = {name: value for name, value in os.environ.items() if name not in {'LD_PRELOAD', 'DYLD_INSERT_LIBRARIES'}}
    timed_out = False
    if shutil.which(command[0]) is None:
        output = f'{command[0]} is not installed\n'
    else:
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors='replace',
                env=env,
                timeout=timeout,
                check=False,
            )
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            output = f'{command[0]} timed out after {timeout} s\n'
            timed_out = True
    # sample writes its report itself
    if not path.exists():
        path.write_text(output, encoding='utf-8')
    return timed_out


def send(pid: int, signum: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(pid, signum)


def _snapshot(pid: int, out_dir: pathlib.Path) -> None:
    for command, path, timeout in _commands(pid, out_dir):
        # a debugger killed on its timeout may leave the process stopped
        if _run(command, path, timeout) and sys.platform != 'win32':
            send(pid, signal.SIGCONT)


def collect(root: int, out_dir: pathlib.Path, *, signal_root: bool) -> list[Process]:
    """Writes the native stacks of a tree to ``<pid>-<tool>.txt`` files, and returns the processes of the tree."""
    out_dir.mkdir(parents=True, exist_ok=True)
    processes = tree(root)[:MAX_PROCESSES]
    for process in processes:
        _snapshot(process.pid, out_dir)
    is_python = processes != [] and processes[0].pid == root and processes[0].comm.lower().startswith('python')
    # SIGUSR1 kills a process that hasn't registered it with faulthandler; a Python one dumps to its stderr
    if signal_root and is_python and sys.platform != 'win32':
        send(root, signal.SIGUSR1)
        time.sleep(PYTHON_STACKS_WAIT)
    return processes


def core_backtrace(executable: str, core: pathlib.Path, path: pathlib.Path) -> None:
    """Writes the stack of the thread that crashed, from a Linux core."""
    _run([*GDB, '-ex', 'bt', executable, str(core)], path, 120)


def main() -> None:
    if sys.platform == 'win32':
        sys.exit('stacks: not supported on Windows')
    parser = argparse.ArgumentParser(description='Native stacks of a process and its descendants.')
    parser.add_argument('pid', type=int)
    parser.add_argument('--out', type=pathlib.Path, help='write a file per process and tool to this directory')
    parser.add_argument('--signal', action='store_true', help='then SIGUSR1: Python stacks, if the process registered')
    args = parser.parse_args()
    if args.out is not None:
        collect(args.pid, args.out, signal_root=args.signal)
        return
    with tempfile.TemporaryDirectory() as out_dir:
        for process in collect(args.pid, pathlib.Path(out_dir), signal_root=args.signal):
            for path in sorted(pathlib.Path(out_dir).glob(f'{process.pid}-*.txt')):
                tool = path.stem.split('-', 1)[1]
                print(f'== {process.pid} {process.comm} ({tool}) ==')
                print(path.read_text(encoding='utf-8', errors='replace'))


if __name__ == '__main__':
    main()
