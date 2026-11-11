# File : library_panel.py
# Author : Sébastien Deriaz
# License : GPL
"""
The component classes, grouped by layer, to drag on the canvas
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QMimeData, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QFont,
    QPainter,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.introspection import (
    ComponentInfo,
    Kind,
)
from ..core.library import Library, LibraryError
from ..style.icons import add_leading_icon, set_icon
from ..style.theme import theme
from ..style.widgets import (
    panel,
)

MIME = "application/x-syndesi-component"

GROUPS = [
    (Kind.DRIVER, "Drivers", "the commands of an instrument"),
    (Kind.PROTOCOL, "Protocols", "turn frames into messages"),
    (Kind.ADAPTER, "Adapters", "the transport to the device"),
    (Kind.SUBDRIVER, "Sub-drivers", "parts of a driver"),
]


def class_from_mime(mime: QMimeData, library: Library) -> type | None:
    if not mime.hasFormat(MIME):
        return None
    name = bytes(mime.data(MIME).data()).decode()
    try:
        return library.find(name)
    except LibraryError:
        return None


_GROUP = "group:"


def _group_kind(data: Any) -> Kind | None:
    """Kind of a group row of the library (Qt hands a StrEnum back as a str)"""
    if isinstance(data, str) and data.startswith(_GROUP):
        return Kind(data.removeprefix(_GROUP))
    return None


def _tag(info: ComponentInfo, library: Library) -> str:
    """Small label after the name of a component"""
    if info.code_only:
        return "code only"
    if info.is_base_class:
        return "base class"
    if info.cls in library.sources:
        return "loaded"
    return ""


def _tooltip(info: ComponentInfo, library: Library) -> str:
    lines = [info.summary]
    if info.code_only:
        lines.append(info.code_only)
    if info.is_base_class:
        lines.append("Base class : open/close/test are abstract, derive from it")
    if info.cls in library.sources:
        lines.append(f"Loaded from {library.sources[info.cls]}")
    return "\n\n".join(line for line in lines if line)


class _PaletteDelegate(QStyledItemDelegate):
    """
    A component : a dot of the color of its layer, its name, the docstring summary below.
    A group : its name in small capitals, in the color of the layer
    """

    def __init__(self, library: Library, parent: QWidget) -> None:
        super().__init__(parent)
        self._library = library


    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        data = index.data(Qt.ItemDataRole.UserRole)
        self.initStyleOption(option, index)
        t = theme()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        group = _group_kind(data)
        if group is not None or not isinstance(data, ComponentInfo):
            if group is not None:
                self._paint_group(painter, option, group)
            painter.restore()
            return
        info: ComponentInfo = data
        text = option.text
        option.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        rect = option.rect.adjusted(10, 5, -8, -5)

        dot = t.kind(info.kind)
        if not enabled:
            dot.setAlphaF(0.3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot)
        metrics = option.fontMetrics
        painter.drawEllipse(rect.left(), rect.top() + metrics.height() // 2 - 3, 7, 7)

        text_rect = rect.adjusted(16, 0, 0, 0)
        main = t.text if enabled else t.faint
        muted = t.muted if enabled else t.faint
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(main)
        bold_metrics = painter.fontMetrics()
        name_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), bold_metrics.height())
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

        tag = _tag(info, self._library)
        if tag:
            small = QFont(option.font)
            small.setPointSizeF(small.pointSizeF() * 0.78)
            small.setWeight(QFont.Weight.DemiBold)
            painter.setFont(small)
            tag_metrics = painter.fontMetrics()
            x = name_rect.left() + bold_metrics.horizontalAdvance(text) + 8
            tag_rect = QRect(x, name_rect.top() + 2, tag_metrics.horizontalAdvance(tag) + 10,
                             name_rect.height() - 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(t.hover)
            painter.drawRoundedRect(tag_rect, 4, 4)
            painter.setPen(muted)
            painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag)

        small = QFont(option.font)
        small.setPointSizeF(small.pointSizeF() * 0.9)
        painter.setFont(small)
        painter.setPen(muted)
        summary_rect = QRect(
            text_rect.left(), name_rect.bottom() + 2, text_rect.width(), painter.fontMetrics().height()
        )
        summary = painter.fontMetrics().elidedText(
            info.summary or "", Qt.TextElideMode.ElideRight, summary_rect.width()
        )
        painter.drawText(summary_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, summary)
        painter.restore()

    @staticmethod
    def _paint_group(painter: QPainter, option: QStyleOptionViewItem, kind: Kind) -> None:
        t = theme()
        name, description = next((n, d) for k, n, d in GROUPS if k is kind)
        rect = option.rect.adjusted(10, 8, -8, 0)
        font = QFont(option.font)
        font.setPointSizeF(font.pointSizeF() * 0.8)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        painter.setFont(font)
        painter.setPen(t.kind(kind))
        title = name.upper()
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        x = painter.fontMetrics().horizontalAdvance(title) + 8
        font = QFont(option.font)
        font.setPointSizeF(font.pointSizeF() * 0.85)
        painter.setFont(font)
        painter.setPen(t.faint)
        description = painter.fontMetrics().elidedText(
            description, Qt.TextElideMode.ElideRight, max(rect.width() - x, 0)
        )
        painter.drawText(rect.adjusted(x, 0, 0, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, description)

    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
        size = super().sizeHint(option, index)
        height = option.fontMetrics.height()
        if _group_kind(index.data(Qt.ItemDataRole.UserRole)) is not None:
            return QSize(size.width(), height + 14)
        return QSize(size.width(), int(height * 2.4) + 10)


class _PaletteTree(QTreeWidget):
    """Draggable rows, see _PaletteDelegate"""

    def __init__(self, library: Library) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setItemsExpandable(False)
        self.setItemDelegate(_PaletteDelegate(library, self))
        self.setMouseTracking(True)

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:  # type: ignore[override]
        mime = QMimeData()
        info = items[0].data(0, Qt.ItemDataRole.UserRole) if items else None
        if isinstance(info, ComponentInfo):
            mime.setData(MIME, info.qualified_name.encode())
            mime.setText(info.name)
        return mime


class Palette(QWidget):
    """The component classes, grouped by layer"""

    activated = Signal(type)
    library_changed = Signal()

    def __init__(self, library: Library) -> None:
        super().__init__()
        self.library = library
        self._filter: Callable[[type], bool] | None = None
        panel(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Library")
        title.setObjectName("Heading")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.api = QComboBox()
        self.api.addItems(["Sync API", "Async API"])
        self.api.setToolTip(
            "Syndesi has a sync and an async version of every adapter and protocol\n"
            "(IP / AsyncIP, SCPI / AsyncSCPI...). They can't be mixed in a stack"
        )
        self.api.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.api, 1)
        load = QToolButton()
        load.setText("Load")
        set_icon(load, "folder-plus")
        load.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        load.setToolTip("Add your own drivers, protocols or adapters")
        load.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(load)
        menu.addAction("Python file…", self._load_file)
        menu.addAction("Module…", self._load_module)
        load.setMenu(menu)
        row.addWidget(load)
        layout.addLayout(row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search components")
        self.search.setClearButtonEnabled(True)
        add_leading_icon(self.search, "search")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        self.hint = QLabel()
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        self.hint.hide()
        layout.addWidget(self.hint)

        self.tree = _PaletteTree(library)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.tree, 1)

        self.refresh()

    @property
    def async_api(self) -> bool:
        """True if the async classes are shown"""
        return self.api.currentIndex() == 1

    def set_async(self, value: bool) -> None:
        """Show the sync or the async classes"""
        self.api.setCurrentIndex(1 if value else 0)

    def set_filter(self, accepts: Callable[[type], bool] | None, hint: str = "") -> None:
        """Disable the classes a selected slot doesn't accept"""
        self._filter = accepts
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the list, once the current event is handled (it may come from an item)"""
        if not getattr(self, "_refresh_pending", False):
            self._refresh_pending = True
            QTimer.singleShot(0, self._rebuild)

    def _rebuild(self) -> None:
        self._refresh_pending = False
        self.tree.clear()
        text = self.search.text().lower()
        infos = self.library.infos()
        for kind, name, _ in GROUPS:
            members = [
                i
                for i in infos
                if i.kind is kind
                and (kind in (Kind.DRIVER, Kind.SUBDRIVER) or i.is_async == self.async_api)
                and (not text or text in i.name.lower() or text in i.summary.lower())
            ]
            if not members:
                continue
            group = QTreeWidgetItem([name])
            group.setData(0, Qt.ItemDataRole.UserRole, _GROUP + kind.value)
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(group)
            for info in members:
                item = QTreeWidgetItem([info.name])
                item.setData(0, Qt.ItemDataRole.UserRole, info)
                item.setToolTip(0, _tooltip(info, self.library))
                compatible = not info.code_only and (
                    self._filter is None or self._filter(info.cls)
                )
                flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
                if compatible:
                    flags |= Qt.ItemFlag.ItemIsEnabled
                item.setFlags(flags)
                group.addChild(item)
            group.setExpanded(True)

    def _double_clicked(self, item: QTreeWidgetItem) -> None:
        info = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(info, ComponentInfo) and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.activated.emit(info.cls)

    def load(self, spec: str) -> list[type]:
        """Load a file or a module, errors are shown to the user"""
        try:
            classes = self.library.load(spec)
        except LibraryError as e:
            QMessageBox.warning(self, "Cannot load", str(e))
            return []
        self.refresh()
        self.library_changed.emit()
        return classes

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load components", "", "Python files (*.py)")
        if path:
            self.load(path)

    def _load_module(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Load components", "Module (package.module or package.module:Class)"
        )
        if ok and name.strip():
            self.load(name.strip())
