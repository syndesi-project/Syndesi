# File : library.py
# Author : Sébastien Deriaz
# License : GPL
"""
The component classes the user can stack : the ones of syndesi, and the ones loaded
from a python file or a module
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .introspection import (
    ComponentInfo,
    ParamSpec,
    component_info,
    kind_of,
)


def _builtin_classes() -> list[type]:
    # pylint: disable=import-outside-toplevel
    from ...adapters.ip import IP, AsyncIP
    from ...adapters.ipserver import AsyncIPServer, IPServer
    from ...adapters.serialport import AsyncSerialPort, SerialPort
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
        AsyncIP,
        AsyncSerialPort,
        AsyncVisa,
        AsyncIPServer,
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


@dataclass
class Library:
    """The component classes the user can stack"""

    classes: list[type] = field(default_factory=list)
    # Where a class was loaded from (file or module), None for the library ones
    sources: dict[type, str] = field(default_factory=dict)
    loaded: list[str] = field(default_factory=list)

    @classmethod
    def default(cls) -> Library:
        """The adapters, protocols and drivers of syndesi"""
        return cls(classes=_builtin_classes())

    def infos(self) -> list[ComponentInfo]:
        """Introspected classes, the ones that fail to introspect are left out"""
        result = []
        for c in self.classes:
            try:
                result.append(component_info(c))
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        return result

    def add(self, cls: type, source: str | None = None) -> None:
        """Add a component class"""
        if kind_of(cls) is None:
            raise LibraryError(f"{cls.__qualname__} isn't an adapter, a protocol or a driver")
        if cls not in self.classes:
            self.classes.append(cls)
        if source is not None:
            self.sources[cls] = source

    def load(self, spec: str) -> list[type]:
        """
        Load the components of a python file or of a module

            ./drivers/psu.py            every component class defined in the file
            ./drivers/psu.py:PSU        only PSU
            mypackage.drivers           every component class of the module
            mypackage.drivers:PSU       only PSU

        Returns the classes loaded
        """
        location, _, class_name = spec.partition(":")
        # A Windows drive letter (C:\\...) isn't a class separator
        if len(location) == 1 and class_name[:1] in ("\\", "/"):
            location, _, class_name = spec[2:].partition(":")
            location = spec[:2] + location
        module = _import(location)
        found = [
            obj
            for obj in vars(module).values()
            if isinstance(obj, type)
            and obj.__module__ == module.__name__
            and kind_of(obj) is not None
        ]
        if class_name:
            found = [c for c in found if c.__name__ == class_name]
            if not found:
                raise LibraryError(f"No component class '{class_name}' in {location}")
        if not found:
            raise LibraryError(f"No adapter, protocol or driver class in {location}")
        for c in found:
            self.add(c, location)
        if location not in self.loaded:
            self.loaded.append(location)
        return found

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


def _import(location: str) -> Any:
    path = Path(location)
    if location.endswith(".py") or path.is_file():
        if not path.is_file():
            raise LibraryError(f"No such file : {location}")
        path = path.resolve()
        module_name = "syndesi_ui_user." + re.sub(r"\W", "_", path.stem)
        # Sibling modules of the file must be importable from it
        if str(path.parent) not in sys.path:
            sys.path.insert(0, str(path.parent))
        module_spec = importlib.util.spec_from_file_location(module_name, path)
        if module_spec is None or module_spec.loader is None:
            raise LibraryError(f"Cannot load {location}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        try:
            module_spec.loader.exec_module(module)
        except Exception as e:
            del sys.modules[module_name]
            raise LibraryError(f"Error while loading {location} : {e!r}") from e
        return module
    try:
        return importlib.import_module(location)
    except Exception as e:
        raise LibraryError(f"Cannot import {location} : {e!r}") from e
