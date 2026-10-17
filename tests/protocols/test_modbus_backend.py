"""
Modbus backends (framing of TCP, RTU and ASCII) and client construction
"""

import struct

import pytest
from modbus_device import frame_rtu

from syndesi import AsyncModbus, Modbus
from syndesi.adapters.framer import AdapterReadFrame
from syndesi.protocols.modbus import (
    ExceptionCode,
    ExceptionResponseSDU,
    FunctionCode,
    ModbusASCIIBackend,
    ModbusCommon,
    ModbusRTUBackend,
    ModbusTCPBackend,
    ReadCoilsRequestSDU,
    ReadCoilsResponseSDU,
    ReadExceptionStatusRequestSDU,
    WriteSingleCoilResponseSDU,
    _ascii_frame,
    _serial_backend,
)
from syndesi.tools.errors import ProtocolError, ProtocolReadError

SLAVE_ADDRESS = 12
REQUEST = ReadCoilsRequestSDU(1, 3)
RESPONSE_SDU = bytes.fromhex("01 01 05")
RESPONSE = ReadCoilsResponseSDU([True, False, True])


def frame(data: bytes) -> AdapterReadFrame[bytes]:
    return AdapterReadFrame(data=data, id=0, stop_timestamp=0.0, response_delay=0.0)


def mbap(sdu: bytes, protocol_id: int = 0) -> bytes:
    return struct.pack(">HHHB", 0, protocol_id, len(sdu) + 1, 0) + sdu


def tcp_backend() -> ModbusTCPBackend:
    backend = ModbusTCPBackend()
    backend.encode(REQUEST)
    return backend


# ┌─────┐
# │ TCP │
# └─────┘


def test_tcp_assembly():
    backend = tcp_backend()
    data = mbap(RESPONSE_SDU)

    assert backend.push(frame(data[:4])).payloads == []  # header incomplete
    assert backend.in_progress
    assert backend.push(frame(data[4:8])).payloads == []  # body incomplete
    # The end of the frame and a whole second frame in the same read
    assert backend.push(frame(data[8:] + data)).payloads == [RESPONSE, RESPONSE]
    assert not backend.in_progress

    backend.push(frame(data[:4]))
    backend.reset()
    assert not backend.in_progress


@pytest.mark.parametrize(
    "data, error",
    [
        (struct.pack(">HHH", 0, 0, 0), "Modbus TCP frame is too short"),
        (mbap(RESPONSE_SDU, protocol_id=1), "Invalid Modbus TCP protocol id"),
        (mbap(b""), "Empty Modbus response"),
        (mbap(b"\x02\x01\x05"), "Function code mismatch"),
        (mbap(b"\x01\x02\x05"), "Malformed Modbus response"),
    ],
)
def test_tcp_invalid_response(data, error):
    with pytest.raises(ProtocolReadError, match=error):
        tcp_backend().push(frame(data))


def test_exception_response():
    response = tcp_backend().push(frame(mbap(b"\x81\x02"))).payloads[0]
    assert response == ExceptionResponseSDU(
        FunctionCode.READ_COILS, ExceptionCode.ILLEGAL_DATA_ADDRESS
    )


def test_read_without_write():
    with pytest.raises(ProtocolReadError, match="without a prior write"):
        ModbusTCPBackend().push(frame(mbap(RESPONSE_SDU)))


def test_tcp_serial_line_only():
    with pytest.raises(ProtocolError, match="cannot be used with Modbus TCP"):
        ModbusTCPBackend().encode(ReadExceptionStatusRequestSDU())


@pytest.mark.parametrize(
    "backend",
    [
        ModbusTCPBackend(),
        ModbusRTUBackend(SLAVE_ADDRESS, 19200),
        ModbusASCIIBackend(SLAVE_ADDRESS),
    ],
)
def test_encode_response(backend):
    with pytest.raises(RuntimeError, match="Can only encode ModbusRequestSDU"):
        backend.encode(RESPONSE)


# ┌─────┐
# │ RTU │
# └─────┘


def rtu_backend() -> ModbusRTUBackend:
    backend = ModbusRTUBackend(SLAVE_ADDRESS, 115200)
    backend.encode(REQUEST)
    return backend


def test_rtu():
    data = frame_rtu(SLAVE_ADDRESS, RESPONSE_SDU)
    assert rtu_backend().push(frame(data)).payloads == [RESPONSE]


@pytest.mark.parametrize(
    "data, error",
    [
        (b"\x0c\x01\x00", "Modbus RTU frame is too short"),
        (frame_rtu(SLAVE_ADDRESS, RESPONSE_SDU)[:-1] + b"\x00", "CRC mismatch"),
        (frame_rtu(SLAVE_ADDRESS + 1, RESPONSE_SDU), "came from slave 13"),
    ],
)
def test_rtu_invalid_frame(data, error):
    with pytest.raises(ProtocolReadError, match=error):
        rtu_backend().push(frame(data))


# ┌───────┐
# │ ASCII │
# └───────┘


def ascii_backend() -> ModbusASCIIBackend:
    backend = ModbusASCIIBackend(SLAVE_ADDRESS)
    backend.encode(REQUEST)
    return backend


def test_ascii():
    data = _ascii_frame(SLAVE_ADDRESS, RESPONSE_SDU)
    assert ascii_backend().push(frame(data)).payloads == [RESPONSE]


@pytest.mark.parametrize(
    "data, error",
    [
        (b"0C0101\r\n", "Malformed Modbus ASCII frame"),
        (b":0C01ZZ\r\n", "isn't hex"),
        (b":0C01\r\n", "Modbus ASCII frame is too short"),
        (b":0C010105FF\r\n", "LRC mismatch"),
        (_ascii_frame(SLAVE_ADDRESS + 1, RESPONSE_SDU), "came from slave 13"),
    ],
)
def test_ascii_invalid_frame(data, error):
    with pytest.raises(ProtocolReadError, match=error):
        ascii_backend().push(frame(data))


# ┌──────────────┐
# │ Construction │
# └──────────────┘


@pytest.mark.parametrize(
    "serial_type, slave_address, baudrate, error",
    [
        ("rtu", None, 19200, "slave_address must be set"),
        ("rtu", 248, 19200, "Invalid slave address : 248"),
        ("rtu", SLAVE_ADDRESS, None, "Baudrate hasn't been defined"),
        ("binary", SLAVE_ADDRESS, 19200, "Invalid modbus serial type : binary"),
    ],
)
def test_invalid_serial_parameters(serial_type, slave_address, baudrate, error):
    with pytest.raises(ValueError, match=error):
        _serial_backend(serial_type, slave_address, baudrate)


@pytest.mark.parametrize("client_type", [Modbus, AsyncModbus])
def test_invalid_adapter(client_type):
    with pytest.raises(ValueError, match="Invalid adapter"):
        client_type(object())


def test_unexpected_response_type():
    with pytest.raises(ProtocolReadError, match="expected WriteSingleCoilResponseSDU"):
        ModbusCommon._check_response(REQUEST, RESPONSE, WriteSingleCoilResponseSDU)
