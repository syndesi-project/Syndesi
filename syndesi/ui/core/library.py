# File : library.py
# Author : Sébastien Deriaz
# License : GPL
"""
The component classes the user can stack, in collections

    Syndesi           the adapters, protocols and drivers of syndesi
    syndesi-drivers   loaded by default when installed, shown as missing otherwise
    mypackage         a package or a folder loaded by the user, one collection each
    Files             the files and modules loaded one by one

Loading a package or a folder imports a lot of code, so it tolerates what goes wrong :
a module that fails is reported in its collection, the others are still loaded. In a
plain folder, a file is only imported if it looks like a library (it defines a class
and runs nothing at the top level) : a folder of scripts would otherwise start them
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import pkgutil
import re
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import ModuleType
from typing import Any

from .introspection import (
    ComponentInfo,
    ParamSpec,
    component_info,
    kind_of,
)


# pylint: disable=too-many-locals
def _builtin_classes() -> list[type]:
    # pylint: disable=import-outside-toplevel
    from ...adapters.i2c import I2C, AsyncI2C
    from ...adapters.ip import IP, AsyncIP
    from ...adapters.ipserver import AsyncIPServer, IPServer
    from ...adapters.serialport import AsyncSerialPort, SerialPort
    from ...adapters.spi import SPI, AsyncSPI
    from ...adapters.visa import AsyncVisa, Visa
    from ...drivers.scpi_driver import SCPIDriver
    from ...protocols.delimited import AsyncDelimited, Delimited
    from ...protocols.modbus import AsyncModbus, Modbus
    from ...protocols.raw import AsyncRaw, Raw
    from ...protocols.scpi import SCPI, AsyncSCPI

    return [
        IP,
        SerialPort,
        Visa,
        IPServer,
        I2C,
        SPI,
        AsyncIP,
        AsyncSerialPort,
        AsyncVisa,
        AsyncIPServer,
        AsyncI2C,
        AsyncSPI,
        Raw,
        Delimited,
        SCPI,
        Modbus,
        AsyncRaw,
        AsyncDelimited,
        AsyncSCPI,
        AsyncModbus,
        SCPIDriver,
    ]


class LibraryError(Exception):
    """A module or a file couldn't be loaded"""


class CollectionKind(StrEnum):
    """Where the classes of a collection come from"""

    BUILTIN = "builtin"
    PACKAGE = "package"  # an installed package, or a folder with an __init__.py
    FOLDER = "folder"  # the python files of a folder
    FILES = "files"  # files and modules loaded one by one


@dataclass(frozen=True)
class DefaultPackage:
    """A package loaded at startup if it is installed"""

    module: str
    name: str
    description: str
    install: str


DEFAULT_PACKAGES = (
    DefaultPackage(
        module="syndesi_drivers",
        name="syndesi-drivers",
        description="Ready-made drivers for lab instruments and industrial I/O",
        install="pip install syndesi-drivers",
    ),
)

FILES_NAME = "Files"

# Not part of a library : tests, examples, packaging. A package named test_and_measurement
# is part of it, only a module test_x.py isn't
_SKIPPED_MODULES = re.compile(r"^(_|test_|conftest$|example_|setup$)")
_SKIPPED_PACKAGES = re.compile(r"^(_|tests?$|examples?$)")
_SKIPPED_FOLDERS = {
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "site-packages",
    "venv",
}


@dataclass
class Collection:  # pylint: disable=too-many-instance-attributes
    """
    The classes of one origin, a tab of the library

    categories gives the sub-package (or the file) of each class, how the GUI groups
    them. errors gives what couldn't be imported, by module or file. skipped lists the
    files that weren't imported because they look like scripts. missing says why the
    collection can't be used and what to do about it, empty if it can
    """

    name: str
    kind: CollectionKind
    location: str | None = None
    classes: list[type] = field(default_factory=list)
    categories: dict[type, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    missing: str = ""
    description: str = ""
    # Command that makes a missing collection available
    install: str = ""

    @property
    def available(self) -> bool:
        """True if the collection could be loaded"""
        return not self.missing


@dataclass
class Library:
    """The component classes the user can stack"""

    classes: list[type] = field(default_factory=list)
    # Where a class was loaded from (file, folder or module), None for the library ones
    sources: dict[type, str] = field(default_factory=dict)
    # What the user loaded, saved with a stack to load it again
    loaded: list[str] = field(default_factory=list)
    collections: list[Collection] = field(default_factory=list)

    @classmethod
    def default(
        cls, packages: tuple[DefaultPackage, ...] = DEFAULT_PACKAGES
    ) -> Library:
        """The adapters, protocols and drivers of syndesi, and the default packages"""
        builtin = _builtin_classes()
        library = cls(
            classes=list(builtin),
            collections=[
                Collection(
                    "Syndesi",
                    CollectionKind.BUILTIN,
                    classes=list(builtin),
                    description="The adapters, protocols and drivers of Syndesi",
                )
            ],
        )
        for package in packages:
            library.load_default(package)
        return library

    # ┌─────────┐
    # │ Queries │
    # └─────────┘

    def infos(self) -> list[ComponentInfo]:
        """Introspected classes, the ones that fail to introspect are left out"""
        return _infos(self.classes)

    def collection_of(self, cls: type) -> Collection | None:
        """Collection a class belongs to"""
        return next((c for c in self.collections if cls in c.classes), None)

    def find(self, qualified_name: str) -> type:
        """Class from its module:QualName"""
        for c in self.classes:
            if f"{c.__module__}:{c.__qualname__}" == qualified_name:
                return c
        module_name, _, qualname = qualified_name.partition(":")
        try:
            obj: Any = importlib.import_module(module_name)
            for part in qualname.split("."):
                obj = getattr(obj, part)
        except (ImportError, AttributeError) as e:
            raise LibraryError(f"Cannot find {qualified_name}") from e
        if not isinstance(obj, type):
            raise LibraryError(f"{qualified_name} is not a class")
        self.add(obj)
        return obj

    def compatible(self, slot: ParamSpec) -> list[type]:
        """Classes a slot accepts"""
        return [c for c in self.classes if slot.accepts(c)]

    # ┌─────────┐
    # │ Loading │
    # └─────────┘

    def add(self, cls: type, source: str | None = None) -> None:
        """Add a component class"""
        if kind_of(cls) is None:
            raise LibraryError(
                f"{cls.__qualname__} isn't an adapter, a protocol or a driver"
            )
        if cls not in self.classes:
            self.classes.append(cls)
        if source is not None:
            self.sources[cls] = source

    def load(self, spec: str) -> list[type]:
        """
        Load the components of a python file, a folder or a module

            ./drivers/psu.py            every component class defined in the file
            ./drivers/psu.py:PSU        only PSU
            ./drivers                   every file of the folder (a package if it has
                                        an __init__.py)
            mypackage                   every module of the package
            mypackage.drivers:PSU       only PSU

        Returns the classes loaded
        """
        location, class_name = _split(spec)
        path = Path(location)
        if path.is_dir():
            if class_name:
                raise LibraryError(
                    f"{location} is a folder : give the file of {class_name}, "
                    "folder/file.py:Class"
                )
            classes = self._load_folder(path)
        elif location.endswith(".py") or path.is_file():
            classes = self._load_file(location, class_name)
        else:
            module = _import_module(location)
            if hasattr(module, "__path__") and not class_name:
                classes = self._load_package(location, location, location)
            else:
                classes = self._load_module(module, location, class_name)
        if location not in self.loaded:
            self.loaded.append(location)
        return classes

    def load_default(self, package: DefaultPackage) -> Collection:
        """Load a default package, or record why it is missing. Never raises"""
        if importlib.util.find_spec(package.module) is None:
            collection = Collection(
                package.name,
                CollectionKind.PACKAGE,
                location=package.module,
                missing=f"{package.name} is not installed. {package.description}, "
                f"install it with :\n    {package.install}",
                description=package.description,
                install=package.install,
            )
            self.collections.append(collection)
            return collection
        try:
            self._load_package(package.module, package.name, package.module)
        except LibraryError as e:
            self.collections.append(
                Collection(
                    package.name,
                    CollectionKind.PACKAGE,
                    location=package.module,
                    missing=str(e),
                    description=package.description,
                )
            )
        collection = self.collections[-1]
        collection.description = package.description
        return collection

    def _files(self) -> Collection:
        """The collection of the files and modules loaded one by one"""
        for collection in self.collections:
            if collection.kind is CollectionKind.FILES:
                return collection
        collection = Collection(
            FILES_NAME,
            CollectionKind.FILES,
            description="Files and modules loaded one by one",
        )
        self.collections.append(collection)
        return collection

    def _existing(self, location: str) -> Collection | None:
        return next((c for c in self.collections if c.location == location), None)

    def _collect(
        self, collection: Collection, module: ModuleType, source: str, category: str
    ) -> list[type]:
        found = _components(module)
        for c in found:
            self.add(c, source)
            if c not in collection.classes:
                collection.classes.append(c)
            collection.categories[c] = category
        return found

    def _load_file(self, location: str, class_name: str) -> list[type]:
        path = Path(location)
        if not path.is_file():
            raise LibraryError(f"No such file : {location}")
        module = _import_file(path)
        return self._pick(module, location, class_name, path.name)

    def _load_module(
        self, module: ModuleType, location: str, class_name: str
    ) -> list[type]:
        return self._pick(module, location, class_name, location)

    def _pick(
        self, module: ModuleType, location: str, class_name: str, category: str
    ) -> list[type]:
        """Add the classes of a module (or only class_name) to the Files collection"""
        found = _components(module)
        if class_name:
            found = [c for c in found if c.__name__ == class_name]
            if not found:
                raise LibraryError(f"No component class '{class_name}' in {location}")
        if not found:
            raise LibraryError(f"No adapter, protocol or driver class in {location}")
        files = self._files()
        for c in found:
            self.add(c, location)
            if c not in files.classes:
                files.classes.append(c)
            files.categories[c] = category
        return found

    def _load_package(self, module_name: str, name: str, location: str) -> list[type]:
        """Import a package and every module in it, errors are kept in the collection"""
        existing = self._existing(location)
        if existing is not None and existing.available:
            return list(existing.classes)

        package = _import_module(module_name)
        collection = Collection(name, CollectionKind.PACKAGE, location=location)
        self._collect(
            collection, package, location, _category(module_name, module_name, True)
        )

        pending = [package]
        while pending:
            parent = pending.pop(0)
            for info in pkgutil.iter_modules(parent.__path__, parent.__name__ + "."):
                short = info.name.rsplit(".", 1)[-1]
                if (_SKIPPED_PACKAGES if info.ispkg else _SKIPPED_MODULES).match(short):
                    continue
                spec = importlib.util.find_spec(info.name)
                origin = spec.origin if spec is not None else None
                if not info.ispkg and origin and origin.endswith(".py"):
                    reason = _not_a_library(Path(origin))
                    if reason == "no class":
                        continue
                    if reason:
                        collection.skipped.append(f"{info.name} ({reason})")
                        continue
                try:
                    module = importlib.import_module(info.name)
                # SystemExit too : a sys.exit() in a module must not close the GUI
                except (
                    Exception,
                    SystemExit,
                ) as e:  # pylint: disable=broad-exception-caught
                    collection.errors[info.name] = f"{type(e).__name__}: {e}"
                    continue
                category = _category(info.name, module_name, info.ispkg)
                self._collect(collection, module, location, category)
                if info.ispkg:
                    pending.append(module)

        if not collection.classes:
            raise LibraryError(_nothing_loaded(name, collection))
        self.collections.append(collection)
        return list(collection.classes)

    def _load_folder(self, path: Path) -> list[type]:
        """The files of a folder, or the package it is"""
        path = path.resolve()
        location = str(path)
        if (path / "__init__.py").is_file():
            if str(path.parent) not in sys.path:
                sys.path.insert(0, str(path.parent))
            return self._load_package(path.name, path.name, location)

        existing = self._existing(location)
        if existing is not None:
            return list(existing.classes)
        collection = Collection(path.name, CollectionKind.FOLDER, location=location)
        for file in sorted(path.rglob("*.py")):
            relative = file.relative_to(path)
            folders = relative.parts[:-1]
            if any(p.startswith(".") or p in _SKIPPED_FOLDERS for p in folders):
                continue
            if _SKIPPED_MODULES.match(file.stem) or any(
                _SKIPPED_PACKAGES.match(p) for p in folders
            ):
                continue
            reason = _not_a_library(file)
            if reason:
                if reason != "no class":
                    collection.skipped.append(f"{relative.as_posix()} ({reason})")
                continue
            try:
                module = _import_file(file)
            except LibraryError as e:
                collection.errors[relative.as_posix()] = str(e)
                continue
            self._collect(collection, module, str(file), relative.as_posix())

        if not collection.classes:
            raise LibraryError(_nothing_loaded(location, collection))
        self.collections.append(collection)
        return list(collection.classes)


# ┌─────────┐
# │ Helpers │
# └─────────┘


def _infos(classes: list[type]) -> list[ComponentInfo]:
    result = []
    for c in classes:
        try:
            result.append(component_info(c))
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return result


def _split(spec: str) -> tuple[str, str]:
    """(location, class name) of 'location:Class', a Windows drive isn't a separator"""
    location, _, class_name = spec.partition(":")
    if len(location) == 1 and class_name[:1] in ("\\", "/"):
        location, _, class_name = spec[2:].partition(":")
        location = spec[:2] + location
    return location, class_name


def _components(module: ModuleType) -> list[type]:
    """Component classes defined in a module, not the ones it imports"""
    return [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and obj.__module__ == module.__name__
        and kind_of(obj) is not None
    ]


def _category(module_name: str, root: str, is_package: bool) -> str:
    """
    Sub-package of a module, relative to the root of its collection

    syndesi_drivers.test_and_measurement.multimeters.keysight -> 'multimeters'
    """
    parts = module_name.split(".")[len(root.split(".")) :]
    if not is_package:
        parts = parts[:-1]
    return parts[-1] if parts else ""


# Top-level statements that run code when a file is imported
_SCRIPT_STATEMENTS = (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)


def _not_a_library(path: Path) -> str:
    """
    Why a file shouldn't be imported to find classes, empty if it can be

    A library defines classes and runs nothing at the top level, apart from imports
    and assignments. A script (a call, a loop, a with) would run when imported : start
    a server, talk to a device...
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    except (SyntaxError, UnicodeDecodeError, OSError) as e:
        return f"unreadable : {e}"
    if not any(isinstance(node, ast.ClassDef) for node in tree.body):
        return "no class"
    for node in tree.body:
        if isinstance(node, _SCRIPT_STATEMENTS):
            return "runs code when imported"
        if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
            return "runs code when imported"
    return ""


def _nothing_loaded(name: str, collection: Collection) -> str:
    message = f"No adapter, protocol or driver class could be loaded from {name}"
    if collection.errors:
        details = "\n".join(
            f"  {k} : {v}" for k, v in list(collection.errors.items())[:5]
        )
        message += f"\n\nErrors :\n{details}"
    if collection.skipped:
        message += "\n\nSkipped :\n" + "\n".join(
            f"  {s}" for s in collection.skipped[:5]
        )
    return message


def _import_module(location: str) -> ModuleType:
    try:
        return importlib.import_module(location)
    except (Exception, SystemExit) as e:
        raise LibraryError(f"Cannot import {location} : {e!r}") from e


def _import_file(path: Path) -> ModuleType:
    path = path.resolve()
    module_name = "syndesi_ui_user." + re.sub(r"\W", "_", path.stem)
    # Already imported (by a folder, or a stack) : the same classes, not new ones
    existing = sys.modules.get(module_name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
    # Sibling modules of the file must be importable from it
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise LibraryError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    # SystemExit too : a sys.exit() in a file must not close the GUI
    except (Exception, SystemExit) as e:
        del sys.modules[module_name]
        raise LibraryError(f"Error while loading {path} : {e!r}") from e
    return module
