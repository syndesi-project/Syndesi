# File : stack.py
# Author : Sébastien Deriaz
# License : GPL
"""
The stack the user is assembling, independently of how it is drawn

    StackNode(SCPI)                       values   : termination='\\n', ...
      └ children['adapter'] = StackNode(IP)        values : address=..., port=...

A node only holds the values the user changed : the others are left out of the
constructor call, so that the defaults keep their meaning (port=None lets SCPI pick
5025, timeout=DEFAULT lets the protocol pick its own, ...)
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from typing import Any

from .introspection import (
    Kind,
    ParamSpec,
    component_info,
)


class StackNode:
    """One component of the stack the user configures"""

    def __init__(self, cls: type) -> None:
        self.cls = cls
        self.info = component_info(cls)
        # Only the values the user set, see the module docstring
        self.values: dict[str, Any] = {}
        self.children: dict[str, StackNode | None] = {s.name: None for s in self.info.slots}
        self.parent: StackNode | None = None
        self.parent_slot: str | None = None
        # Built instance, None until the stack is built
        self.instance: Any = None

    def __repr__(self) -> str:
        return f"StackNode({self.info.name})"

    @property
    def kind(self) -> Kind:
        """Kind of the component"""
        return self.info.kind

    def set_child(self, slot: str, child: StackNode | None) -> None:
        """Put a component in a slot (None empties it)"""
        if slot not in self.children:
            raise KeyError(slot)
        previous = self.children[slot]
        if previous is not None:
            previous.parent = None
            previous.parent_slot = None
        self.children[slot] = child
        if child is not None:
            child.detach()
            child.parent = self
            child.parent_slot = slot

    def detach(self) -> None:
        """Remove the node from its parent slot"""
        if self.parent is not None and self.parent_slot is not None:
            self.parent.children[self.parent_slot] = None
        self.parent = None
        self.parent_slot = None

    def walk(self) -> Iterator[StackNode]:
        """This node and the nodes below, depth first"""
        yield self
        for child in self.children.values():
            if child is not None:
                yield from child.walk()

    def slot_spec(self, slot: str) -> ParamSpec:
        """Spec of one of the slots"""
        return next(s for s in self.info.slots if s.name == slot)

    def problems(self) -> list[str]:
        """What prevents building the node and the ones below"""
        result = []
        for node in self.walk():
            for spec in node.info.params:
                if spec.is_slot:
                    if node.children.get(spec.name) is None and spec.required:
                        result.append(f"{node.info.name} : choose what '{spec.name}' is built on")
                elif not spec.hidden and spec.required and node.values.get(spec.name) in (None, ""):
                    if spec.allows_none and spec.name in node.values:
                        continue
                    result.append(f"{node.info.name} : '{spec.name}' is required")
        return result

    def build(self) -> Any:
        """
        Instantiate the components, the lowest layers first. Run it on the worker
        thread, some constructors wait for the reactor
        """
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        for spec in self.info.params:
            if spec.is_slot:
                child = self.children.get(spec.name)
                if child is None:
                    if spec.has_default:
                        continue
                    raise ValueError(f"{self.info.name} : '{spec.name}' is missing")
                value = child.build()
            elif spec.name in self.values:
                value = self.values[spec.name]
            else:
                continue
            if spec.kind is inspect.Parameter.POSITIONAL_ONLY:
                args.append(value)
            else:
                kwargs[spec.name] = value
        self.instance = self.cls(*args, **kwargs)
        return self.instance

    def clear_instances(self) -> None:
        """Forget the built instances"""
        for node in self.walk():
            node.instance = None


class Stack:
    """
    The stack being edited : its top node, and the edits of the stack screen

    Every edit keeps what can be kept : a component put on top takes the current top
    in its first slot that accepts it, a component removed can leave its only child
    in its place
    """

    def __init__(self, root: StackNode | None = None) -> None:
        self.root = root

    def problems(self) -> list[str]:
        """What prevents building the stack"""
        return ["Choose the top layer"] if self.root is None else self.root.problems()

    def place(self, parent: StackNode | None, slot: str | None, cls: type) -> StackNode:
        """Put a new component in a slot of parent, or at the top if parent is None"""
        node = StackNode(cls)
        if parent is None or slot is None:
            self.root = node
        else:
            parent.set_child(slot, node)
        return node

    def can_wrap(self, cls: type) -> bool:
        """True if cls can be put on top of the current top"""
        if self.root is None:
            return True
        return any(spec.accepts(self.root.cls) for spec in component_info(cls).slots)

    def wrap(self, cls: type) -> StackNode:
        """Put cls on top, the current top goes in its first slot that accepts it"""
        node = StackNode(cls)
        if self.root is not None:
            slot = next(s.name for s in node.info.slots if s.accepts(self.root.cls))
            node.set_child(slot, self.root)
        self.root = node
        return node

    def can_replace(self, node: StackNode, cls: type) -> bool:
        """True if cls can take the place of node"""
        if cls is node.cls:
            return False
        if node.parent is None:
            return True
        assert node.parent_slot is not None
        return node.parent.slot_spec(node.parent_slot).accepts(cls)

    def replace(self, node: StackNode, cls: type) -> StackNode:
        """Swap a component, keeping its values and the layers below that still fit"""
        new = StackNode(cls)
        known = {p.name for p in new.info.params if not p.is_slot}
        new.values = {k: v for k, v in node.values.items() if k in known}
        for child in [c for c in node.children.values() if c is not None]:
            slot = next(
                (s.name for s in new.info.slots
                 if new.children[s.name] is None and s.accepts(child.cls)),
                None,
            )
            if slot is not None:
                new.set_child(slot, child)
        if node.parent is None:
            self.root = new
        else:
            assert node.parent_slot is not None
            node.parent.set_child(node.parent_slot, new)
        return new

    def child_taking_place(self, node: StackNode) -> StackNode | None:
        """The only child of node, if it can take the place of node once removed"""
        children = [c for c in node.children.values() if c is not None]
        if len(children) != 1:
            return None
        child = children[0]
        if node.parent is None:
            return child
        assert node.parent_slot is not None
        return child if node.parent.slot_spec(node.parent_slot).accepts(child.cls) else None

    def remove(self, node: StackNode, keep_child: bool) -> StackNode | None:
        """
        Remove a component and the layers below it, or keep its child in its place
        (see child_taking_place). Returns the node now in its place, if any
        """
        parent, slot = node.parent, node.parent_slot
        replacement = self.child_taking_place(node) if keep_child else None
        if parent is None:
            if replacement is not None:
                replacement.detach()
            self.root = replacement
        else:
            assert slot is not None
            parent.set_child(slot, replacement)
        return replacement
