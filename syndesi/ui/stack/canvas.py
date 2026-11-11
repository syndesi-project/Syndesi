# File : canvas.py
# Author : Sébastien Deriaz
# License : GPL
"""
The stack, drawn from the top layer down to the device
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygon,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.introspection import (
    Kind,
    ParamSpec,
    component_info,
)
from ..core.runtime import (
    Role,
    RuntimeItem,
)
from ..core.stack import StackNode
from ..fields import format_value
from ..style.icons import set_icon, set_pixmap
from ..style.theme import monospace, theme
from ..style.widgets import (
    CARD_WIDTH,
    fit_height,
    kind_badge,
    repolish,
    set_tone,
    shadow,
    type_chip,
)
from .library_panel import class_from_mime

if TYPE_CHECKING:
    from .screen import StackScreen


class Connector(QWidget):
    """Vertical link between two layers, with what flows through it"""

    def __init__(self, slot: str, flow: str, dashed: bool = False) -> None:
        super().__init__()
        self._dashed = dashed
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        spacer = QWidget()
        spacer.setFixedWidth(22)
        layout.addWidget(spacer)
        if slot:
            name = QLabel(slot)
            name.setObjectName("Muted")
            layout.addWidget(name)
        if flow:
            layout.addWidget(type_chip(flow))
        layout.addStretch(1)
        self._anchor = spacer

    def paintEvent(self, event: QPaintEvent) -> None:  # pylint: disable=unused-argument
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = theme().border_strong
        pen = QPen(color, 1.5)
        if self._dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        x = self._anchor.geometry().center().x()
        top, bottom = 3, self.height() - 3
        painter.drawLine(x, top + 5, x, bottom - 5)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygon([QPoint(x, top), QPoint(x - 4, top + 6), QPoint(x + 4, top + 6)]))
        painter.drawPolygon(
            QPolygon([QPoint(x, bottom), QPoint(x - 4, bottom - 6), QPoint(x + 4, bottom - 6)])
        )


class Pill(QFrame):
    """Rounded label : the application at the top, the device at the bottom"""

    def __init__(self, text: str, detail: str = "") -> None:
        super().__init__()
        self.setObjectName("Pill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 5, 14, 5)
        label = QLabel(text)
        label.setObjectName("Title")
        layout.addWidget(label)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setObjectName("Muted")
            detail_label.setFont(monospace(0.85))
            layout.addWidget(detail_label)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class _DropTarget(QFrame):
    """A frame that accepts the components of the library"""

    def __init__(self, screen: StackScreen) -> None:
        super().__init__()
        self.owner = screen
        self.setAcceptDrops(True)

    def accepts_class(self, cls: type) -> bool:
        """True if the class can be dropped here"""
        raise NotImplementedError

    def drop_class(self, cls: type) -> None:
        """A class was dropped"""
        raise NotImplementedError

    def set_drop_state(self, state: str) -> None:
        """'', 'accept' or 'refuse'"""

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        cls = class_from_mime(event.mimeData(), self.owner.library)
        if cls is None:
            event.ignore()
            return
        self.set_drop_state("accept" if self.accepts_class(cls) else "refuse")
        event.accept()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        cls = class_from_mime(event.mimeData(), self.owner.library)
        if cls is not None and self.accepts_class(cls):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: Any) -> None:  # pylint: disable=unused-argument
        self.set_drop_state("")

    def dropEvent(self, event: QDropEvent) -> None:
        self.set_drop_state("")
        cls = class_from_mime(event.mimeData(), self.owner.library)
        if cls is not None and self.accepts_class(cls):
            event.acceptProposedAction()
            self.drop_class(cls)


class SlotWidget(_DropTarget):
    """An empty slot, waiting for a component"""

    def __init__(self, screen: StackScreen, parent_node: StackNode | None, spec: ParamSpec | None) -> None:
        super().__init__(screen)
        self.parent_node = parent_node
        self.spec = spec
        self.setObjectName("Slot")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 12)
        layout.setSpacing(2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout()
        if spec is None:
            text = "Choose the top layer"
            detail = "the component you want to test : a driver, a protocol or an adapter"
        else:
            text = f"{spec.name}" + ("" if spec.required else "  (optional)")
            detail = f"accepts {spec.type_label}"
        title = QLabel(text)
        title.setObjectName("Title")
        row.addWidget(title, 1)
        add = QToolButton()
        set_icon(add, "plus")
        add.setToolTip("Choose a component")
        add.clicked.connect(self._menu)
        row.addWidget(add)
        layout.addLayout(row)
        detail_label = QLabel(detail)
        detail_label.setObjectName("Muted")
        detail_label.setWordWrap(True)
        layout.addWidget(detail_label)
        compatible = [c for c in self.owner.visible_classes() if self.accepts_class(c)]
        names = ", ".join(c.__name__ for c in compatible[:6]) + ("…" if len(compatible) > 6 else "")
        if spec is not None:
            choices = QLabel(f"e.g. {names}" if compatible else "Nothing in the library fits, load one")
            choices.setObjectName("Muted")
            choices.setWordWrap(True)
            layout.addWidget(choices)
        fit_height(self)
        self._refresh_state()

    def _refresh_state(self) -> None:
        selected = self.owner.selected_slot == (self.parent_node, self.spec.name if self.spec else None)
        self.setProperty("state", "selected" if selected else "")
        repolish(self)

    def accepts_class(self, cls: type) -> bool:
        return self.spec is None or self.spec.accepts(cls)

    def drop_class(self, cls: type) -> None:
        self.owner.fill_slot(self.parent_node, self.spec.name if self.spec else None, cls)

    def set_drop_state(self, state: str) -> None:
        if state:
            self.setProperty("state", state)
            repolish(self)
        else:
            self._refresh_state()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pylint: disable=unused-argument
        self.owner.select_slot(self.parent_node, self.spec.name if self.spec else None)

    def _menu(self) -> None:
        menu = QMenu(self)
        self.owner.fill_menu(menu, self.accepts_class, self.drop_class)
        menu.exec(self.mapToGlobal(QPoint(self.width() - 20, 30)))


class TopZone(_DropTarget):
    """Above the top card : drop a component here to put it on top of the stack"""

    def __init__(self, screen: StackScreen) -> None:
        super().__init__(screen)
        self.setObjectName("Slot")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 12, 4)
        layout.setSpacing(6)
        plus = QLabel()
        set_pixmap(plus, "plus", "muted", size=14)
        layout.addWidget(plus)
        label = QLabel("Add a layer on top")
        label.setObjectName("Muted")
        layout.addWidget(label)
        self.setToolTip("Drop a component that can be built on the current top layer")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def accepts_class(self, cls: type) -> bool:
        return self.owner.can_wrap(cls)

    def drop_class(self, cls: type) -> None:
        self.owner.wrap_root(cls)

    def set_drop_state(self, state: str) -> None:
        self.setProperty("state", state)
        repolish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pylint: disable=unused-argument
        menu = QMenu(self)
        self.owner.fill_menu(menu, self.accepts_class, self.drop_class)
        if menu.isEmpty():
            menu.addAction("Nothing in the library can be built on it").setEnabled(False)
        menu.exec(self.mapToGlobal(QPoint(0, self.height())))


class NodeCard(_DropTarget):
    """Card of a component of the stack"""

    def __init__(self, screen: StackScreen, node: StackNode) -> None:
        super().__init__(screen)
        self.node = node
        info = node.info
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        shadow(self)

        body = QVBoxLayout(self)
        body.setContentsMargins(14, 10, 8, 12)
        body.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(kind_badge(info.kind))
        name = QLabel(info.name)
        name.setObjectName("Heading")
        header.addWidget(name)
        if info.is_async:
            header.addWidget(type_chip("async"))
        header.addStretch(1)
        self.status = QLabel()
        header.addWidget(self.status)
        more = QToolButton()
        set_icon(more, "more", "muted")
        more.setToolTip("Add a layer on top, remove")
        more.setAutoRaise(True)
        more.clicked.connect(self._menu)
        header.addWidget(more)
        body.addLayout(header)

        if info.summary:
            summary = QLabel(info.summary)
            summary.setObjectName("Muted")
            summary.setWordWrap(True)
            body.addWidget(summary)

        self.values = QLabel()
        self.values.setFont(monospace(0.85))
        self.values.setWordWrap(True)
        body.addSpacing(2)
        body.addWidget(self.values)
        if info.is_base_class:
            note = QLabel("Base class : open(), close() and test() are abstract")
            set_tone(note, "warning")
            note.setWordWrap(True)
            body.addWidget(note)
        self.refresh()

    def refresh(self) -> None:
        """Show the configured values and the selection"""
        parts = [f"{k}={format_value(v)}" for k, v in self.node.values.items()]
        text = "  ".join(parts[:4]) + ("  …" if len(parts) > 4 else "")
        self.values.setText(text or "default configuration")
        set_tone(self.values, "" if text else "muted")
        self.setProperty("selected", self.owner.selected_node is self.node)
        repolish(self)
        problems = [p for p in self.node.problems() if p.startswith(self.node.info.name + " ")]
        own = [p for p in problems if "choose what" not in p]
        if own:
            set_pixmap(self.status, "alert", "error", size=16)
            self.status.setToolTip("\n".join(own))
        else:
            self.status.clear()
        fit_height(self)

    def accepts_class(self, cls: type) -> bool:
        return self.owner.can_replace(self.node, cls)

    def drop_class(self, cls: type) -> None:
        self.owner.replace_node(self.node, cls)

    def set_drop_state(self, state: str) -> None:
        self.setProperty("drop", state)
        repolish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pylint: disable=unused-argument
        self.owner.select_node(self.node)

    def contextMenuEvent(self, event: Any) -> None:
        self.owner.select_node(self.node)
        self._menu(event.globalPos())

    def _menu(self, position: QPoint | None = None) -> None:
        menu = QMenu(self)
        if self.node.parent is None:
            wrap = menu.addMenu("Add a layer on top")
            self.owner.fill_menu(wrap, self.owner.can_wrap, self.owner.wrap_root)
            wrap.setEnabled(not wrap.isEmpty())
            menu.addSeparator()
        keep = self.owner.removable_keeping_children(self.node)
        if keep is not None:
            menu.addAction(
                f"Remove this layer only (keep {keep.info.name})",
                lambda: self.owner.remove_node(self.node, keep_children=True),
            )
        menu.addAction("Remove", lambda: self.owner.remove_node(self.node, keep_children=False))
        menu.exec(position or self.mapToGlobal(QPoint(self.width() - 30, 30)))


class InternalCard(QFrame):
    """A component a driver built for itself, shown in the chain but not configurable"""

    def __init__(self, screen: StackScreen, item: RuntimeItem) -> None:
        super().__init__()
        self.owner = screen
        self.item = item
        self.setObjectName("InternalCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(kind_badge(item.kind, small=True))
        name = QLabel(item.label)
        name.setObjectName("Title")
        row.addWidget(name)
        row.addStretch(1)
        layout.addLayout(row)
        owner = item.parent.label if item.parent else ""
        detail = QLabel(f"internal · built by {owner} in {item.path}")
        detail.setObjectName("Muted")
        detail.setFont(monospace(0.8))
        layout.addWidget(detail)
        self.setToolTip(
            "This layer is created by the driver itself.\n"
            "It is configured through the driver parameters, not here."
        )
        fit_height(self, CARD_WIDTH - 40)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pylint: disable=unused-argument
        self.owner.select_internal(self.item)


class _DotGrid(QWidget):
    """Background of the canvas : a grid of faint dots"""

    SPACING = 20

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        color = QColor(theme().border_strong)
        color.setAlphaF(0.7)
        painter.setPen(QPen(color, 1.6))
        area = event.rect()
        step = self.SPACING
        for x in range(area.left() - area.left() % step, area.right() + 1, step):
            for y in range(area.top() - area.top() % step, area.bottom() + 1, step):
                painter.drawPoint(x, y)


class StackCanvas(QScrollArea):
    """The stack, drawn from the top layer down to the device"""

    def __init__(self, screen: StackScreen) -> None:
        super().__init__()
        self.owner = screen
        self.setObjectName("Canvas")
        self.setWidgetResizable(True)
        self.cards: dict[int, NodeCard] = {}
        self.redraw()

    def redraw(self) -> None:
        """Draw everything again"""
        scroll = self.verticalScrollBar().value()
        self.cards = {}
        container = _DotGrid()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)
        root = self.owner.root

        app = Pill("Your application", "tests run here")
        layout.addWidget(app, 0, Qt.AlignmentFlag.AlignHCenter)
        if root is None:
            layout.addWidget(Connector("", ""), 0, Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(SlotWidget(self.owner, None, None), 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            layout.addWidget(
                Connector("", root.info.provides_label), 0, Qt.AlignmentFlag.AlignHCenter
            )
            layout.addWidget(TopZone(self.owner), 0, Qt.AlignmentFlag.AlignHCenter)
            layout.addSpacing(6)
            layout.addWidget(self._node_view(root), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        self.setWidget(container)
        self.verticalScrollBar().setValue(scroll)

    def _node_view(self, node: StackNode) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        card = NodeCard(self.owner, node)
        self.cards[id(node)] = card
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)

        # Built : what the driver made for itself, then what it exposes
        item = self.owner.runtime_item(node)
        if item is not None:
            for internal in self._internal_chain(item):
                layout.addWidget(
                    Connector("", _flow(internal), dashed=True), 0, Qt.AlignmentFlag.AlignHCenter
                )
                layout.addWidget(InternalCard(self.owner, internal), 0, Qt.AlignmentFlag.AlignHCenter)
            subdrivers = [c for c in item.children if c.role is Role.SUBDRIVER]
            if subdrivers:
                classes = sorted({c.cls.__name__ for c in subdrivers})
                exposes = QLabel(
                    f"⤷ exposes {len(subdrivers)} sub-driver{'s' if len(subdrivers) > 1 else ''}"
                    f" ({', '.join(classes)})"
                )
                exposes.setObjectName("Muted")
                exposes.setToolTip("\n".join(f"{c.path} : {c.cls.__name__}" for c in subdrivers))
                layout.addSpacing(4)
                layout.addWidget(exposes, 0, Qt.AlignmentFlag.AlignHCenter)

        if node.children:
            row = QHBoxLayout()
            row.setSpacing(24)
            row.addStretch(1)
            for slot, child in node.children.items():
                spec = node.slot_spec(slot)
                column = QVBoxLayout()
                column.setSpacing(0)
                flow = child.info.provides_label if child is not None else spec.type_label
                column.addWidget(Connector(slot, flow), 0, Qt.AlignmentFlag.AlignHCenter)
                if child is None:
                    column.addWidget(SlotWidget(self.owner, node, spec), 0, Qt.AlignmentFlag.AlignHCenter)
                else:
                    column.addWidget(self._node_view(child), 0, Qt.AlignmentFlag.AlignHCenter)
                column.addStretch(1)
                row.addLayout(column)
            row.addStretch(1)
            layout.addLayout(row)
        elif node.kind is Kind.ADAPTER:
            layout.addWidget(Connector("", "bytes" if node.info.provides is bytes else ""), 0,
                             Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(Pill("Device", _device_text(node)), 0, Qt.AlignmentFlag.AlignHCenter)
        return view

    def _internal_chain(self, item: RuntimeItem) -> list[RuntimeItem]:
        chain = []
        for child in item.children:
            if child.role is Role.INTERNAL:
                chain.append(child)
                chain.extend(self._internal_chain(child))
        return chain


def _flow(item: RuntimeItem) -> str:
    try:
        return component_info(item.cls).provides_label
    except TypeError:
        return ""


def _device_text(node: StackNode) -> str:
    if node.instance is not None:
        try:
            return str(node.instance.descriptor)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    values = [format_value(v) for k, v in node.values.items() if k in _DESCRIPTOR_HINTS]
    return ":".join(v.strip("'") for v in values)


_DESCRIPTOR_HINTS = ("address", "port", "baudrate", "descriptor", "transport")
