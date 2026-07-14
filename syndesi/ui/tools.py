# File : tools.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi UI tools
"""

from dataclasses import dataclass
from enum import IntEnum
import inspect
import sys
from abc import ABC, abstractmethod
from typing import Any, List, Tuple, get_type_hints

import dearpygui.dearpygui as dpg  # type: ignore


# From dearpygui's demo.py
def _hsv_to_rgb(h : float, s : float, v : float) -> tuple[int, int, int]:
    def to_int(inp : tuple[float, float, float]) -> tuple[int, int, int]:
        return (int(inp[0]), int(inp[1]), int(inp[2]))
    
    if s == 0.0:
        return to_int((v, v, v))
    i = int(h*6.) # XXX assume int() truncates!
    f = (h*6.)-i
    p,q,t = v*(1.-s), v*(1.-s*f), v*(1.-s*(1.-f))
    i%=6
    if i == 0:
        return to_int((255*v, 255*t, 255*p))
    if i == 1:
        return to_int((255*q, 255*v, 255*p))
    if i == 2:
        return to_int((255*p, 255*v, 255*t))
    if i == 3:
        return to_int((255*p, 255*q, 255*v))
    if i == 4:
        return to_int((255*t, 255*p, 255*v))
    if i == 5:
        return to_int((255*v, 255*p, 255*q))
    return to_int((0,0,0))

def _help(message : str) -> None:
    last_item = dpg.last_item()
    with dpg.group(horizontal=True) as group:
        dpg.move_item(last_item, parent=group)
        t = dpg.add_text("(?)", color=[0, 255, 0])
        with dpg.tooltip(t):
            dpg.add_text(message)

def get_method_arguments(
        cls: type,
        method_name: str,
        *,
        include_self: bool = False
    ) -> list[dict[str, Any]]:
    """
    Return all input arguments of a class method, with:
    - name
    - type
    - whether a default exists
    - default value
    - parameter kind

    Works for:
    - normal instance methods
    - @classmethod
    - @staticmethod

    Parameters
    ----------
    cls:
        The class containing the method.
    method_name:
        Name of the method to inspect.
    include_self:
        If False, omit the first 'self' or 'cls' parameter when present.
    """

    # Get the raw attribute without triggering descriptor binding
    raw = inspect.getattr_static(cls, method_name)

    # Unwrap @classmethod / @staticmethod
    if isinstance(raw, (classmethod, staticmethod)):
        func = raw.__func__
    else:
        func = raw

    signature = inspect.signature(func)

    # Resolve type hints, including forward references when possible
    try:
        module_globals = vars(sys.modules[func.__module__])
        localns = dict(vars(cls))
        type_hints = get_type_hints(func, globalns=module_globals, localns=localns)
    except Exception:
        # Fallback if some hints cannot be resolved
        type_hints = getattr(func, "__annotations__", {})

    parameters = list(signature.parameters.values())

    if not include_self and parameters:
        first = parameters[0]
        if first.name in {"self", "cls"}:
            parameters = parameters[1:]

    result = []
    for param in parameters:
        has_default = param.default is not inspect.Parameter.empty
        annotation = type_hints.get(
            param.name,
            None if param.annotation is inspect.Parameter.empty else param.annotation,
        )

        result.append(
            {
                "name": param.name,
                "type": annotation,
                "has_default": has_default,
                "default": None if not has_default else param.default,
                "kind": param.kind,  # POSITIONAL_ONLY, POSITIONAL_OR_KEYWORD, VAR_POSITIONAL, etc.
            }
        )

    return result

    

class Block(ABC):
    """A collection of dearpygui items"""
    @abstractmethod
    def build(self, parent : int | str) -> None:
        """Construct the block in dearpygui"""

class Tab(ABC):
    @abstractmethod
    def reset(self): ...

    @abstractmethod
    def build_configuration_tab(self, configuration_tab : int | str): ...

    @abstractmethod
    def build_testing_window(self, testing_window : int | str): ...



class TestingEntryType(IntEnum):
    WRITE = 0
    READ = 1
    EVENT = 2

ENTRY_SYMBOL = {
    TestingEntryType.WRITE : "→",
    TestingEntryType.READ : "←",
    TestingEntryType.EVENT : "◆"
}

ENTRY_COLOR = {
    TestingEntryType.WRITE : (212, 235, 197),
    TestingEntryType.READ : (197, 213, 235),
    TestingEntryType.EVENT : (127, 127, 127)
}

# ✗ ▲
# ● ○ ◆ ◇ ▲ △ ■ □
# ← → ↑ ↓ ↔ ⇒ ⇐ ⇑ ⇓ ➔ 🡰 🠄 🠘

@dataclass
class TestingEntry:
    entry_type : TestingEntryType
    group_tag : int | str

class TestingWindow(Block):
    def __init__(self) -> None:
        super().__init__()
        self._entries : List[TestingEntry] = []
        self._testing_window : int | str = -1

    def build(self, parent : int | str):
        self._testing_window = dpg.add_child_window(parent=parent)

    def _add(self, entry_type : TestingEntryType, text : str):
        with dpg.group(horizontal=True, parent=self._testing_window) as group_tag:
            dpg.add_text(ENTRY_SYMBOL[entry_type] + " ", color=ENTRY_COLOR[entry_type])

        self._entries.append(TestingEntry(
            entry_type=entry_type,
            group_tag=group_tag
        ))

    def resize_height(self, height : int) -> None:
        dpg.configure_item(self._testing_window, height=height)

    def add_write(self, text : str):
        self._add(TestingEntryType.WRITE, text)

    def add_read(self, text : str):
        self._add(TestingEntryType.READ, text)

    def add_event(self, text : str):
        self._add(TestingEntryType.EVENT, text)

