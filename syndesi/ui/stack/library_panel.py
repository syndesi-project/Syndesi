# File : library_panel.py
# Author : Sébastien Deriaz
# License : GPL
"""
The component classes to drag on the canvas, one tab per collection

    Syndesi | syndesi-drivers | mypackage | Files

The Syndesi tab groups its classes by layer, the others by sub-package or file. A stack
mixes collections (a driver of a package on an IP of syndesi) : selecting a slot moves
to a tab that has something for it, and a search says what the other tabs have
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

from PySide6.QtCore import QMimeData, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QFont,
    QPainter,
    QResizeEvent,
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
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionTab,
    QStyleOptionViewItem,
    QTabBar,
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
from ..core.library import Collection, CollectionKind, Library, LibraryError
from ..style.icons import add_leading_icon, set_icon
from ..style.theme import theme
from ..style.widgets import (
    panel,
    set_tone,
)

MIME = "application/x-syndesi-component"

GROUPS = [
    (Kind.DRIVER, "Drivers", "the commands of an instrument"),
    (Kind.PROTOCOL, "Protocols", "turn frames into messages"),
    (Kind.ADAPTER, "Adapters", "the transport to the device"),
    (Kind.SUBDRIVER, "Sub-drivers", "parts of a driver"),
]


def class_from_mime(mime: QMimeData, library: Library) -> type | None:
    """Generate a class from QMimeData"""
    if not mime.hasFormat(MIME):
        return None
    name = bytes(mime.data(MIME).data()).decode()
    try:
        return library.find(name)
    except LibraryError:
        return None


_GROUP = "group:"
_CATEGORY = "category:"
_KIND_ORDER = {kind: i for i, (kind, _, _) in enumerate(GROUPS)}


def _group_kind(data: Any) -> Kind | None:
    """Kind of a group row of the library (Qt hands a StrEnum back as a str)"""
    if isinstance(data, str) and data.startswith(_GROUP):
        return Kind(data.removeprefix(_GROUP))
    return None


def _category_title(data: Any) -> str | None:
    """Title of a category row (a sub-package, a file), None for another row"""
    if isinstance(data, str) and data.startswith(_CATEGORY):
        return data.removeprefix(_CATEGORY)
    return None


def _category_label(collection: Collection, category: str) -> str:
    """waveform_generators -> waveform generators, a file name is kept as it is"""
    if not category:
        return collection.name
    if collection.kind is CollectionKind.PACKAGE:
        return category.replace("_", " ")
    return category


def _tag(info: ComponentInfo) -> str:
    """Small label after the name of a component"""
    if info.code_only:
        return "code only"
    if info.is_base_class:
        return "base class"
    return ""


def _tooltip(info: ComponentInfo, library: Library) -> str:
    lines = [info.summary]
    if info.code_only:
        lines.append(info.code_only)
    if info.is_base_class:
        lines.append("Base class : open/close/test are abstract, derive from it")
    if info.cls in library.sources:
        lines.append(f"Loaded from {library.sources[info.cls]}")
    else:
        lines.append(f"From {info.cls.__module__}")
    return "\n\n".join(line for line in lines if line)


def _missing_text(collection: Collection) -> str:
    """Rich text of a collection that can't be used"""
    if not collection.install:
        return collection.missing.replace("\n", "<br>")
    return (
        f"<b>{collection.name} isn't installed</b><br><br>"
        f"{collection.description}.<br><br>"
        f"Install it, then start syndesi ui again :<br>"
        f"<pre>{collection.install}</pre>"
    )


class _CollectionTabs(QTabBar):
    """
    One tab per collection. A collection that can't be used (a default package that
    isn't installed) is drawn disabled, but stays selectable : its tab says why

    The tabs that don't fit are hidden rather than scrolled or shortened, like in a
    browser : the selected one always stays in sight, the menu next to the tabs lists
    them all. overflow is emitted with the number of hidden tabs
    """

    overflow = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.unavailable: set[int] = set()
        self.setExpanding(False)
        self.setUsesScrollButtons(False)
        self.setDrawBase(False)
        self.setElideMode(Qt.TextElideMode.ElideNone)
        # The width comes from the panel, not from the tabs : they adapt to it
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.currentChanged.connect(lambda _: self.fit())

    def initStyleOption(self, option: QStyleOptionTab, tab_index: int) -> None:
        super().initStyleOption(option, tab_index)
        if tab_index in self.unavailable:
            option.state &= ~QStyle.StateFlag.State_Enabled

    def resizeEvent(self, event: QResizeEvent) -> None:  # pylint: disable=invalid-name
        super().resizeEvent(event)
        self.fit()

    def fit(self) -> None:
        """Show the tabs that fit, in order, the selected one first"""
        available = self.width()
        current = self.currentIndex()
        widths = [self.tabSizeHint(i).width() for i in range(self.count())]
        used = widths[current] if 0 <= current < len(widths) else 0
        visible = {current}
        for i, width in enumerate(widths):
            if i != current and used + width <= available:
                visible.add(i)
                used += width
            elif i != current:
                break
        for i in range(self.count()):
            if self.isTabVisible(i) != (i in visible):
                self.setTabVisible(i, i in visible)
        self.overflow.emit(self.count() - len(visible & set(range(self.count()))))


class _PaletteDelegate(QStyledItemDelegate):
    """
    A component : a dot of the color of its layer, its name, the docstring summary below.
    A group : its name in small capitals, in the color of the layer
    """

    def __init__(self, library: Library, parent: QWidget) -> None:
        super().__init__(parent)
        self._library = library

    # pylint: disable=too-many-statements, too-many-locals
    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: Any
    ) -> None:
        data = index.data(Qt.ItemDataRole.UserRole)
        self.initStyleOption(option, index)
        t = theme()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        group = _group_kind(data)
        category = _category_title(data)
        if (
            group is not None
            or category is not None
            or not isinstance(data, ComponentInfo)
        ):
            if group is not None:
                self._paint_group(painter, option, group)
            elif category is not None:
                self._paint_category(painter, option, category, index.data())
            painter.restore()
            return
        info: ComponentInfo = data
        text = option.text
        option.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget
        )
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
        name_rect = QRect(
            text_rect.left(), text_rect.top(), text_rect.width(), bold_metrics.height()
        )
        left_centered = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        painter.drawText(name_rect, left_centered, text)

        tag = _tag(info)
        if tag:
            small = QFont(option.font)
            small.setPointSizeF(small.pointSizeF() * 0.78)
            small.setWeight(QFont.Weight.DemiBold)
            painter.setFont(small)
            tag_metrics = painter.fontMetrics()
            x = name_rect.left() + bold_metrics.horizontalAdvance(text) + 8
            tag_rect = QRect(
                x,
                name_rect.top() + 2,
                tag_metrics.horizontalAdvance(tag) + 10,
                name_rect.height() - 4,
            )
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
            text_rect.left(),
            name_rect.bottom() + 2,
            text_rect.width(),
            painter.fontMetrics().height(),
        )
        summary = painter.fontMetrics().elidedText(
            info.summary or "", Qt.TextElideMode.ElideRight, summary_rect.width()
        )
        painter.drawText(summary_rect, left_centered, summary)
        painter.restore()

    @staticmethod
    def _paint_group(
        painter: QPainter, option: QStyleOptionViewItem, kind: Kind
    ) -> None:
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
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title
        )
        x = painter.fontMetrics().horizontalAdvance(title) + 8
        font = QFont(option.font)
        font.setPointSizeF(font.pointSizeF() * 0.85)
        painter.setFont(font)
        painter.setPen(t.faint)
        description = painter.fontMetrics().elidedText(
            description, Qt.TextElideMode.ElideRight, max(rect.width() - x, 0)
        )
        painter.drawText(
            rect.adjusted(x, 0, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            description,
        )

    @staticmethod
    def _paint_category(
        painter: QPainter, option: QStyleOptionViewItem, title: str, count: str
    ) -> None:
        """A sub-package or a file : its name in small capitals, and how many classes"""
        t = theme()
        rect = option.rect.adjusted(10, 8, -8, 0)
        font = QFont(option.font)
        font.setPointSizeF(font.pointSizeF() * 0.8)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        painter.setFont(font)
        painter.setPen(t.muted)
        left_centered = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        # A sub-package in small capitals, a file or a module name as it is written
        is_name = "." in title or "/" in title
        text = painter.fontMetrics().elidedText(
            title if is_name else title.upper(),
            Qt.TextElideMode.ElideMiddle,
            max(rect.width() - 30, 0),
        )
        painter.drawText(rect, left_centered, text)
        x = painter.fontMetrics().horizontalAdvance(text) + 8
        font = QFont(option.font)
        font.setPointSizeF(font.pointSizeF() * 0.85)
        painter.setFont(font)
        painter.setPen(t.faint)
        painter.drawText(rect.adjusted(x, 0, 0, 0), left_centered, count)

    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
        size = super().sizeHint(option, index)
        height = option.fontMetrics.height()
        data = index.data(Qt.ItemDataRole.UserRole)
        if _group_kind(data) is not None or _category_title(data) is not None:
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


class Palette(QWidget):  # pylint: disable=too-many-instance-attributes
    """The component classes, one tab per collection"""

    activated = Signal(type)
    library_changed = Signal()

    def __init__(self, library: Library) -> None:
        super().__init__()
        self.library = library
        self._filter: Callable[[type], bool] | None = None
        self._collections: list[Collection] = []
        panel(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Library")
        title.setObjectName("Heading")
        layout.addWidget(title)
        self._build_toolbar(layout)
        self._build_messages(layout)
        self._build_body(layout)
        self.refresh()

    def _build_toolbar(self, layout: QVBoxLayout) -> None:
        """API choice and Load, the tabs, the search"""
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
        menu.addAction("Folder…", self._load_folder)
        menu.addAction("Module or package…", self._load_module)
        load.setMenu(menu)
        row.addWidget(load)
        layout.addLayout(row)

        # The tabs, and a menu of every collection for when they don't all fit
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(2)
        self.tabs = _CollectionTabs()
        self.tabs.currentChanged.connect(self.refresh)
        tabs_row.addWidget(self.tabs, 1)
        self.all_tabs = QToolButton()
        set_icon(self.all_tabs, "chevron-down", "muted")
        self.all_tabs.setToolTip("Every collection of the library")
        self.all_tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.tabs.overflow.connect(self._overflow)
        self.all_tabs.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.all_tabs.setMenu(QMenu(self.all_tabs))
        self.all_tabs.menu().aboutToShow.connect(self._fill_tabs_menu)
        tabs_row.addWidget(self.all_tabs)
        layout.addLayout(tabs_row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search components")
        self.search.setClearButtonEnabled(True)
        add_leading_icon(self.search, "search")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

    def _build_messages(self, layout: QVBoxLayout) -> None:
        """What the selected slot accepts, what other tabs have, what failed to load"""
        self.hint = QLabel()
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        self.hint.hide()
        layout.addWidget(self.hint)

        # What the other tabs have for the search or the selected slot, as links
        self.elsewhere = QLabel()
        self.elsewhere.setObjectName("Muted")
        self.elsewhere.setWordWrap(True)
        self.elsewhere.linkActivated.connect(self._show_tab)
        self.elsewhere.hide()
        layout.addWidget(self.elsewhere)

        # Modules that failed to import, files skipped
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        set_tone(self.notice, "warning")
        self.notice.linkActivated.connect(self._show_problems)
        self.notice.hide()
        layout.addWidget(self.notice)

    def _build_body(self, layout: QVBoxLayout) -> None:
        """The components, or why there are none"""
        self.tree = _PaletteTree(self.library)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.empty = QLabel()
        self.empty.setObjectName("Muted")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.empty.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.empty.setContentsMargins(6, 10, 6, 6)
        self.body = QStackedWidget()
        self.body.addWidget(self.tree)
        self.body.addWidget(self.empty)
        layout.addWidget(self.body, 1)

    @property
    def async_api(self) -> bool:
        """True if the async classes are shown"""
        return self.api.currentIndex() == 1

    @property
    def current_collection(self) -> Collection | None:
        """Collection of the selected tab"""
        index = self.tabs.currentIndex()
        if 0 <= index < len(self._collections):
            return self._collections[index]
        return None

    def set_async(self, value: bool) -> None:
        """Show the sync or the async classes"""
        self.api.setCurrentIndex(1 if value else 0)

    def show_collection(self, collection: Collection) -> None:
        """Select the tab of a collection"""
        self._sync_tabs()
        if collection in self._collections:
            self.tabs.setCurrentIndex(self._collections.index(collection))

    def set_filter(
        self, accepts: Callable[[type], bool] | None, hint: str = ""
    ) -> None:
        """
        Disable the classes a selected slot doesn't accept

        If the current tab has nothing for the slot, move to the first one that has :
        the driver of a package usually sits on an adapter of syndesi
        """
        self._filter = accepts
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        self._sync_tabs()
        current = self.current_collection
        if accepts is not None and (current is None or not self._usable(current)):
            for collection in self._collections:
                if self._usable(collection):
                    self.tabs.setCurrentIndex(self._collections.index(collection))
                    break
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the list, once the current event is handled (it may come from an item)"""
        if not getattr(self, "_refresh_pending", False):
            self._refresh_pending = True
            QTimer.singleShot(0, self._rebuild)

    # ┌──────────┐
    # │ Contents │
    # └──────────┘

    def _ordered(self) -> list[Collection]:
        """Syndesi first, then the packages and folders in loading order, Files last"""
        files = [c for c in self.library.collections if c.kind is CollectionKind.FILES]
        others = [
            c for c in self.library.collections if c.kind is not CollectionKind.FILES
        ]
        return others + [c for c in files if c.classes]

    def _sync_tabs(self) -> None:
        """One tab per collection, the selected one kept if it still exists"""
        collections = self._ordered()
        if collections == self._collections:
            return
        current = self.current_collection
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        self.tabs.unavailable = set()
        for index, collection in enumerate(collections):
            self.tabs.addTab(collection.name)
            tooltip = [collection.description, collection.location or ""]
            if not collection.available:
                self.tabs.unavailable.add(index)
                tooltip = [collection.missing]
            self.tabs.setTabToolTip(index, "\n".join(line for line in tooltip if line))
        self._collections = collections
        if current in collections:
            self.tabs.setCurrentIndex(collections.index(current))
        self.tabs.blockSignals(False)
        self.tabs.fit()

    def _visible(self, info: ComponentInfo) -> bool:
        """Shown with the current API (sync or async) and search"""
        text = self.search.text().lower()
        if (
            info.kind not in (Kind.DRIVER, Kind.SUBDRIVER)
            and info.is_async != self.async_api
        ):
            return False
        return not text or text in info.name.lower() or text in info.summary.lower()

    def _enabled(self, info: ComponentInfo) -> bool:
        return not info.code_only and (self._filter is None or self._filter(info.cls))

    def _members(self, collection: Collection) -> list[ComponentInfo]:
        return [i for i in self.library_infos(collection) if self._visible(i)]

    def library_infos(self, collection: Collection) -> list[ComponentInfo]:
        """Introspected classes of a collection, in its order"""
        by_class = {i.cls: i for i in self.library.infos()}
        return [by_class[c] for c in collection.classes if c in by_class]

    def _usable(self, collection: Collection) -> bool:
        """True if the collection has something enabled for the current filter"""
        return any(self._enabled(i) for i in self._members(collection))

    def _rebuild(self) -> None:
        self._refresh_pending = False
        self._sync_tabs()
        self.tree.clear()
        collection = self.current_collection
        self._show_notice(collection)
        self._show_elsewhere(collection)
        if collection is None:
            return
        if not collection.available:
            self.empty.setText(_missing_text(collection))
            self.body.setCurrentWidget(self.empty)
            return
        self.body.setCurrentWidget(self.tree)

        members = self._members(collection)
        if collection.kind is CollectionKind.BUILTIN:
            sections = [
                (_GROUP + kind.value, name, [i for i in members if i.kind is kind])
                for kind, name, _ in GROUPS
            ]
        else:
            categories = sorted({collection.categories.get(i.cls, "") for i in members})
            sections = []
            for category in categories:
                infos = sorted(
                    (
                        i
                        for i in members
                        if collection.categories.get(i.cls, "") == category
                    ),
                    key=lambda i: (_KIND_ORDER[i.kind], i.name.lower()),
                )
                sections.append(
                    (
                        _CATEGORY + _category_label(collection, category),
                        str(len(infos)),
                        infos,
                    )
                )

        for data, text, infos in sections:
            if not infos:
                continue
            group = QTreeWidgetItem([text])
            group.setData(0, Qt.ItemDataRole.UserRole, data)
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(group)
            for info in infos:
                item = QTreeWidgetItem([info.name])
                item.setData(0, Qt.ItemDataRole.UserRole, info)
                item.setToolTip(0, _tooltip(info, self.library))
                flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
                if self._enabled(info):
                    flags |= Qt.ItemFlag.ItemIsEnabled
                item.setFlags(flags)
                group.addChild(item)
            group.setExpanded(True)

        if not self.tree.topLevelItemCount():
            self.empty.setText(
                "Nothing matches the search here."
                if self.search.text()
                else "Nothing to show."
            )
            self.body.setCurrentWidget(self.empty)

    def _show_notice(self, collection: Collection | None) -> None:
        """What couldn't be loaded in the current collection, with a link to the details"""
        parts = []
        if collection is not None and collection.errors:
            n = len(collection.errors)
            parts.append(f"{n} module{'s' if n > 1 else ''} couldn't be imported")
        if collection is not None and collection.skipped:
            n = len(collection.skipped)
            parts.append(f"{n} file{'s' if n > 1 else ''} skipped")
        if parts:
            self.notice.setText(", ".join(parts) + ' · <a href="details">details</a>')
        self.notice.setVisible(bool(parts))

    def _show_problems(self) -> None:
        collection = self.current_collection
        if collection is None:
            return
        text = []
        if collection.errors:
            text.append(
                "These modules couldn't be imported, their classes are missing :\n"
            )
            text += [
                f"{name}\n    {error}\n" for name, error in collection.errors.items()
            ]
        if collection.skipped:
            text.append(
                "These files weren't imported : they run code when imported (a script) "
                "or can't be read. Load one with Load → Python file… if it is safe :\n"
            )
            text += [f"{name}" for name in collection.skipped]
        box = QMessageBox(self)
        box.setWindowTitle(f"{collection.name} : what wasn't loaded")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Some of {collection.name} couldn't be loaded")
        box.setDetailedText("\n".join(text))
        box.exec()

    def _overflow(self, hidden: int) -> None:
        """How many tabs the menu has that the bar doesn't show"""
        self.all_tabs.setText(f"+{hidden}" if hidden else "")
        self.all_tabs.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            if hidden
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )

    def _fill_tabs_menu(self) -> None:
        menu = self.all_tabs.menu()
        menu.clear()
        for index, collection in enumerate(self._collections):
            label = collection.name
            if not collection.available:
                label += " (not installed)"
            action = menu.addAction(label, partial(self.tabs.setCurrentIndex, index))
            action.setCheckable(True)
            action.setChecked(index == self.tabs.currentIndex())

    def _show_elsewhere(self, collection: Collection | None) -> None:
        """Links to the other tabs that match the search or have something for the slot"""
        if not self.search.text() and self._filter is None:
            self.elsewhere.hide()
            return
        links = []
        for index, other in enumerate(self._collections):
            if other is collection or not other.available:
                continue
            members = self._members(other)
            n = sum(1 for i in members if self._enabled(i))
            if n:
                links.append(f'<a href="{index}">{other.name}</a> ({n})')
        if not links:
            self.elsewhere.hide()
            return
        what = "Matches" if self.search.text() else "Also compatible"
        self.elsewhere.setText(f"{what} in " + ", ".join(links))
        self.elsewhere.show()

    def _show_tab(self, link: str) -> None:
        self.tabs.setCurrentIndex(int(link))

    def _double_clicked(self, item: QTreeWidgetItem) -> None:
        info = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(info, ComponentInfo) and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.activated.emit(info.cls)

    # ┌─────────┐
    # │ Loading │
    # └─────────┘

    def load(self, spec: str) -> list[type]:
        """Load a file, a folder or a module, errors are shown to the user"""
        try:
            classes = self.library.load(spec)
        except LibraryError as e:
            QMessageBox.warning(self, "Cannot load", str(e))
            return []
        collection = self.library.collection_of(classes[0]) if classes else None
        if collection is not None:
            self.show_collection(collection)
        self.refresh()
        self.library_changed.emit()
        return classes

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load components", "", "Python files (*.py)"
        )
        if path:
            self.load(path)

    def _load_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Load the components of a folder")
        if path:
            self.load(path)

    def _load_module(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Load components",
            "Module or package, installed or on the python path\n"
            "(package, package.module or package.module:Class)",
        )
        if ok and name.strip():
            self.load(name.strip())
