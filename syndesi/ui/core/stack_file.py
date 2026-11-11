# File : stack_file.py
# Author : Sébastien Deriaz
# License : GPL
"""
Saving and loading a stack (JSON)
"""

from __future__ import annotations

import enum
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from ...adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    Length,
    StopCondition,
    Termination,
    Total,
)
from .library import Library
from .stack import StackNode

STACK_FILE_VERSION = 1

_STOP_CONDITIONS: dict[str, type[StopCondition]] = {
    "Termination": Termination,
    "Length": Length,
    "Continuation": Continuation,
    "Total": Total,
    "FragmentSC": FragmentSC,
}


def _stop_condition_args(sc: StopCondition) -> list[Any]:
    if isinstance(sc, Termination):
        return [{"$bytes": sc.sequence.hex()}]
    if isinstance(sc, Length):
        return [sc.n]
    if isinstance(sc, Continuation):
        return [sc.continuation]
    if isinstance(sc, Total):
        return [sc.total]
    return []


def encode_value(value: Any) -> Any:
    """JSON form of a parameter value"""
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, enum.Enum):
        return {"$enum": f"{type(value).__module__}:{type(value).__qualname__}", "name": value.name}
    if isinstance(value, StopCondition):
        return {"$stop": type(value).__name__, "args": _stop_condition_args(value)}
    if isinstance(value, (list, tuple)):
        return [encode_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Cannot save {value!r}")


def decode_value(value: Any) -> Any:
    """Inverse of encode_value"""
    if isinstance(value, list):
        return [decode_value(v) for v in value]
    if isinstance(value, dict):
        if "$bytes" in value:
            return bytes.fromhex(value["$bytes"])
        if "$enum" in value:
            module_name, _, qualname = value["$enum"].partition(":")
            enum_cls: Any = importlib.import_module(module_name)
            for part in qualname.split("."):
                enum_cls = getattr(enum_cls, part)
            return enum_cls[value["name"]]
        if "$stop" in value:
            sc_cls = _STOP_CONDITIONS[value["$stop"]]
            return sc_cls(*[decode_value(a) for a in value["args"]])
    return value


def node_to_dict(node: StackNode) -> dict[str, Any]:
    """JSON form of a node and the nodes below"""
    values = {}
    for name, value in node.values.items():
        try:
            values[name] = encode_value(value)
        except TypeError:
            continue
    return {
        "class": node.info.qualified_name,
        "values": values,
        "children": {
            name: node_to_dict(child) for name, child in node.children.items() if child is not None
        },
    }


def node_from_dict(data: dict[str, Any], library: Library) -> StackNode:
    """Inverse of node_to_dict"""
    node = StackNode(library.find(data["class"]))
    known = {p.name for p in node.info.params}
    for name, value in data.get("values", {}).items():
        if name in known:
            node.values[name] = decode_value(value)
    for name, child in data.get("children", {}).items():
        if name in node.children:
            node.set_child(name, node_from_dict(child, library))
    return node


def save_stack(path: str | Path, root: StackNode | None, library: Library) -> None:
    """Save the stack and the modules it needs"""
    data = {
        "version": STACK_FILE_VERSION,
        "load": library.loaded,
        "root": None if root is None else node_to_dict(root),
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_stack(path: str | Path, library: Library) -> StackNode | None:
    """Load a stack saved by save_stack, loading the modules it needs first"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for location in data.get("load", []):
        if location not in library.loaded:
            library.load(location)
    root = data.get("root")
    return None if root is None else node_from_dict(root, library)
