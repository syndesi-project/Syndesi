# File : event_log.py
# Author : Sébastien Deriaz
# License : GPL
"""
Event table of the test screen

Two kinds of rows, like the previous UI :

- the main ones, always shown : what the user did (write, read, query, commands and
  their results) and the adapters opening and closing
- the events of the adapters and protocols (fragments, frames, ...), shown in gray
  when "Show events" is checked, each category can be hidden on its own

Rows are kept in timestamp order : the events arrive from the reactor thread a bit
after the action that caused them
"""

from __future__ import annotations

import bisect
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...adapters.events import (
    AdapterBufferEvent,
    AdapterClosedEvent,
    AdapterFragmentEvent,
    AdapterFrameEvent,
    AdapterOpenedEvent,
    AdapterReadEvent,
    AdapterStopConditionsUpdatedEvent,
    AdapterTimeoutUpdatedEvent,
    AdapterWriteEvent,
    SyndesiEvent,
)
from ...protocols.protocol import (
    ProtocolBufferEvent,
    ProtocolDecodeErrorEvent,
    ProtocolFrameEvent,
    ProtocolReadEvent,
    ProtocolWriteEvent,
)
from ..core.introspection import (
    Kind,
)
from ..style.icons import set_icon
from ..style.theme import EntryStyle, monospace, theme
from ..style.widgets import (
    panel,
)


class Category(Enum):
    """Event categories, each one can be hidden"""

    WRITE = "Writes"
    FRAGMENT = "Fragments"
    FRAME = "Frames"
    READ = "Reads"
    BUFFER = "Buffer"
    CONFIG = "Configuration"
    PROTOCOL = "Protocol specific"


DEFAULT_CATEGORIES = {
    Category.WRITE,
    Category.FRAGMENT,
    Category.FRAME,
    Category.READ,
    Category.PROTOCOL,
}


@dataclass
class LogEntry:
    """One row"""

    timestamp: float
    source: str  # label of the component
    kind: Kind | None
    label: str
    data: str
    style: EntryStyle
    # None for the main rows
    category: Category | None = None
    # Same key, same component : a main row and the event telling the same thing
    # (the write the user asked for and the ProtocolWriteEvent it causes), see EventLog
    key: str = ""

    @property
    def is_event(self) -> bool:
        """True for the secondary rows"""
        return self.category is not None


def _short(data: Any, limit: int = 400) -> str:
    text = repr(data)
    return text if len(text) <= limit else text[:limit] + "…"


def write_key(data: Any) -> str:
    """Key of a written payload, see LogEntry.key"""
    return "write:" + _short(data)


def read_key(data: Any) -> str:
    """Key of a payload read, see LogEntry.key"""
    return "read:" + _short(data)


def event_key(event: SyndesiEvent) -> str:
    """Key of the events a main row can duplicate"""
    match event:
        case AdapterWriteEvent():
            return write_key(event.frame.data)
        case ProtocolWriteEvent():
            return write_key(event.payload)
        case AdapterReadEvent() | ProtocolReadEvent():
            return read_key(event.frame.data)
    return ""


def describe_event(event: SyndesiEvent) -> tuple[str, str, EntryStyle, Category | None] | None:
    """(label, data, style, category) of an event, None to drop it"""
    # pylint: disable=too-many-return-statements
    gray = EntryStyle.EVENT
    match event:
        case AdapterOpenedEvent():
            return "● opened", "", EntryStyle.OPENED, None
        case AdapterClosedEvent():
            return "● closed", "", EntryStyle.CLOSED, None
        case AdapterWriteEvent():
            return "→ write", _short(event.frame.data), gray, Category.WRITE
        case AdapterFragmentEvent():
            label = "↓ frag*" if event.first else "↓ frag"
            return label, _short(event.fragment.data), gray, Category.FRAGMENT
        case AdapterFrameEvent():
            sc = event.frame.stop_condition
            reason = "(error)" if sc is None else str(sc)
            buffered = ", buffered" if event.buffered else ""
            return "↓ frame", f"{_short(event.frame.data)} ({reason}{buffered})", gray, Category.FRAME
        case AdapterReadEvent():
            origin = " (buffer)" if event.from_buffer else ""
            return "← read", _short(event.frame.data) + origin, gray, Category.READ
        case AdapterBufferEvent() | ProtocolBufferEvent():
            text = f"+{event.added_frame_ids} −{event.removed_frame_ids}"
            return "≡ buffer", text, gray, Category.BUFFER
        case AdapterTimeoutUpdatedEvent():
            return "~ config", "timeout updated", gray, Category.CONFIG
        case AdapterStopConditionsUpdatedEvent():
            return "~ config", "stop-conditions updated", gray, Category.CONFIG
        case ProtocolWriteEvent():
            return "→ write", _short(event.payload), gray, Category.WRITE
        case ProtocolFrameEvent():
            buffered = " (buffered)" if event.buffered else ""
            return "↓ frame", _short(event.frame.data) + buffered, gray, Category.FRAME
        case ProtocolReadEvent():
            origin = " (buffer)" if event.from_buffer else ""
            return "← read", _short(event.frame.data) + origin, gray, Category.READ
        case ProtocolDecodeErrorEvent():
            return "✗ decode", str(event.error), EntryStyle.READ_FAIL, Category.PROTOCOL
    # Events a protocol declares itself (ModbusExceptionEvent, ...)
    fields = {k: v for k, v in vars(event).items() if k != "timestamp"}
    name = type(event).__name__.removesuffix("Event")
    data = ", ".join(f"{k}={_short(v, 120)}" for k, v in fields.items())
    return f"◆ {name}", data, gray, Category.PROTOCOL


COLUMNS = ["Time", "Type", "Component", "Event", "Data"]


class EventLogModel(QAbstractTableModel):
    """The rows, in timestamp order"""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[LogEntry] = []
        self._timestamps: list[float] = []
        # Rows with a key not matched yet, see add
        self._unmatched: list[LogEntry] = []
        self.start = time.time()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        entry = self.entries[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return [
                f"{entry.timestamp - self.start:+9.3f}",
                entry.kind.letter if entry.kind else "",
                entry.source,
                entry.label,
                entry.data,
            ][column]
        if role == Qt.ItemDataRole.ForegroundRole:
            # One color for the whole row, gray for the events
            return theme().entry(EntryStyle.EVENT if entry.is_event else entry.style)
        if role == Qt.ItemDataRole.ToolTipRole:
            stamp = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            millis = int((entry.timestamp % 1) * 1000)
            return f"{stamp}.{millis:03d}  {entry.source}  {entry.label}\n{entry.data}"
        if role == Qt.ItemDataRole.UserRole:
            return entry
        return None

    # A main row and the event it duplicates are at most that far apart
    DUPLICATE_WINDOW = 2.0

    def add(self, entry: LogEntry) -> None:
        """
        Insert a row at its place in time

        An event telling the same as a main row of the same component (same key) is
        dropped, whichever arrives first : the write is logged before its event, the
        read after it
        """
        if entry.key:
            duplicate = self._duplicate_of(entry)
            if duplicate is None:
                self._unmatched.append(entry)
            else:
                self._unmatched.remove(duplicate)
                if entry.is_event:
                    return
                # The event came first : the main row takes its place
                self._remove(duplicate)
        self._insert(entry)

    def _duplicate_of(self, entry: LogEntry) -> LogEntry | None:
        now = entry.timestamp
        self._unmatched = [e for e in self._unmatched if now - e.timestamp < self.DUPLICATE_WINDOW]
        return next(
            (
                other
                for other in self._unmatched
                if other.key == entry.key
                and other.source == entry.source
                and other.is_event != entry.is_event
            ),
            None,
        )

    def _insert(self, entry: LogEntry) -> None:
        position = bisect.bisect_right(self._timestamps, entry.timestamp)
        self.beginInsertRows(QModelIndex(), position, position)
        self.entries.insert(position, entry)
        self._timestamps.insert(position, entry.timestamp)
        self.endInsertRows()

    def _remove(self, entry: LogEntry) -> None:
        position = next(i for i, e in enumerate(self.entries) if e is entry)
        self.beginRemoveRows(QModelIndex(), position, position)
        del self.entries[position]
        del self._timestamps[position]
        self.endRemoveRows()

    def clear(self) -> None:
        """Remove every row"""
        self.beginResetModel()
        self.entries.clear()
        self._timestamps.clear()
        self._unmatched.clear()
        self.endResetModel()



class _Filter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.show_events = False
        self.categories = set(DEFAULT_CATEGORIES)
        self.component = ""

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        model = self.sourceModel()
        assert isinstance(model, EventLogModel)
        entry = model.entries[source_row]
        if self.component and entry.source != self.component:
            return False
        if entry.category is None:
            return True
        return self.show_events and entry.category in self.categories


class EventLog(QWidget):
    """Table of the main rows and, optionally, of the events"""

    show_events_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.model = EventLogModel()
        self.filter = _Filter()
        self.filter.setSourceModel(self.model)

        panel(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        title = QLabel("Log")
        title.setObjectName("Heading")
        toolbar.addWidget(title)
        toolbar.addSpacing(8)
        self.show_events = QCheckBox("Show events")
        self.show_events.setToolTip(
            "Show what happens inside the adapters and protocols : fragments received,\n"
            "frames completed, reads served from the buffer..."
        )
        self.show_events.toggled.connect(self._show_events)
        toolbar.addWidget(self.show_events)

        self.categories = QToolButton()
        self.categories.setText("Event types")
        set_icon(self.categories, "filter")
        self.categories.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.categories.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.categories)
        for category in Category:
            action = QAction(category.value, menu)
            action.setCheckable(True)
            action.setChecked(category in DEFAULT_CATEGORIES)
            action.toggled.connect(lambda checked, c=category: self._category(c, checked))
            menu.addAction(action)
        self.categories.setMenu(menu)
        self.categories.setEnabled(False)
        toolbar.addWidget(self.categories)

        self.component = QComboBox()
        self.component.addItem("All components", "")
        self.component.currentIndexChanged.connect(self._component)
        toolbar.addWidget(self.component)
        toolbar.addStretch(1)

        self.autoscroll = QCheckBox("Auto-scroll")
        self.autoscroll.setChecked(True)
        toolbar.addWidget(self.autoscroll)
        copy = QPushButton("Copy")
        set_icon(copy, "copy")
        copy.setToolTip("Copy the rows shown")
        copy.clicked.connect(self._copy)
        toolbar.addWidget(copy)
        clear = QPushButton("Clear")
        set_icon(clear, "trash")
        clear.clicked.connect(self.clear)
        toolbar.addWidget(clear)
        layout.addLayout(toolbar)

        self.table = QTableView()
        self.table.setModel(self.filter)
        font = monospace(0.86)
        self.table.setFont(font)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setMinimumSectionSize(1)
        self.table.verticalHeader().setDefaultSectionSize(self.table.fontMetrics().height() + 1)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header_font = QFont(self.font())
        header_font.setPointSizeF(header_font.pointSizeF() * 0.85)
        header.setFont(header_font)
        header.setFixedHeight(QFontMetrics(header_font).height() + 8)
        for column, width in enumerate([75, 32, 110, 80]):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        self.filter.rowsInserted.connect(self._scroll)

    def set_components(self, labels: list[str]) -> None:
        """Components the table can be filtered on"""
        current = self.component.currentData()
        self.component.blockSignals(True)
        self.component.clear()
        self.component.addItem("All components", "")
        for label in labels:
            self.component.addItem(label, label)
        index = self.component.findData(current)
        self.component.setCurrentIndex(max(index, 0))
        self.component.blockSignals(False)
        self._component()

    def add(self, entry: LogEntry) -> None:
        """Add a row"""
        self.model.add(entry)

    def add_event(self, source: str, kind: Kind, event: SyndesiEvent) -> None:
        """Add the row of an adapter or protocol event"""
        description = describe_event(event)
        if description is None:
            return
        label, data, style, category = description
        self.add(
            LogEntry(event.timestamp, source, kind, label, data, style, category, event_key(event))
        )

    def clear(self) -> None:
        """Remove every row"""
        self.model.clear()

    def _show_events(self, checked: bool) -> None:
        self.filter.show_events = checked
        self.categories.setEnabled(checked)
        self.filter.invalidate()
        self.show_events_changed.emit(checked)
        self._scroll()

    def _category(self, category: Category, checked: bool) -> None:
        if checked:
            self.filter.categories.add(category)
        else:
            self.filter.categories.discard(category)
        self.filter.invalidate()

    def _component(self) -> None:
        self.filter.component = self.component.currentData() or ""
        self.filter.invalidate()

    def _scroll(self, *_: Any) -> None:
        if self.autoscroll.isChecked():
            self.table.scrollToBottom()

    def _copy(self) -> None:
        lines = []
        for row in range(self.filter.rowCount()):
            entry: LogEntry = self.filter.index(row, 0).data(Qt.ItemDataRole.UserRole)
            letter = entry.kind.letter if entry.kind else ""
            lines.append(
                f"{entry.timestamp - self.model.start:+9.3f}\t{letter}\t{entry.source}\t"
                f"{entry.label}\t{entry.data}"
            )
        QGuiApplication.clipboard().setText("\n".join(lines))
