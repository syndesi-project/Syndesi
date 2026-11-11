# File : object_tree.py
# Author : Sébastien Deriaz
# License : GPL
"""
Tree of the components that exist once the stack is built (see core.runtime)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ..core.runtime import Role, RuntimeItem
from ..style.theme import theme


class ObjectTree(QTreeWidget):
    """One row per component, emits selected(RuntimeItem)"""

    selected = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderLabels(["Component", "Where"])
        self.setColumnWidth(0, 200)
        self._rows: dict[int, QTreeWidgetItem] = {}
        self.currentItemChanged.connect(self._current_changed)

    def show_runtime(self, root: RuntimeItem) -> None:
        """Show a new build, its top selected"""
        self.clear()
        self._rows.clear()
        self._add(root, None)
        self.expandAll()
        self.select(root)

    def add(self, item: RuntimeItem) -> None:
        """Add a component found later (and the ones below it), under its parent"""
        if id(item.instance) in self._rows:
            return
        parent = self._rows.get(id(item.parent.instance)) if item.parent else None
        self._add(item, parent)
        if parent is not None:
            parent.setExpanded(True)

    def select(self, item: RuntimeItem) -> None:
        """Select a component"""
        row = self._rows.get(id(item.instance))
        if row is not None:
            self.setCurrentItem(row)

    def current(self) -> RuntimeItem | None:
        """Selected component"""
        row = self.currentItem()
        return None if row is None else _item(row)

    def set_open_states(self, states: dict[str, bool]) -> None:
        """A dot after the adapters : ● open, ○ closed"""
        for row in self._rows.values():
            item = _item(row)
            if item.label in states:
                is_open = states[item.label]
                row.setText(0, f"{item.label}  {'●' if is_open else '○'}")
                row.setToolTip(1, "open" if is_open else "closed")

    def retheme(self) -> None:
        """Colors of a new theme"""
        for row in self._rows.values():
            row.setForeground(0, theme().kind(_item(row).kind))

    def _add(self, item: RuntimeItem, parent: QTreeWidgetItem | None) -> None:
        where = "top" if item.role is Role.TOP else item.path
        if item.role not in (Role.TOP, Role.EXTERNAL):
            where += f" · {item.role.value}"
        row = QTreeWidgetItem([item.label, where])
        row.setData(0, Qt.ItemDataRole.UserRole, item)
        row.setForeground(0, theme().kind(item.kind))
        font = row.font(0)
        font.setBold(item.role is Role.TOP)
        font.setItalic(item.role is Role.INTERNAL)
        row.setFont(0, font)
        row.setToolTip(0, f"{item.cls.__module__}.{item.cls.__qualname__}")
        if parent is None:
            self.addTopLevelItem(row)
        else:
            parent.addChild(row)
        self._rows[id(item.instance)] = row
        for child in item.children:
            self._add(child, row)

    def _current_changed(self, row: QTreeWidgetItem | None, _: Any = None) -> None:
        if row is not None:
            self.selected.emit(_item(row))


def _item(row: QTreeWidgetItem) -> RuntimeItem:
    item: RuntimeItem = row.data(0, Qt.ItemDataRole.UserRole)
    return item
