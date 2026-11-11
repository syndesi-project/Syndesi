"""What the GUI reads from the type hints and docstrings, no Qt needed"""

from pathlib import Path

from syndesi import (
    IP,
    SCPI,
    AsyncIP,
    AsyncSCPI,
    Delimited,
    IPServer,
    Modbus,
    SCPIDriver,
    SerialPort,
)
from syndesi.ui.core.introspection import (
    FieldType,
    Kind,
    commands_of,
    component_info,
    io_payload_type,
    parse_numpy_doc,
)
from syndesi.ui.core.library import Library

EXAMPLE = Path(__file__).parents[2] / "examples" / "drivers" / "demo_psu.py"


def _slot(cls, name="adapter"):
    return next(s for s in component_info(cls).slots if s.name == name)


def test_kinds_and_provides():
    assert component_info(IP).kind is Kind.ADAPTER
    assert component_info(IP).provides is bytes
    assert component_info(SCPI).kind is Kind.PROTOCOL
    assert component_info(SCPI).provides is str
    assert component_info(IPServer).provides is IP
    assert component_info(SCPIDriver).kind is Kind.DRIVER
    assert component_info(SCPIDriver).is_base_class


def test_slot_compatibility_follows_type_hints():
    slot = _slot(SCPI)
    assert slot.accepts(IP)
    assert slot.accepts(SerialPort)
    # Adapter[..., IP] isn't Adapter[Any, bytes]
    assert not slot.accepts(IPServer)
    # Sync and async don't mix
    assert not slot.accepts(AsyncIP)
    assert _slot(AsyncSCPI).accepts(AsyncIP)
    assert not _slot(AsyncSCPI).accepts(IP)
    # A protocol isn't an adapter
    assert not slot.accepts(Delimited)


def test_fields():
    params = {p.name: p for p in component_info(IP).params}
    assert params["address"].field_type is FieldType.STR and params["address"].required
    assert params["port"].field_type is FieldType.INT and params["port"].allows_none
    # Choices from the numpy docstring : transport : {'TCP', 'UDP'}
    assert params["transport"].field_type is FieldType.CHOICE
    assert params["transport"].choices == ["TCP", "UDP"]
    assert params["timeout"].allows_default and params["timeout"].allows_none
    assert params["stop_conditions"].field_type is FieldType.STOP_CONDITIONS
    # socket.socket can't be edited, and has a default : hidden
    assert params["sock"].hidden
    assert "well-known port" in params["port"].doc.description


def test_suggestions_from_list_method():
    params = {p.name: p for p in component_info(SerialPort).params}
    assert params["port"].suggestions is not None


def test_commands():
    names = [c.name for c in commands_of(SCPIDriver)]
    assert "get_identification" in names
    # Abstract, and handled by the toolbar
    assert "open" not in names and "test" not in names
    write_raw = next(c for c in commands_of(Delimited) if c.name == "write_raw")
    # Protocol.write_raw(data: AdapterT) once AdapterT is bytes
    assert write_raw.params[0].field_type is FieldType.BYTES
    registers = next(c for c in commands_of(Modbus) if c.name == "write_multiple_registers")
    assert registers.params[1].field_type is FieldType.EXPRESSION


def test_io_payload():
    assert io_payload_type(IP) is bytes
    assert io_payload_type(Delimited) is str
    assert io_payload_type(Modbus) is None
    assert io_payload_type(SCPIDriver) is None


def test_numpy_doc_several_names():
    summary, params = parse_numpy_doc(
        """
        Summary line

        Parameters
        ----------
        a, b : int
            Shared description
        c : {'x', 'y'}
        """
    )
    assert summary == "Summary line"
    assert params["a"].description == params["b"].description == "Shared description"
    assert params["c"].type == "{'x', 'y'}"


def test_user_driver_slots():
    library = Library.default()
    classes = {c.__name__: c for c in library.load(str(EXAMPLE))}
    bench, psu = classes["Bench"], classes["DemoPowerSupply"]
    assert _slot(bench, "psu").accepts(psu)
    assert not _slot(bench, "psu").accepts(SCPIDriver)
    assert _slot(psu).accepts(IP)
    assert component_info(classes["PowerSupplyChannel"]).kind is Kind.SUBDRIVER
    channel = next(c for c in commands_of(psu) if c.name == "channel")
    assert channel.returns is classes["PowerSupplyChannel"]
