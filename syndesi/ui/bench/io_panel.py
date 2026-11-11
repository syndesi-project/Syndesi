# File : io_panel.py
# Author : Sébastien Deriaz
# License : GPL
"""
Write, query and read on an adapter or a protocol, with its frame buffer
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...adapters.engine import ReadScope
from ...adapters.events import (
    AdapterBufferEvent,
    AdapterFrameEvent,
    SyndesiEvent,
)
from ...protocols.protocol import (
    ProtocolBufferEvent,
    ProtocolFrameEvent,
)
from ..core.introspection import (
    signature_params,
)
from ..core.runtime import (
    RuntimeItem,
    is_adapter,
)
from ..fields import FieldEditor, parse_escaped, parse_hex
from ..style.icons import set_icon
from ..style.theme import EntryStyle, monospace, theme
from ..style.widgets import (
    section,
    set_tone,
)
from ..worker import error_text
from .event_log import read_key, write_key

if TYPE_CHECKING:
    from .screen import TestScreen


class FrameBuffer(QObject):
    """
    Frames received while no read was waiting, kept up to date from the events of a
    component : a FrameEvent gives the data of a frame, a BufferEvent the frames that
    entered or left the buffer. The engine's own buffer belongs to the reactor thread
    and isn't read from here
    """

    changed = Signal()
    KNOWN_FRAMES = 1000

    def __init__(self) -> None:
        super().__init__()
        self._frames: dict[int, tuple[float, Any]] = {}
        self.waiting: list[int] = []

    def handle(self, event: SyndesiEvent) -> None:
        """Update from an event of the component"""
        if isinstance(event, (AdapterFrameEvent, ProtocolFrameEvent)):
            self._frames[event.frame.id] = (event.timestamp, event.frame.data)
            if len(self._frames) > self.KNOWN_FRAMES:
                for frame_id in list(self._frames)[: -self.KNOWN_FRAMES]:
                    if frame_id not in self.waiting:
                        del self._frames[frame_id]
        elif isinstance(event, (AdapterBufferEvent, ProtocolBufferEvent)):
            for frame_id in event.added_frame_ids:
                if frame_id not in self.waiting:
                    self.waiting.append(frame_id)
            for frame_id in event.removed_frame_ids:
                if frame_id in self.waiting:
                    self.waiting.remove(frame_id)
            self.changed.emit()

    def frames(self) -> list[tuple[int, float | None, Any]]:
        """(id, timestamp, data) of the frames waiting, the oldest first"""
        result = []
        for frame_id in self.waiting:
            timestamp, data = self._frames.get(frame_id, (None, None))
            result.append((frame_id, timestamp, data))
        return result


class IOPanel(QWidget):
    """Write, query and read on an adapter or a protocol"""

    def __init__(self, screen: TestScreen, item: RuntimeItem, payload: type) -> None:
        super().__init__()
        self.owner = screen
        self.item = item
        self.payload = payload
        grid = QGridLayout(self)
        grid.setColumnStretch(1, 1)

        is_bytes = payload is bytes
        self.format = QComboBox()
        self.format.addItems(["Text", "Hex"] if is_bytes else ["Text"])
        self.format.setToolTip("Text : \\n \\r \\t \\xHH escapes accepted\nHex : 01 02 ff")
        self.format.setEnabled(is_bytes)
        explanation = QLabel(
            f"Payloads are <code>{payload.__name__}</code>"
            + (
                ""
                if is_bytes
                else " : the protocol adds the termination when writing and removes it when reading"
            )
        )
        explanation.setObjectName("Muted")
        explanation.setWordWrap(True)
        grid.addWidget(explanation, 0, 0, 1, 3)
        grid.addWidget(QLabel("Format"), 1, 0)
        grid.addWidget(self.format, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.write_input = self._input("data to write")
        write = QPushButton("Write")
        set_icon(write, "send")
        write.clicked.connect(self.write)
        self.write_input.lineEdit().returnPressed.connect(self.write)  # type: ignore[union-attr]
        grid.addWidget(QLabel("Write"), 2, 0)
        grid.addWidget(self.write_input, 2, 1)
        grid.addWidget(write, 2, 2)

        self.query_input = self._input("data to write, then read the answer")
        query = QPushButton("Query")
        set_icon(query, "swap")
        query.clicked.connect(self.query)
        self.query_input.lineEdit().returnPressed.connect(self.query)  # type: ignore[union-attr]
        grid.addWidget(QLabel("Query"), 3, 0)
        grid.addWidget(self.query_input, 3, 1)
        grid.addWidget(query, 3, 2)

        read_row = QHBoxLayout()
        self.scope = QComboBox()
        for scope in ReadScope:
            self.scope.addItem(scope.value, scope)
        self.scope.setCurrentIndex(self.scope.findData(ReadScope.BUFFERED))
        self.scope.setToolTip(
            "buffered : return a frame received before the read if there is one\n"
            "next : only a frame received after the read starts\n"
            "last_write : a frame received after the last write"
        )
        read_row.addWidget(QLabel("scope"))
        read_row.addWidget(self.scope)
        # The timeout parameter of read(), with its Default / None checkboxes
        read_params = signature_params(type(item.instance).read, type(item.instance), {})
        timeout_spec = next(p for p in read_params if p.name == "timeout")
        self.timeout = FieldEditor(timeout_spec)
        self.timeout.setToolTip(
            "Default : the timeout of the component\nNone : wait forever\n"
            "otherwise : seconds to wait for a frame"
        )
        read_row.addSpacing(12)
        read_row.addWidget(QLabel("timeout"))
        read_row.addWidget(self.timeout)
        read_row.addStretch(1)
        read = QPushButton("Read")
        set_icon(read, "download")
        read.clicked.connect(self.read)
        grid.addWidget(QLabel("Read"), 4, 0)
        grid.addLayout(read_row, 4, 1)
        grid.addWidget(read, 4, 2)

        self.hex_view = QCheckBox("Hex")
        self.hex_view.setVisible(is_bytes)
        self.hex_view.setToolTip("Show the bytes received in hexadecimal")
        self.hex_view.toggled.connect(self._show_received)
        self.hex_view.toggled.connect(self._show_buffer)
        grid.addWidget(self.hex_view, 1, 2, Qt.AlignmentFlag.AlignRight)

        bottom = QSplitter(Qt.Orientation.Horizontal)
        bottom.setChildrenCollapsible(False)
        grid.addWidget(bottom, 5, 0, 1, 3)
        grid.setRowStretch(5, 1)

        # Frames waiting : what a 'buffered' read returns first
        buffer_box = QWidget()
        buffer_layout = QVBoxLayout(buffer_box)
        buffer_layout.setContentsMargins(0, 8, 0, 0)
        buffer_layout.setSpacing(6)
        buffer_bar = QHBoxLayout()
        buffer_bar.addWidget(section("Buffer"))
        self.buffer_count = QLabel()
        self.buffer_count.setObjectName("Status")
        buffer_bar.addWidget(self.buffer_count)
        buffer_bar.addStretch(1)
        clear = QPushButton("Clear")
        set_icon(clear, "trash")
        clear.setToolTip("Drop the frames waiting (clear_buffer)")
        clear.clicked.connect(self.clear_buffer)
        buffer_bar.addWidget(clear)
        buffer_layout.addLayout(buffer_bar)
        self.buffer_list = QListWidget()
        self.buffer_list.setObjectName("Field")
        self.buffer_list.setFont(monospace(0.9))
        self.buffer_list.setToolTip(
            "Frames received while no read was waiting for them.\n"
            "A read with the 'buffered' scope returns the oldest one,\n"
            "'next' and 'last_write' skip the ones received before"
        )
        buffer_layout.addWidget(self.buffer_list, 1)
        bottom.addWidget(buffer_box)

        # What was read, apart from the log
        received_box = QWidget()
        received_layout = QVBoxLayout(received_box)
        received_layout.setContentsMargins(0, 8, 0, 0)
        received_layout.setSpacing(6)
        received_bar = QHBoxLayout()
        received_bar.addWidget(section("Received"))
        received_bar.addStretch(1)
        clear_received = QPushButton("Clear")
        set_icon(clear_received, "trash")
        clear_received.clicked.connect(self._clear_received)
        received_bar.addWidget(clear_received)
        received_layout.addLayout(received_bar)
        self.received = QPlainTextEdit()
        self.received.setReadOnly(True)
        self.received.setFont(monospace(0.9))
        self.received.setPlaceholderText("Data returned by read and query")
        self.received.setMaximumBlockCount(1000)
        received_layout.addWidget(self.received, 1)
        bottom.addWidget(received_box)
        bottom.setSizes([400, 600])
        self._history: list[tuple[float, Any, str]] = []

        self.buffer = screen.buffer_of(item)
        self.buffer.changed.connect(self._show_buffer)
        self._show_buffer()

    def _input(self, placeholder: str) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        combo.setMaxCount(30)
        line = combo.lineEdit()
        assert line is not None
        line.setPlaceholderText(placeholder)
        combo.setFont(monospace())
        return combo

    def _data(self, combo: QComboBox) -> Any:
        text = combo.currentText()
        if self.payload is bytes:
            if self.format.currentText() == "Hex":
                return parse_hex(text)
            return parse_escaped(text, as_bytes=True)
        return parse_escaped(text, as_bytes=False)

    def _timeout(self) -> Any:
        return self.timeout.value()

    def _format(self, value: Any) -> str:
        if isinstance(value, bytes) and self.hex_view.isChecked():
            return value.hex(" ")
        return repr(value)

    def _line(self, timestamp: float, value: Any, error: str) -> str:
        stamp = f"{timestamp - self.owner.log_view.model.start:+9.3f}  "
        return stamp + (f"✗ {error}" if error else self._format(value))

    def _show_buffer(self) -> None:
        frames = self.buffer.frames()
        self.buffer_list.clear()
        for frame_id, timestamp, data in frames:
            stamp = "" if timestamp is None else f"{timestamp - self.owner.log_view.model.start:+9.3f}  "
            text = "?" if timestamp is None else self._format(data)
            self.buffer_list.addItem(f"#{frame_id:<3} {stamp}{text}")
        if not frames:
            empty = QListWidgetItem("No frame waiting")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setData(Qt.ItemDataRole.UserRole, "")
            empty.setForeground(theme().faint)
            self.buffer_list.addItem(empty)
        self.buffer_count.setText(f"{len(frames)} waiting" if frames else "empty")
        set_tone(self.buffer_count, "warning" if frames else "")

    def _show_received(self) -> None:
        self.received.setPlainText("\n".join(self._line(*entry) for entry in self._history))
        self.received.moveCursor(self.received.textCursor().MoveOperation.End)

    def _clear_received(self) -> None:
        self._history.clear()
        self.received.clear()

    def _add_received(self, value: Any, error: str = "") -> None:
        entry = (time.time(), value, error)
        self._history = self._history[-999:] + [entry]
        self.received.appendPlainText(self._line(*entry))

    def _read_done(self, result: Any) -> None:
        self.owner.log(self.item, "← read", repr(result), EntryStyle.READ, key=read_key(result))
        self._add_received(result)

    def _read_failed(self, error: BaseException) -> None:
        self._add_received(None, error_text(error))

    def _remember(self, combo: QComboBox) -> None:
        text = combo.currentText()
        index = combo.findText(text)
        if index > 0:
            combo.removeItem(index)
        if index != 0:
            combo.insertItem(0, text)
        combo.setCurrentIndex(0)

    def write(self) -> None:
        """Write the data"""
        try:
            data = self._data(self.write_input)
        except ValueError as e:
            self.owner.log_error(self.item, str(e))
            return
        self._remember(self.write_input)
        instance = self.item.instance
        self.owner.log(self.item, "→ write", repr(data), EntryStyle.WRITE, key=write_key(data))
        self.owner.run(self.item, lambda: instance.write(data), None, failure="✗ write")

    def query(self) -> None:
        """Write the data and read the answer"""
        try:
            data = self._data(self.query_input)
        except ValueError as e:
            self.owner.log_error(self.item, str(e))
            return
        self._remember(self.query_input)
        instance = self.item.instance
        timeout = self._timeout()
        self.owner.log(self.item, "→ write", repr(data), EntryStyle.WRITE, key=write_key(data))
        self.owner.run(
            self.item,
            lambda: instance.query(data, timeout=timeout),
            self._read_done,
            failure="← read",
            failure_style=EntryStyle.READ_FAIL,
            on_error=self._read_failed,
        )

    def read(self) -> None:
        """Read one frame"""
        instance = self.item.instance
        timeout = self._timeout()
        scope = self.scope.currentData()
        self.owner.run(
            self.item,
            lambda: instance.read(timeout=timeout, scope=scope),
            self._read_done,
            failure="← read",
            failure_style=EntryStyle.READ_FAIL,
            on_error=self._read_failed,
        )

    def clear_buffer(self) -> None:
        """Drop the buffered frames"""
        instance = self.item.instance
        name = "clear_read_buffer" if is_adapter(instance) else "clear_buffer"
        self.owner.log(self.item, "▶ command", f"{name}()", EntryStyle.COMMAND)
        self.owner.run(self.item, getattr(instance, name), None)
