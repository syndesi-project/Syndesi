# File : fields.py
# Author : Sébastien Deriaz
# License : GPL
"""
Editors generated from the parameters of a constructor or of a method

The same form configures a layer of the stack and the arguments of a command. Its
values only hold what differs from the defaults, see model.StackNode
"""

from __future__ import annotations

import enum
import inspect
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    Length,
    StopCondition,
    Termination,
    Total,
)
from ..tools.others import DEFAULT
from .core.introspection import FieldType, ParamSpec
from .style.icons import set_icon

# ┌─────────┐
# │ Escapes │
# └─────────┘

_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "\\": "\\", "'": "'", '"': '"'}
_REVERSE = {"\n": "\\n", "\r": "\\r", "\t": "\\t", "\\": "\\\\"}


def format_escaped(value: str | bytes) -> str:
    """Show control characters as \\n, \\r, \\xHH"""
    out = []
    if isinstance(value, bytes):
        for byte in value:
            char = chr(byte)
            if char in _REVERSE:
                out.append(_REVERSE[char])
            elif 0x20 <= byte < 0x7F:
                out.append(char)
            else:
                out.append(f"\\x{byte:02x}")
        return "".join(out)
    for char in value:
        if char in _REVERSE:
            out.append(_REVERSE[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\x{ord(char):02x}")
        else:
            out.append(char)
    return "".join(out)


def parse_escaped(text: str, as_bytes: bool) -> str | bytes:
    """
    Inverse of format_escaped. \\xHH is a byte in bytes mode, a character otherwise,
    the other characters are encoded in UTF-8
    """
    data = bytearray()
    chars: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            following = text[i + 1]
            if following in _ESCAPES:
                piece = _ESCAPES[following]
                chars.append(piece)
                data += piece.encode()
                i += 2
                continue
            if following == "x" and i + 3 < len(text) + 0:
                try:
                    value = int(text[i + 2 : i + 4], 16)
                except ValueError as e:
                    raise ValueError(f"Invalid escape \\x{text[i + 2:i + 4]}") from e
                chars.append(chr(value))
                data.append(value)
                i += 4
                continue
        chars.append(char)
        data += char.encode()
        i += 1
    return bytes(data) if as_bytes else "".join(chars)


def parse_hex(text: str) -> bytes:
    """'01 02 ff' or '0102ff' to bytes"""
    return bytes.fromhex(text.replace(" ", "").replace(",", ""))


def format_value(value: Any) -> str:
    """Short text of a value for the user"""
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, StopCondition):
        return str(value)
    if isinstance(value, list) and value and all(isinstance(v, StopCondition) for v in value):
        return ", ".join(str(v) for v in value)
    return repr(value)


def expression_namespace() -> dict[str, Any]:
    """Names available in the python expression fields"""
    # pylint: disable=import-outside-toplevel
    import syndesi
    from syndesi.protocols import modbus

    namespace: dict[str, Any] = {}
    namespace.update({n: getattr(modbus, n) for n in dir(modbus) if not n.startswith("_")})
    namespace.update({n: getattr(syndesi, n) for n in syndesi.__all__})
    namespace["DEFAULT"] = DEFAULT
    return namespace


# ┌─────────────────┐
# │ Stop-conditions │
# └─────────────────┘

_SC_TYPES: dict[str, type[StopCondition]] = {
    "Termination": Termination,
    "Length": Length,
    "Continuation": Continuation,
    "Total": Total,
    "Fragment": FragmentSC,
}


class _StopConditionRow(QWidget):
    changed = Signal()
    removed = Signal(object)

    def __init__(self, sc: StopCondition | None = None) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.type = QComboBox()
        self.type.setMinimumWidth(90)
        self.type.addItems(list(_SC_TYPES))
        self.text = QLineEdit("\\n")
        self.text.setToolTip("Sequence ending a frame, \\n \\r \\xHH accepted")
        self.length = QSpinBox()
        self.length.setMinimumWidth(60)
        self.length.setRange(1, 1_000_000)
        self.length.setValue(10)
        self.seconds = QDoubleSpinBox()
        self.seconds.setMinimumWidth(60)
        self.seconds.setRange(0, 3600)
        self.seconds.setDecimals(3)
        self.seconds.setSingleStep(0.05)
        self.seconds.setSuffix(" s")
        self.seconds.setValue(0.2)
        remove = QToolButton()
        set_icon(remove, "x")
        remove.setToolTip("Remove this stop-condition")
        remove.clicked.connect(lambda: self.removed.emit(self))
        for widget in (self.type, self.text, self.length, self.seconds):
            layout.addWidget(widget)
        layout.addWidget(remove)
        layout.setStretch(1, 1)
        layout.setStretch(2, 1)
        layout.setStretch(3, 1)
        self.type.currentTextChanged.connect(self._type_changed)
        self.text.textChanged.connect(self.changed)
        self.length.valueChanged.connect(self.changed)
        self.seconds.valueChanged.connect(self.changed)
        if sc is not None:
            self.set_value(sc)
        self._type_changed()

    def _type_changed(self) -> None:
        name = self.type.currentText()
        self.text.setVisible(name == "Termination")
        self.length.setVisible(name == "Length")
        self.seconds.setVisible(name in ("Continuation", "Total"))
        self.changed.emit()

    def set_value(self, sc: StopCondition) -> None:
        """Show a stop-condition"""
        for name, cls in _SC_TYPES.items():
            if isinstance(sc, cls):
                self.type.setCurrentText(name)
        if isinstance(sc, Termination):
            self.text.setText(format_escaped(sc.sequence))
        elif isinstance(sc, Length):
            self.length.setValue(sc.n)
        elif isinstance(sc, Continuation):
            self.seconds.setValue(sc.continuation)
        elif isinstance(sc, Total):
            self.seconds.setValue(sc.total)

    def value(self) -> StopCondition:
        """Stop-condition shown"""
        name = self.type.currentText()
        if name == "Termination":
            sequence = parse_escaped(self.text.text(), as_bytes=True)
            if not sequence:
                raise ValueError("A termination can't be empty")
            return Termination(sequence)
        if name == "Length":
            return Length(self.length.value())
        if name == "Continuation":
            return Continuation(self.seconds.value())
        if name == "Total":
            return Total(self.seconds.value())
        return FragmentSC()


class StopConditionsEditor(QWidget):
    """A list of stop-conditions, a frame ends on the first one reached"""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._rows: list[_StopConditionRow] = []
        self._add = QPushButton("Add stop-condition")
        set_icon(self._add, "plus")
        self._add.clicked.connect(lambda: self._add_row(Termination(b"\n")))
        self._layout.addWidget(self._add)

    def _add_row(self, sc: StopCondition | None) -> None:
        row = _StopConditionRow(sc)
        row.changed.connect(self.changed)
        row.removed.connect(self._remove_row)
        self._rows.append(row)
        self._layout.insertWidget(len(self._rows) - 1, row)
        self.changed.emit()

    def _remove_row(self, row: _StopConditionRow) -> None:
        self._rows.remove(row)
        row.deleteLater()
        self.changed.emit()

    def set_value(self, value: StopCondition | list[StopCondition]) -> None:
        """Show stop-conditions"""
        for row in list(self._rows):
            self._rows.remove(row)
            row.deleteLater()
        for sc in value if isinstance(value, list) else [value]:
            self._add_row(sc)

    def value(self) -> list[StopCondition]:
        """Stop-conditions shown"""
        if not self._rows:
            raise ValueError("Add at least one stop-condition")
        return [row.value() for row in self._rows]


# ┌────────┐
# │ Fields │
# └────────┘

class FieldEditor(QWidget):
    """Editor of one parameter"""

    changed = Signal()

    def __init__(self, spec: ParamSpec) -> None:
        super().__init__()
        self.spec = spec
        # The stop-conditions list is tall : its checkboxes go above it
        vertical = spec.field_type is FieldType.STOP_CONDITIONS
        outer = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        boxes = QHBoxLayout()
        outer.addLayout(boxes)
        layout = QHBoxLayout()
        outer.addLayout(layout, 1)

        # Checked : the parameter isn't passed, the component uses its own default
        self._default_box: QCheckBox | None = None
        if spec.allows_default:
            self._default_box = QCheckBox("Default")
            self._default_box.setToolTip("Let the component choose (the parameter isn't passed)")
            boxes.addWidget(self._default_box)
        # Checked : None is passed
        self._none_box: QCheckBox | None = None
        if spec.allows_none:
            self._none_box = QCheckBox("None")
            self._none_box.setToolTip("Pass None")
            boxes.addWidget(self._none_box)
        if vertical:
            boxes.addStretch(1)

        self._escaped = spec.field_type in (FieldType.TEXT, FieldType.BYTES) or (
            spec.field_type is FieldType.STR
            and isinstance(spec.default, str)
            and format_escaped(spec.default) != spec.default
        )
        self._editor = self._make_editor()
        layout.addWidget(self._editor, 1)

        if spec.suggestions is not None:
            refresh = QToolButton()
            set_icon(refresh, "refresh")
            refresh.setToolTip("Refresh the list")
            refresh.clicked.connect(self._refresh_suggestions)
            layout.addWidget(refresh)

        self._set_initial()
        for box in (self._default_box, self._none_box):
            if box is not None:
                box.toggled.connect(self._boxes_changed)
        self._boxes_changed()

    # Construction

    def _make_editor(self) -> QWidget:
        spec = self.spec
        editor: QWidget
        match spec.field_type:
            case FieldType.BOOL:
                editor = QCheckBox()
                editor.toggled.connect(self.changed)
            case FieldType.INT:
                editor = QSpinBox()
                editor.setRange(-(2**31), 2**31 - 1)
                editor.setMinimumWidth(80)
                editor.valueChanged.connect(self.changed)
            case FieldType.FLOAT:
                editor = QDoubleSpinBox()
                editor.setRange(-1e9, 1e9)
                editor.setDecimals(3)
                editor.setMinimumWidth(80)
                editor.setSingleStep(0.1)
                editor.valueChanged.connect(self.changed)
            case FieldType.CHOICE:
                editor = QComboBox()
                editor.setMinimumWidth(80)
                for choice in spec.choices or []:
                    text = str(choice.value) if isinstance(choice, enum.Enum) else str(choice)
                    editor.addItem(text, choice)
                editor.currentIndexChanged.connect(self.changed)
            case FieldType.STOP_CONDITIONS:
                editor = StopConditionsEditor()
                editor.changed.connect(self.changed)
            case _:
                if spec.suggestions is not None:
                    editor = QComboBox()
                    editor.setEditable(True)
                    editor.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                    editor.editTextChanged.connect(self.changed)
                    self._fill_suggestions(editor)
                else:
                    editor = QLineEdit()
                    editor.textChanged.connect(self.changed)
                    editor.textChanged.connect(self._validate)
                    if self._escaped:
                        editor.setPlaceholderText("text, \\n \\r \\t \\xHH accepted")
                    elif spec.field_type is FieldType.EXPRESSION:
                        editor.setPlaceholderText("python expression, e.g. [1, 2, 3]")
        return editor

    def _fill_suggestions(self, combo: QComboBox) -> None:
        assert self.spec.suggestions is not None
        text = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        try:
            combo.addItems([str(s) for s in self.spec.suggestions()])
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        combo.setEditText(text)
        combo.blockSignals(False)

    def _refresh_suggestions(self) -> None:
        if isinstance(self._editor, QComboBox):
            self._fill_suggestions(self._editor)

    def _set_initial(self) -> None:
        spec = self.spec
        default = spec.default
        if spec.has_default and default is not DEFAULT and default is not None:
            try:
                self.set_value(default)
            except (TypeError, ValueError):
                pass
            return
        if spec.has_default and default is DEFAULT and self._default_box is not None:
            self._default_box.setChecked(True)
        elif spec.has_default and default is None and self._none_box is not None:
            self._none_box.setChecked(True)
        if spec.field_type is FieldType.STOP_CONDITIONS and isinstance(self._editor, StopConditionsEditor):
            self._editor.set_value([Termination(b"\n")])

    def _boxes_changed(self) -> None:
        default = self._default_box is not None and self._default_box.isChecked()
        none = self._none_box is not None and self._none_box.isChecked()
        if self._none_box is not None:
            self._none_box.setEnabled(not default)
        self._editor.setEnabled(not default and not none)
        self.changed.emit()

    def _validate(self) -> None:
        if isinstance(self._editor, QLineEdit):
            try:
                self.value()
                invalid = False
            except ValueError:
                invalid = True
            self._editor.setProperty("invalid", invalid)
            self._editor.style().unpolish(self._editor)
            self._editor.style().polish(self._editor)

    # Values

    def set_value(self, value: Any) -> None:
        """Show a value (DEFAULT and None check the matching box)"""
        if self._default_box is not None:
            self._default_box.setChecked(value is DEFAULT)
            if value is DEFAULT:
                return
        if self._none_box is not None:
            self._none_box.setChecked(value is None)
            if value is None:
                return
        editor = self._editor
        if isinstance(editor, QCheckBox):
            editor.setChecked(bool(value))
        elif isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value))
        elif isinstance(editor, QSpinBox):
            editor.setValue(int(value))
        elif isinstance(editor, StopConditionsEditor):
            editor.set_value(value)
        elif isinstance(editor, QComboBox) and not editor.isEditable():
            index = editor.findData(value)
            if index < 0:
                index = editor.findText(str(value.value if isinstance(value, enum.Enum) else value))
            if index >= 0:
                editor.setCurrentIndex(index)
        elif isinstance(editor, QComboBox):
            editor.setEditText(str(value))
        elif isinstance(editor, QLineEdit):
            if self._escaped and isinstance(value, (str, bytes)):
                editor.setText(format_escaped(value))
            elif self.spec.field_type is FieldType.EXPRESSION:
                editor.setText(repr(value))
            else:
                editor.setText(str(value))

    def value(self) -> Any:
        """Value of the parameter, raises ValueError if it's invalid"""
        if self._default_box is not None and self._default_box.isChecked():
            return DEFAULT
        if self._none_box is not None and self._none_box.isChecked():
            return None
        editor = self._editor
        spec = self.spec
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        if isinstance(editor, QDoubleSpinBox):
            return editor.value()
        if isinstance(editor, QSpinBox):
            return editor.value()
        if isinstance(editor, StopConditionsEditor):
            return editor.value()
        if isinstance(editor, QComboBox) and not editor.isEditable():
            return editor.currentData()
        text = editor.currentText() if isinstance(editor, QComboBox) else editor.text()  # type: ignore[attr-defined]
        if spec.field_type is FieldType.EXPRESSION:
            if not text.strip():
                raise ValueError("Enter a python expression")
            try:
                return eval(text, expression_namespace())  # pylint: disable=eval-used
            except Exception as e:
                raise ValueError(f"Invalid expression : {e}") from e
        if spec.field_type is FieldType.BYTES:
            return parse_escaped(text, as_bytes=True)
        if self._escaped:
            return parse_escaped(text, as_bytes=False)
        return text

    def is_default(self) -> bool:
        """True if the value is the default one, the parameter is then left out"""
        spec = self.spec
        if not spec.has_default:
            return False
        try:
            value = self.value()
        except ValueError:
            return False
        if value is spec.default:
            return True
        if type(value) is type(spec.default):  # pylint: disable=unidiomatic-typecheck
            try:
                return bool(value == spec.default)
            except Exception:  # pylint: disable=broad-exception-caught
                return False
        return False


class ParamForm(QWidget):
    """Form of the parameters of a constructor or of a method"""

    changed = Signal()

    def __init__(
        self, params: list[ParamSpec], *, show_docs: bool = True, labels_above: bool = False
    ) -> None:
        super().__init__()
        self.editors: dict[str, FieldEditor] = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows if labels_above else QFormLayout.RowWrapPolicy.WrapLongRows
        )
        layout.setVerticalSpacing(10 if labels_above else 6)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for spec in params:
            if spec.is_slot or spec.hidden:
                continue
            editor = FieldEditor(spec)
            editor.changed.connect(self.changed)
            self.editors[spec.name] = editor
            label = QLabel(spec.name + (" *" if spec.required else ""))
            if spec.required:
                label.setObjectName("Title")
            tooltip = spec.type_label
            if spec.doc.description:
                tooltip += "\n\n" + spec.doc.description
            label.setToolTip(tooltip)
            editor.setToolTip(tooltip)
            field = QWidget()
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(1)
            field_layout.addWidget(editor)
            if show_docs and spec.doc.description:
                doc = QLabel(spec.doc.description)
                doc.setObjectName("Muted")
                doc.setWordWrap(True)
                font = doc.font()
                font.setPointSizeF(font.pointSizeF() * 0.88)
                doc.setFont(font)
                field_layout.addWidget(doc)
            layout.addRow(label, field)
        if not self.editors:
            empty = QLabel("No parameter")
            empty.setObjectName("Muted")
            layout.addRow(empty)

    def set_values(self, values: dict[str, Any]) -> None:
        """Show values, the other fields keep their default"""
        for name, value in values.items():
            editor = self.editors.get(name)
            if editor is not None:
                editor.blockSignals(True)
                try:
                    editor.set_value(value)
                finally:
                    editor.blockSignals(False)

    def values(self) -> tuple[dict[str, Any], dict[str, str]]:
        """(values different from the defaults, errors by parameter)"""
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, editor in self.editors.items():
            try:
                value = editor.value()
            except ValueError as e:
                errors[name] = str(e)
                continue
            if not editor.is_default():
                values[name] = value
        return values, errors

    def call_arguments(self) -> tuple[list[Any], dict[str, Any]]:
        """Arguments of a call, raises ValueError on the first invalid field"""
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        values, errors = self.values()
        if errors:
            name, message = next(iter(errors.items()))
            raise ValueError(f"{name} : {message}")
        for name, editor in self.editors.items():
            if name not in values:
                continue
            if editor.spec.kind is inspect.Parameter.POSITIONAL_ONLY:
                args.append(values[name])
            else:
                kwargs[name] = values[name]
        return args, kwargs
