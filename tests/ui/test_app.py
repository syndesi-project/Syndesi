"""Smoke test of the GUI, offscreen, against the fake power supply of the examples"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication  # noqa: E402

from syndesi import IP  # noqa: E402
from syndesi.ui.app import MainWindow  # noqa: E402
from syndesi.ui.bench.command_panel import CommandPanel  # noqa: E402
from syndesi.ui.bench.io_panel import IOPanel  # noqa: E402
from syndesi.ui.core.library import Library  # noqa: E402
from syndesi.ui.fields import format_escaped, parse_escaped  # noqa: E402
from syndesi.ui.style import theme  # noqa: E402

EXAMPLES = Path(__file__).parents[2] / "examples" / "drivers"


@pytest.fixture(scope="module")
def psu_port():
    sys.path.insert(0, str(EXAMPLES))
    import fake_psu  # pylint: disable=import-outside-toplevel

    server = fake_psu.Server(("127.0.0.1", 0), fake_psu.FakePSU)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    theme.apply(application, "dark")
    return application


def _wait(app, condition, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_escapes():
    for value in (b"\n", b"a\r\n", b"\x00\xff", "tab\there"):
        text = format_escaped(value)
        assert parse_escaped(text, isinstance(value, bytes)) == value
    assert parse_escaped("\\x41\\n", as_bytes=True) == b"A\n"


def test_build_and_run_commands(app, psu_port):
    library = Library.default()
    classes = {c.__name__: c for c in library.load(str(EXAMPLES / "demo_psu.py"))}
    window = MainWindow(library)
    window.show()
    stack = window.stack_screen
    stack.fill_slot(None, None, classes["Bench"])
    stack.fill_slot(stack.root, "psu", classes["DemoPowerSupply"])
    psu = stack.root.children["psu"]
    stack.fill_slot(psu, "adapter", IP)
    psu.children["adapter"].values.update(address="127.0.0.1", port=psu_port)
    # What the inspector does when a field changes
    stack.node_changed(psu.children["adapter"])
    assert window.build_button.isEnabled()
    assert "bench = Bench(demo_power_supply)" in stack.code.editor.toPlainText()

    window.build()
    test = window.test_screen
    assert _wait(app, lambda: test.runtime is not None and not window.worker.busy)
    assert window.pages.currentIndex() == 1
    labels = {i.label for i in test.runtime.walk()}
    assert {"Bench", "DemoPowerSupply", "SCPI", "IP", "PowerSupplyChannel"} <= labels

    # A command of the top driver
    test.open()
    panel = test.panel(test.runtime.root).findChild(CommandPanel)
    row = next(i for i in range(panel.list.count()) if panel.list.item(i).text().strip() == "power_up")
    panel.list.setCurrentRow(row)
    panel.run()
    assert _wait(app, lambda: any(e.label == "= result" for e in test.log_view.model.entries))
    result = next(e for e in test.log_view.model.entries if e.label == "= result")
    assert abs(float(result.data) - 3.3) < 0.01
    # Events were received, and are hidden until "Show events" is checked
    assert any(e.is_event for e in test.log_view.model.entries)
    shown = test.log_view.filter.rowCount()
    test.log_view.show_events.setChecked(True)
    assert test.log_view.filter.rowCount() > shown

    # The internal protocol can be used directly
    scpi = next(i for i in test.runtime.walk() if i.label == "SCPI")
    test.select(scpi)
    io = test.panel(scpi).findChild(IOPanel)
    io.query_input.setEditText("*IDN?")
    io.query()
    assert _wait(app, lambda: any("DemoPSU" in e.data and e.label == "← read" and not e.is_event
                                  for e in test.log_view.model.entries))

    # A sub-driver returned by a command is already in the tree : nothing added twice
    count = len(list(test.runtime.walk()))
    psu_item = next(i for i in test.runtime.walk() if i.label == "DemoPowerSupply")
    test.add_returned(psu_item, psu_item.instance.channel(1), "channel(1)")
    assert len(list(test.runtime.walk())) == count

    window.close()


def test_pyside_keeps_none_alive():
    """PySide6 6.12.0 + Python 3.11 aborts after a while, see app.leaks_none_references"""
    from syndesi.ui.app import leaks_none_references  # pylint: disable=import-outside-toplevel

    assert not leaks_none_references()


def test_main_rows_are_not_duplicated_by_events(app, psu_port):
    from syndesi import Delimited  # pylint: disable=import-outside-toplevel

    window = MainWindow(Library.default())
    stack = window.stack_screen
    stack.fill_slot(None, None, Delimited)
    stack.fill_slot(stack.root, "adapter", IP)
    stack.root.children["adapter"].values.update(address="127.0.0.1", port=psu_port)
    window.build()
    test = window.test_screen
    assert _wait(app, lambda: test.runtime is not None and not window.worker.busy)
    io = test.panel(test.runtime.root).findChild(IOPanel)
    io.query_input.setEditText("*IDN?")
    io.query()
    assert _wait(app, lambda: "DemoPSU" in io.received.toPlainText())
    _wait(app, lambda: False, timeout=0.3)
    rows = [e for e in test.log_view.model.entries if e.source == "Delimited"]
    writes = [e for e in rows if e.label == "→ write"]
    reads = [e for e in rows if e.label == "← read"]
    # One row each, the main ones : the ProtocolWrite/ReadEvent were dropped
    assert len(writes) == 1 and not writes[0].is_event
    assert len(reads) == 1 and not reads[0].is_event
    # The adapter events are still there
    assert any(e.source == "IP" and e.label == "→ write" for e in test.log_view.model.entries)
    window.close()


def test_frame_buffer_view(app, psu_port):
    from syndesi import Delimited  # pylint: disable=import-outside-toplevel

    window = MainWindow(Library.default())
    stack = window.stack_screen
    stack.fill_slot(None, None, Delimited)
    stack.fill_slot(stack.root, "adapter", IP)
    stack.root.children["adapter"].values.update(address="127.0.0.1", port=psu_port)
    window.build()
    test = window.test_screen
    assert _wait(app, lambda: test.runtime is not None and not window.worker.busy)
    assert window.edit_button.isVisibleTo(window) and not window.build_button.isVisibleTo(window)
    io = test.panel(test.runtime.root).findChild(IOPanel)
    # Answers to writes nobody reads wait in the buffer
    for command in ("*IDN?", "VOLT?"):
        io.write_input.setEditText(command)
        io.write()
    assert _wait(app, lambda: len(io.buffer.frames()) == 2)
    assert io.buffer.frames()[0][2] == "Syndesi,DemoPSU,0001,1.0"
    # A buffered read takes the oldest
    io.read()
    assert _wait(app, lambda: len(io.buffer.frames()) == 1)
    assert "DemoPSU" in io.received.toPlainText()
    io.clear_buffer()
    assert _wait(app, lambda: not io.buffer.frames())
    window.close()


def test_portal_color_scheme_values():
    from syndesi.ui.style.system import _scheme_is_dark  # pylint: disable=import-outside-toplevel

    # org.freedesktop.appearance color-scheme : 1 dark, 2 light, 0 no preference
    assert _scheme_is_dark(1) is True
    assert _scheme_is_dark(2) is False
    assert _scheme_is_dark(0) is False
    assert _scheme_is_dark("unexpected") is None


def test_stylesheet_is_complete(app):
    """Every token is filled in, and the rules the screens rely on are there"""
    for dark in (False, True):
        sheet = theme.Theme(dark=dark).stylesheet()
        assert "$" not in sheet
        for rule in ("QWidget#Panel", "QFrame#Card", "QPushButton#Primary", "QPushButton#Outline",
                     "QLabel#Badge", "QListView#Field"):
            assert rule in sheet, rule
