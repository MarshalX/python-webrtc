#
#  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""The configuration of the Sphinx documentation, see https://www.sphinx-doc.org/en/master/usage/configuration.html."""

from __future__ import annotations

import ast
import enum
import inspect
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pygments.formatters import HtmlFormatter
from sphinx.ext.autodoc.mock import mock
from sphinxawesome_theme.postprocess import Icons

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment

sys.path.insert(0, str(Path(__file__).parents[2] / 'python-webrtc' / 'python'))

master_doc = 'index'

source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# -- Project information -----------------------------------------------------

project = 'Python WebRTC'
copyright = '2022-2026 Ilya (Marshal) 🦁'
author = 'Ilya (Marshal) 🦁'

language = 'en'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.napoleon',
    'sphinxext.opengraph',
    'sphinx_design',
    'sphinx_sitemap',
    'sphinx_favicon',
    'myst_parser',
]

DOCSEARCH_APP_ID = os.environ.get('DOCSEARCH_APP_ID')
DOCSEARCH_API_KEY = os.environ.get('DOCSEARCH_API_KEY')
DOCSEARCH_INDEX_NAME = os.environ.get('DOCSEARCH_INDEX_NAME')

if DOCSEARCH_APP_ID and DOCSEARCH_API_KEY and DOCSEARCH_INDEX_NAME:
    extensions.append('sphinx_docsearch')
    docsearch_app_id = DOCSEARCH_APP_ID
    docsearch_api_key = DOCSEARCH_API_KEY
    docsearch_index_name = DOCSEARCH_INDEX_NAME
    docsearch_placeholder = 'Search the docs'
    docsearch_max_results_per_group = 20
    docsearch_search_parameters = {'hitsPerPage': 50}
    docsearch_missing_results_url = (
        'https://github.com/MarshalX/python-webrtc/discussions/new?category=q-a&title=${query}'
    )
else:
    print(
        '[conf.py] DocSearch env vars missing - the built-in Sphinx search will be used',
        file=sys.stderr,
    )

# Headings of the included Markdown files, and names exported both by the package and their modules.
suppress_warnings = ['myst.header', 'ref.python']

# -- Pygments ---------------------------------------------------
pygments_style = 'friendly'
pygments_style_dark = 'monokai'

# -- MyST-Parser ---------------------------------------------------
myst_heading_anchors = 4
myst_enable_extensions = ['colon_fence', 'alert', 'strikethrough', 'deflist', 'html_image', 'gfm_autolink']

# -- Intersphinx ---------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}
# the build must not fail or hang when an inventory is unreachable
intersphinx_timeout = 10
intersphinx_disabled_reftypes = ['*.std:doc']

# -- Autodoc ---------------------------------------------------
# the extension is mocked, so the docs build without libwebrtc
autodoc_mock_imports = ['wrtc']
autodoc_default_options = {'members': True}
autodoc_member_order = 'bysource'
autodoc_typehints = 'description'
autodoc_typehints_description_target = 'documented_params'
napoleon_use_rtype = False

# -- Options for HTML output -------------------------------------------------

html_static_path = ['_static']
html_extra_path = ['robots.txt']

html_search_language = 'en'

html_title = project
html_theme = 'sphinxawesome_theme'
html_domain_indices = False
html_copy_source = False
html_show_sourcelink = False
html_show_sphinx = False
html_permalinks_icon = Icons.permalinks_icon

html_css_files = [
    'css/custom.css',
]

html_theme_options = {
    'show_prev_next': True,
    'awesome_external_links': True,
    'show_breadcrumbs': True,
    'show_scrolltop': True,
    'main_nav_links': {
        'Quickstart': 'quickstart',
        'Guides': 'guides/index',
        'Examples': 'examples/index',
        'API reference': 'api/index',
        'Changelog': 'change_log',
    },
    'logo_light': '_static/img/favicon.svg',
    'logo_dark': '_static/img/favicon.svg',
    'extra_header_link_icons': {
        'repository on GitHub': {
            'link': 'https://github.com/MarshalX/python-webrtc',
            'icon': (
                '<svg height="16px" style="margin-top:-2px;display:inline" viewBox="0 0 45 44" '
                'fill="currentColor" xmlns="http://www.w3.org/2000/svg">'
                '<path fill-rule="evenodd" clip-rule="evenodd" '
                'd="M22.477.927C10.485.927.76 10.65.76 22.647c0 9.596 6.223 17.736 '
                '14.853 20.608 1.087.2 1.483-.47 1.483-1.047 '
                '0-.516-.019-1.881-.03-3.693-6.04 '
                '1.312-7.315-2.912-7.315-2.912-.988-2.51-2.412-3.178-2.412-3.178-1.972-1.346.149-1.32.149-1.32 '
                '2.18.154 3.327 2.24 3.327 2.24 1.937 3.318 5.084 2.36 6.321 '
                '1.803.197-1.403.759-2.36 '
                '1.379-2.903-4.823-.548-9.894-2.412-9.894-10.734 '
                '0-2.37.847-4.31 2.236-5.828-.224-.55-.969-2.759.214-5.748 0 0 '
                '1.822-.584 5.972 2.226 '
                '1.732-.482 3.59-.722 5.437-.732 1.845.01 3.703.25 5.437.732 '
                '4.147-2.81 5.967-2.226 '
                '5.967-2.226 1.185 2.99.44 5.198.217 5.748 1.392 1.517 2.232 3.457 '
                '2.232 5.828 0 '
                '8.344-5.078 10.18-9.916 10.717.779.67 1.474 1.996 1.474 4.021 0 '
                '2.904-.027 5.247-.027 '
                '5.96 0 .58.392 1.256 1.493 1.044C37.981 40.375 44.2 32.24 44.2 '
                '22.647c0-11.996-9.726-21.72-21.722-21.72" fill="currentColor"/></svg>'
            ),
        },
        'package on PyPI': {
            'link': 'https://pypi.org/project/wrtc/',
            'icon': (
                '<svg height="16px" style="margin-top:-2px;display:inline" viewBox="0 0 24 24" '
                'fill="currentColor" xmlns="http://www.w3.org/2000/svg">'
                '<path d="M11.885.002c-.98.004-1.918.088-2.744.234-2.433.43-2.875 1.33-2.875 '
                '2.99v2.193h5.75v.73H4.108c-1.672 0-3.136 1.005-3.594 2.917-.528 2.19-.552 '
                '3.558 0 5.846.41 '
                '1.703 1.386 2.916 3.058 2.916h1.977v-2.628c0-1.9 1.644-3.574 3.594-3.574h5.746c1.6 '
                '0 2.875-1.315 2.875-2.92V3.226c0-1.558-1.314-2.728-2.875-2.988A17.99 17.99 0 0 0 '
                '11.885.002zM8.775 1.762c.595 0 1.08.492 1.08 1.097 0 .603-.485 1.09-1.08 '
                '1.09-.596 0-1.08-.487-1.08-1.09-.001-.606.484-1.097 1.08-1.097z"/>'
                '<path d="M19.132 6.149v2.556c0 1.982-1.68 3.651-3.595 3.651H9.79c-1.574 '
                '0-2.876 1.347-2.876 '
                '2.922v5.478c0 1.56 1.356 2.475 2.876 2.922 1.822.535 3.567.632 5.747 0 '
                '1.447-.419 2.875-1.263 '
                '2.875-2.922v-2.193H12.67v-.73h8.617c1.672 0 2.295-1.165 2.876-2.917.6-1.804.575-3.54 '
                '0-5.846-.414-1.664-1.201-2.917-2.876-2.917h-2.156zm-3.232 13.876c.596 0 1.08.486 '
                '1.08 1.09 0 .606-.484 '
                '1.097-1.08 1.097-.595 0-1.08-.491-1.08-1.097.001-.604.485-1.09 1.08-1.09z"/></svg>'
            ),
        },
    },
}

# -- Sitemap ---------------------------------------------------
sitemap_locales = [None]
sitemap_url_scheme = '{link}'

# -- Favicons ---------------------------------------------------
favicons = [
    {
        'rel': 'icon',
        'static-file': 'img/favicon.svg',
        'type': 'image/svg+xml',
    },
    {
        'rel': 'icon',
        'sizes': '16x16',
        'static-file': 'img/favicon-16x16.png',
        'type': 'image/png',
    },
    {
        'rel': 'icon',
        'sizes': '32x32',
        'static-file': 'img/favicon-32x32.png',
        'type': 'image/png',
    },
    {
        'rel': 'apple-touch-icon',
        'sizes': '180x180',
        'static-file': 'img/apple-touch-icon-180x180.png',
        'type': 'image/png',
    },
]

# -- Read The docs ---------------------------------------------------
html_baseurl = os.environ.get('READTHEDOCS_CANONICAL_URL', 'https://wrtc.marshal.dev/')

if os.environ.get('READTHEDOCS', '') == 'True':
    html_context = {'READTHEDOCS': True}

# -- OpenGraph ---------------------------------------------------
ogp_site_url = 'https://wrtc.marshal.dev/'
# the social preview of the GitHub repository
ogp_image = 'https://repository-images.githubusercontent.com/444007147/cbcbf096-57d3-4715-93b0-4dba751db76a'
ogp_type = 'article'
ogp_enable_meta_description = True
ogp_social_cards = {'enable': False}


def _is_camel_case(name: str) -> bool:
    return name != name.lower() and '_' not in name and not name[0].isupper()


def skip_member(_app: Sphinx, what: str, name: str, obj: object, skip: bool, _options: object) -> bool:
    """Hide the camelCase aliases of the specification names, and the per-event overloads of ``on`` and ``once``.

    The aliases are documented by their snake_case originals, the overloads by the events of the class.

    Returns:
        :obj:`bool`: Whether to skip the member.
    """
    if skip or what != 'class':
        return skip
    overloaded = name in {'on', 'once'} and not getattr(obj, '__qualname__', '').startswith('UniformEventTarget.')
    return _is_camel_case(name) or overloaded


def _literal_names(node: ast.expr, aliases: dict[str, ast.expr]) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            names.append(child.value)
        elif isinstance(child, ast.Name) and child.id in aliases:
            names.extend(_literal_names(aliases[child.id], aliases))
    return names


def _event_types(cls: type) -> dict[str, str]:
    """The event object of each event of a class, from the overloads of its ``on``."""
    tree = ast.parse(inspect.getsource(sys.modules[cls.__module__]))
    aliases = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    types: dict[str, str] = {}
    for node in tree.body:
        if not (isinstance(node, ast.ClassDef) and node.name == cls.__name__):
            continue
        for method in node.body:
            returns = getattr(method, 'returns', None)
            if not (
                isinstance(method, ast.FunctionDef)
                and method.name == 'on'
                and isinstance(returns, ast.Subscript)
                and ast.unparse(returns.value) == 'HandlerDecorator'
            ):
                continue
            annotation = method.args.args[1].annotation
            for name in _literal_names(annotation, aliases) if annotation is not None else []:
                types[name] = ast.unparse(returns.slice)
    return types


def document_events(_app: Sphinx, what: str, _name: str, obj: object, _options: object, lines: list[str]) -> None:
    """List the events of a class and their event objects, which the hidden overloads of ``on`` type."""
    events = getattr(obj, '_events', ())
    if what != 'class' or not isinstance(obj, type) or len(events) == 0:
        return

    types = _event_types(obj)
    lines.extend(['', '.. rubric:: Events', ''])
    lines.extend(f'- ``{event}``: :obj:`~webrtc.{types.get(event, "Event")}`' for event in events)
    lines.extend(['', 'Handlers are registered with :meth:`~webrtc.utils.events.UniformEventTarget.on`.', ''])


def hide_enum_signatures(
    _app: Sphinx, what: str, _name: str, obj: object, _options: object, _signature: str | None, annotation: str | None
) -> tuple[str, str | None] | None:
    """Drop the ``(*values)`` signature of enums: they are compared with, not called."""
    if what == 'class' and isinstance(obj, type) and issubclass(obj, enum.Enum):
        return '', annotation
    return None


def register_short_aliases(app: Sphinx, env: BuildEnvironment) -> None:
    """Resolve ``webrtc.X`` references to the module the object is documented in."""
    # parallel builds import the package in the workers only
    with mock(app.config.autodoc_mock_imports):
        import webrtc  # ruff: ignore[import-outside-top-level]

    py_objects = env.domains['py'].objects
    for name in webrtc.__all__:
        obj = getattr(webrtc, name, None)
        module = getattr(obj, '__module__', None)
        if not module or module == 'webrtc' or not (inspect.isclass(obj) or inspect.isfunction(obj)):
            continue
        canonical = f'{module}.{obj.__qualname__}'
        # the object and its members
        for target in [key for key in py_objects if key == canonical or key.startswith(f'{canonical}.')]:
            short = f'webrtc.{name}{target[len(canonical) :]}'
            if short not in py_objects:
                entry = py_objects[target]
                py_objects[short] = entry.__class__(entry.docname, entry.node_id, entry.objtype, aliased=True)


def disable_search_index(app: Sphinx) -> None:
    """Skip the built-in search index: DocSearch crawls the published HTML instead."""
    if 'sphinx_docsearch' in app.config.extensions and hasattr(app.builder, 'search'):
        app.builder.search = False  # type: ignore[attr-defined]


def scope_pygments_to_theme(app: Sphinx, exception: Exception | None) -> None:
    """Rewrite the Pygments stylesheet so both palettes follow the theme toggle.

    The theme emits its dark palette inside ``@media (prefers-color-scheme: dark)`` while
    switching the page on an ``html.dark`` class, so a system preference that disagrees
    with the toggle mixes the palettes. The palettes' own background is dropped: the theme
    renders code on the page background.
    """
    if exception is not None or app.builder.name not in {'html', 'dirhtml'}:
        return

    blocks = []
    for style, selector in (
        (app.config.pygments_style, 'html:not(.dark) .highlight'),
        (app.config.pygments_style_dark, 'html.dark .highlight'),
    ):
        defs = HtmlFormatter(style=style).get_style_defs(selector)
        blocks.append('\n'.join(line for line in defs.splitlines() if not line.startswith(f'{selector} {{')))

    (Path(app.outdir) / '_static' / 'pygments.css').write_text('\n'.join(blocks), encoding='UTF-8')


def setup(app: Sphinx) -> None:
    """Connects the handlers of the build events."""
    app.connect('builder-inited', disable_search_index)
    app.connect('autodoc-skip-member', skip_member)
    # after Napoleon, which connects at the default priority
    app.connect('autodoc-process-docstring', document_events, priority=600)
    app.connect('autodoc-process-signature', hide_enum_signatures)
    app.connect('env-check-consistency', register_short_aliases)
    app.connect('build-finished', scope_pygments_to_theme)
