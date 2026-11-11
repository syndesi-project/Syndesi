# File : theme.py
# Author : Sébastien Deriaz
# License : GPL
"""
Look of the GUI : design tokens, fonts and the application stylesheet

Everything visual is decided here, the screens only name their widgets :

- ``Panel``      a surface (library, inspector, log, ...)
- ``Card``       a component of the stack, ``InternalCard``, ``Slot``, ``Pill``
- ``Primary``    the main button of a screen, ``Success`` / ``Danger`` for open / close
- ``Outline``    a secondary navigation button, ``size='large'`` for the header ones
- ``Heading``, ``Title``, ``Section``, ``Muted`` labels, and the ``tone`` property
  ('muted', 'ok', 'error', 'warning') for a label whose color carries a state

One color per layer (adapter, protocol, driver), the same everywhere, so that the user
associates a color with each. Fonts : Inter for the interface, JetBrains Mono for the
data, both bundled (SIL Open Font License, see assets/fonts)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import cache
from importlib import resources
from string import Template

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QStyleFactory,
)

from ..core.introspection import Kind
from .icons import icon_file, refresh_icons
from .system import SystemWatcher, system_prefers_dark

UI_FAMILY = "Inter"
MONO_FAMILY = "JetBrains Mono"


class EntryStyle(Enum):
    """Color of a row of the event table"""

    READ = "read"
    READ_FAIL = "read_fail"
    WRITE = "write"
    OPENED = "opened"
    CLOSED = "closed"
    COMMAND = "command"
    RESULT = "result"
    ERROR = "error"
    INFO = "info"
    EVENT = "event"


def _mix(a: QColor, b: QColor, ratio: float) -> QColor:
    """a blended with b, ratio of b"""
    return QColor(
        round(a.red() + (b.red() - a.red()) * ratio),
        round(a.green() + (b.green() - a.green()) * ratio),
        round(a.blue() + (b.blue() - a.blue()) * ratio),
    )


def _rgba(color: QColor, alpha: float) -> str:
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


@cache
def _stylesheet_template() -> str:
    """style.qss, $name being the tokens filled in by Theme.stylesheet"""
    return (resources.files("syndesi.ui.style") / "style.qss").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Theme:
    """Design tokens of a light or a dark theme"""

    dark: bool

    # Surfaces, from the back to the front

    @property
    def background(self) -> QColor:
        """Window, behind the panels"""
        return QColor("#0f1115" if self.dark else "#eef0f3")

    @property
    def surface(self) -> QColor:
        """Panels"""
        return QColor("#171a1f" if self.dark else "#ffffff")

    @property
    def raised(self) -> QColor:
        """Cards, buttons, menus"""
        return QColor("#1f232a" if self.dark else "#ffffff")

    @property
    def field(self) -> QColor:
        """Inputs"""
        return QColor("#13161a" if self.dark else "#f7f8fa")

    @property
    def hover(self) -> QColor:
        """Hovered items and buttons"""
        return QColor("#272c34" if self.dark else "#eef0f3")

    @property
    def border(self) -> QColor:
        """Panels and separators"""
        return QColor("#252931" if self.dark else "#e3e6ea")

    @property
    def border_strong(self) -> QColor:
        """Inputs and buttons"""
        return QColor("#333943" if self.dark else "#d3d7dd")

    # Text

    @property
    def text(self) -> QColor:
        """Main text"""
        return QColor("#e6e8ec" if self.dark else "#16191f")

    @property
    def muted(self) -> QColor:
        """Secondary text"""
        return QColor("#8d94a0" if self.dark else "#667080")

    @property
    def faint(self) -> QColor:
        """Disabled text, placeholders"""
        return QColor("#575e69" if self.dark else "#a8aeb8")

    # States

    @property
    def accent(self) -> QColor:
        """Selection, focus, primary actions"""
        return QColor("#5b7cfa" if self.dark else "#3d5ef0")

    @property
    def accent_hover(self) -> QColor:
        """Primary button hovered"""
        return _mix(self.accent, QColor("white"), 0.12)

    @property
    def ok(self) -> QColor:
        """Success, open"""
        return QColor("#34c77b" if self.dark else "#16a35a")

    @property
    def error(self) -> QColor:
        """Error, closed"""
        return QColor("#f05d6c" if self.dark else "#dc3545")

    @property
    def warning(self) -> QColor:
        """Warning"""
        return QColor("#f0b03c" if self.dark else "#c27c0e")

    # Layers

    def kind(self, kind: Kind) -> QColor:
        """Color of a layer"""
        colors = {
            Kind.ADAPTER: "#38bdf8" if self.dark else "#0b8fd0",
            Kind.PROTOCOL: "#f6a23b" if self.dark else "#d97a06",
            Kind.DRIVER: "#b48cfa" if self.dark else "#8b4fe8",
            Kind.SUBDRIVER: "#f077c0" if self.dark else "#d6409a",
        }
        return QColor(colors[kind])

    def kind_soft(self, kind: Kind) -> QColor:
        """Background tint of a layer"""
        color = self.kind(kind)
        color.setAlphaF(0.16 if self.dark else 0.12)
        return color

    def entry(self, style: EntryStyle) -> QColor:
        """Text color of a row of the event table"""
        colors = {
            EntryStyle.READ: "#7cb7ff" if self.dark else "#1f5fbf",
            EntryStyle.READ_FAIL: self.error.name(),
            EntryStyle.WRITE: "#6fd39c" if self.dark else "#17804a",
            EntryStyle.OPENED: self.ok.name(),
            EntryStyle.CLOSED: self.error.name(),
            EntryStyle.COMMAND: "#c4a8ff" if self.dark else "#6b3fd0",
            EntryStyle.RESULT: "#7cb7ff" if self.dark else "#1f5fbf",
            EntryStyle.ERROR: self.error.name(),
            EntryStyle.INFO: self.muted.name(),
            EntryStyle.EVENT: self.faint.name() if self.dark else "#9aa1ab",
        }
        return QColor(colors[style])

    def shadow(self) -> QColor:
        """Shadow of the cards"""
        return QColor(0, 0, 0, 110 if self.dark else 30)

    # Stylesheet

    def stylesheet(self) -> str:
        """Application stylesheet"""
        c = {
            "bg": self.background.name(),
            "surface": self.surface.name(),
            "raised": self.raised.name(),
            "field": self.field.name(),
            "hover": self.hover.name(),
            "pressed": _mix(self.hover, self.text, 0.08).name(),
            "border": self.border.name(),
            "strong": self.border_strong.name(),
            "strong_hover": _mix(self.border_strong, self.text, 0.25).name(),
            "text": self.text.name(),
            "muted": self.muted.name(),
            "faint": self.faint.name(),
            "accent": self.accent.name(),
            "accent_hover": self.accent_hover.name(),
            "accent_soft": _rgba(self.accent, 0.22 if self.dark else 0.12),
            "ok": self.ok.name(),
            "ok_soft": _rgba(self.ok, 0.14 if self.dark else 0.10),
            "ok_border": _rgba(self.ok, 0.45),
            "error": self.error.name(),
            "error_soft": _rgba(self.error, 0.14 if self.dark else 0.09),
            "error_border": _rgba(self.error, 0.45),
            "warning": self.warning.name(),
            "scroll": _rgba(self.text, 0.16 if self.dark else 0.20),
            "scroll_hover": _rgba(self.text, 0.30),
            "down": icon_file("chevron-down", self.muted.name()),
            "up": icon_file("chevron-up", self.muted.name()),
            "right": icon_file("chevron-right", self.muted.name()),
            "check": icon_file("check", "#ffffff"),
        }
        return Template(_stylesheet_template()).substitute(c) + self._badges()

    def _badges(self) -> str:
        """Layer badges : the color of the layer on a tint of it"""
        rules = [
            "QLabel#Badge { border-radius: 4px; padding: 2px 6px; font-weight: 700;"
            " font-size: 7.5pt; letter-spacing: 0.5px; }",
            'QLabel#Badge[small="true"] { font-size: 7pt; }',
        ]
        for kind in Kind:
            soft = self.kind_soft(kind)
            rules.append(
                f'QLabel#Badge[kind="{kind.name.lower()}"] {{ color: {self.kind(kind).name()};'
                f" background: {_rgba(soft, round(soft.alphaF(), 2))}; }}"
            )
        return "\n".join(rules) + "\n"

    def palette(self) -> QPalette:
        """Palette matching the tokens, for what the stylesheet doesn't cover"""
        palette = QPalette()
        roles = {
            QPalette.ColorRole.Window: self.background,
            QPalette.ColorRole.WindowText: self.text,
            QPalette.ColorRole.Base: self.field,
            QPalette.ColorRole.AlternateBase: _mix(self.surface, self.text, 0.025),
            QPalette.ColorRole.ToolTipBase: self.raised,
            QPalette.ColorRole.ToolTipText: self.text,
            QPalette.ColorRole.Text: self.text,
            QPalette.ColorRole.Button: self.raised,
            QPalette.ColorRole.ButtonText: self.text,
            QPalette.ColorRole.Highlight: self.accent,
            QPalette.ColorRole.HighlightedText: QColor("white"),
            QPalette.ColorRole.PlaceholderText: self.faint,
            QPalette.ColorRole.Link: self.accent,
            QPalette.ColorRole.Mid: self.border_strong,
            QPalette.ColorRole.Midlight: self.border,
        }
        for role, color in roles.items():
            palette.setColor(role, color)
        for role in (
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
            QPalette.ColorRole.WindowText,
        ):
            palette.setColor(QPalette.ColorGroup.Disabled, role, self.faint)
        return palette




_theme: Theme | None = None
_fonts_loaded = False


def theme() -> Theme:
    """Current theme"""
    return _theme if _theme is not None else Theme(dark=False)


def load_fonts() -> bool:
    """Register the bundled fonts, True if Inter is available"""
    global _fonts_loaded  # pylint: disable=global-statement
    if not _fonts_loaded:
        _fonts_loaded = True
        directory = resources.files("syndesi.ui.style") / "fonts"
        for entry in directory.iterdir():
            if entry.name.endswith(".ttf"):
                with resources.as_file(entry) as path:
                    QFontDatabase.addApplicationFont(str(path))
    return UI_FAMILY in QFontDatabase.families()


class ThemeEvents(QObject):
    """Emits changed when the theme is switched while the application runs"""

    changed = Signal()


_events: ThemeEvents | None = None


def events() -> ThemeEvents:
    """Signals of the theme"""
    global _events  # pylint: disable=global-statement
    if _events is None:
        _events = ThemeEvents()
    return _events


def _use(app: QApplication, dark: bool) -> None:
    """Switch the palette, the stylesheet and the icons to a theme"""
    global _theme  # pylint: disable=global-statement
    switching = _theme is not None and _theme.dark != dark
    _theme = Theme(dark=dark)
    app.setPalette(_theme.palette())
    app.setStyleSheet(_theme.stylesheet())
    if switching:
        refresh_icons()
        events().changed.emit()


def apply(app: QApplication, mode: str = "auto") -> Theme:
    """
    Set the style, the fonts, the palette and the stylesheet. mode : 'light', 'dark',
    or 'auto' to follow the system, also when it changes while the application runs
    """
    app.setStyle(QStyleFactory.create("Fusion"))
    if load_fonts():
        font = QFont(UI_FAMILY, 10)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)
    if mode == "auto":
        _use(app, system_prefers_dark())
        if app.findChild(SystemWatcher) is None:
            SystemWatcher(app, lambda dark: _use(app, dark))
    else:
        _use(app, mode == "dark")
    return theme()


def monospace(scale: float = 1.0) -> QFont:
    """Font of the data, the event table and the code"""
    if MONO_FAMILY in QFontDatabase.families():
        font = QFont(MONO_FAMILY, 10)
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if scale != 1.0:
        font.setPointSizeF(font.pointSizeF() * scale)
    return font
