#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Coverage of the extension's C++ and of the webrtc package, by the suite and by the hunt.

python -m scripts.debug.cover run [pytest arguments]   # the suite once, then the report; make coverage
python -m scripts.debug.cover report                  # make coverage-report
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, TypedDict

if sys.platform != 'win32':
    import fcntl

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[2]
DIR = ROOT / 'build' / 'coverage'
NATIVE = DIR / 'native'
PYTHON = DIR / 'python'
HTML = DIR / 'html'
NEVER = DIR / 'NEVER.md'
STAMP = DIR / 'stamp'
# outside DIR, which a reset deletes
LOCK = ROOT / 'build' / 'coverage.lock'
SOURCES = ROOT / 'python-webrtc' / 'cpp' / 'src'
PACKAGE = ROOT / 'python-webrtc' / 'python' / 'webrtc'
EXTENSION_DIR = ROOT / 'build' / 'asan' / 'python-webrtc' / 'cpp'
CONFIG = ROOT / 'pyproject.toml'
SANITIZERS = ROOT / '.github' / 'scripts' / 'sanitizers-macos.sh'

SUITE = 'suite'
CHAOS = 'chaos'
GROUPS = (SUITE, CHAOS)
ALL = 'all'
NATIVE_HERE = sys.platform == 'darwin'

_NO_PROFILE = 'no profile can be merged'
_STATIC_PREFIX = re.compile(r'^[^\[\]:]+\.(?:cpp|mm|h):')

#: (file, first line) -> (name, whether it ran); template instantiations share one key
Functions = dict[tuple[str, int], tuple[str, bool]]


class _Count(TypedDict):
    count: int
    covered: int
    percent: float


class _NativeTotals(TypedDict):
    lines: _Count
    functions: _Count


class _NativeFunction(TypedDict):
    name: str
    count: int
    filenames: list[str]
    #: line start, column start, line end, column end, count, file id, ...
    regions: list[list[int]]


class _NativeExport(TypedDict):
    functions: list[_NativeFunction]
    totals: _NativeTotals


class _Summary(TypedDict):
    covered_lines: int
    num_statements: int
    percent_covered: float


class _PythonFunction(TypedDict):
    summary: _Summary
    start_line: int


class _PythonFile(TypedDict):
    functions: dict[str, _PythonFunction]


class _PythonReport(TypedDict):
    files: dict[str, _PythonFile]
    totals: _Summary


def env(group: str, *, python: bool) -> dict[str, str]:
    variables = {'LLVM_PROFILE_FILE': str(NATIVE / f'{group}-%4m.profraw')}
    if python:
        PYTHON.mkdir(parents=True, exist_ok=True)
        variables |= {'COVERAGE_PROCESS_START': str(CONFIG), 'COVERAGE_FILE': str(PYTHON / group)}
    return variables


def count_run(name: str) -> int:
    counter = DIR / f'{name}.runs'
    runs = int(counter.read_text(encoding='utf-8')) + 1 if counter.exists() else 1
    DIR.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(runs), encoding='utf-8')
    return runs


@contextlib.contextmanager
def _locked() -> Generator[None]:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('w', encoding='utf-8') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _extension() -> pathlib.Path | None:
    return next(EXTENSION_DIR.glob('wrtc*.so'), None)


def _stamp() -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    extension = _extension()
    for path in [*([extension] if extension is not None else []), *sorted(PACKAGE.rglob('*.py'))]:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _reset_if_stale() -> None:
    stamp = _stamp()
    if STAMP.exists() and STAMP.read_text(encoding='utf-8') == stamp:
        return
    shutil.rmtree(DIR, ignore_errors=True)
    DIR.mkdir(parents=True)
    STAMP.write_text(stamp, encoding='utf-8')


def _ok(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode != 0:
        print(f'coverage: {shlex.join(result.args)} failed:\n{result.stderr.strip()}', file=sys.stderr)
    return result.returncode == 0


def _llvm(*args: object, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    # not Homebrew's LLVM, whose profile format differs
    return subprocess.run(['xcrun', *map(str, args)], input=stdin, capture_output=True, text=True, check=False)


def _coverage(*args: object) -> bool:
    command = [sys.executable, '-m', 'coverage', *map(str, args)]
    return _ok(subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False))


def _unlink(paths: Iterable[pathlib.Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _merge_native(group: str) -> None:
    raws = sorted(NATIVE.glob(f'{group}-*.profraw'))
    if raws == []:
        return
    merged = NATIVE / f'{group}.profdata'
    fresh = NATIVE / f'{group}.new'
    result = _llvm('llvm-profdata', 'merge', '-sparse', '--failure-mode=all', *raws, '-o', fresh)
    if not _ok(result):
        if _NO_PROFILE in result.stderr:
            _unlink(raws)
        return
    if merged.exists():
        temporary = NATIVE / f'{group}.tmp'
        if not _ok(_llvm('llvm-profdata', 'merge', '-sparse', merged, fresh, '-o', temporary)):
            return
        temporary.replace(merged)
        fresh.unlink()
    else:
        fresh.replace(merged)
    _unlink(raws)


def _combine_python(group: str) -> None:
    # without paths, combine takes <group>.* next to the data file and deletes them
    if any(PYTHON.glob(f'{group}.*')):
        _coverage('combine', '--append', '--quiet', f'--data-file={PYTHON / group}')


def _collect() -> None:
    _reset_if_stale()
    for group in GROUPS:
        if NATIVE_HERE:
            _merge_native(group)
        _combine_python(group)


def collect() -> None:
    with _locked():
        _collect()


def _native_data(groups: Sequence[str]) -> pathlib.Path | None:
    profiles = [NATIVE / f'{group}.profdata' for group in groups]
    profiles = [profile for profile in profiles if profile.exists()]
    if not NATIVE_HERE or profiles == [] or _extension() is None:
        return None
    if len(profiles) == 1:
        return profiles[0]
    merged = NATIVE / f'{ALL}.profdata'
    return merged if _ok(_llvm('llvm-profdata', 'merge', '-sparse', *profiles, '-o', merged)) else None


def _python_data(groups: Sequence[str]) -> pathlib.Path | None:
    files = [PYTHON / group for group in groups if (PYTHON / group).exists()]
    if files == []:
        return None
    if len(files) == 1:
        return files[0]
    combined = PYTHON / ALL
    return combined if _coverage('combine', '--keep', '--quiet', f'--data-file={combined}', *files) else None


def _export(profile: pathlib.Path, *options: str) -> _NativeExport | None:
    result = _llvm('llvm-cov', 'export', _extension(), f'-instr-profile={profile}', *options, SOURCES)
    if not _ok(result):
        return None
    exported: _NativeExport = json.loads(result.stdout)['data'][0]
    return exported


def _python_report(data: pathlib.Path) -> _PythonReport | None:
    output = DIR / f'{data.name}.json'
    if not _coverage('json', '--quiet', f'--data-file={data}', '-o', output):
        return None
    report: _PythonReport = json.loads(output.read_text(encoding='utf-8'))
    return report


def _cpp_summary(profile: pathlib.Path | None) -> str:
    if not NATIVE_HERE:
        return 'C++ macOS only'
    exported = _export(profile, '-summary-only') if profile is not None else None
    if exported is None:
        return 'C++ none collected'
    lines, functions = exported['totals']['lines'], exported['totals']['functions']
    return f'C++ {lines["percent"]:.1f}% of lines, {functions["covered"]}/{functions["count"]} functions'


def _python_summary(data: pathlib.Path | None) -> str:
    report = _python_report(data) if data is not None else None
    if report is None:
        return 'Python none collected'
    return f'Python {report["totals"]["percent_covered"]:.1f}% of statements and branches'


def summary_line() -> str | None:
    with _locked():
        profile, data = _native_data(GROUPS), _python_data(GROUPS)
        if profile is None and data is None:
            return None
        return f'Coverage: {_cpp_summary(profile)}; {_python_summary(data)}'


def _demangle(names: list[str]) -> list[str]:
    plain = [_STATIC_PREFIX.sub('', name) for name in names]
    result = _llvm('llvm-cxxfilt', '--no-params', stdin='\n'.join(plain))
    if not _ok(result) or len(result.stdout.splitlines()) != len(plain):
        return plain
    return result.stdout.splitlines()


def _cpp_functions(profile: pathlib.Path | None) -> Functions:
    exported = _export(profile, '-skip-expansions') if profile is not None else None
    if exported is None:
        return {}
    found: Functions = {}
    for function in exported['functions']:
        region = function['regions'][0]
        path = pathlib.Path(function['filenames'][region[5]])
        if not path.is_relative_to(SOURCES):
            continue
        key = (path.relative_to(SOURCES).as_posix(), region[0])
        name, ran = found.get(key, (function['name'], False))
        found[key] = (name, ran or function['count'] > 0)
    names = _demangle([name for name, _ran in found.values()])
    return {key: (name, ran) for (key, (_mangled, ran)), name in zip(found.items(), names)}


def _python_functions(data: pathlib.Path | None) -> Functions:
    report = _python_report(data) if data is not None else None
    if report is None:
        return {}
    found: Functions = {}
    for file, entry in report['files'].items():
        relative = pathlib.Path(os.path.relpath(ROOT / file, PACKAGE.parent)).as_posix()
        for name, function in entry['functions'].items():
            summary = function['summary']
            if summary['num_statements'] > 0:
                # the module's own code at line 0, since a function may start at line 1
                line, label = (function['start_line'], name) if name != '' else (0, '<module>')
                found[relative, line] = (label, summary['covered_lines'] > 0)
    return found


def _never(functions: Functions) -> Functions:
    return {key: value for key, value in functions.items() if not value[1]}


def _missed_by(reached: Functions, missed: Functions) -> Functions:
    return {key: value for key, value in reached.items() if value[1] and key in missed and not missed[key][1]}


def _by_file(functions: Iterable[tuple[str, int]]) -> dict[str, list[int]]:
    files: dict[str, list[int]] = {}
    for file, line in sorted(functions):
        files.setdefault(file, []).append(line)
    return files


def _section(title: str, listed: Functions, every: Functions) -> list[str]:
    if every == {}:
        return [f'## {title}: no data', '']
    totals = _by_file(every)
    lines = [f'## {title}: {len(listed)} of {len(every)} functions', '']
    for file, starts in _by_file(listed).items():
        if len(starts) == len(totals[file]):
            lines.append(f'- `{file}`: all {len(starts)}')
            continue
        lines.append(f'- `{file}`: {len(starts)} of {len(totals[file])}')
        lines += [f'  - {line} `{listed[file, line][0]}`' for line in starts]
    return [*lines, '']


def _suite_only(title: str, suite: Functions, chaos: Functions, *, every: Functions) -> list[str]:
    return _section(title, _missed_by(suite, chaos), every if suite != {} and chaos != {} else {})


def _split(cpp: Functions, python: Functions) -> list[str]:
    suite_cpp, chaos_cpp = _cpp_functions(_native_data([SUITE])), _cpp_functions(_native_data([CHAOS]))
    suite_python, chaos_python = _python_functions(_python_data([SUITE])), _python_functions(_python_data([CHAOS]))
    return [
        '# The suite reaches, chaos never does',
        '',
        *_suite_only('C++', suite_cpp, chaos_cpp, every=cpp),
        *_suite_only('Python', suite_python, chaos_python, every=python),
    ]


def _write_never(profile: pathlib.Path | None, data: pathlib.Path | None) -> None:
    cpp, python = _cpp_functions(profile), _python_functions(data)
    lines = ['# Never executed', '', 'Functions by file and first line, of the suite and the hunt together.', '']
    lines += _section('C++', _never(cpp), cpp) + _section('Python', _never(python), python) + _split(cpp, python)
    NEVER.write_text('\n'.join(lines), encoding='utf-8')


def _render_cpp(profile: pathlib.Path | None) -> str:
    summary = _cpp_summary(profile)
    if profile is None:
        return summary
    shutil.rmtree(HTML / 'cpp', ignore_errors=True)
    show = ['llvm-cov', 'show', _extension(), f'-instr-profile={profile}', '-format=html', '-show-branches=count']
    _ok(_llvm(*show, f'-output-dir={HTML / "cpp"}', SOURCES))
    return f'{summary}: {HTML / "cpp" / "index.html"}'


def _render_python(data: pathlib.Path | None) -> str:
    summary = _python_summary(data)
    if data is None:
        return summary
    _coverage('html', '--quiet', f'--data-file={data}', '-d', HTML / 'python')
    return f'{summary}: {HTML / "python" / "index.html"}'


def report() -> None:
    with _locked():
        _collect()
        profile, data = _native_data(GROUPS), _python_data(GROUPS)
        print(_render_cpp(profile))
        print(_render_python(data))
        _write_never(profile, data)
    print(f'Never executed: {NEVER}')


def run(pytest_args: list[str]) -> int:
    if NATIVE_HERE:
        built = subprocess.run([SANITIZERS, '--build-only'], cwd=ROOT, check=False)
        if built.returncode != 0:
            return built.returncode
    else:
        print('coverage: C++ coverage is macOS only, measuring Python')
    collect()
    tests = [SANITIZERS] if NATIVE_HERE else [sys.executable, '-m', 'pytest', '--ignore=tests/wpt']
    variables = {**os.environ, **env(SUITE, python=True)}
    returncode = subprocess.run([*tests, *pytest_args], cwd=ROOT, env=variables, check=False).returncode
    report()
    return returncode


def main() -> None:
    if sys.platform == 'win32':
        sys.exit('coverage: not supported on Windows')
    parser = argparse.ArgumentParser(description='Coverage of the C++ and the Python package, in build/coverage.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('run', help='the suite once, then the report; other arguments go to pytest')
    commands.add_parser('report', help='HTML and NEVER.md of the suite, make asan and the hunt')
    commands.add_parser('collect', help='merge what the runs left; sanitizers-macos.sh after a build')
    # argparse.REMAINDER would reject a leading option such as -k
    args, pytest_args = parser.parse_known_args()
    if args.command != 'run' and pytest_args != []:
        parser.error(f'unrecognized arguments: {" ".join(pytest_args)}')
    if args.command == 'run':
        sys.exit(run(pytest_args))
    if args.command == 'collect':
        collect()
    else:
        report()


if __name__ == '__main__':
    main()
