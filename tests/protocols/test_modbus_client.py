"""
Modbus and AsyncModbus against the in-memory device of modbus_device.py

Every test runs on Modbus TCP, RTU and ASCII, with both the sync and the async client
"""

import asyncio
import inspect
import time
from contextlib import ExitStack

import pytest
from modbus_device import (
    COMM_EVENT_COUNTER,
    COMM_EVENT_LOG,
    COUNTER_VALUE,
    EXCEPTION_STATUS,
    FIFO,
    RTU_SILENCE,
    SERVER_ID,
    SLAVE_ADDRESS,
    FakeDevice,
    serve_serial,
    serve_tcp,
)

from syndesi import IP, AsyncModbus, Modbus, ModbusMultiRegisterValue
from syndesi.adapters.ip import AsyncIP
from syndesi.adapters.serialport import AsyncSerialPort, SerialPort
from syndesi.protocols.modbus import DiagnosticsCode, ExceptionCode, ModbusError
from syndesi.tools.errors import ProtocolError

BAUDRATE = 19200


class Synchronized:
    """Runs the coroutines of an async client, so the same tests drive both clients"""

    def __init__(self, client: AsyncModbus, runner: asyncio.Runner) -> None:
        self._client = client
        self._runner = runner

    def __getattr__(self, name: str):
        attribute = getattr(self._client, name)
        if not inspect.iscoroutinefunction(attribute):
            return attribute
        return lambda *args, **kwargs: self._runner.run(attribute(*args, **kwargs))


@pytest.fixture
def device() -> FakeDevice:
    return FakeDevice()


@pytest.fixture(params=["tcp", "rtu", "ascii"])
def transport(request) -> str:
    return request.param


@pytest.fixture(params=["sync", "async"])
def client(request, device, transport):
    with ExitStack() as stack:
        if transport == "tcp":
            host, port = stack.enter_context(serve_tcp(device))
        else:
            path = stack.enter_context(serve_serial(device, transport))

        if request.param == "sync":
            if transport == "tcp":
                modbus = Modbus(IP(host, port=port))
            else:
                modbus = Modbus(
                    SerialPort(path, baudrate=BAUDRATE),
                    serial_type=transport,
                    slave_address=SLAVE_ADDRESS,
                )
            yield modbus
            modbus.close()
        else:
            runner = stack.enter_context(asyncio.Runner())

            async def create() -> AsyncModbus:
                if transport == "tcp":
                    return AsyncModbus(AsyncIP(host, port=port))
                return AsyncModbus(
                    AsyncSerialPort(path, baudrate=BAUDRATE),
                    serial_type=transport,
                    slave_address=SLAVE_ADDRESS,
                )

            modbus = Synchronized(runner.run(create()), runner)
            yield modbus
            modbus.close()


# ┌─────────────────────────┐
# │ Coils and discrete bits │
# └─────────────────────────┘


def test_coils(client):
    values = [True, False, True, True, False, False, True, False, True]
    client.write_multiple_coils(10, values)
    assert client.read_coils(10, len(values)) == values
    assert client.read_discrete_inputs(10, len(values)) == values

    client.write_single_coil(30, True)
    assert client.read_single_coil(30) is True
    client.write_single_coil(30, False)
    assert client.read_single_coil(30) is False


# ┌───────────┐
# │ Registers │
# └───────────┘


def test_single_register(client):
    client.write_single_register(5, 0xBEEF)
    assert client.read_single_register(5) == 0xBEEF


def test_multiple_registers(client):
    values = [1, 2, 0xFFFF]
    client.write_multiple_registers(100, values)
    assert client.read_holding_registers(100, 3) == values
    assert client.read_input_registers(100, 3) == values


def test_mask_write_register(client, device):
    device.registers[7] = 0x12
    client.mask_write_register(7, and_mask=0xF2, or_mask=0x25)
    assert client.read_single_register(7) == 0x17  # example of the specification


def test_read_write_multiple_registers(client):
    client.write_multiple_registers(1, [10, 20])
    assert client.read_write_multiple_registers(1, 2, 50, [30, 40]) == [10, 20]
    assert client.read_holding_registers(50, 2) == [30, 40]


def test_multi_register_value(client):
    value = ModbusMultiRegisterValue.from_float(1.5, n_registers=2, word_order="little")
    client.write_multi_register_value(200, value)
    read = client.read_multi_register_value(200, 2, word_order="little")
    assert read.to_float() == 1.5


# ┌────────────────────────────┐
# │ Files, FIFO, encapsulation │
# └────────────────────────────┘


def test_file_records(client):
    client.write_file_record([(4, 7, b"\x06\xaf\x04\xbe"), (4, 9, b"\x10\x0d")])
    assert client.read_file_record([(4, 7, 2), (4, 9, 1)]) == [
        b"\x06\xaf\x04\xbe",
        b"\x10\x0d",
    ]


def test_read_fifo_queue(client):
    assert client.read_fifo_queue(0x04DE) == FIFO


def test_encapsulated_interface_transport(client):
    assert client.encapsulated_interface_transport(0x0E, b"\x01\x00") == b"\x01\x00"


# ┌────────────┐
# │ Exceptions │
# └────────────┘


def test_exception_response(client, device):
    device.exception = ExceptionCode.ILLEGAL_DATA_ADDRESS
    with pytest.raises(ModbusError, match="02 : Invalid data address"):
        client.read_coils(1, 1)
    # The client is still usable after an exception
    client.write_single_coil(1, True)


def test_extra_exceptions(client, device):
    device.exception = 0x42
    with pytest.raises(ModbusError, match="42 : MEI specific error"):
        client.encapsulated_interface_transport(
            0x0E, b"\x01\x00", extra_exceptions={0x42: "MEI specific error"}
        )


# ┌───────────────────┐
# │ Serial line only  │
# └───────────────────┘


@pytest.fixture
def serial_client(client, transport):
    if transport == "tcp":
        pytest.skip("Serial line only function")
    return client


def test_serial_only_function_over_tcp(client, transport):
    if transport != "tcp":
        pytest.skip("Modbus TCP only")
    with pytest.raises(ProtocolError, match="cannot be used with Modbus TCP"):
        client.read_exception_status()


def test_status_functions(serial_client):
    assert serial_client.read_exception_status() == EXCEPTION_STATUS
    assert serial_client.get_comm_event_counter() == COMM_EVENT_COUNTER
    assert serial_client.get_comm_event_log() == COMM_EVENT_LOG
    assert serial_client.report_server_id(4, 2) == SERVER_ID


@pytest.mark.parametrize(
    "method",
    [
        "diagnostics_return_diagnostic_register",
        "diagnostics_return_bus_message_count",
        "diagnostics_return_bus_communication_error_count",
        "diagnostics_return_bus_exception_error_count",
        "diagnostics_return_server_no_response_count",
        "diagnostics_return_server_nak_count",
        "diagnostics_return_server_busy_count",
        "diagnostics_return_bus_character_overrun_count",
    ],
)
def test_diagnostics_counters(serial_client, method):
    assert getattr(serial_client, method)() == COUNTER_VALUE


def test_diagnostics(serial_client, device):
    assert serial_client.diagnostics_return_query_data(0xA537) is True
    serial_client.diagnostics_restart_communications_option(clear_communications_event_log=True)
    serial_client.diagnostics_change_ascii_input_delimiter("\n")
    serial_client.diagnostics_change_ascii_input_delimiter(b"\n")
    serial_client.diagnostics_clear_counters_and_diagnostic_register()
    serial_client.diagnostics_clear_overrun_counter_and_flag()

    with pytest.raises(ValueError, match="Invalid char length"):
        serial_client.diagnostics_change_ascii_input_delimiter("ab")


def test_force_listen_only_mode(serial_client, device):
    # No answer to this one, the next query makes sure the device got it. The client
    # doesn't wait for the RTU inter-frame silence after a write, the test does
    serial_client.diagnostics_force_listen_only_mode()
    time.sleep(2 * RTU_SILENCE)
    serial_client.diagnostics_restart_communications_option()
    assert [request.code for request in device.requests] == [
        DiagnosticsCode.FORCE_LISTEN_ONLY_MODE,
        DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION,
    ]
