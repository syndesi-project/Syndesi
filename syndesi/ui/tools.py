# File : tools.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi UI tools
"""

import asyncio
import inspect
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Awaitable, get_type_hints

import dearpygui.dearpygui as dpg # type: ignore

from syndesi.component import ReadScope, SyndesiEvent

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

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
        ...

class ComponentBlock(ABC):
    _is_top_level : bool
    _ui_event_callback : Callable[[SyndesiEvent, bool], None]
    def __init__(self,
                 is_top_level : bool,
                 write_callback : Callable[[str], None],
                 read_callback : Callable[[str], Awaitable[None]],
                 read_fail_callback : Callable[[str], Awaitable[None]]
                ) -> None:
        self._is_top_level = is_top_level
        self._ui_write_callback = write_callback
        self._ui_read_callback = read_callback
        self._ui_read_fail_callback = read_fail_callback
        super().__init__()

    title : str = ""
    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def build_configuration_tab(self, configuration_tab : int | str) -> None: ...

    @abstractmethod
    def build_testing_group(self, testing_window : int | str) -> int | str: ...

    @abstractmethod
    def open(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @abstractmethod
    def sync_component_to_block(self) -> None:
        ...

    @abstractmethod
    def sync_block_to_component(self) -> None:
        ...

def bytes_help() -> None:
    _help("bytes formatting can be used such as \\n and \\r")

class StringTestingGroup:
    def __init__(self, write_callback : Callable[[str], None], read_callback : Callable[[ReadScope], Awaitable[None]], lines : int = 5) -> None:
        self._lines = lines
        self._write_callback = write_callback
        self._read_callback = read_callback
        self._write_status : int | str = -1
        self._read_scope_combo: int | str = -1

    def write_status(self, text : str, status : str = "neutral") -> None:
        if self._write_status != -1:
            if status == "ok":
                dpg.configure_item(self._write_status, color=(30, 199, 38))
            elif status == "error":
                dpg.configure_item(self._write_status, color=(255,0,0))
            else:
                dpg.configure_item(self._write_status, color=(255,255,255))
            dpg.set_value(self._write_status, text)

    def _write_advanced_callback(self, sender : int | str, enabled : bool) -> None:
        for i in range(1, self._lines):
            if enabled:
                dpg.show_item(self._write_group[i])
            else:
                dpg.hide_item(self._write_group[i])

    def _write_input_callback(self, _ : int | str, __ : Any, index : int) -> None:
        self._write_callback(dpg.get_value(self._write_input[index]))

    async def _read_button_callback(self) -> None:
        scope = ReadScope(dpg.get_value(self._read_scope_combo))
        await self._read_callback(scope)

    def build(self, parent : int | str) -> int | str:
        testing_group : int | str
        with dpg.group(horizontal=False, parent=parent) as testing_group:
            dpg.add_text("Write", color=(70, 142, 194))
            dpg.add_checkbox(label="Advanced", callback=self._write_advanced_callback)
            self._write_input = {}
            self._write_group = {}
            with dpg.group(horizontal=True):
                with dpg.group(horizontal=False):
                    for i in range(self._lines):
                        with dpg.group(horizontal=True, show=i==0):
                            self._write_group[i] = dpg.last_item()
                            dpg.add_button(
                                label="Write",
                                callback=self._write_input_callback,
                                user_data=i,
                                width=100
                            )
                            self._write_input[i] = dpg.add_input_text()
                            if i == 0:
                                bytes_help()
            self._write_status = dpg.add_text("")

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Read", callback=self._read_button_callback)
                self._read_scope_combo = dpg.add_combo(label="Scope", items=list(ReadScope), width=100, default_value=ReadScope.BUFFERED)

        return testing_group
