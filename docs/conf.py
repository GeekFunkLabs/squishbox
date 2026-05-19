# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, os.path.abspath('../src'))

ROOT = Path(__file__).resolve().parent.parent
with open(ROOT / "pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'SquishBox'
copyright = '2026, Bill Peterson'
author = 'Bill Peterson'
release = pyproject["project"]["version"]

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
]

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']
html_sidebars = {
    '**': [
        'about.html',
        'searchfield.html',
        'navigation.html',
    ]
}
html_theme_options = {
    'github_user': 'GeekFunkLabs',
    'github_repo': 'squishbox',
}
