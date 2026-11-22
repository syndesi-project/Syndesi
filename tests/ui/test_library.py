"""
Loading components : files, folders, modules, packages, and the default packages

Packages and folders are written to tmp_path, so that what they contain (a module
that fails, a script, a test) is under control
"""

import os
import sys
import textwrap
from pathlib import Path

import pytest

from syndesi import IP
from syndesi.ui.core.library import (
    CollectionKind,
    DefaultPackage,
    Library,
    LibraryError,
    _category,
)

DRIVER = '''
from syndesi import Driver


class {name}(Driver):
    """{name} driver"""

    def open(self) -> None: ...

    def close(self) -> None: ...

    def test(self) -> bool:
        return True
'''


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


@pytest.fixture
def package(tmp_path, monkeypatch):
    """
    labpkg/
        __init__.py
        instruments/psu.py          a driver
        instruments/broken.py       fails to import
        instruments/test_psu.py     a test, not imported
        industrial/relay.py         a driver
        tools.py                    no component
    """
    name = f"labpkg_{os.getpid()}_{id(tmp_path)}"
    root = tmp_path / name
    _write(root / "__init__.py", "")
    _write(root / "instruments" / "__init__.py", "")
    _write(root / "instruments" / "psu.py", DRIVER.format(name="PowerSupply"))
    _write(
        root / "instruments" / "broken.py",
        "import module_broken_on_purpose\n" + DRIVER.format(name="Broken"),
    )
    _write(root / "instruments" / "test_psu.py", "raise AssertionError('never imported')")
    _write(root / "industrial" / "__init__.py", "")
    _write(root / "industrial" / "relay.py", DRIVER.format(name="Relay"))
    _write(root / "tools.py", "VALUE = 1")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name, root
    for module in [m for m in sys.modules if m.startswith(name)]:
        del sys.modules[module]


def _names(classes):
    return sorted(c.__name__ for c in classes)


# Default packages


def test_missing_default_package_says_how_to_install():
    package = DefaultPackage("no_such_package_xyz", "no-such", "Nothing", "pip install no-such")
    library = Library.default(packages=(package,))
    collection = library.collections[-1]
    assert not collection.available
    assert collection.name == "no-such"
    assert "pip install no-such" in collection.missing
    assert collection.install == "pip install no-such"


def test_default_package_is_loaded_but_not_saved(package):
    name, _ = package
    default = DefaultPackage(name, "lab", "Lab drivers", f"pip install {name}")
    library = Library.default(packages=(default,))
    collection = library.collections[-1]
    assert collection.available
    assert collection.name == "lab"
    assert _names(collection.classes) == ["PowerSupply", "Relay"]
    # Loaded at every start : not something a stack file has to load again
    assert library.loaded == []


# Packages


def test_package(package):
    name, _ = package
    library = Library.default(packages=())
    assert _names(library.load(name)) == ["PowerSupply", "Relay"]
    collection = library.collections[-1]
    assert collection.kind is CollectionKind.PACKAGE
    assert sorted(collection.categories.values()) == ["industrial", "instruments"]
    # The broken module is reported, the others are still loaded
    assert list(collection.errors) == [f"{name}.instruments.broken"]
    assert "module_broken_on_purpose" in collection.errors[f"{name}.instruments.broken"]
    assert library.loaded == [name]


def test_package_loaded_twice_is_one_collection(package):
    name, _ = package
    library = Library.default(packages=())
    library.load(name)
    library.load(name)
    assert sum(c.kind is CollectionKind.PACKAGE for c in library.collections) == 1


def test_package_folder(package):
    _, root = package
    library = Library.default(packages=())
    assert _names(library.load(str(root))) == ["PowerSupply", "Relay"]
    assert library.collections[-1].kind is CollectionKind.PACKAGE


def test_category():
    assert _category("pkg.test_and_measurement.multimeters.dmm", "pkg", False) == "multimeters"
    assert _category("pkg.industrial.adam", "pkg", True) == "adam"
    assert _category("pkg.tools", "pkg", False) == ""


# Folders of files


def test_folder_skips_scripts_and_tests(tmp_path):
    folder = tmp_path / "bench"
    _write(folder / "psu.py", DRIVER.format(name="BenchPSU"))
    _write(folder / "sub" / "dmm.py", DRIVER.format(name="BenchDMM"))
    # Would run when imported : must not be
    _write(
        folder / "script.py",
        DRIVER.format(name="Scripted") + "\nraise SystemExit('a script ran')\n",
    )
    _write(folder / "talk.py", DRIVER.format(name="Talker") + "\nprint('hello')\n")
    _write(folder / "test_psu.py", "raise AssertionError('never imported')")
    _write(folder / "venv" / "lib.py", "raise AssertionError('never imported')")
    _write(folder / "notes.py", "VALUE = 1")

    library = Library.default(packages=())
    assert _names(library.load(str(folder))) == ["BenchDMM", "BenchPSU"]
    collection = library.collections[-1]
    assert collection.kind is CollectionKind.FOLDER
    assert collection.name == "bench"
    assert sorted(collection.categories.values()) == ["psu.py", "sub/dmm.py"]
    assert sorted(s.split(" ")[0] for s in collection.skipped) == ["talk.py"]
    # raise is not a script statement, but the class is still never reached : an
    # error, reported, not a crash
    assert list(collection.errors) == ["script.py"]


def test_folder_without_components(tmp_path):
    _write(tmp_path / "empty" / "notes.py", "VALUE = 1")
    with pytest.raises(LibraryError, match="No adapter, protocol or driver class"):
        Library.default(packages=()).load(str(tmp_path / "empty"))


def test_folder_class_needs_a_file(tmp_path):
    _write(tmp_path / "f" / "psu.py", DRIVER.format(name="X"))
    with pytest.raises(LibraryError, match="give the file"):
        Library.default(packages=()).load(f"{tmp_path / 'f'}:X")


# Files and modules


def test_file_and_module_go_to_files(tmp_path):
    _write(tmp_path / "single.py", DRIVER.format(name="Single"))
    library = Library.default(packages=())
    library.load(str(tmp_path / "single.py"))
    library.load("syndesi.drivers.scpi_driver")
    files = library.collections[-1]
    assert files.kind is CollectionKind.FILES
    assert files.categories[files.classes[0]] == "single.py"
    assert "syndesi.drivers.scpi_driver" in files.categories.values()


def test_same_file_twice_gives_the_same_classes(tmp_path):
    folder = tmp_path / "twice"
    _write(folder / "psu.py", DRIVER.format(name="TwicePSU"))
    library = Library.default(packages=())
    (from_folder,) = library.load(str(folder))
    (from_file,) = library.load(str(folder / "psu.py"))
    assert from_folder is from_file


def test_builtin_collection_first():
    library = Library.default(packages=())
    assert library.collections[0].kind is CollectionKind.BUILTIN
    assert IP in library.collections[0].classes
