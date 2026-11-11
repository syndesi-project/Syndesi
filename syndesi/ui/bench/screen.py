# File : screen.py
# Author : Sébastien Deriaz
# License : GPL
"""
Test screen : use the built stack

    ┌ Objects ──────────┐ ┌ SCPIDriver ─────────────────────────────────┐
    │ SCPIDriver   top  │ │ [ Commands ]  [ I/O ]  [ State ]            │
    │  ◇ SCPI  _prot    │ │  get_identification() → str      [Run ▶]    │
    │    IP    adapter  │ ├ Log ───────────────────── ☐ Show events ────┤
    │ PSUChannel ch[0]  │ │ +1.204  D  SCPIDriver  ▶ command  get_id…   │
    └───────────────────┘ └─────────────────────────────────────────────┘

Every component of the tree can be tested, not only the top one : the protocol a
driver built for itself, the adapter below it, the sub-drivers the driver exposes and
the components a command returned (a channel, a client of an IPServer, ...)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...adapters.events import AdapterClosedEvent, AdapterOpenedEvent, SyndesiEvent
from ...drivers.driver import Driver
from ..core.introspection import (
    Kind,
    commands_of,
    component_info,
    io_payload_type,
    returned_components,
)
from ..core.runtime import Role, RuntimeItem, RuntimeTree, describe, is_endpoint, open_targets
from ..style.icons import set_icon
from ..style.theme import EntryStyle
from ..style.widgets import kind_badge, panel, set_tone, type_chip
from ..worker import Worker, error_text, resolve
from .command_panel import CommandPanel, StatePanel
from .event_log import EventLog, LogEntry
from .io_panel import FrameBuffer, IOPanel
from .object_tree import ObjectTree
from .relay import EventRelay


def _role_text(item: RuntimeItem) -> str:
    parent = item.parent.label if item.parent else ""
    return {
        Role.TOP: "Top layer of the stack",
        Role.EXTERNAL: f"Configured in the stack screen, <code>{item.path}</code> of {parent}",
        Role.INTERNAL: f"Internal : built by {parent} in <code>{item.path}</code>",
        Role.SUBDRIVER: f"Sub-driver of {parent} : <code>{item.path}</code>",
        Role.RETURNED: f"Returned by <code>{item.path}</code> of {parent}",
    }[item.role]


class TestScreen(QWidget):
    """
    Second screen : open, send, read, run commands, watch the events

    The panels of the components (I/O, Commands, State) call log() and run(), the
    calls run on the worker thread and their results come back here
    """

    def __init__(self, worker: Worker) -> None:
        super().__init__()
        self.worker = worker
        self.runtime: RuntimeTree | None = None
        # Results of the calls made on a previous build are dropped
        self._generation = 0
        self._open_states: dict[str, bool] = {}
        self._panels: dict[int, QWidget] = {}
        self._buffers: dict[str, FrameBuffer] = {}
        self._relay = EventRelay(worker)
        self._relay.received.connect(self._event)
        self._relay.opened.connect(self._adapter_state)
        self._relay.failed.connect(self.log_error)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(self._toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        splitter.addWidget(self._objects())
        right = QSplitter(Qt.Orientation.Vertical)
        self.detail = panel(QWidget())
        self.detail_layout = QVBoxLayout(self.detail)
        self.detail_layout.setContentsMargins(14, 12, 14, 12)
        right.addWidget(self.detail)
        self.log_view = EventLog()
        right.addWidget(self.log_view)
        right.setSizes([340, 360])
        splitter.addWidget(right)
        splitter.setSizes([320, 900])
        self._update_status()

    def _toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.status = QLabel()
        self.status.setObjectName("Status")
        toolbar.addWidget(self.status)
        toolbar.addSpacing(6)
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("Success")
        set_icon(self.open_button, "plug", "ok")
        self.open_button.clicked.connect(self.open)
        toolbar.addWidget(self.open_button)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("Danger")
        set_icon(self.close_button, "stop", "error")
        self.close_button.clicked.connect(self.close_stack)
        toolbar.addWidget(self.close_button)
        toolbar.addStretch(1)
        busy = QLabel("")
        busy.setObjectName("Muted")
        toolbar.addWidget(busy)
        self.worker.busy_changed.connect(lambda working: busy.setText("working…" if working else ""))
        return toolbar

    def _objects(self) -> QWidget:
        objects = panel(QWidget())
        layout = QVBoxLayout(objects)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)
        title = QLabel("Objects")
        title.setObjectName("Heading")
        layout.addWidget(title)
        self.tree = ObjectTree()
        self.tree.selected.connect(self._show_panel)
        layout.addWidget(self.tree, 1)
        legend = QLabel(
            "<i>internal</i> : built by a driver · <i>sub-driver</i> : exposed by a driver"
            " · components returned by a command are added here"
        )
        legend.setObjectName("Muted")
        legend.setWordWrap(True)
        font = legend.font()
        font.setPointSizeF(font.pointSizeF() * 0.88)
        legend.setFont(font)
        layout.addWidget(legend)
        return objects

    # Loading

    def load(self, runtime: RuntimeTree) -> None:
        """Show a freshly built stack"""
        self._generation += 1
        self._relay.reset()
        self.runtime = runtime
        self._open_states.clear()
        self._panels.clear()
        self._buffers.clear()
        self.tree.show_runtime(runtime.root)
        self.log(runtime.root, "✓ built", describe(runtime.root.instance), EntryStyle.INFO)
        for item in runtime.walk():
            self._relay.listen(item)
        self._update_components()
        has_targets = bool(open_targets(runtime))
        self.open_button.setEnabled(has_targets)
        self.close_button.setEnabled(has_targets)
        self._update_status()

    def _add(self, item: RuntimeItem) -> None:
        """A component found after the build (returned by a command, created by one)"""
        self.tree.add(item)
        for each in item.walk():
            self._relay.listen(each)
        self._update_components()

    def _update_components(self) -> None:
        if self.runtime is not None:
            self.log_view.set_components([i.label for i in self.runtime.walk()])

    # Panels

    def select(self, item: RuntimeItem) -> None:
        """Show the panel of a component"""
        self.tree.select(item)

    def panel(self, item: RuntimeItem) -> QWidget:
        """Panel of a component (I/O, Commands, State), made the first time it is shown"""
        widget = self._panels.get(id(item.instance))
        if widget is None:
            widget = self._panels[id(item.instance)] = self._make_panel(item)
        return widget

    def _show_panel(self, item: RuntimeItem) -> None:
        while self.detail_layout.count():
            layout_item = self.detail_layout.takeAt(0)
            shown = layout_item.widget() if layout_item is not None else None
            if shown is not None:
                shown.setParent(None)
        widget = self.panel(item)
        self.detail_layout.addWidget(widget)
        widget.show()

    def _make_panel(self, item: RuntimeItem) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(kind_badge(item.kind))
        title = QLabel(item.label)
        title.setObjectName("Heading")
        header.addWidget(title)
        if item.kind in (Kind.ADAPTER, Kind.PROTOCOL):
            header.addWidget(type_chip(f"provides {component_info(item.cls).provides_label}"))
        role = QLabel(_role_text(item))
        role.setObjectName("Muted")
        header.addWidget(role)
        header.addStretch(1)
        layout.addLayout(header)

        # I/O first for the adapters and protocols exchanging text or bytes, the
        # commands first for the others
        tabs = QTabWidget()
        commands = commands_of(item.cls)
        payload = io_payload_type(item.cls)
        command_tab = (CommandPanel(self, item, commands), f"Commands ({len(commands)})")
        io_tab = (IOPanel(self, item, payload), "I/O") if payload is not None else None
        driver = item.kind in (Kind.DRIVER, Kind.SUBDRIVER)
        for tab in ([command_tab, io_tab] if driver or io_tab is None else [io_tab, command_tab]):
            if tab is not None:
                tabs.addTab(*tab)
        tabs.addTab(StatePanel(self, item), "State")
        layout.addWidget(tabs, 1)
        return container

    def buffer_of(self, item: RuntimeItem) -> FrameBuffer:
        """Frames waiting in the buffer of a component, see FrameBuffer"""
        return self._buffer(item.label)

    def _buffer(self, label: str) -> FrameBuffer:
        buffer = self._buffers.get(label)
        if buffer is None:
            buffer = self._buffers[label] = FrameBuffer()
        return buffer

    def retheme(self) -> None:
        """Redraw with the colors of a new theme"""
        self.log_view.table.viewport().update()
        self.tree.retheme()

    # Calls

    def log(self, item: RuntimeItem, label: str, data: str, style: EntryStyle,
            timestamp: float | None = None, key: str = "") -> None:
        """Add a main row, key : see LogEntry.key"""
        self.log_view.add(
            LogEntry(time.time() if timestamp is None else timestamp, item.label, item.kind,
                     label, data, style, key=key)
        )

    def log_error(self, item: RuntimeItem, message: str) -> None:
        """Add an error row"""
        self.log(item, "✗ error", message, EntryStyle.ERROR)

    def run(
        self,
        item: RuntimeItem,
        call: Callable[[], Any],
        on_result: Callable[[Any], None] | None,
        *,
        failure: str = "✗ error",
        failure_style: EntryStyle = EntryStyle.ERROR,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        """
        Run a call on the worker, then on_result(result) or, if it raises, log the error
        and on_error(error). A command may have created components : they are added
        """
        generation = self._generation

        def done(result: Any, error: BaseException | None) -> None:
            if generation != self._generation:
                return
            if error is not None:
                self.log(item, failure, error_text(error), failure_style)
                if on_error is not None:
                    on_error(error)
                return
            if on_result is not None:
                on_result(result)
            if self.runtime is not None and self.runtime.find(item.instance) is not None:
                for new in self.runtime.refresh(item):
                    self._add(new)

        self.worker.submit(lambda: resolve(call()), done)

    def add_returned(self, item: RuntimeItem, value: Any, call_text: str) -> None:
        """Components returned by a command go in the tree"""
        if self.runtime is None:
            return
        for found in returned_components(value):
            new = self.runtime.add(found.instance, Role.RETURNED, call_text + found.path, item)
            if new is not None:
                self._add(new)
                self.log(item, "+ object", f"{new.label} added to the objects", EntryStyle.INFO)

    def open(self) -> None:
        """Open the stack"""
        self._open_close("open")

    def close_stack(self) -> None:
        """Close the stack"""
        self._open_close("close")

    def _open_close(self, action: str) -> None:
        if self.runtime is None:
            return
        targets = open_targets(self.runtime)
        for target in targets:
            item = self.runtime.find(target) or self.runtime.root
            self.log(item, "▶ command", f"{action}()", EntryStyle.COMMAND)

        def job() -> None:
            for target in targets:
                resolve(getattr(target, action)())

        self.run(self.runtime.root, job, None)

    def shutdown_job(self) -> Callable[[], None] | None:
        """A job closing what is open, before the stack is rebuilt or the app quits"""
        if self.runtime is None:
            return None
        self._generation += 1
        self._relay.reset()
        runtime, self.runtime = self.runtime, None
        top = runtime.root.instance
        endpoints = [i.instance for i in runtime.walk() if is_endpoint(i.instance)]

        def job() -> None:
            top_cls: Any = type(top)
            if isinstance(top, Driver) and not component_info(top_cls).is_base_class:
                _quietly(top.close)
            for endpoint in endpoints:
                if endpoint.is_open:
                    _quietly(endpoint.close)

        return job

    # Events

    def _event(self, label: str, kind: Kind, event: SyndesiEvent) -> None:
        self._buffer(label).handle(event)
        self.log_view.add_event(label, kind, event)
        if isinstance(event, (AdapterOpenedEvent, AdapterClosedEvent)):
            self._adapter_state(label, isinstance(event, AdapterOpenedEvent))

    def _adapter_state(self, label: str, is_open: bool) -> None:
        self._open_states[label] = is_open
        self._update_status()

    def _update_status(self) -> None:
        states = self._open_states
        opened = sum(states.values())
        if self.runtime is None:
            text, tone = "Not built", ""
        elif not states:
            text, tone = "No adapter", ""
        elif opened == len(states):
            text, tone = "Opened", "ok"
        elif opened == 0:
            text, tone = "Closed", "error"
        else:
            text, tone = f"{opened}/{len(states)} adapters open", "warning"
        self.status.setText(f"●  {text}")
        set_tone(self.status, tone)
        self.status.setToolTip(
            "\n".join(f"{k} : {'open' if v else 'closed'}" for k, v in states.items())
        )
        self.tree.set_open_states(states)


def _quietly(close: Callable[[], Any]) -> None:
    """Close on shutdown : a component that fails to close mustn't stop the others"""
    try:
        resolve(close())
    except Exception:  # pylint: disable=broad-exception-caught
        pass
