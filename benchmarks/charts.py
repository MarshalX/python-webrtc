#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Bar charts of the newest run of each suite, every library relative to the baseline (1x), higher is better.

python -m benchmarks.charts  # writes benchmarks/charts/*.png
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import matplotlib as mpl
import seaborn as sns  # pyrefly: ignore[untyped-import]
from matplotlib import pyplot as plt
from matplotlib.container import BarContainer
from matplotlib.ticker import FuncFormatter

from benchmarks import report
from benchmarks.markdown import BASELINE
from benchmarks.report import SUITES
from benchmarks.runner import BENCHMARKS, LIBRARIES, RESULTS

if TYPE_CHECKING:
    import pathlib

    from matplotlib.axes import Axes

    from benchmarks.figures import Figure
    from benchmarks.protocol import Hello
    from benchmarks.report import Manifest

CHARTS = BENCHMARKS / 'charts'


def _relative(figure: Figure) -> tuple[list[str], list[str], list[float]]:
    """The categories, the libraries and the values relative to the baseline's, as the columns of a long table."""
    categories: list[str] = []
    libraries: list[str] = []
    relative: list[float] = []

    for category, values in figure.values.items():
        baseline = values.get(BASELINE, math.nan)
        for library, value in values.items():
            ratio = baseline / value if figure.lower_is_better else value / baseline
            if math.isfinite(ratio):
                categories.append(category)
                libraries.append(library)
                relative.append(ratio)

    return categories, libraries, relative


def _label(library: str, versions: dict[str, Hello]) -> str:
    hello = versions.get(library)
    return library if hello is None else f'{library} {hello["version"]}'


def _footer(manifest: Manifest) -> str:
    """The machine and the conditions of a run, for the foot of its charts."""
    go = f', {manifest["go"]}' if manifest['go'] is not None else ''
    runs = 'a quick run, not results' if manifest['quick'] else f'median of {manifest["repeat"]} runs'
    return f'{manifest["machine"]}{go}; {manifest["date"][:10]}; {runs}; loopback, both peers on one machine'


def _times(value: float, _: int | None) -> str:
    return f'{value:g}x'


def _annotate(ax: Axes, figure: Figure, *, categories: list[str], libraries: list[str]) -> None:
    """Draws the notes of a figure on its bars: a container a library, in legend order; a bar's x is its category."""
    if len(figure.notes) == 0:
        return
    for container, library in zip(ax.containers, libraries, strict=False):
        if not isinstance(container, BarContainer):
            continue
        labels: list[str] = []
        for bar in container.patches:
            center: float = bar.get_x() + bar.get_width() / 2
            category = categories[round(center)]
            labels.append(figure.notes.get(category, {}).get(library, ''))
        ax.bar_label(container, labels=labels, fontsize=8, padding=2)


def plot(figure: Figure, manifest: Manifest, path: pathlib.Path) -> None:
    """Draws a figure into a PNG file, skipping one without a value."""
    categories, libraries, relative = _relative(figure)
    if len(relative) == 0:
        return

    versions = manifest['libraries']
    order = [library for library in LIBRARIES if library in libraries]
    labels = [_label(library, versions) for library in libraries]
    legend = [_label(library, versions) for library in order]

    sns.set_theme(style='darkgrid')
    fig, ax = plt.subplots(figsize=(max(8, 1.6 * len(set(categories))), 6))

    # the bars, their notes and the baseline at 1x
    sns.barplot(x=categories, y=relative, hue=labels, hue_order=legend, ax=ax)
    _annotate(ax, figure, categories=list(dict.fromkeys(categories)), libraries=order)
    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1)

    # the text around them
    ax.set_title(figure.title)
    ax.set_ylabel(f'{figure.measure} relative to {BASELINE}, higher is better')
    ax.yaxis.set_major_formatter(FuncFormatter(_times))
    ax.tick_params(axis='x', labelrotation=20)
    ax.legend(title='library')
    fig.text(0.5, 0.01, _footer(manifest), ha='center', fontsize=8, color='gray')

    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    """Draws every figure of the newest run of each suite into ``benchmarks/charts``."""
    mpl.use('Agg')
    CHARTS.mkdir(exist_ok=True)
    for suite, run in report.newest_runs(RESULTS.glob('*.json')).items():
        for figure in SUITES[suite].figures(run['suites'][suite]):
            plot(figure, run['manifest'], CHARTS / f'{figure.name}.png')
            print(f'wrote {figure.name}.png')


if __name__ == '__main__':
    main()
