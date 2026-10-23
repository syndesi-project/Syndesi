"""
ModbusServer and AsyncModbusServer, driven by the Modbus client

Every test runs on Modbus TCP, RTU and ASCII, with both the sync and the async server
"""

import asyncio
import socket
import struct
import threading
import time
from contextlib import contextmanager

import pytest
from modbus_device import RTU_SILENCE, virtual_serial_pair

from syndesi import IP, AsyncIPServer, AsyncSerialPort, IPServer, Modbus, SerialPort
from syndesi.adapters.framer import AdapterReadFrame
from syndesi.protocols.modbus import (
    AsyncModbusServer,
    DiagnosticsCode,
    ExceptionCode,
    ExceptionResponseSDU,
    ModbusConnectionClosedEvent,
    ModbusConnectionOpenedEvent,
    ModbusException,
    ModbusExceptionEvent,
    ModbusHandlerErrorEvent,
    ModbusRequestHandledEvent,
    ModbusRTUBackend,
    ModbusServer,
    ModbusTCPBackend,
    ReadCoilsRequestSDU,
    ReadCoilsResponseSDU,
    ReadHoldingRegistersRequestSDU,
    ReadHoldingRegistersResponseSDU,
    WriteSingleCoilRequestSDU,
    WriteSingleCoilResponseSDU,
    _serial_backend,
    modbus_crc,
)
from syndesi.protocols.protocol import ProtocolFrameEvent
from syndesi.tools.errors import AdapterTimeoutError, ProtocolError

HOST = "localhost"
BAUDRATE = 19200
SLAVE_ADDRESS = 12
CLIENT_TIMEOUT = 0.5


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


# ┌──────────┐
# │ Fixtures │
# └──────────┘


@contextmanager
def run_sync_server(transport, endpoint):
    if transport == "tcp":
        server = ModbusServer(IPServer(HOST, endpoint))
    else:
        server = ModbusServer(
            SerialPort(endpoint, baudrate=BAUDRATE),
            serial_type=transport,
            slave_address=SLAVE_ADDRESS,
        )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server
    finally:
        server.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()


@contextmanager
def run_async_server(transport, endpoint):
    """The async server runs its own event loop, in a thread"""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()

    def run(coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    async def create() -> AsyncModbusServer:
        if transport == "tcp":
            ip_server = AsyncIPServer(HOST, endpoint, auto_open=False)
            await ip_server.open()  # listening before the client connects
            return AsyncModbusServer(ip_server)
        return AsyncModbusServer(
            AsyncSerialPort(endpoint, baudrate=BAUDRATE),
            serial_type=transport,
            slave_address=SLAVE_ADDRESS,
        )

    server = run(create())
    serving = asyncio.run_coroutine_threadsafe(server.serve_forever(), loop)
    try:
        yield server
    finally:
        run(server.stop())
        serving.result(timeout=5)
        loop.call_soon_threadsafe(loop.stop)
        thread.join()
        loop.close()


@pytest.fixture(params=["tcp", "rtu", "ascii"])
def transport(request) -> str:
    return request.param


@pytest.fixture(params=["sync", "async"])
def flavour(request) -> str:
    return request.param


@pytest.fixture
def endpoints(transport):
    """(server endpoint, client endpoint)"""
    if transport == "tcp":
        port = free_port()
        yield port, port
    else:
        with virtual_serial_pair() as paths:
            yield paths


@pytest.fixture
def server(flavour, transport, endpoints):
    run_server = run_sync_server if flavour == "sync" else run_async_server
    with run_server(transport, endpoints[0]) as server:
        yield server


def connect(transport, endpoint) -> Modbus:
    if transport == "tcp":
        return Modbus(IP(HOST, port=endpoint), timeout=CLIENT_TIMEOUT)
    return Modbus(
        SerialPort(endpoint, baudrate=BAUDRATE),
        timeout=CLIENT_TIMEOUT,
        serial_type=transport,
        slave_address=SLAVE_ADDRESS,
    )


@pytest.fixture
def client(server, transport, endpoints):
    client = connect(transport, endpoints[1])
    yield client
    client.close()


# ┌────────────┐
# │ Data model │
# └────────────┘


def test_bits(server, client):
    client.write_multiple_coils(1, [True, False, True])
    client.write_single_coil(10, True)
    assert [server.coils[address] for address in (1, 2, 3, 10)] == [True, False, True, True]
    assert client.read_coils(1, 3) == [True, False, True]

    server.discrete_inputs[5] = True
    assert client.read_discrete_inputs(4, 2) == [False, True]


def test_registers(server, client):
    client.write_multiple_registers(1, [10, 20, 30])
    client.write_single_register(4, 40)
    assert client.read_holding_registers(1, 4) == [10, 20, 30, 40]

    server.input_registers[7] = 70
    assert client.read_input_registers(7, 1) == [70]


def test_mask_write_register(server, client):
    server.holding_registers[1] = 0x12
    client.mask_write_register(1, and_mask=0xF2, or_mask=0x25)
    assert server.holding_registers[1] == 0x17  # example of the specification


def test_read_write_multiple_registers(server, client):
    # The write happens before the read
    assert client.read_write_multiple_registers(1, 2, 2, [5, 6]) == [0, 5]


def test_file_records(server, client):
    client.write_file_record([(4, 7, b"\x06\xaf\x04\xbe")])
    assert server.files[4][8] == 0x04BE
    assert client.read_file_record([(4, 7, 2), (4, 9, 1)]) == [b"\x06\xaf\x04\xbe", b"\x00\x00"]

    with pytest.raises(ModbusException, match="Invalid data address"):
        client.read_file_record([(0, 1, 1)])
    with pytest.raises(ModbusException, match="Invalid data address"):
        client.write_file_record([(1, 9999, b"\x00\x01\x00\x02")])


def test_fifo(server, client):
    server.fifos[3] = [1, 2, 3]
    assert client.read_fifo_queue(3) == [1, 2, 3]

    server.fifos[3] = list(range(32))
    with pytest.raises(ModbusException, match="Invalid data value"):
        client.read_fifo_queue(3)


def test_no_default_behaviour(server, client):
    with pytest.raises(ModbusException) as error:
        client.encapsulated_interface_transport(0x0E, b"\x01\x00")
    assert error.value.exception_code == ExceptionCode.ILLEGAL_FUNCTION


# ┌──────────┐
# │ Handlers │
# └──────────┘


def test_custom_handler(server, client):
    server.set_handler(
        ReadHoldingRegistersRequestSDU,
        lambda request: ReadHoldingRegistersResponseSDU([42] * request.n_registers),
    )
    assert client.read_holding_registers(1, 2) == [42, 42]

    server.set_handler(ReadHoldingRegistersRequestSDU, None)  # back to the default
    assert client.read_holding_registers(1, 2) == [0, 0]


def test_handler_keeps_default(server, client):
    requests = []

    def log(request):
        requests.append(request)
        return server.default_handler(request)

    server.set_handler(ReadCoilsRequestSDU, log)
    server.coils[1] = True
    assert client.read_coils(1, 1) == [True]
    assert requests == [ReadCoilsRequestSDU(1, 1)]


def test_handler_exceptions(server, client):
    def busy(request):
        raise ModbusException(ExceptionCode.SERVER_DEVICE_BUSY)

    def broken(request):
        raise RuntimeError("bug in the handler")

    server.set_handler(ReadCoilsRequestSDU, busy)
    with pytest.raises(ModbusException, match="06 : Server is busy"):
        client.read_coils(1, 1)

    server.set_handler(ReadCoilsRequestSDU, broken)
    with pytest.raises(ModbusException, match="04 : Unrecoverable error"):
        client.read_coils(1, 1)


@pytest.mark.parametrize("flavour", ["async"])
def test_coroutine_handler(server, client):
    async def handler(request):
        await asyncio.sleep(0)
        return ReadCoilsResponseSDU([True] * request.number_of_coils)

    server.set_handler(ReadCoilsRequestSDU, handler)
    assert client.read_coils(1, 3) == [True, True, True]


# ┌─────────────┐
# │ Connections │
# └─────────────┘


@pytest.mark.parametrize("transport", ["tcp"])
def test_several_clients(server, endpoints):
    clients = [connect("tcp", endpoints[1]) for _ in range(3)]
    for i, client in enumerate(clients):
        client.write_single_register(1 + i, i)
    for client in clients:
        assert client.read_holding_registers(1, 3) == [0, 1, 2]
        client.close()

    # A new client after the others left
    client = connect("tcp", endpoints[1])
    assert client.read_single_register(3) == 2
    client.close()


@pytest.mark.parametrize("transport", ["tcp"])
def test_invalid_requests(server, endpoints):
    """Requests a client wouldn't send, answered with an exception"""
    with socket.create_connection((HOST, endpoints[1])) as connection:

        def query(sdu: bytes) -> bytes:
            connection.sendall(struct.pack(">HHHB", 1, 0, len(sdu) + 1, 0) + sdu)
            return connection.recv(256)[7:]

        assert query(b"\x41") == b"\xc1\x01"  # unknown function code
        assert query(b"\x07") == b"\x87\x01"  # serial line only
        assert query(bytes.fromhex("01 FFFF 0002")) == b"\x81\x02"  # past the last address
        assert query(bytes.fromhex("01 0000 0000")) == b"\x81\x03"  # no coil

        # Not a Modbus TCP frame, counted then ignored
        connection.sendall(struct.pack(">HHHB", 1, 5, 2, 0) + b"\x01")
        assert query(bytes.fromhex("01 0000 0001")) == b"\x01\x01\x00"
    assert server.counters[DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT] == 1
    assert server.counters[DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT] == 4


# ┌────────┐
# │ Events │
# └────────┘


def of_type(events, event_type):
    return [event for event in events if isinstance(event, event_type)]


@pytest.mark.parametrize("transport", ["tcp"])
def test_events(server, endpoints):
    events = []
    server.register_event_callback(events.append)
    server.register_event_callback(lambda event: 1 / 0)  # doesn't stop the others

    def broken(request):
        raise RuntimeError("bug in the handler")

    server.set_handler(ReadCoilsRequestSDU, broken)

    client = connect("tcp", endpoints[1])
    client.write_single_coil(1, True)
    with pytest.raises(ModbusException):
        client.read_coils(1, 1)
    client.close()

    deadline = time.monotonic() + 2
    while not of_type(events, ModbusConnectionClosedEvent):
        assert time.monotonic() < deadline
        time.sleep(0.01)

    assert len(of_type(events, ModbusConnectionOpenedEvent)) == 1
    write, read = of_type(events, ModbusRequestHandledEvent)
    assert write.request == WriteSingleCoilRequestSDU(1, True)
    assert write.response == WriteSingleCoilResponseSDU(1, True)
    assert read.response == ExceptionResponseSDU(1, ExceptionCode.SERVER_DEVICE_FAILURE)
    (error,) = of_type(events, ModbusHandlerErrorEvent)
    assert error.request == ReadCoilsRequestSDU(1, 1)
    # The protocol events of the connection come through too
    assert [event.frame.data for event in of_type(events, ProtocolFrameEvent)] == [
        write.request,
        read.request,
    ]

    server.clear_event_callbacks()
    client = connect("tcp", endpoints[1])
    client.write_single_coil(1, True)
    client.close()
    assert len(of_type(events, ModbusRequestHandledEvent)) == 2


@pytest.mark.parametrize("transport", ["tcp"])
def test_invalid_request_event(server, endpoints):
    events = []
    server.register_event_callback(events.append)
    with socket.create_connection((HOST, endpoints[1])) as connection:
        connection.sendall(struct.pack(">HHHB", 1, 0, 2, 0) + b"\x41")
        connection.recv(256)
    (event,) = of_type(events, ModbusExceptionEvent)
    assert event.response == ExceptionResponseSDU(0x41, ExceptionCode.ILLEGAL_FUNCTION)


# ┌──────────────────┐
# │ Serial line only │
# └──────────────────┘


@pytest.fixture
def serial_client(client, transport):
    if transport == "tcp":
        pytest.skip("Serial line only function")
    return client


def test_status_functions(server, serial_client):
    server.exception_status = 0x55
    server.server_id = b"ID"
    server.additional_data = b"\x01"
    assert serial_client.read_exception_status() == 0x55
    assert serial_client.report_server_id(2, 1) == (b"ID", True, b"\x01")


def test_comm_events(server, serial_client):
    serial_client.write_single_coil(1, True)
    serial_client.write_single_coil(1, False)
    # The event counter doesn't count itself, nor the event log requests
    assert serial_client.get_comm_event_counter() == (0, 2)
    assert serial_client.get_comm_event_log() == (0, 2, 4, b"")


def test_diagnostics(server, serial_client):
    assert serial_client.diagnostics_return_query_data(0xA537) is True

    server.diagnostic_register = 0x1234
    assert serial_client.diagnostics_return_diagnostic_register() == 0x1234

    server.counters[DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT] = 3
    assert serial_client.diagnostics_return_bus_character_overrun_count() == 3
    serial_client.diagnostics_clear_overrun_counter_and_flag()
    assert serial_client.diagnostics_return_bus_character_overrun_count() == 0

    with pytest.raises(ModbusException, match="01 : Function code not supported"):
        serial_client.diagnostics_change_ascii_input_delimiter("\n")
    assert serial_client.diagnostics_return_bus_exception_error_count() == 1
    # Every request so far, this one included
    assert serial_client.diagnostics_return_bus_message_count() == 8

    serial_client.diagnostics_clear_counters_and_diagnostic_register()
    assert server.diagnostic_register == 0
    assert serial_client.diagnostics_return_server_no_response_count() == 0


def test_listen_only_mode(server, serial_client):
    serial_client.write_single_coil(1, True)
    serial_client.diagnostics_force_listen_only_mode()
    time.sleep(2 * RTU_SILENCE)  # inter-frame silence, the client doesn't wait for it
    with pytest.raises(AdapterTimeoutError):
        serial_client.read_coils(1, 1)
    assert server.listen_only

    # Only the restart is answered, it can clear the event log too
    serial_client.diagnostics_restart_communications_option(clear_communications_event_log=True)
    assert serial_client.read_coils(1, 1) == [True]
    assert serial_client.get_comm_event_counter() == (0, 2)  # the restart, the read
    assert server.counters[DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT] == 2


@pytest.mark.parametrize("transport", ["rtu"])
def test_corrupted_frame(server, serial_client):
    serial_client.write_raw(b"\x0c\x01\x00\x00")  # wrong CRC
    time.sleep(2 * RTU_SILENCE)
    assert serial_client.diagnostics_return_bus_communication_error_count() == 1


# ┌─────────────────────┐
# │ Backends and errors │
# └─────────────────────┘


def frame(data: bytes) -> AdapterReadFrame[bytes]:
    return AdapterReadFrame(data=data, id=0, stop_timestamp=0.0, response_delay=0.0)


def rtu(address: int, sdu: bytes) -> bytes:
    data = bytes([address]) + sdu
    return data + struct.pack("<H", modbus_crc(data))


READ_COIL = bytes.fromhex("01 0000 0001")
COIL = ReadCoilsResponseSDU([True])


def test_tcp_server_backend():
    backend = ModbusTCPBackend(server=True)
    with pytest.raises(ProtocolError, match="no request to answer"):
        backend.encode(COIL)
    with pytest.raises(RuntimeError, match="can only encode ModbusResponseSDU"):
        backend.encode(ReadCoilsRequestSDU(1, 1))

    # Two requests in the same read, each answer gets its transaction id back
    requests = b"".join(
        struct.pack(">HHHB", transaction_id, 0, len(READ_COIL) + 1, 3) + READ_COIL
        for transaction_id in (7, 8)
    )
    assert backend.push(frame(requests)).payloads == [ReadCoilsRequestSDU(1, 1)] * 2
    assert backend.encode(COIL)[0][:2] == b"\x00\x07"
    assert backend.encode(COIL)[0][:2] == b"\x00\x08"


def test_serial_server_backend():
    backend = ModbusRTUBackend(SLAVE_ADDRESS, BAUDRATE, server=True)

    # Another slave's request is ignored
    assert backend.push(frame(rtu(SLAVE_ADDRESS + 1, READ_COIL))).payloads == []

    # A broadcast is handled, never answered
    assert backend.push(frame(rtu(0, READ_COIL))).payloads == [ReadCoilsRequestSDU(1, 1)]
    assert backend.encode(COIL) == []

    assert backend.push(frame(rtu(SLAVE_ADDRESS, b"\x07"))).payloads[0].function_code == 7
    assert backend.encode(COIL) == [rtu(SLAVE_ADDRESS, COIL.make_sdu())]

    with pytest.raises(ProtocolError, match="Empty Modbus request"):
        backend._parse_request(b"")


def test_invalid_request_payload():
    backend = ModbusTCPBackend(server=True)
    request = struct.pack(">HHHB", 0, 0, 2, 0) + b"\x41"
    output = backend.push(frame(request))
    assert output.payloads == [ExceptionResponseSDU(0x41, 1)]
    assert [event.response for event in output.events] == output.payloads


@pytest.mark.parametrize("server_type", [ModbusServer, AsyncModbusServer])
def test_invalid_adapter(server_type):
    with pytest.raises(ValueError, match="Invalid adapter"):
        server_type(object())


def test_invalid_serial_server():
    with pytest.raises(ValueError, match="slave_address must be set"):
        _serial_backend("rtu", None, BAUDRATE, server=True)


def test_stop_before_serving():
    """serve_forever() returns at once, the connection is closed as soon as it opens"""
    with virtual_serial_pair() as (path, _):
        server = ModbusServer(SerialPort(path, baudrate=BAUDRATE), slave_address=SLAVE_ADDRESS)
        server.stop()
        server.serve_forever()

    async def main():
        with virtual_serial_pair() as (path, _):
            server = AsyncModbusServer(
                AsyncSerialPort(path, baudrate=BAUDRATE), slave_address=SLAVE_ADDRESS
            )
            await server.stop()
            await asyncio.wait_for(server.serve_forever(), 2)

    asyncio.run(main())


def test_stop_before_any_client():
    with run_sync_server("tcp", free_port()):
        pass
