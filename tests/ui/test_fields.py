"""Parameter editors, offscreen"""

import inspect
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

from syndesi import FlexibleEnum  # noqa: E402
from syndesi.ui.core.introspection import FieldType, ParamSpec  # noqa: E402
from syndesi.ui.fields import FieldEditor, format_value  # noqa: E402


class _Range(FlexibleEnum):
    _2V = "R1", 2, "2V"
    AUTO = "AUTO"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_flexible_enum_shows_its_label(app):
    spec = ParamSpec(
        "voltage_range",
        annotation=_Range,
        default=inspect.Parameter.empty,
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        field_type=FieldType.CHOICE,
        choices=list(_Range),
    )
    editor = FieldEditor(spec)
    combo = editor.findChild(QComboBox)
    # The device wants R1, people read 2V
    assert [combo.itemText(i) for i in range(combo.count())] == ["2V", "AUTO"]
    editor.set_value(_Range.AUTO)
    assert editor.value() is _Range.AUTO
    assert format_value(_Range._2V) == "2V"
