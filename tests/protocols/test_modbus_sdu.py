"""
Modbus SDUs and values, without any transport
"""

import pytest

from syndesi.protocols.modbus import (
    MAX_ADDRESS,
    DiagnosticsCode,
    DiagnosticsRequestSDU,
    DiagnosticsResponseSDU,
    ExceptionCode,
    ExceptionResponseSDU,
    FunctionCode,
    MaskWriteRegisterRequestSDU,
    MaskWriteRegisterResponseSDU,
    ModbusMultiRegisterValue,
    ReadCoilsRequestSDU,
    ReadFifoQueueRequestSDU,
    ReadFifoQueueResponseSDU,
    ReadFileRecordRequestSDU,
    ReadFileRecordResponseSDU,
    ReadHoldingRegistersRequestSDU,
    ReadHoldingRegistersResponseSDU,
    ReadWriteMultipleRegistersRequestSDU,
    ReportServerIdRequestSDU,
    ReportServerIdResponseSDU,
    WriteFileRecordRequestSDU,
    WriteFileRecordResponseSDU,
    WriteMultipleCoilsRequestSDU,
    WriteMultipleCoilsResponseSDU,
    WriteMultipleRegistersRequestSDU,
    WriteMultipleRegistersResponseSDU,
    WriteSingleCoilRequestSDU,
    WriteSingleCoilResponseSDU,
    WriteSingleRegisterRequestSDU,
    WriteSingleRegisterResponseSDU,
)
from syndesi.tools.errors import ProtocolReadError

# ┌──────────────────────────────┐
# │ Requests built by the client │
# └──────────────────────────────┘


@pytest.mark.parametrize(
    "request_type, args, error",
    [
        (ReadCoilsRequestSDU, (1, 0), "Invalid number of inputs/outputs : 0"),
        (ReadCoilsRequestSDU, (0, 1), "Invalid address : 0"),
        (ReadCoilsRequestSDU, (MAX_ADDRESS, 2), "cannot exceed"),
        (ReadHoldingRegistersRequestSDU, (1, 126), "Invalid number of registers"),
        (WriteSingleRegisterRequestSDU, (1, 0x10000), "Invalid register value"),
        (WriteMultipleRegistersRequestSDU, (1, []), "Empty register list"),
        (WriteMultipleRegistersRequestSDU, (1, [0] * 124), "Cannot set more than"),
        (ReadWriteMultipleRegistersRequestSDU, (1, 0, 1, [0]), "read registers"),
        (ReadWriteMultipleRegistersRequestSDU, (1, 1, 1, []), "write registers"),
        (ReadFileRecordRequestSDU, ([(1, 1, 1)] * 36,), "Number of records"),
        (ReadFileRecordRequestSDU, ([(1, 1, 126)],), "Sum of records lengths"),
    ],
)
def test_invalid_request(request_type, args, error):
    with pytest.raises(ValueError, match=error):
        request_type(*args)


def test_write_file_record_records():
    record = (1, 2, b"\x00\x01")
    assert WriteFileRecordRequestSDU(record).records == [record]
    with pytest.raises(TypeError, match="Invalid records type"):
        WriteFileRecordRequestSDU("record")


# ┌───────────────────────────────┐
# │ Requests received by a server │
# └───────────────────────────────┘


@pytest.mark.parametrize(
    "request_type, sdu, error",
    [
        (WriteSingleCoilRequestSDU, "05 0000 1234", "Invalid coil value"),
        (WriteMultipleCoilsRequestSDU, "0F 0000 0009 01 FF", "Invalid byte count"),
        (WriteMultipleRegistersRequestSDU, "10 0000 0001 03 0000", "Invalid byte count"),
        (ReadWriteMultipleRegistersRequestSDU, "17 0000 0001 0000 0001 03", "Invalid byte count"),
        (ReadFileRecordRequestSDU, "14 06 06 0001 0001 00", "Invalid byte count"),
        (ReadFileRecordRequestSDU, "14 07 05 0001 0001 0001", "Invalid reference type"),
        (WriteFileRecordRequestSDU, "15 08 06 0001 0001 0001", "Invalid byte count"),
        (WriteFileRecordRequestSDU, "15 09 05 0001 0001 0001 0000", "Invalid reference type"),
        (WriteFileRecordRequestSDU, "15 09 06 0001 0001 0002 0000", "exceeds the frame"),
    ],
)
def test_invalid_request_sdu(request_type, sdu, error):
    with pytest.raises(ValueError, match=error):
        request_type.parse_sdu(bytes.fromhex(sdu))


# ┌────────────────────────────────┐
# │ Responses received by a client │
# └────────────────────────────────┘

DIAGNOSTICS = DiagnosticsRequestSDU(DiagnosticsCode.RETURN_QUERY_DATA, b"\x12\x34", 2)


@pytest.mark.parametrize(
    "response_type, request_sdu, sdu, error",
    [
        (ExceptionResponseSDU, ReadCoilsRequestSDU(1, 1), "01 02", "Not an exception"),
        (ExceptionResponseSDU, ReadCoilsRequestSDU(1, 1), "83 02", "for function code 3"),
        (ReadHoldingRegistersResponseSDU, ReadHoldingRegistersRequestSDU(1, 2), "03 02 0001", "Invalid byte count"),
        (WriteSingleCoilResponseSDU, WriteSingleCoilRequestSDU(1, True), "05 0000 0000", "should match query"),
        (WriteSingleRegisterResponseSDU, WriteSingleRegisterRequestSDU(1, 1), "06 0000 0002", "should match query"),
        (MaskWriteRegisterResponseSDU, MaskWriteRegisterRequestSDU(1, 1, 1), "16 0000 0001 0002", "should match query"),
        (DiagnosticsResponseSDU, DIAGNOSTICS, "07 0000 1234", "Invalid returned function code"),
        (DiagnosticsResponseSDU, DIAGNOSTICS, "08 0001 1234", "Invalid returned subfunction code"),
        (WriteMultipleCoilsResponseSDU, WriteMultipleCoilsRequestSDU(1, [True] * 3), "0F 0000 0002", "Number of coils written"),
        (WriteMultipleCoilsResponseSDU, WriteMultipleCoilsRequestSDU(1, [True] * 3), "0F 0001 0003", "Start address mismatch"),
        (WriteMultipleRegistersResponseSDU, WriteMultipleRegistersRequestSDU(1, [0] * 3), "10 0000 0002", "Number of registers written"),
        (WriteMultipleRegistersResponseSDU, WriteMultipleRegistersRequestSDU(1, [0] * 3), "10 0001 0003", "Start address mismatch"),
        (ReportServerIdResponseSDU, ReportServerIdRequestSDU(4, 2), "11 03 0000FF", "Invalid byte count"),
        (ReadFileRecordResponseSDU, ReadFileRecordRequestSDU([(1, 1, 1)]), "14 04 03 05 0001", "Invalid reference type"),
        (WriteFileRecordResponseSDU, WriteFileRecordRequestSDU([(1, 1, b"\x00\x01")]), "15 09 06 0001 0001 0001 0002", "different from query"),
        (ReadFifoQueueResponseSDU, ReadFifoQueueRequestSDU(1), "18 0006 0001 0001 0002", "FIFO count mismatch"),
    ],
)  # fmt: skip
def test_invalid_response_sdu(response_type, request_sdu, sdu, error):
    with pytest.raises(ProtocolReadError, match=error):
        response_type.parse_sdu(bytes.fromhex(sdu), request_sdu)


def test_diagnostics_without_check():
    request = DiagnosticsRequestSDU(
        DiagnosticsCode.RETURN_QUERY_DATA, b"\x12\x34", 2, check_response=False
    )
    response = DiagnosticsResponseSDU.parse_sdu(bytes.fromhex("08 0001 1234"), request)
    assert response.data == b"\x12\x34"


def test_exception_response():
    response = ExceptionResponseSDU(FunctionCode.READ_COILS, ExceptionCode.SERVER_DEVICE_BUSY)
    assert response.make_sdu() == b"\x81\x06"
    assert ExceptionResponseSDU.is_exception(response.make_sdu())
    assert not ExceptionResponseSDU.is_exception(b"\x01\x06")
    assert not ExceptionResponseSDU.is_exception(b"")
    assert response.description == "Server is busy, retry later"
    assert ExceptionResponseSDU(FunctionCode.READ_COILS, 0x42).description == (
        "Unknown exception code"
    )


# ┌───────────────────────┐
# │ Multi register values │
# └───────────────────────┘


@pytest.mark.parametrize("n_registers", [1, 2, 4])
def test_int_values(n_registers):
    assert ModbusMultiRegisterValue.from_int(-2, n_registers).to_int() == -2
    assert ModbusMultiRegisterValue.from_uint(2, n_registers).to_uint() == 2


@pytest.mark.parametrize("word_order", ["big", "little"])
@pytest.mark.parametrize("byte_order", ["big", "little"])
def test_registers(word_order, byte_order):
    registers = [0x0102, 0x0304]
    value = ModbusMultiRegisterValue.from_registers(registers, byte_order, word_order)
    assert value.to_registers() == registers


def test_string_value():
    value = ModbusMultiRegisterValue.from_string("abc", n_registers=3)
    assert value.to_array() == b"abc\0\0\0"
    assert value.to_string() == "abc"
    with pytest.raises(ValueError, match="cannot fit in 1 registers"):
        ModbusMultiRegisterValue.from_string("abc", n_registers=1)


@pytest.mark.parametrize("conversion", ["to_int", "to_uint", "to_float"])
def test_invalid_conversion(conversion):
    value = ModbusMultiRegisterValue.from_array(bytes(6), n_registers=3)
    with pytest.raises(ValueError, match="cannot be converted"):
        getattr(value, conversion)()


def test_invalid_array():
    with pytest.raises(ValueError, match="Cannot fit"):
        ModbusMultiRegisterValue.from_array(bytes(3), n_registers=2)
