# File : runtime.py
# Author : Sébastien Deriaz
# License : GPL
"""
Everything that exists once the stack is built : the components of the stack, the
ones a driver built for itself (internal layers), the sub-drivers it exposes
"""

from __future__ import annotations

import enum
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from ...adapters.adapter import Adapter, AsyncAdapter
from ...drivers.driver import Driver, SubDriver
from ...protocols.protocol import AsyncProtocol, Protocol
from .introspection import (
    Kind,
    component_info,
    discover_components,
    kind_of,
)
from .stack import StackNode


class Role(enum.StrEnum):
    """How a built component relates to the stack"""

    TOP = "top"
    EXTERNAL = "external"  # configured by the user in the stack screen
    INTERNAL = "internal"  # built by a driver for itself, not configurable
    SUBDRIVER = "sub-driver"  # exposed by a driver (a channel, ...)
    RETURNED = "returned"  # returned by a command


@dataclass
class RuntimeItem:
    """A component instance of the test screen"""

    instance: Any
    role: Role
    path: str  # attribute or slot it was found in
    parent: RuntimeItem | None = None
    children: list[RuntimeItem] = field(default_factory=list)
    node: StackNode | None = None
    label: str = ""

    @property
    def cls(self) -> type:
        """Class of the instance"""
        return type(self.instance)

    @property
    def kind(self) -> Kind:
        """Kind of the instance"""
        kind = kind_of(type(self.instance))
        assert kind is not None
        return kind

    def walk(self) -> Iterator[RuntimeItem]:
        """This item and the ones below"""
        yield self
        for child in self.children:
            yield from child.walk()


class RuntimeTree:
    """
    Everything that exists once the stack is built

    The components a driver holds are looked for in its attributes. One reached from
    several places appears once, under the first : SCPIDriver → _prot (SCPI) → adapter (IP)
    rather than IP twice
    """

    def __init__(self, root: StackNode) -> None:
        self._external = {id(n.instance): n for n in root.walk() if n.instance is not None}
        self._placed: set[int] = set()
        self._names: dict[str, int] = {}
        self.root = self._item(root.instance, Role.TOP, "", None)
        self._place(self.root)

    def _label(self, instance: Any) -> str:
        name = type(instance).__name__
        count = self._names.get(name, 0) + 1
        self._names[name] = count
        return name if count == 1 else f"{name}#{count}"

    def _item(self, instance: Any, role: Role, path: str, parent: RuntimeItem | None) -> RuntimeItem:
        node = self._external.get(id(instance))
        if node is not None and role is not Role.TOP:
            role = Role.EXTERNAL
        item = RuntimeItem(
            instance=instance,
            role=role,
            path=path,
            parent=parent,
            node=node,
            label=self._label(instance),
        )
        self._placed.add(id(instance))
        if parent is not None:
            parent.children.append(item)
        return item

    def _place(self, item: RuntimeItem) -> None:
        for found in discover_components(item.instance):
            if id(found.instance) in self._placed:
                continue
            if id(found.instance) in self._external:
                role = Role.EXTERNAL
            elif isinstance(found.instance, SubDriver) and not isinstance(found.instance, Driver):
                role = Role.SUBDRIVER
            else:
                role = Role.INTERNAL
            self._place(self._item(found.instance, role, found.path, item))
        # The stack children the instance doesn't keep a reference to
        if item.node is not None:
            for slot, child in item.node.children.items():
                if child is not None and child.instance is not None:
                    if id(child.instance) not in self._placed:
                        self._place(self._item(child.instance, Role.EXTERNAL, slot, item))

    def add(self, instance: Any, role: Role, path: str, parent: RuntimeItem) -> RuntimeItem | None:
        """Add a component found later (returned by a command), None if already there"""
        if id(instance) in self._placed:
            return None
        item = self._item(instance, role, path, parent)
        self._place(item)
        return item

    def refresh(self, item: RuntimeItem) -> list[RuntimeItem]:
        """Look again for components in an item (a command may have created some)"""
        before = set(self._placed)
        self._place(item)
        return [i for i in self.root.walk() if id(i.instance) not in before]

    def find(self, instance: Any) -> RuntimeItem | None:
        """Item of an instance"""
        return next((i for i in self.root.walk() if i.instance is instance), None)

    def walk(self) -> Iterator[RuntimeItem]:
        """Every item"""
        return self.root.walk()


def is_endpoint(obj: Any) -> bool:
    """Adapters and protocols, the components that emit events"""
    return isinstance(obj, (Adapter, AsyncAdapter, Protocol, AsyncProtocol))


def is_adapter(obj: Any) -> bool:
    return isinstance(obj, (Adapter, AsyncAdapter))


def open_targets(runtime: RuntimeTree) -> list[Any]:
    """
    What the Open and Close buttons act on : the top component if it knows how to open
    itself, else the highest adapters and protocols below it (a base class driver like
    SCPIDriver has an abstract open)
    """
    top = runtime.root
    if is_endpoint(top.instance):
        return [top.instance]
    if isinstance(top.instance, Driver) and not component_info(top.cls).is_base_class:
        return [top.instance]

    def highest(item: RuntimeItem) -> list[Any]:
        if is_endpoint(item.instance):
            return [item.instance]
        result = []
        for child in item.children:
            if child.role in (Role.INTERNAL, Role.EXTERNAL):
                result.extend(highest(child))
        return result

    return highest(top)


def describe(obj: Any) -> str:
    """repr of a component, its class name if it has no repr of its own"""
    if type(obj).__repr__ is object.__repr__:  # type: ignore[comparison-overlap]
        kind = kind_of(type(obj))
        return f"{type(obj).__name__} ({kind.value if kind else 'object'})"
    return repr(obj)
