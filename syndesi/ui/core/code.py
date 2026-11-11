# File : code.py
# Author : Sébastien Deriaz
# License : GPL
"""
The python code that builds the same stack as the GUI
"""

from __future__ import annotations

import enum
import inspect
import keyword
import re
from typing import Any

from ...adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    Length,
    StopCondition,
    Termination,
    Total,
)
from .introspection import (
    Kind,
)
from .library import Library
from .stack import StackNode


def stop_condition_code(sc: StopCondition) -> str:
    """Python expression of a stop-condition"""
    if isinstance(sc, Termination):
        return f"Termination({sc.sequence!r})"
    if isinstance(sc, Length):
        return f"Length({sc.n})"
    if isinstance(sc, Continuation):
        return f"Continuation({sc.continuation})"
    if isinstance(sc, Total):
        return f"Total({sc.total})"
    if isinstance(sc, FragmentSC):
        return "FragmentSC()"
    return repr(sc)


def _import_line(cls: type, library: Library | None) -> tuple[str, str]:
    """(module to import from, comment)"""
    import syndesi  # pylint: disable=import-outside-toplevel

    if getattr(syndesi, cls.__name__, None) is cls:
        return "syndesi", ""
    if cls.__module__.startswith("syndesi_ui_user."):
        source = library.sources.get(cls, "") if library else ""
        return cls.__module__.removeprefix("syndesi_ui_user."), f"  # {source}"
    return cls.__module__, ""


def _value_code(value: Any, imports: dict[str, set[str]], library: Library | None) -> str:
    if isinstance(value, StopCondition):
        imports.setdefault("syndesi", set()).add(type(value).__name__)
        return stop_condition_code(value)
    if isinstance(value, list) and value and all(isinstance(v, StopCondition) for v in value):
        return "[" + ", ".join(_value_code(v, imports, library) for v in value) + "]"
    if isinstance(value, enum.Enum):
        module, _ = _import_line(type(value), library)
        imports.setdefault(module, set()).add(type(value).__name__)
        return f"{type(value).__name__}.{value.name}"
    return repr(value)


def _variable_name(cls: type, used: set[str]) -> str:
    name = cls.__name__.removeprefix("Async")
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).lower()
    snake = snake or "component"
    if keyword.iskeyword(snake):
        snake += "_"
    candidate, i = snake, 2
    while candidate in used:
        candidate, i = f"{snake}{i}", i + 1
    used.add(candidate)
    return candidate


def to_code(root: StackNode | None, library: Library | None = None) -> str:
    """The python code that builds the same stack"""
    if root is None:
        return "# Choose a component to start the stack"
    imports: dict[str, set[str]] = {}
    comments: dict[str, str] = {}
    lines: list[str] = []
    used: set[str] = set()

    def generate(node: StackNode) -> str:
        children = {
            name: generate(child) for name, child in node.children.items() if child is not None
        }
        module, comment = _import_line(node.cls, library)
        imports.setdefault(module, set()).add(node.cls.__name__)
        if comment:
            comments[module] = comment
        arguments: list[str] = []
        positional = True
        for spec in node.info.params:
            if spec.is_slot:
                code = children.get(spec.name)
            elif spec.name in node.values:
                code = _value_code(node.values[spec.name], imports, library)
            else:
                code = None
            if code is None:
                positional = False
                continue
            can_be_positional = spec.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
            if positional and can_be_positional and (spec.required or spec.is_slot):
                arguments.append(code)
            else:
                positional = positional and spec.kind is inspect.Parameter.POSITIONAL_ONLY
                arguments.append(code if spec.kind is inspect.Parameter.POSITIONAL_ONLY
                                 else f"{spec.name}={code}")
        variable = _variable_name(node.cls, used)
        lines.append(f"{variable} = {node.cls.__name__}({', '.join(arguments)})")
        return variable

    top = generate(root)
    header = []
    for module in sorted(imports, key=lambda m: (m != "syndesi", m)):
        names = ", ".join(sorted(imports[module]))
        header.append(f"from {module} import {names}{comments.get(module, '')}")
    body = "\n".join(lines)
    usage = _usage_hint(root, top)
    return "\n".join(header) + "\n\n" + body + ("\n\n" + usage if usage else "")


def _usage_hint(root: StackNode, variable: str) -> str:
    prefix = "await " if root.info.is_async else ""
    if root.kind is Kind.DRIVER:
        return f"{prefix}{variable}.open()"
    if root.kind in (Kind.ADAPTER, Kind.PROTOCOL):
        payload = root.info.provides
        if payload is str:
            return f"print({prefix}{variable}.query('*IDN?'))"
        if payload is bytes:
            return f"print({prefix}{variable}.query(b'hello'))"
    return ""
