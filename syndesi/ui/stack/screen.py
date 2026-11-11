# File : screen.py
# Author : Sébastien Deriaz
# License : GPL
"""
Stack screen : assemble and configure the layers

    ┌ Library ─────┐ ┌ Stack ────────────────────┐ ┌ Inspector ───┐
    │ Adapters     │ │      Your application     │ │ IP           │
    │  IP          │ │            ⇅ str          │ │  address  …  │
    │  SerialPort  │ │  ┌ PROTOCOL  SCPI ──────┐ │ │  port     …  │
    │ Protocols    │ │  └──────────────────────┘ │ │              │
    │  SCPI   ─────┼─┼─▶       ⇅ adapter · bytes │ │              │
    │ Drivers      │ │  ┌ ADAPTER   IP ────────┐ │ │              │
    │              │ │  └──────────────────────┘ │ │              │
    └──────────────┘ │          🔌 device         │ └──────────────┘
                     └ Python code ──────────────┘

The slots of a component (the parameters typed as another component) are drawn under
its card, a slot only accepts what its type hint accepts. Components are dragged from
the library, or picked with the + of a slot
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.code import to_code
from ..core.introspection import (
    Kind,
    component_info,
)
from ..core.library import Library
from ..core.runtime import (
    RuntimeItem,
    RuntimeTree,
)
from ..core.stack import Stack, StackNode
from ..style.icons import set_pixmap
from ..style.widgets import (
    set_tone,
)
from .canvas import StackCanvas
from .inspector import CodePreview, Inspector
from .library_panel import GROUPS, Palette


class StackScreen(QWidget):
    """
    First screen : assemble and configure the stack

    The controller of the screen : the canvas, the library and the inspector call its
    public methods, it edits the Stack, keeps the selection and redraws. ``changed`` is
    emitted on every edit of the stack, structure or values
    """

    changed = Signal()

    def __init__(self, library: Library) -> None:
        super().__init__()
        self.library = library
        self.stack = Stack()
        self.selected_node: StackNode | None = None
        self.selected_slot: tuple[StackNode | None, str | None] | None = (None, None)
        self.runtime: RuntimeTree | None = None
        self._render_pending = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 12)
        layout.setSpacing(10)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.library_panel = Palette(library)
        self.library_panel.activated.connect(self._palette_activated)
        self.library_panel.library_changed.connect(self._render)
        self.library_panel.api.currentIndexChanged.connect(self._render)
        splitter.addWidget(self.library_panel)

        center = QSplitter(Qt.Orientation.Vertical)
        self.canvas = StackCanvas(self)
        center.addWidget(self.canvas)
        self.code = CodePreview()
        center.addWidget(self.code)
        center.setStretchFactor(0, 4)
        center.setStretchFactor(1, 1)
        center.setSizes([600, 170])
        splitter.addWidget(center)

        self.inspector = Inspector(self)
        self.inspector.values_changed.connect(self.node_changed)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([270, 640, 360])

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.problems_icon = QLabel()
        bottom.addWidget(self.problems_icon)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        bottom.addWidget(self.problems, 1)
        layout.addLayout(bottom)

        self._render()
        self.select_slot(None, None)

    # Queries

    def visible_classes(self) -> list[type]:
        """Classes that can be stacked : sync or async as chosen, usable in the GUI"""
        async_api = self.library_panel.async_api
        return [
            i.cls
            for i in self.library.infos()
            if not i.code_only
            and (i.kind in (Kind.DRIVER, Kind.SUBDRIVER) or i.is_async == async_api)
        ]

    @property
    def root(self) -> StackNode | None:
        """Top of the stack"""
        return self.stack.root

    @property
    def complete(self) -> bool:
        """True if the stack can be built"""
        return not self.stack.problems()

    def can_wrap(self, cls: type) -> bool:
        """True if cls can be put on top of the stack"""
        return self.stack.can_wrap(cls)

    def can_replace(self, node: StackNode, cls: type) -> bool:
        """True if cls can take the place of node"""
        return self.stack.can_replace(node, cls)

    def removable_keeping_children(self, node: StackNode) -> StackNode | None:
        """The child that can take the place of node when it is removed, if any"""
        return self.stack.child_taking_place(node)

    def runtime_item(self, node: StackNode) -> RuntimeItem | None:
        """Built item of a node, if the stack is built"""
        if self.runtime is None or node.instance is None:
            return None
        return self.runtime.find(node.instance)

    def fill_menu(self, menu: QMenu, accepts: Callable[[type], bool], action: Callable[[type], None]) -> None:
        """Add the compatible classes to a menu, grouped by layer"""
        infos = [component_info(c) for c in self.visible_classes() if accepts(c)]
        for kind, name, _ in GROUPS:
            members = [i for i in infos if i.kind is kind]
            if not members:
                continue
            menu.addSection(name)
            for info in members:
                cls = info.cls
                menu.addAction(info.name, lambda c=cls: action(c)).setToolTip(  # type: ignore[misc]
                    info.summary
                )

    # Edition

    def set_root(self, root: StackNode | None) -> None:
        """Replace the whole stack"""
        self.stack.root = root
        if root is not None:
            self.library_panel.set_async(root.info.is_async)
        self._edited()
        if root is None:
            self.select_slot(None, None)
        else:
            self.select_node(root)

    def fill_slot(self, parent: StackNode | None, slot: str | None, cls: type) -> None:
        """Put a new component in a slot (parent None : the top), then select what's next"""
        node = self.stack.place(parent, slot, cls)
        self._edited()
        empty = next((s for s, c in node.children.items() if c is None), None)
        if empty is not None:
            self.select_slot(node, empty)
        else:
            self.select_node(node)

    def wrap_root(self, cls: type) -> None:
        """Put cls on top of the stack"""
        node = self.stack.wrap(cls)
        self._edited()
        self.select_node(node)

    def replace_node(self, node: StackNode, cls: type) -> None:
        """Swap a component (a component dropped on a card)"""
        new = self.stack.replace(node, cls)
        self._edited()
        self.select_node(new)

    def remove_node(self, node: StackNode, keep_children: bool) -> None:
        """Remove a component, and the layers below unless keep_children"""
        parent, slot = node.parent, node.parent_slot
        replacement = self.stack.remove(node, keep_children)
        self._edited()
        if replacement is not None:
            self.select_node(replacement)
        else:
            self.select_slot(parent, slot)

    # Selection

    def select_node(self, node: StackNode) -> None:
        """Select a card"""
        self.selected_node = node
        self.selected_slot = None
        self.library_panel.set_filter(None)
        self.inspector.show_node(node)
        self._render()

    def select_slot(self, parent: StackNode | None, slot: str | None) -> None:
        """Select a slot, the library then only enables what it accepts"""
        self.selected_node = None
        self.selected_slot = (parent, slot)
        if parent is None or slot is None:
            self.library_panel.set_filter(None, "Pick the top layer of your stack")
            self.inspector.show_slot(None, None)
        else:
            spec = parent.slot_spec(slot)
            self.library_panel.set_filter(
                spec.accepts, f"Showing what {parent.info.name}.{slot} accepts : {spec.type_label}"
            )
            self.inspector.show_slot(parent, spec)
        self._render()

    def select_internal(self, item: RuntimeItem) -> None:
        """Select a layer built by a driver"""
        self.selected_node = None
        self.selected_slot = None
        self.library_panel.set_filter(None)
        self.inspector.show_internal(item)
        self._render()

    def _palette_activated(self, cls: type) -> None:
        if self.selected_slot is not None:
            parent, slot = self.selected_slot
            if parent is None and self.root is not None:
                if self.can_wrap(cls):
                    self.wrap_root(cls)
                return
            self.fill_slot(parent, slot, cls)
        elif self.selected_node is not None and self.can_replace(self.selected_node, cls):
            self.replace_node(self.selected_node, cls)
        elif self.root is None:
            self.fill_slot(None, None, cls)
        elif self.can_wrap(cls):
            self.wrap_root(cls)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Delete and self.selected_node is not None:
            self.remove_node(self.selected_node, keep_children=False)
        else:
            super().keyPressEvent(event)

    # Updates

    def set_runtime(self, runtime: RuntimeTree | None) -> None:
        """Show the internal layers once built"""
        self.runtime = runtime
        self._render()

    def _edited(self) -> None:
        # The built instances no longer match the stack
        self.runtime = None
        self._render()
        self.changed.emit()

    def node_changed(self, node: StackNode) -> None:
        """The values of a node changed (in the inspector)"""
        self.runtime = None
        card = self.canvas.cards.get(id(node))
        if card is not None:
            card.refresh()
        self._update_status()
        self.changed.emit()

    def retheme(self) -> None:
        """Redraw with the colors of a new theme"""
        self.library_panel.refresh()
        self.code.retheme()
        self._render()

    def _render(self) -> None:
        # Deferred : the widget that asked for it (a card, a slot) is redrawn too
        if not self._render_pending:
            self._render_pending = True
            QTimer.singleShot(0, self._do_render)
        self._update_status()

    def _do_render(self) -> None:
        self._render_pending = False
        self.canvas.redraw()

    def _update_status(self) -> None:
        self.code.set_code(to_code(self.root, self.library))
        problems = self.stack.problems()
        if problems:
            set_pixmap(self.problems_icon, "alert", "warning", size=16)
            self.problems.setText("  ·  ".join(problems))
            set_tone(self.problems, "warning")
        else:
            set_pixmap(self.problems_icon, "check", "ok", size=16)
            self.problems.setText("The stack is complete")
            set_tone(self.problems, "ok")
