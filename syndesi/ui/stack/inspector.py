# File : inspector.py
# Author : Sébastien Deriaz
# License : GPL
"""
Configuration of the selected component, and the python code of the stack
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QFont,
    QGuiApplication,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.introspection import (
    Kind,
    ParamSpec,
)
from ..core.runtime import (
    RuntimeItem,
)
from ..core.stack import StackNode
from ..fields import ParamForm
from ..style.icons import set_icon
from ..style.theme import monospace, theme
from ..style.widgets import (
    kind_badge,
    panel,
    section,
)

INTRO = """<h3>How Syndesi works</h3>
<p>Communication with a device is a <b>stack of layers</b>, each one built on the one
below:</p>
<p><span style="color:{driver}">■ <b>Driver</b></span> — the commands of an instrument
(<code>get_identification()</code>, <code>set_voltage()</code>…). It often builds its
protocol itself.</p>
<p><span style="color:{protocol}">■ <b>Protocol</b></span> — turns frames into messages:
text lines (Delimited), SCPI, Modbus…</p>
<p><span style="color:{adapter}">■ <b>Adapter</b></span> — the transport (IP, serial
port, VISA). It sends bytes and cuts what it receives into frames with
<i>stop-conditions</i>.</p>
<p>Start with the <b>top layer</b>, the one you want to test, then fill the slots below
it. Only the components a slot accepts (according to the type hints) can go in it.</p>
<p>Drag a component from the library, or click <b>+</b> in a slot.</p>"""

if TYPE_CHECKING:
    from .screen import StackScreen


class Inspector(QScrollArea):
    """Configuration of the selected component"""

    values_changed = Signal(object)

    def __init__(self, screen: StackScreen) -> None:
        super().__init__()
        self.owner = screen
        panel(self)
        self.setWidgetResizable(True)
        self.setMinimumWidth(300)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._form: ParamForm | None = None
        self._errors = QLabel()
        self._node: StackNode | None = None
        self.show_intro()

    def _container(self) -> QVBoxLayout:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        self.setWidget(container)
        return layout

    def show_intro(self) -> None:
        """Explain the layers"""
        self._node = None
        self._form = None
        layout = self._container()
        t = theme()
        text = QLabel(
            INTRO.format(
                driver=t.kind(Kind.DRIVER).name(),
                protocol=t.kind(Kind.PROTOCOL).name(),
                adapter=t.kind(Kind.ADAPTER).name(),
            )
        )
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(text)
        layout.addStretch(1)

    def show_slot(self, parent: StackNode | None, spec: ParamSpec | None) -> None:
        """Explain what a slot accepts"""
        self._node = None
        self._form = None
        layout = self._container()
        title = QLabel("Top layer" if spec is None else f"Slot '{spec.name}'")
        title.setObjectName("Heading")
        layout.addWidget(title)
        if spec is None:
            text = (
                "The top layer is the component you will test : a driver to run its "
                "commands, a protocol or an adapter to send and receive data."
            )
        else:
            assert parent is not None
            text = (
                f"<b>{parent.info.name}</b> is built on <code>{spec.name}</code>, typed "
                f"<code>{spec.type_label}</code>.<br><br>"
                "The library only enables the components this type hint accepts. "
                "Double-click one, or drag it here."
            )
            if spec.doc.description:
                text += f"<br><br><i>{spec.doc.description}</i>"
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)

    def show_internal(self, item: RuntimeItem) -> None:
        """A layer built by a driver"""
        self._node = None
        self._form = None
        layout = self._container()
        row = QHBoxLayout()
        row.addWidget(kind_badge(item.kind))
        title = QLabel(item.label)
        title.setObjectName("Heading")
        row.addWidget(title)
        row.addStretch(1)
        layout.addLayout(row)
        owner = item.parent.label if item.parent else "?"
        label = QLabel(
            f"Built by <b>{owner}</b> and stored in <code>{item.path}</code>.<br><br>"
            "An internal layer is configured by the driver that owns it : change the "
            "driver parameters instead. It can still be tested directly in the test "
            f"screen.<br><br><code>{item.instance!r}</code>"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)

    def show_node(self, node: StackNode) -> None:
        """Configure a component"""
        self._node = node
        info = node.info
        layout = self._container()
        row = QHBoxLayout()
        row.addWidget(kind_badge(info.kind))
        title = QLabel(info.name)
        title.setObjectName("Heading")
        row.addWidget(title)
        row.addStretch(1)
        layout.addLayout(row)
        if info.summary:
            summary = QLabel(info.summary)
            summary.setWordWrap(True)
            layout.addWidget(summary)
        details = [f"provides <code>{info.provides_label}</code> to the layer above"]
        source = self.owner.library.sources.get(info.cls)
        details.append(f"from <code>{source or info.cls.__module__}</code>")
        detail = QLabel("<br>".join(details))
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        layout.addSpacing(10)
        layout.addWidget(section("Parameters"))
        self._form = ParamForm(info.params, labels_above=True)
        self._form.set_values(node.values)
        self._form.changed.connect(self._changed)
        layout.addWidget(self._form)
        self._errors = QLabel()
        self._errors.setObjectName("Error")
        self._errors.setWordWrap(True)
        layout.addWidget(self._errors)

        if info.slots:
            layout.addSpacing(10)
            layout.addWidget(section("Built on"))
            for spec in info.slots:
                child = node.children.get(spec.name)
                state = child.info.name if child is not None else "— empty —"
                label = QLabel(f"<code>{spec.name}</code> : {state}<br>"
                               f"<span style='color:{theme().muted.name()}'>accepts "
                               f"<code>{spec.type_label}</code></span>")
                label.setWordWrap(True)
                layout.addWidget(label)
        layout.addStretch(1)

    def _changed(self) -> None:
        if self._node is None or self._form is None:
            return
        values, errors = self._form.values()
        self._node.values = values
        self._errors.setText("\n".join(f"{k} : {v}" for k, v in errors.items()))
        self.values_changed.emit(self._node)


# ┌──────┐
# │ Code │
# └──────┘


class PythonHighlighter(QSyntaxHighlighter):
    """Minimal python highlighting"""

    def highlightBlock(self, text: str) -> None:
        import re  # pylint: disable=import-outside-toplevel

        keyword = QTextCharFormat()
        keyword.setForeground(theme().kind(Kind.DRIVER))
        keyword.setFontWeight(QFont.Weight.Bold)
        string = QTextCharFormat()
        string.setForeground(theme().kind(Kind.PROTOCOL))
        comment = QTextCharFormat()
        comment.setForeground(theme().muted)
        cls = QTextCharFormat()
        cls.setForeground(theme().kind(Kind.ADAPTER))
        for match in re.finditer(r"\b(from|import|await|print|async|def|return)\b", text):
            self.setFormat(match.start(), match.end() - match.start(), keyword)
        for match in re.finditer(r"\b[A-Z]\w*", text):
            self.setFormat(match.start(), match.end() - match.start(), cls)
        for match in re.finditer(r"b?'[^']*'|b?\"[^\"]*\"", text):
            self.setFormat(match.start(), match.end() - match.start(), string)
        index = text.find("#")
        if index >= 0:
            self.setFormat(index, len(text) - index, comment)


class CodePreview(QWidget):
    """The python code building the same stack"""

    def __init__(self) -> None:
        super().__init__()
        panel(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(section("Equivalent Python code"))
        row.addStretch(1)
        self.editor = QPlainTextEdit()
        copy = QToolButton()
        copy.setText("Copy")
        set_icon(copy, "copy")
        copy.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.editor.toPlainText()))
        row.addWidget(copy)
        layout.addLayout(row)
        self.editor.setReadOnly(True)
        self.editor.setFont(monospace(0.92))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlighter = PythonHighlighter(self.editor.document())
        layout.addWidget(self.editor)

    def retheme(self) -> None:
        """Color the code with the colors of a new theme"""
        self._highlighter.rehighlight()

    def set_code(self, code: str) -> None:
        """Show code"""
        self.editor.setPlainText(code)
