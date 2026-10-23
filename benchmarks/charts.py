#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Bar charts of each library's newest results, relative to the baseline (1x), higher is better.

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
    from matplotlib.figure import Figure as MplFigure

    from benchmarks.figures import Detail, Figure
    from benchmarks.protocol import Hello
    from benchmarks.report import Newest

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


def _footer(found: Newest) -> str:
    """The machine and the conditions of the runs, for the foot of their charts."""
    manifest, _ = found.sources[-1]
    go = f', {manifest["go"]}' if manifest['go'] is not None else ''
    dates = sorted({source['date'][:10] for source, _ in found.sources})

    if any(source['quick'] for source, _ in found.sources):
        runs = 'a quick run, not results'
    elif len(found.sources) > 1:
        runs = f'median of {manifest["repeat"]} runs, newest per library'
    else:
        runs = f'median of {manifest["repeat"]} runs'
    return f'{manifest["machine"]}{go}; {", ".join(dates)}; {runs}; loopback, both peers on one machine'


def _times(value: float, _: int | None) -> str:
    return f'{value:g}x'


def _detail(ax: Axes, detail: Detail, *, categories: list[str], legend: dict[str, str]) -> None:
    """Draws a panel of absolute values under a chart, its bars in the chart's categories and colors."""
    bar_categories: list[str] = []
    bar_labels: list[str] = []
    bar_values: list[float] = []
    for category in categories:
        for library, value in detail.values.get(category, {}).items():
            if library in legend and math.isfinite(value):
                bar_categories.append(category)
                bar_labels.append(legend[library])
                bar_values.append(value)

    sns.barplot(
        x=bar_categories,
        y=bar_values,
        hue=bar_labels,
        hue_order=list(legend.values()),
        order=categories,
        ax=ax,
        legend=False,
    )
    ax.set_ylabel(detail.label)
    if detail.of_target:
        ax.axhline(1.0, color='gray', linestyle='--', linewidth=1)
        ax.yaxis.set_major_formatter(FuncFormatter(_times))
    else:
        for container in ax.containers:
            if isinstance(container, BarContainer):
                ax.bar_label(container, fmt='%.0f', fontsize=8, padding=2)


def _subplots(figure: Figure, columns: list[str]) -> tuple[MplFigure, list[Axes]]:
    """The chart's axes on top and a shorter one for each of its panels, all over the same categories."""
    sns.set_theme(style='darkgrid')
    heights = [6, *(2.5 for _ in figure.details)]
    fig, axes = plt.subplots(
        len(heights),
        figsize=(max(8, 1.6 * len(columns)), sum(heights)),
        sharex=True,
        squeeze=False,
        gridspec_kw={'height_ratios': heights},
    )
    return fig, list(axes[:, 0])


def plot(figure: Figure, found: Newest, path: pathlib.Path) -> None:
    """Draws a figure and its panels into a PNG file, skipping one without a value."""
    categories, libraries, relative = _relative(figure)
    if len(relative) == 0:
        return

    versions = found.libraries
    order = [library for library in LIBRARIES if library in libraries]
    legend = {library: _label(library, versions) for library in order}
    columns = list(dict.fromkeys(categories))

    fig, axes = _subplots(figure, columns)
    ax = axes[0]

    # the bars and the baseline at 1x
    sns.barplot(
        x=categories,
        y=relative,
        hue=[_label(library, versions) for library in libraries],
        hue_order=list(legend.values()),
        order=columns,
        ax=ax,
    )
    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1)
    for detail, panel in zip(figure.details, axes[1:], strict=True):
        _detail(panel, detail, categories=columns, legend=legend)

    # the text around them
    ax.set_title(figure.title)
    ax.set_ylabel(f'{figure.measure} relative to {BASELINE}, higher is better')
    ax.yaxis.set_major_formatter(FuncFormatter(_times))
    axes[-1].tick_params(axis='x', labelrotation=20)
    ax.legend(title='library')
    fig.text(0.5, 0.01, _footer(found), ha='center', fontsize=8, color='gray', wrap=True)

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    """Draws every figure of each library's newest results into ``benchmarks/charts``."""
    mpl.use('Agg')
    CHARTS.mkdir(exist_ok=True)
    for suite, found in report.newest(RESULTS.glob('*.json')).items():
        for figure in SUITES[suite].figures(found.data):
            plot(figure, found, CHARTS / f'{figure.name}.png')
            print(f'wrote {figure.name}.png')


if __name__ == '__main__':
    main()
