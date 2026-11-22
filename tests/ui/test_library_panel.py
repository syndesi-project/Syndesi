"""The library panel : one tab per collection, offscreen"""

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication  # noqa: E402

from syndesi import IP  # noqa: E402
from syndesi.ui.core.library import DefaultPackage, Library  # noqa: E402
from syndesi.ui.stack.library_panel import Palette  # noqa: E402
from syndesi.ui.style import theme  # noqa: E402

EXAMPLES = Path(__file__).parents[2] / "examples"
MISSING = DefaultPackage("no_such_package_xyz", "no-such", "Nothing here", "pip install no-such")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    theme.apply(application, "light")
    return application


@pytest.fixture
def palette(app):
    library = Library.default(packages=(MISSING,))
    widget = Palette(library)
    widget.resize(300, 700)
    widget.show()
    _settle(app)
    yield widget
    widget.close()


def _settle(app):
    for _ in range(3):
        app.processEvents()


def _rows(palette):
    tree = palette.tree
    return [
        tree.topLevelItem(i).child(j).text(0)
        for i in range(tree.topLevelItemCount())
        for j in range(tree.topLevelItem(i).childCount())
    ]


def test_one_tab_per_collection(app, palette):
    names = [palette.tabs.tabText(i) for i in range(palette.tabs.count())]
    assert names == ["Syndesi", "no-such"]
    assert "IP" in _rows(palette)


def test_missing_package_is_greyed_and_explains(app, palette):
    assert 1 in palette.tabs.unavailable
    palette.tabs.setCurrentIndex(1)
    _settle(app)
    assert palette.body.currentWidget() is palette.empty
    assert "pip install no-such" in palette.empty.text()


def test_loading_a_folder_opens_its_tab(app, palette):
    palette.load(str(EXAMPLES))
    _settle(app)
    assert palette.current_collection.name == "examples"
    assert "DemoPowerSupply" in _rows(palette)
    # scpi_driver.py runs code when imported : skipped, and said so
    assert palette.notice.isVisible()
    assert "skipped" in palette.notice.text()


def test_slot_moves_to_a_tab_that_has_something(app, palette):
    palette.load(str(EXAMPLES))
    _settle(app)
    palette.set_filter(lambda cls: cls is IP, "adapter slot")
    _settle(app)
    assert palette.current_collection.name == "Syndesi"


def test_search_links_to_other_tabs(app, palette):
    palette.load(str(EXAMPLES))
    palette.tabs.setCurrentIndex(0)
    palette.search.setText("DemoPower")
    _settle(app)
    assert palette.elsewhere.isVisible()
    assert "examples" in palette.elsewhere.text()


def test_tabs_that_dont_fit_are_counted(app, palette):
    palette.load(str(EXAMPLES))
    palette.resize(160, 700)
    _settle(app)
    hidden = sum(not palette.tabs.isTabVisible(i) for i in range(palette.tabs.count()))
    assert hidden > 0
    assert palette.all_tabs.text() == f"+{hidden}"
    assert palette.tabs.isTabVisible(palette.tabs.currentIndex())
