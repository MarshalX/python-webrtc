# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# http://www.sphinx-doc.org/en/master/config

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

sys.path.insert(0, os.path.abspath('../..'))
sys.path.insert(0, os.path.abspath('../links'))

master_doc = 'index'

# -- Project information -----------------------------------------------------

project = 'Python WebRTC'
copyright = '2022 Il`ya (Marshal) <https://github.com/MarshalX>'
author = 'Il`ya Semyonov'

language = 'en'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_search_language = 'en'

# These folders are copied to the documentation's HTML output
html_static_path = ['_static']

# Add favicon
extensions += ['sphinx-favicon']
html_static_path += ['images']
favicons = [
    {
        'rel': 'icon',
        'static-file': 'favicon.svg',
        'type': 'image/svg+xml',
    },
    {
        'rel': 'icon',
        'sizes': '16x16',
        'static-file': 'favicon-16x16.png',
        'type': 'image/png',
    },
    {
        'rel': 'icon',
        'sizes': '32x32',
        'static-file': 'favicon-32x32.png',
        'type': 'image/png',
    },
    {
        'rel': 'apple-touch-icon',
        'sizes': '180x180',
        'static-file': 'apple-touch-icon-180x180.png',
        'type': 'image/png',
    },
]

# Add OpenGraph
extensions += ['sphinxext.opengraph']
ogp_site_url = 'https://wrtc.readthedocs.io/'
# Social preview of GitHub. I guess its lifetime link until reuploading, for example
ogp_image = 'https://repository-images.githubusercontent.com/444007147/cbcbf096-57d3-4715-93b0-4dba751db76a'

# These paths are either relative to html_static_path
# or fully qualified paths (eg. https://...)
html_css_files = [
    'css/custom.css',
]

html_title = 'Python WebRTC'
html_theme = 'furo'
html_logo = 'images/logo.png'

html_theme_options = {
    'sidebar_hide_name': True,
    'navigation_with_keys': True,
}
