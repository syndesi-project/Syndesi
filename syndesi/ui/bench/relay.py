# File : relay.py
# Author : Sébastien Deriaz
# License : GPL
"""
Events of the adapters and protocols, from the reactor thread to the GUI

A callback registered on an adapter or a protocol runs on the reactor thread and must
not block : it only emits a Qt signal, that Qt delivers on the GUI thread. Each build
is a new generation, the events of the components of a previous one are dropped
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, Signal

from ...adapters.events import AdapterEvent, SyndesiEvent
from ..core.introspection import Kind
from ..core.runtime import RuntimeItem, is_adapter, is_endpoint
from ..worker import Worker


class EventRelay(QObject):
    """
    Listens to the components, emits received(label, kind, event) on the GUI thread

    opened(label, is_open) gives the state of each adapter when it starts being
    listened to, the AdapterOpened/ClosedEvent tell the changes
    """

    received = Signal(str, object, object)
    opened = Signal(str, bool)
    failed = Signal(object, str)
    _forward = Signal(int, str, object, object)

    def __init__(self, worker: Worker) -> None:
        super().__init__()
        self._worker = worker
        self._generation = 0
        self._listened: set[int] = set()
        self._forward.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def reset(self) -> None:
        """A new build : forget the components listened to so far, drop their events"""
        self._generation += 1
        self._listened.clear()

    def listen(self, item: RuntimeItem) -> None:
        """Listen to an adapter or a protocol (anything else is ignored)"""
        instance = item.instance
        if not is_endpoint(instance) or id(instance) in self._listened:
            return
        self._listened.add(id(instance))
        generation, label, kind = self._generation, item.label, item.kind
        adapter = is_adapter(instance)
        forward = self._forward

        def callback(event: SyndesiEvent) -> None:
            # Reactor thread : only hand it over. A protocol also forwards the events
            # of its adapter, which has its own callback
            if adapter == isinstance(event, AdapterEvent):
                forward.emit(generation, label, kind, event)

        def register() -> bool:
            instance.register_event_callback(callback)
            return bool(instance.is_open)

        def registered(is_open: Any, error: BaseException | None) -> None:
            if generation != self._generation:
                return
            if error is not None:
                self.failed.emit(item, f"Cannot listen to the events : {error}")
            elif adapter:
                self.opened.emit(label, bool(is_open))

        self._worker.submit(register, registered)

    def _deliver(self, generation: int, label: str, kind: Kind, event: SyndesiEvent) -> None:
        if generation == self._generation:
            self.received.emit(label, kind, event)
