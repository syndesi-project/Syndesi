# Configuration file for the Sphinx documentation builder
#
# Structure follows Diátaxis (https://diataxis.fr) :
#   tutorials/    learning, step by step
#   how-to/       recipes for a precise goal
#   explanation/  how and why Syndesi works the way it does
#   reference/    API, CLI and defaults

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

# -- Project information -------------------------------------------------------

project = "Syndesi"
author = "Sébastien Deriaz"
copyright = "2023–2026, Sébastien Deriaz"

try:
    release = _version("syndesi")
except PackageNotFoundError:
    release = "dev"
version = ".".join(release.split(".")[:2])

# -- General configuration -----------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "sphinx_design",
]

root_doc = "index"
templates_path = ["_templates"]
exclude_patterns = ["_build"]

# Shown in short form ("IP" rather than "syndesi.adapters.ip.IP")
add_module_names = False
python_use_unqualified_type_names = True

# -- Autodoc -------------------------------------------------------------------

autoclass_content = "class"
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented_params"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_mock_imports = ["PySide6"]

napoleon_numpy_docstring = True
napoleon_google_docstring = False
napoleon_use_param = True
napoleon_use_rtype = True

typehints_use_signature = False
typehints_use_signature_return = False
always_document_param_types = False

# The docstrings name types informally ("float, None or DEFAULT"), not every one of
# them can be resolved
nitpicky = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}

# -- Copy button : don't copy prompts and outputs ------------------------------

copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True
copybutton_only_copy_prompt_lines = False

# -- HTML output ---------------------------------------------------------------

html_theme = "furo"
html_title = "Syndesi"
html_short_title = "Syndesi"
html_static_path = ["_static"]
html_css_files = [
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;600&display=swap",
    "syndesi.css",
]
html_favicon = "_static/favicon.svg"
html_show_sourcelink = False
html_copy_source = False

# Colors are the ones of the Syndesi GUI (syndesi/ui/style/theme.py) : an indigo
# accent, and one color per layer (adapter, protocol, driver), see _static/syndesi.css
_FONT = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
_MONO = '"JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace'

html_theme_options = {
    "light_logo": "logo-light.svg",
    "dark_logo": "logo-dark.svg",
    "sidebar_hide_name": True,
    "navigation_with_keys": True,
    "top_of_page_buttons": ["view"],
    "source_repository": "https://github.com/syndesi-project/Syndesi/",
    "source_branch": "main",
    "source_directory": "docs/source/",
    "light_css_variables": {
        "font-stack": _FONT,
        "font-stack--monospace": _MONO,
        "font-stack--headings": _FONT,
        "color-brand-primary": "#3d5ef0",
        "color-brand-content": "#3d5ef0",
        "color-brand-visited": "#3d5ef0",
        "color-api-name": "#3d5ef0",
        "color-api-pre-name": "#667080",
        "color-highlighted-background": "#e8ecfe",
    },
    "dark_css_variables": {
        "color-brand-primary": "#8ba0ff",
        "color-brand-content": "#8ba0ff",
        "color-brand-visited": "#8ba0ff",
        "color-api-name": "#8ba0ff",
        "color-api-pre-name": "#8d94a0",
        "color-background-primary": "#0f1115",
        "color-background-secondary": "#14171c",
        "color-background-hover": "#1f232a",
        "color-background-border": "#252931",
        "color-highlighted-background": "#1f2747",
    },
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/syndesi-project/Syndesi",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" stroke-width="0" '
                'viewBox="0 0 16 16"><path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 '
                "8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01"
                ".37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01"
                " 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-"
                ".89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2"
                ".82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 "
                "1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25"
                ".54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016"
                ' 8c0-4.42-3.58-8-8-8z"></path></svg>'
            ),
            "class": "",
        },
    ],
}

pygments_style = "friendly"
pygments_dark_style = "github-dark"

# -- Other formats -------------------------------------------------------------

epub_show_urls = "footnote"
