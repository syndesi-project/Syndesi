# File : app.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi GUI : main window and entry point

    syndesi ui                              start with an empty stack
    syndesi ui stack.json                   open a saved stack
    syndesi ui -l ./psu.py                  add the components of a file to the library
    syndesi ui -l ./psu.py:PSU              ... and put PSU on top of the stack
    syndesi ui -l mypackage.drivers         add the components of a module
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLoggingCategory, QObject, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from .bench import TestScreen
from .core.library import Library, LibraryError
from .core.runtime import RuntimeTree
from .core.stack import StackNode
from .core.stack_file import load_stack, save_stack
from .stack import StackScreen
from .style import theme as theme_module
from .style.icons import set_icon, set_pixmap
from .style.widgets import panel
from .worker import Worker, error_text

STACK_FILTER = "Syndesi stack (*.json)"


class MainWindow(QMainWindow):
    """Two screens : the stack, then the test of what was built"""

    def __init__(self, library: Library) -> None:
        super().__init__()
        self.library = library
        self.worker = Worker()
        self._path: Path | None = None
        # Built : the test screen has something to show. Outdated : the stack was
        # edited since, the test screen shows the previous build
        self._built = False
        self._outdated = False
        self.setWindowTitle("Syndesi")
        self.resize(1360, 860)
        self.setMinimumSize(900, 600)

        self.stack_screen = StackScreen(library)
        self.stack_screen.changed.connect(self._stack_changed)
        self.test_screen = TestScreen(self.worker)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.stack_screen)
        self.pages.addWidget(self.test_screen)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header())
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        QShortcut(QKeySequence("F5"), self).activated.connect(self._build_shortcut)
        self.worker.busy_changed.connect(self._busy)
        theme_module.events().changed.connect(self._theme_changed)
        self.show_step(0)

    def _header(self) -> QWidget:
        """Logo, file actions, and the navigation between the two screens"""
        header = panel(QWidget(), "Header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 12, 4)
        logo = QLabel()
        set_pixmap(logo, "layers", "accent", size=22)
        layout.addWidget(logo)
        name = QLabel("Syndesi")
        name.setObjectName("Brand")
        layout.addWidget(name)
        layout.addStretch(1)
        for text, icon_name, slot, shortcut in (
            ("New", "file-plus", self.new_stack, QKeySequence.StandardKey.New),
            ("Open", "folder", self.open_stack, QKeySequence.StandardKey.Open),
            ("Save", "save", self.save_stack, QKeySequence.StandardKey.Save),
        ):
            action = set_icon(QAction(text, self), icon_name)
            action.setShortcut(shortcut)
            action.setToolTip(f"{text} ({QKeySequence(shortcut).toString()})")
            action.triggered.connect(slot)
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            layout.addWidget(button)
        layout.addSpacing(12)

        # Only the buttons that make sense on the screen shown, see _update_steps
        self.to_test_button = _nav_button("Back to test", "arrow-right", "Outline")
        self.to_test_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.to_test_button.setToolTip("Go back to the stack as it was built, without rebuilding it")
        self.to_test_button.clicked.connect(lambda: self.show_step(1))
        self.build_button = _nav_button("Build && test", "play", "Primary")
        self.build_button.setToolTip("Build the stack and test it (F5)")
        self.build_button.clicked.connect(self.build)
        self.edit_button = _nav_button("Edit the stack", "arrow-left", "Outline")
        self.edit_button.clicked.connect(lambda: self.show_step(0))
        for navigation in (self.to_test_button, self.build_button, self.edit_button):
            layout.addWidget(navigation)
        return header

    def show_step(self, index: int) -> None:
        """Show the stack (0) or the test (1) screen"""
        if index == 1 and not self._built:
            index = 0
        self.pages.setCurrentIndex(index)
        self._update_steps()

    def _update_steps(self) -> None:
        """The navigation buttons, from the screen shown and the state of the build"""
        on_stack = self.pages.currentIndex() == 0
        self.build_button.setVisible(on_stack)
        self.build_button.setText("Rebuild && test" if self._built else "Build && test")
        self.build_button.setEnabled(self.stack_screen.complete and not self.worker.busy)
        # Back to the test without rebuilding, only if it still matches the stack
        self.to_test_button.setVisible(on_stack and self._built and not self._outdated)
        self.edit_button.setVisible(not on_stack)

    def _stack_changed(self) -> None:
        if self._built:
            self._outdated = True
        self._update_steps()

    def _build_shortcut(self) -> None:
        if self.pages.currentIndex() == 0 and self.build_button.isEnabled():
            self.build()

    def _busy(self, busy: bool) -> None:
        self._update_steps()
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _theme_changed(self) -> None:
        """The system switched between light and dark : redraw what isn't styled by Qt"""
        self.stack_screen.retheme()
        self.test_screen.retheme()

    # Build

    def build(self) -> None:
        """Instantiate the stack on the worker thread, then show the test screen"""
        root = self.stack_screen.root
        if root is None or not self.stack_screen.complete:
            return
        self._release()
        root.clear_instances()

        def job() -> RuntimeTree:
            root.build()
            return RuntimeTree(root)

        def done(runtime: Any, error: BaseException | None) -> None:
            if error is not None:
                root.clear_instances()
                details = getattr(error, "__syndesi_traceback__", "") or "".join(
                    traceback.format_exception(error)
                )
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("Cannot build the stack")
                box.setText(error_text(error))
                box.setInformativeText(
                    "A constructor refused the configuration. Check the parameters of the "
                    "layers, the details show where it failed."
                )
                box.setDetailedText(details)
                box.exec()
                return
            self._built = True
            self._outdated = False
            self.stack_screen.set_runtime(runtime)
            self.test_screen.load(runtime)
            self._update_steps()
            self.show_step(1)

        self.worker.submit(job, done)

    def _release(self) -> None:
        """Close the components of the previous build"""
        job = self.test_screen.shutdown_job()
        if job is not None:
            self.worker.submit(job)

    # Files

    def new_stack(self) -> None:
        """Start again from an empty stack"""
        self.stack_screen.set_root(None)
        self._path = None

    def open_stack(self, path: str | None = None) -> None:
        """Load a saved stack"""
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open a stack", "", STACK_FILTER)
            if not path:
                return
        try:
            root = load_stack(path, self.library)
        except (LibraryError, OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "Cannot open the stack", str(e))
            return
        self._path = Path(path)
        self.stack_screen.library_panel.refresh()
        self.stack_screen.set_root(root)
        self.setWindowTitle(f"Syndesi — {self._path.name}")

    def save_stack(self) -> None:
        """Save the stack"""
        start = str(self._path) if self._path else "stack.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save the stack", start, STACK_FILTER)
        if not path:
            return
        try:
            save_stack(path, self.stack_screen.root, self.library)
        except OSError as e:
            QMessageBox.warning(self, "Cannot save the stack", str(e))
            return
        self._path = Path(path)
        self.setWindowTitle(f"Syndesi — {self._path.name}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Close what is open before leaving"""
        job = self.test_screen.shutdown_job()
        if job is not None:
            try:
                self.worker.call_sync(job, timeout=3)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        self.worker.stop()
        super().closeEvent(event)


def _nav_button(text: str, icon_name: str, style: str) -> QPushButton:
    """A large button of the header"""
    button = QPushButton(text)
    button.setObjectName(style)
    button.setProperty("size", "large")
    set_icon(button, icon_name, "white" if style == "Primary" else "accent")
    return button


def leaks_none_references() -> bool:
    """
    True if the PySide6 in use drops a reference to None on every call returning void
    (PySide6 6.12.0). Before Python 3.12 None isn't immortal : the interpreter aborts with
    "none_dealloc" after a few thousand calls, typically while resizing the window
    """
    if sys.version_info >= (3, 12):
        return False
    probe = QObject()
    before = sys.getrefcount(None)
    for _ in range(100):
        probe.setObjectName("probe")
    return sys.getrefcount(None) < before - 50


def main(args: list[str] | None = None) -> int:
    """Entry point of syndesi ui"""
    parser = argparse.ArgumentParser(prog="syndesi ui", description="Syndesi graphical interface")
    parser.add_argument("stack", nargs="?", help="stack file saved by the GUI (.json)")
    parser.add_argument(
        "-l",
        "--load",
        action="append",
        default=[],
        metavar="FILE_OR_MODULE[:CLASS]",
        help="add the components of a python file or module to the library, "
        "':Class' also puts it on top of the stack",
    )
    parser.add_argument("--theme", choices=["auto", "light", "dark"], default="auto")
    parser.add_argument("--version", action="version", version=f"Syndesi {__version__}")
    arguments = parser.parse_args(args)

    if leaks_none_references():
        import PySide6  # pylint: disable=import-outside-toplevel

        sys.stderr.write(
            f"PySide6 {PySide6.__version__} has a reference counting bug that crashes "
            f"Python {sys.version_info.major}.{sys.version_info.minor} after a while.\n"
            "Install another version, for example :\n"
            "  python -m pip install 'pyside6-essentials!=6.12.0'\n"
            "or use Python 3.12 or newer\n"
        )
        return 1

    # Qt's Wayland plugin warns about a focus mismatch of the text-input-v3 protocol on
    # every focus change between inputs. Harmless, and nothing the application can act
    # on : only that category is silenced
    QLoggingCategory.setFilterRules("qt.qpa.wayland.textinput=false")

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Syndesi")
    theme_module.apply(app, arguments.theme)  # type: ignore[arg-type]

    library = Library.default()
    window = MainWindow(library)
    top: type | None = None
    for spec in arguments.load:
        try:
            classes = library.load(spec)
        except LibraryError as e:
            QMessageBox.warning(window, "Cannot load", str(e))
            continue
        if ":" in spec.replace(":\\", "").replace(":/", "") and len(classes) == 1:
            top = classes[0]
    window.stack_screen.library_panel.refresh()
    if arguments.stack:
        window.open_stack(arguments.stack)
    elif top is not None:
        window.stack_screen.set_root(StackNode(top))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
