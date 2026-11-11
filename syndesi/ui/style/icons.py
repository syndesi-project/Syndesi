# File : icons.py
# Author : Sébastien Deriaz
# License : GPL
"""
Line icons of the GUI

Each icon is the inside of a 24×24 SVG drawn with a 2 px stroke. The color is baked in
when the file is written (in a temporary directory) : Qt stylesheets can only reference
files, and a QIcon needs one file per color anyway (normal, disabled)
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
import weakref
from pathlib import Path
from typing import Any

import shiboken6
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

_PATHS: dict[str, str] = {
    "layers": '<path d="M12 3 21 8l-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "play": '<path d="M7 4.5v15l12-7.5z" fill="{color}"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "more": '<circle cx="5.5" cy="12" r="1.2" fill="{color}"/><circle cx="12" cy="12" r="1.2" '
    'fill="{color}"/><circle cx="18.5" cy="12" r="1.2" fill="{color}"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/>'
    '<path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    "file-plus": '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4M12 11v6M9 14h6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1'
    '-2-2z"/>',
    "folder-plus": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0'
    ' 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h7M8 21v-7h8v7"/>',
    "arrow-left": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-up": '<path d="m6 15 6-6 6 6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "send": '<path d="M4 12h13M12 6l6 6-6 6"/><path d="M4 6v12" opacity=".5"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "swap": '<path d="M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4"/>',
    "plug": '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "filter": '<path d="M4 5h16l-6 7.5V19l-4-2v-4.5z"/>',
    "alert": '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>',
}

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

_directory: Path | None = None


def _cache() -> Path:
    global _directory  # pylint: disable=global-statement
    if _directory is None:
        _directory = Path(tempfile.mkdtemp(prefix="syndesi-icons-"))
        atexit.register(shutil.rmtree, _directory, True)
    return _directory


def icon_file(name: str, color: str) -> str:
    """Path of an SVG file of the icon in a color (#rrggbb), for stylesheets"""
    path = _cache() / f"{name}-{color.lstrip('#')}.svg"
    if not path.exists():
        body = _PATHS[name].replace("{color}", color)
        path.write_text(_SVG.format(color=color, body=body), encoding="utf-8")
    return path.as_posix()


# Colors an icon can take, resolved against the current theme when it is drawn
ROLES = ("text", "muted", "faint", "accent", "ok", "error", "warning", "white")


def _resolve(color: str | None) -> str:
    """#rrggbb of a role (or of a color given as #rrggbb)"""
    # pylint: disable=import-outside-toplevel,cyclic-import
    from .theme import theme

    if color is None:
        color = "text"
    if color == "white":
        return "#ffffff"
    if color in ROLES:
        return str(getattr(theme(), color).name())
    return color


def icon(name: str, color: str | None = None) -> QIcon:
    """
    A QIcon in a color role of the theme (the text color by default), faded when
    disabled. It keeps the colors of the theme current when it is made : use set_icon
    for an icon that must follow a change of theme
    """
    result = QIcon()
    result.addFile(icon_file(name, _resolve(color)), QSize(), QIcon.Mode.Normal)
    result.addFile(icon_file(name, _resolve("faint")), QSize(), QIcon.Mode.Disabled)
    return result


# Every widget or action given an icon by set_icon / set_pixmap, to draw it again in
# the colors of a new theme
_registry: list[tuple[weakref.ref[Any], str, str | None, int]] = []


def _register(target: Any, name: str, color: str | None, size: int) -> None:
    # The canvas is redrawn often : forget the widgets deleted since
    if len(_registry) > 400:
        _registry[:] = [
            entry for entry in _registry
            if (alive := entry[0]()) is not None and shiboken6.isValid(alive)
        ]
    _registry.append((weakref.ref(target), name, color, size))


def set_icon(target: Any, name: str, color: str | None = None) -> Any:
    """target.setIcon(icon(name, color)), redrawn when the theme changes. Returns target"""
    target.setIcon(icon(name, color))
    _register(target, name, color, 0)
    return target


def set_pixmap(label: Any, name: str, color: str | None = None, size: int = 16) -> Any:
    """label.setPixmap(...) of an icon, redrawn when the theme changes. Returns label"""
    label.setPixmap(icon(name, color).pixmap(size, size))
    _register(label, name, color, size)
    return label


def add_leading_icon(line_edit: Any, name: str, color: str | None = "muted") -> None:
    """An icon at the start of a line edit (a search field, ...)"""
    action = line_edit.addAction(icon(name, color), line_edit.ActionPosition.LeadingPosition)
    set_icon(action, name, color)


def refresh_icons() -> None:
    """Draw the registered icons again, in the colors of the current theme"""
    alive = []
    for reference, name, color, size in _registry:
        target = reference()
        if target is None or not shiboken6.isValid(target):
            continue
        try:
            if size:
                target.setPixmap(icon(name, color).pixmap(size, size))
            else:
                target.setIcon(icon(name, color))
        except RuntimeError:
            continue
        alive.append((reference, name, color, size))
    _registry[:] = alive


def names() -> list[str]:
    """Available icons"""
    return list(_PATHS)
