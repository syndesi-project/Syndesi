# File : widgets.py
# Author : Sébastien Deriaz
# License : GPL
"""
Small widgets and helpers shared by the screens
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QSizePolicy,
    QWidget,
)

from ..core.introspection import Kind
from .theme import monospace, theme


def panel(widget: QWidget, name: str = "Panel") -> QWidget:
    """Draw a widget as a surface of the window"""
    widget.setObjectName(name)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return widget


def set_tone(label: QLabel, tone: str) -> None:
    """Color of a label carrying a state : '', 'muted', 'ok', 'error' or 'warning'"""
    if label.property("tone") != tone:
        label.setProperty("tone", tone)
        label.style().unpolish(label)
        label.style().polish(label)


def shadow(widget: QWidget) -> None:
    """Soft shadow under a card"""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(22)
    effect.setOffset(0, 3)
    effect.setColor(theme().shadow())
    widget.setGraphicsEffect(effect)


def section(text: str) -> QLabel:
    """Small uppercase heading of a group of fields"""
    label = QLabel(text.upper())
    label.setObjectName("Section")
    return label


def kind_badge(kind: Kind, small: bool = False) -> QLabel:
    """Colored label with the layer name"""
    label = QLabel(kind.value.upper())
    # Colored by the stylesheet, so that it follows a change of theme
    label.setObjectName("Badge")
    label.setProperty("kind", kind.name.lower())
    label.setProperty("small", small)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
    return label


def type_chip(text: str) -> QLabel:
    """Monospace label of a type"""
    label = QLabel(text)
    label.setObjectName("Chip")
    label.setFont(monospace(0.85))
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
    return label


CARD_WIDTH = 340


def fit_height(widget: QWidget, width: int = CARD_WIDTH) -> None:
    """
    Fixed width, and the height the wrapped labels need at that width : a layout only
    asks a widget aligned in it for its sizeHint, which ignores the word wrap
    """
    widget.setFixedWidth(width)
    layout = widget.layout()
    if layout is not None:
        layout.activate()
        height = layout.heightForWidth(width) if layout.hasHeightForWidth() else -1
        widget.setFixedHeight(max(height, layout.minimumSize().height()))


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
