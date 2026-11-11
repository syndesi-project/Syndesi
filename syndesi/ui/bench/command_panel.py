# File : command_panel.py
# Author : Sébastien Deriaz
# License : GPL
"""
The public methods of a component as commands, and its properties
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.introspection import (
    CommandInfo,
    properties_of,
)
from ..core.runtime import (
    RuntimeItem,
    is_adapter,
)
from ..fields import ParamForm
from ..style.icons import add_leading_icon, set_icon
from ..style.theme import EntryStyle, monospace, theme
from ..style.widgets import (
    set_tone,
)
from ..worker import error_text

if TYPE_CHECKING:
    from .screen import TestScreen


class CommandPanel(QWidget):
    """The public methods of a component, with a form for their arguments"""

    def __init__(self, screen: TestScreen, item: RuntimeItem, commands: list[CommandInfo]) -> None:
        super().__init__()
        self.owner = screen
        self.item = item
        self.commands = commands
        self._form: ParamForm | None = None
        self._command: CommandInfo | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search commands")
        self.search.setClearButtonEnabled(True)
        add_leading_icon(self.search, "search")
        self.search.textChanged.connect(self._fill)
        left_layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._selected)
        self.list.itemDoubleClicked.connect(self._double_clicked)
        left_layout.addWidget(self.list)
        splitter.addWidget(left)

        right = QWidget()
        self.right = QVBoxLayout(right)
        self.right.setContentsMargins(8, 0, 0, 0)
        self.signature = QLabel()
        self.signature.setFont(monospace())
        self.signature.setWordWrap(True)
        self.signature.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.right.addWidget(self.signature)
        self.summary = QLabel()
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.right.addWidget(self.summary)
        self.form_area = QScrollArea()
        self.form_area.setWidgetResizable(True)
        self.form_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.right.addWidget(self.form_area, 1)
        row = QHBoxLayout()
        self.result = QLabel()
        self.result.setFont(monospace())
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.result, 1)
        self.run_button = QPushButton("Run")
        set_icon(self.run_button, "play", "white")
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.run)
        row.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignBottom)
        self.right.addLayout(row)
        splitter.addWidget(right)
        splitter.setSizes([260, 500])

        self._fill()

    def _fill(self) -> None:
        text = self.search.text().lower()
        self.list.clear()
        owner = None
        first: QListWidgetItem | None = None
        for command in self.commands:
            if text and text not in command.name.lower() and text not in command.summary.lower():
                continue
            group = f"{command.owner.__name__} (library)" if command.is_framework else command.owner.__name__
            if group != owner:
                owner = group
                header = QListWidgetItem(group.upper())
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setData(Qt.ItemDataRole.UserRole, "")
                font = header.font()
                font.setPointSizeF(font.pointSizeF() * 0.8)
                font.setWeight(font.Weight.Bold)
                font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, 0.5)
                header.setFont(font)
                header.setForeground(theme().muted)
                self.list.addItem(header)
            entry = QListWidgetItem(command.name)
            entry.setData(Qt.ItemDataRole.UserRole, command)
            entry.setToolTip(command.signature + ("\n\n" + command.summary if command.summary else ""))
            self.list.addItem(entry)
            first = first or entry
        if first is not None:
            self.list.setCurrentItem(first)
        else:
            self._selected(None)

    def _selected(self, entry: QListWidgetItem | None, _: Any = None) -> None:
        command = entry.data(Qt.ItemDataRole.UserRole) if entry is not None else None
        command = command if isinstance(command, CommandInfo) else None
        self._command = command
        self.result.setText("")
        if command is None:
            self.signature.setText("")
            self.summary.setText("No command" if not self.commands else "")
            self.form_area.setWidget(QWidget())
            self.run_button.setEnabled(False)
            return
        self.signature.setText(command.signature)
        self.summary.setText(command.summary)
        self._form = ParamForm(command.params)
        self.form_area.setWidget(self._form)
        self.run_button.setEnabled(True)

    def _double_clicked(self, entry: QListWidgetItem) -> None:
        command = entry.data(Qt.ItemDataRole.UserRole)
        if isinstance(command, CommandInfo) and not command.params:
            self.run()

    def run(self) -> None:
        """Run the selected command"""
        command, form = self._command, self._form
        if command is None or form is None:
            return
        try:
            args, kwargs = form.call_arguments()
        except ValueError as e:
            self.result.setText(f"✗ {e}")
            set_tone(self.result, "error")
            return
        call_text = ", ".join([repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
        call_text = f"{command.name}({call_text})"
        method = getattr(self.item.instance, command.name)
        self.result.setText("running…")
        set_tone(self.result, "muted")
        self.owner.log(self.item, "▶ command", call_text, EntryStyle.COMMAND)

        def done(result: Any) -> None:
            text = "done" if result is None else repr(result)
            self.result.setText(f"= {text}")
            set_tone(self.result, "")
            self.owner.log(self.item, "= result", "None" if result is None else repr(result),
                            EntryStyle.RESULT)
            self.owner.add_returned(self.item, result, call_text)

        def failed(error: BaseException) -> None:
            self.result.setText(f"✗ {error_text(error)}")
            set_tone(self.result, "error")

        self.owner.run(self.item, lambda: method(*args, **kwargs), done, on_error=failed)


# ┌───────┐
# │ State │
# └───────┘


class StatePanel(QWidget):
    """The properties of a component"""

    def __init__(self, screen: TestScreen, item: RuntimeItem) -> None:
        super().__init__()
        self.owner = screen
        self.item = item
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.repr = QLabel()
        self.repr.setFont(monospace())
        self.repr.setWordWrap(True)
        self.repr.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.repr, 1)
        refresh = QPushButton("Refresh")
        set_icon(refresh, "refresh")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setFont(monospace())
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        self.names = properties_of(item.cls)
        if is_adapter(item.instance) and "descriptor" not in self.names:
            self.names.insert(0, "descriptor")
        self.refresh()

    def refresh(self) -> None:
        """Read the properties again (on the worker thread)"""
        instance = self.item.instance
        names = list(self.names)

        def read() -> tuple[str, list[tuple[str, str]]]:
            values = []
            for name in names:
                try:
                    values.append((name, repr(getattr(instance, name))))
                except Exception as e:  # pylint: disable=broad-exception-caught
                    values.append((name, f"<{error_text(e)}>"))
            return repr(instance), values

        def show(result: Any, error: BaseException | None) -> None:
            if error is not None:
                self.repr.setText(error_text(error))
                return
            text, values = result
            self.repr.setText(text)
            self.table.setRowCount(len(values))
            for row, (name, value) in enumerate(values):
                self.table.setItem(row, 0, QTableWidgetItem(name))
                self.table.setItem(row, 1, QTableWidgetItem(value))
            self.table.resizeColumnToContents(0)

        self.owner.worker.submit(read, show)
