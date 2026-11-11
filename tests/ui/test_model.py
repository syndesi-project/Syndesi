"""The stack model : problems, build, python code, file, runtime tree. No Qt needed"""

from pathlib import Path

from syndesi import IP, SCPI, IPServer, Length, SCPIDriver, Termination
from syndesi.ui.core.code import to_code
from syndesi.ui.core.library import Library
from syndesi.ui.core.runtime import Role, RuntimeTree
from syndesi.ui.core.stack import StackNode
from syndesi.ui.core.stack_file import load_stack, node_from_dict, node_to_dict, save_stack

EXAMPLE = Path(__file__).parents[2] / "examples" / "drivers" / "demo_psu.py"


def _scpi_stack() -> StackNode:
    root = StackNode(SCPI)
    adapter = StackNode(IP)
    adapter.values["address"] = "127.0.0.1"
    root.set_child("adapter", adapter)
    return root


def test_problems():
    root = StackNode(SCPI)
    assert any("adapter" in p for p in root.problems())
    root.set_child("adapter", StackNode(IP))
    assert root.problems() == ["IP : 'address' is required"]
    root.children["adapter"].values["address"] = "127.0.0.1"
    assert root.problems() == []


def test_only_changed_values_are_passed():
    root = _scpi_stack()
    instance = root.build()
    # port wasn't given : SCPI set its well-known port
    assert instance.adapter.descriptor.port == SCPI.DEFAULT_PORT
    assert instance.adapter.descriptor.address == "127.0.0.1"


def test_code():
    root = _scpi_stack()
    root.children["adapter"].values["stop_conditions"] = [Termination(b"\r"), Length(4)]
    code = to_code(root)
    assert "from syndesi import IP, Length, SCPI, Termination" in code
    assert "ip = IP('127.0.0.1', stop_conditions=[Termination(b'\\r'), Length(4)])" in code
    assert "scpi = SCPI(ip)" in code


def test_round_trip(tmp_path):
    library = Library.default()
    root = _scpi_stack()
    root.children["adapter"].values.update(port=1234, stop_conditions=[Termination(b"\n")])
    again = node_from_dict(node_to_dict(root), library)
    assert to_code(again) == to_code(root)

    path = tmp_path / "stack.json"
    save_stack(path, root, library)
    assert to_code(load_stack(path, library)) == to_code(root)


def test_runtime_tree_finds_internal_layers_and_subdrivers():
    library = Library.default()
    classes = {c.__name__: c for c in library.load(str(EXAMPLE))}
    root = StackNode(classes["Bench"])
    psu = StackNode(classes["DemoPowerSupply"])
    adapter = StackNode(IP)
    adapter.values["address"] = "127.0.0.1"
    psu.set_child("adapter", adapter)
    root.set_child("psu", psu)
    root.build()
    tree = RuntimeTree(root)
    roles = {(i.label, i.role) for i in tree.walk()}
    assert ("Bench", Role.TOP) in roles
    assert ("DemoPowerSupply", Role.EXTERNAL) in roles
    # Built by DemoPowerSupply for itself
    assert ("SCPI", Role.INTERNAL) in roles
    assert ("PowerSupplyChannel", Role.SUBDRIVER) in roles
    assert ("PowerSupplyChannel#2", Role.SUBDRIVER) in roles
    # The external IP is reached through the internal SCPI, and appears once
    ip = [i for i in tree.walk() if i.cls is IP]
    assert len(ip) == 1 and ip[0].parent.cls is SCPI and ip[0].role is Role.EXTERNAL


def test_base_class_driver_builds():
    root = StackNode(SCPIDriver)
    adapter = StackNode(IP)
    adapter.values["address"] = "127.0.0.1"
    root.set_child("adapter", adapter)
    tree = RuntimeTree(root) if root.build() is not None else None
    assert tree is not None
    assert [i.cls for i in tree.walk()] == [SCPIDriver, SCPI, IP]


def test_returned_components_are_added():
    root = StackNode(IPServer)
    root.values.update(address="127.0.0.1", port=0)
    root.build()
    tree = RuntimeTree(root)
    client = IP("127.0.0.1", 1, auto_open=False)
    item = tree.add(client, Role.RETURNED, "read()", tree.root)
    assert item is not None and item.parent is tree.root
    assert tree.add(client, Role.RETURNED, "read()", tree.root) is None


def test_stack_edits():
    from syndesi import Delimited  # pylint: disable=import-outside-toplevel
    from syndesi.ui.core.stack import Stack  # pylint: disable=import-outside-toplevel

    stack = Stack()
    assert stack.problems() == ["Choose the top layer"]
    ip = stack.place(None, None, IP)
    # A protocol put on top takes the adapter in its slot
    assert stack.can_wrap(SCPI) and not stack.can_wrap(IPServer)
    scpi = stack.wrap(SCPI)
    assert stack.root is scpi and scpi.children["adapter"] is ip
    # Replacing keeps the layers below that fit
    delimited = stack.replace(scpi, Delimited)
    assert stack.root is delimited and delimited.children["adapter"] is ip
    # Removing the top can leave its only child in its place
    assert stack.child_taking_place(delimited) is ip
    assert stack.remove(delimited, keep_child=True) is ip
    assert stack.root is ip and ip.parent is None
    assert stack.remove(ip, keep_child=False) is None and stack.root is None


def test_code_only_components():
    from syndesi.ui.core.introspection import (
        component_info,  # pylint: disable=import-outside-toplevel
    )

    assert "use it from your code" in component_info(IPServer).code_only
    assert component_info(IP).code_only == ""
    assert component_info(SCPI).code_only == ""
