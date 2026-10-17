# File : modbus.py
# Author : Sébastien Deriaz
# License : GPL
"""
Modbus implementation : TCP over IP, RTU and ASCII over a serial port
"""

# PDU (Protocol Data Unit) format
#
# Modbus TCP
# ┌────────────────┬─────────────┬────────┬─────────┬───────┐
# │ Transaction ID │ Protocol ID │ Length │ Unit ID │ Data  │
# └────────────────┴─────────────┴────────┴─────────┴───────┘
#       2 bytes        2 bytes     2 bytes   1 byte  N bytes
#
#
# Modbus RTU
# ┌───────────────┬────────┬────────┐
# │ Slave address │  Data  │  CRC   │
# └───────────────┴────────┴────────┘
#      1 byte       N bytes  2 bytes
#
# Modbus ASCII
# ┌────────┬───────────────┬────────┬───────┬─────────┐
# │ HEADER │ Slave address │  Data  │  CRC  │ TRAILER │
# └────────┴───────────────┴────────┴───────┴─────────┘
#   1 byte      1 byte       N bytes 2 bytes   1 byte
#
#
# The PDU is built and parsed by ModbusBackend, each data block (SDU) is constructed
# by its corresponding ModbusRequestSDU class. SDUs are parsed by ModbusResponseSDU
# classes
#
# Framing : the MBAP header carries the length of what follows, so the backend takes
# FragmentSC() and cuts the frames itself from the raw fragments. Stop-conditions
# cannot do it, a single read can bring header and body together

# pylint: disable=too-many-lines

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, IntEnum, StrEnum
from math import ceil
from typing import Any, Generic, TypeVar, cast

from syndesi.adapters.serialport import AsyncSerialPort, SerialPort

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.framer import AdapterReadFrame
from ..adapters.ip import IP, AsyncIP
from ..adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    StopCondition,
    Termination,
)
from ..adapters.utils import TimeoutParameterType, TimeoutType
from ..tools.errors import ProtocolError, ProtocolReadError
from .protocol import AsyncProtocol, BackendOutput, Protocol, ProtocolBackend

MODBUS_TCP_DEFAULT_PORT = 502

MAX_ADDRESS = 0xFFFF
MIN_ADDRESS = 0x0001

MAX_DISCRETE_INPUTS = (
    0x07B0  # 1968. This is to ensure the total PDU length is 255 at most.
)
# This value has been checked and going up to 1976 seems to work but sticking to the
# spec is safer

# Specification says 125, but write_multiple_registers would exceed the allow number
# of bytes in that case
# MAX_NUMBER_OF_REGISTERS = 123

ExceptionCodesType = dict[int, str]


class Endian(StrEnum):
    """
    Endian enum
    """

    BIG = "big"
    LITTLE = "little"


endian_symbol = {Endian.BIG: ">", Endian.LITTLE: "<"}


def _dm_to_pdu_address(dm_address: int) -> int:
    """
    Convert Modbus data model address to Modbus PDU address

    - Modbus data model starts at address 1
    - Modbus PDU addresses start at 0

    Modbus data model is the one specified in the devices datasheets

    Parameters
    ----------
    dm_address : int
    """
    return dm_address - 1


def _pdu_to_dm_address(pdu_address: int) -> int:
    """
    Convert Modbus PDU address to Modbus data model address

    - Modbus data model starts at address 1
    - Modbus PDU addresses start at 0

    Modbus data model is the one specified in the devices datasheets

    Parameters
    ----------
    pdu_address : int
    """
    return pdu_address + 1


def _check_discrete_input_output_count(discrete_inputs: int) -> None:
    if not 1 <= discrete_inputs <= MAX_DISCRETE_INPUTS:
        raise ValueError(
            f"Invalid number of inputs/outputs : {discrete_inputs}, it must be in "
            f"the range [1, {MAX_DISCRETE_INPUTS}]"
        )


def _check_address(address: int, max_address: int | None = None) -> None:
    if not MIN_ADDRESS <= address <= MAX_ADDRESS:
        raise ValueError(
            f"Invalid address : {address}, it must be in the range "
            f"[{MIN_ADDRESS},{MAX_ADDRESS}]"
        )

    if max_address is not None:
        if address > max_address:
            raise ValueError(
                f"Invalid address : {address}, it cannot exceed {max_address}"
                " in the current context"
            )


ENDIAN = endian_symbol[Endian.BIG]

# TCP
# 7 bytes + PDU
# RTU
# 1 byte + PDU + 2 bytes
# Worst case is 255 - 7 bytes = 248 bytes

# Size limitation only apply to Modbus RTU
AVAILABLE_PDU_SIZE = 255 - 3

_ASCII_HEADER = b":"
_PROTOCO_ID = 0
_UNIT_ID = 0
_ASCII_TRAILER = b"\r\n"


class ModbusSerialType(StrEnum):
    """
    Modbus type over serial

    - RTU : Modbus over serial
    - ASCII : Modbus using text based encoding
    """

    RTU = "RTU"
    ASCII = "ASCII"


class FunctionCode(IntEnum):
    """
    Modbus function codes enum
    """

    # Public function codes 1 to 64
    READ_COILS = 0x01
    READ_DISCRETE_INPUTS = 0x02
    READ_HOLDING_REGISTERS = 0x03
    READ_INPUT_REGISTERS = 0x04
    WRITE_SINGLE_COIL = 0x05
    WRITE_SINGLE_REGISTER = 0x06
    READ_EXCEPTION_STATUS = 0x07  # Serial only
    DIAGNOSTICS = 0x08  # Serial only
    GET_COMM_EVENT_COUNTER = 0x0B  # Serial only
    GET_COMM_EVENT_LOG = 0x0C  # Serial only
    WRITE_MULTIPLE_COILS = 0x0F
    WRITE_MULTIPLE_REGISTERS = 0x10
    REPORT_SERVER_ID = 0x11  # Serial only
    READ_FILE_RECORD = 0x14
    WRITE_FILE_RECORD = 0x15
    MASK_WRITE_REGISTER = 0x16
    READ_WRITE_MULTIPLE_REGISTERS = 0x17
    READ_FIFO_QUEUE = 0x18
    ENCAPSULATED_INTERFACE_TRANSPORT = 0x2B
    # User defined function codes 65 to 72
    # Public function codes 73 to 99
    # User defined function codes 100 to 110
    # Public function codes 111 to 127


class DiagnosticsCode(Enum):
    """
    Modbus Diagnostics codes enum
    """

    RETURN_QUERY_DATA = 0x00
    RESTART_COMMUNICATIONS_OPTION = 0x01
    RETURN_DIAGNOSTIC_REGISTER = 0x02
    CHANGE_ASCII_INPUT_DELIMITER = 0x03
    FORCE_LISTEN_ONLY_MODE = 0x04
    # Reserved 0x05 to 0x09
    CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER = 0x0A
    RETURN_BUS_MESSAGE_COUNT = 0x0B
    RETURN_BUS_COMMUNICATION_ERROR_COUNT = 0x0C
    RETURN_BUS_EXCEPTION_ERROR_COUNT = 0x0D
    RETURN_SERVER_MESSAGE_COUNT = 0x0E
    RETURN_SERVER_NO_RESPONSE_COUNT = 0x0F
    RETURN_SERVER_NAK_COUNT = 0x10
    RETURN_SERVER_BUSY_COUNT = 0x11
    RETURN_BUS_CHARACTER_OVERRUN_COUNT = 0x12
    # Reserved 0x13
    CLEAR_OVERRUN_COUNTER_AND_FLAG = 0x14
    # Reserved 0x15 to 0xFF


class EncapsulatedInterfaceTransportSubFunctionCodes(Enum):
    """
    Encapsulated interface transport subfunction codes enum
    """

    CANOPEN_GENERAL_REFERENCE_REQUEST_AND_RESPONSE_PDU = 0x0D
    READ_DEVICE_IDENTIFICATION = 0x0E


class DeviceIndentificationObjects(Enum):
    """
    Device identification objects enum
    """

    VENDOR_NAME = 0x00
    PRODUCT_CODE = 0x01
    MAJOR_MINOR_REVISION = 0x02
    VENDOR_URL = 0x03
    PRODUCT_NAME = 0x04
    MODEL_NAME = 0x05
    USER_APPLICATION_NAME = 0x06
    # Reserved 0x07 to 0x7F
    # Private objects 0x80 to 0xFF


SERIAL_LINE_ONLY_CODES = [
    FunctionCode.DIAGNOSTICS,
    FunctionCode.GET_COMM_EVENT_COUNTER,
    FunctionCode.REPORT_SERVER_ID,
    FunctionCode.READ_EXCEPTION_STATUS,
]


def bool_list_to_bytes(lst: list[bool]) -> bytes:
    """
    Convert a list of bool to bytes, LSB first
    """
    byte_count = ceil(len(lst) / 8)
    result: bytes = sum(2**i * int(v) for i, v in enumerate(lst)).to_bytes(
        byte_count, byteorder="little"
    )
    return result


def bytes_to_bool_list(_bytes: bytes, n: int) -> list[bool]:
    """
    Convert bytes to a list of bool, one per bit, LSB first
    """
    return [c == "1" for c in "".join([f"{x:08b}"[::-1] for x in _bytes])][:n]


class ModbusError(Exception):
    """
    Generic modbus exception
    """


def modbus_crc(_bytes: bytes) -> int:
    """
    CRC-16/MODBUS of the given buffer

    Reflected polynomial 0xA001, initial value 0xFFFF. On the wire the result travels
    low byte first, which is why it is packed little endian and not with ENDIAN
    """
    crc = 0xFFFF
    for byte in _bytes:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def modbus_lrc(_bytes: bytes) -> int:
    """
    LRC of the given buffer, the check used by Modbus ASCII

    Two's complement of the sum of every byte, truncated to 8 bits
    """
    return (-sum(_bytes)) & 0xFF


def _ascii_frame(slave_address: int, sdu: bytes) -> bytes:
    """``:`` then the frame and its LRC as uppercase hex, then CRLF"""
    frame = struct.pack(ENDIAN + "B", slave_address) + sdu
    body = frame + struct.pack(ENDIAN + "B", modbus_lrc(frame))
    return _ASCII_HEADER + body.hex().upper().encode("ascii") + _ASCII_TRAILER


class ModbusSDU:
    """
    Modbus Service Data Unit

    Subclasses of this contain either request or response fields to a modbus
    frame
    """
    function_code: FunctionCode

    # def make_sdu(self) -> bytes:
    #     """Generate a bytes array containing the SDU"""
    #     raise ProtocolError("make_sdu() is not supported for this SDU")

    # def parse_sdu(self, sdu: bytes) -> ModbusSDU:
    #     """Generate a ModbusSDU instance from a given sdu buffer"""
    #     raise ProtocolError("parse_sdu() is not supported for this SDU")

    # def exceptions(self) -> dict[int, str]:
    #     """Return a dictionary of exceptions based on their integer code"""
    #     return {}

    @abstractmethod
    def make_sdu(self) -> bytes:
        ...    

    # @abstractmethod
    # def exceptions(self) -> dict[int, str]:
    #     """Return a dictionary of exceptions based on their integer code"""

    # @property
    # @abstractmethod
    # def function_code(self) -> FunctionCode:
    #     """Return the function code of this modbus request"""

    # def _check_for_error(self, sdu: bytes) -> None:
    #     """Check the given sdu buffer for an exception"""
    #     _raise_if_error(sdu, self.exceptions())

class ModbusRequestSDU(ModbusSDU):
    """
    Base class for modbus request SDUs (Service Data Unit)
    """
    @staticmethod
    @abstractmethod
    def parse_sdu(sdu: bytes) -> ModbusRequestSDU:
        """Generate a ModbusSDU instance from a given sdu buffer"""

RequestT = TypeVar("RequestT", bound=ModbusRequestSDU)
class ModbusResponseSDU(Generic[RequestT], ModbusSDU):
    """
    Base class for modbus response SDUs (Service Data Unit)
    """
    @staticmethod
    @abstractmethod
    def parse_sdu(sdu: bytes, request : RequestT) -> ModbusResponseSDU[RequestT]:
        """Generate a ModbusSDU instance from a given sdu buffer"""

class SerialLineOnlySDU(ModbusRequestSDU, ABC):
    """
    Marker class for serial line only Modbus function codes
    """


class ExceptionCode(IntEnum):
    """
    Modbus exception codes, shared by every function code
    """

    ILLEGAL_FUNCTION = 0x01
    ILLEGAL_DATA_ADDRESS = 0x02
    ILLEGAL_DATA_VALUE = 0x03
    SERVER_DEVICE_FAILURE = 0x04
    ACKNOWLEDGE = 0x05
    SERVER_DEVICE_BUSY = 0x06
    MEMORY_PARITY_ERROR = 0x08
    GATEWAY_PATH_UNAVAILABLE = 0x0A
    GATEWAY_TARGET_DEVICE_FAILED_TO_RESPOND = 0x0B


_EXCEPTION_DESCRIPTIONS = {
    ExceptionCode.ILLEGAL_FUNCTION: "Function code not supported",
    ExceptionCode.ILLEGAL_DATA_ADDRESS: "Invalid data address",
    ExceptionCode.ILLEGAL_DATA_VALUE: "Invalid data value",
    ExceptionCode.SERVER_DEVICE_FAILURE: "Unrecoverable error on the server",
    ExceptionCode.ACKNOWLEDGE: "Request accepted, processing takes a long time",
    ExceptionCode.SERVER_DEVICE_BUSY: "Server is busy, retry later",
    ExceptionCode.MEMORY_PARITY_ERROR: "Memory parity error in the record file",
    ExceptionCode.GATEWAY_PATH_UNAVAILABLE: "Gateway path unavailable",
    ExceptionCode.GATEWAY_TARGET_DEVICE_FAILED_TO_RESPOND: (
        "Gateway target device failed to respond"
    ),
}

# Set on the function code of an exception response
EXCEPTION_FLAG = 0x80


@dataclass
class ExceptionResponseSDU(ModbusResponseSDU[ModbusRequestSDU]):
    """
    Exception response, the answer to any request the server couldn't handle

    function_code is the one of the request, without the exception flag. exception_code
    is kept as an int, devices are free to use non standard codes
    """

    function_code: FunctionCode
    exception_code: int

    @property
    def description(self) -> str:
        """Human readable description of the exception code"""
        if self.exception_code in _EXCEPTION_DESCRIPTIONS:
            return _EXCEPTION_DESCRIPTIONS[ExceptionCode(self.exception_code)]
        return "Unknown exception code"

    @staticmethod
    def is_exception(sdu: bytes) -> bool:
        """True if the given sdu buffer is an exception response"""
        return len(sdu) > 0 and bool(sdu[0] & EXCEPTION_FLAG)

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BB", self.function_code | EXCEPTION_FLAG, self.exception_code
        )

    @staticmethod
    def parse_sdu(sdu: bytes, request: ModbusRequestSDU) -> ExceptionResponseSDU:
        function_code, exception_code = struct.unpack(ENDIAN + "BB", sdu)
        if not function_code & EXCEPTION_FLAG:
            raise ProtocolReadError(f"Not an exception response : {sdu!r}")
        if function_code & ~EXCEPTION_FLAG != request.function_code:
            raise ProtocolReadError(
                f"Exception response for function code {function_code & ~EXCEPTION_FLAG}"
                f", expected {request.function_code}"
            )
        return ExceptionResponseSDU(request.function_code, exception_code)

# Read Coils - 0x01
@dataclass
class ReadCoilsRequestSDU(ModbusRequestSDU):
    """Read coils request"""

    function_code = FunctionCode.READ_COILS
    start_address: int
    number_of_coils: int

    def __post_init__(self) -> None:
        _check_discrete_input_output_count(self.number_of_coils)
        _check_address(self.start_address, MAX_ADDRESS - self.number_of_coils + 1)

    def make_sdu(self) -> bytes:
        data = struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            self.number_of_coils,
        )
        return data

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadCoilsRequestSDU:
        _, start_address, number_of_coils = struct.unpack(ENDIAN + "BHH", sdu)
        return ReadCoilsRequestSDU(_pdu_to_dm_address(start_address), number_of_coils)


@dataclass
class ReadCoilsResponseSDU(ModbusResponseSDU[ReadCoilsRequestSDU]):
    """Read coils response"""

    function_code = FunctionCode.READ_COILS
    coils: list[bool]

    def make_sdu(self) -> bytes:
        coil_bytes = bool_list_to_bytes(self.coils)
        return struct.pack(
            ENDIAN + f"BB{len(coil_bytes)}s",
            self.function_code,
            len(coil_bytes),
            coil_bytes,
        )

    @staticmethod
    def parse_sdu(sdu: bytes, request: ReadCoilsRequestSDU) -> ReadCoilsResponseSDU:
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        coil_bytes = struct.unpack(ENDIAN + f"{byte_count}s", sdu[2:])[0]
        # The count is only in the request, the last byte is padded with zeros
        coils = bytes_to_bool_list(coil_bytes, request.number_of_coils)
        return ReadCoilsResponseSDU(coils)


# Read discrete inputs - 0x02
@dataclass
class ReadDiscreteInputsRequestSDU(ModbusRequestSDU):
    """Read discrete inputs request"""

    function_code = FunctionCode.READ_DISCRETE_INPUTS
    start_address: int
    number_of_inputs: int

    def __post_init__(self) -> None:
        _check_discrete_input_output_count(self.number_of_inputs)
        _check_address(self.start_address, MAX_ADDRESS - self.number_of_inputs + 1)

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            self.number_of_inputs,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadDiscreteInputsRequestSDU:
        _, start_address, number_of_inputs = struct.unpack(ENDIAN + "BHH", sdu)
        return ReadDiscreteInputsRequestSDU(
            _pdu_to_dm_address(start_address), number_of_inputs
        )


@dataclass
class ReadDiscreteInputsResponseSDU(
    ModbusResponseSDU[ReadDiscreteInputsRequestSDU]
):
    """Read discrete inputs response"""

    function_code = FunctionCode.READ_DISCRETE_INPUTS
    inputs: list[bool]

    def make_sdu(self) -> bytes:
        input_bytes = bool_list_to_bytes(self.inputs)
        return struct.pack(
            ENDIAN + f"BB{len(input_bytes)}s",
            self.function_code,
            len(input_bytes),
            input_bytes,
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReadDiscreteInputsRequestSDU
    ) -> ReadDiscreteInputsResponseSDU:
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        data = struct.unpack(ENDIAN + f"{byte_count}s", sdu[2:])[0]
        inputs = bytes_to_bool_list(data, request.number_of_inputs)
        return ReadDiscreteInputsResponseSDU(inputs)


# Shared by read holding registers (0x03) and read input registers (0x04)
def _check_read_registers(start_address: int, n_registers: int) -> None:
    _check_address(start_address, MAX_ADDRESS - n_registers + 1)

    max_number_of_registers = (AVAILABLE_PDU_SIZE - 2) // 2

    if not 1 <= n_registers <= max_number_of_registers:
        raise ValueError(f"Invalid number of registers : {n_registers}")


def _pack_registers_response(function_code: FunctionCode, registers: list[int]) -> bytes:
    return struct.pack(
        ENDIAN + f"BB{len(registers)}H",
        function_code,
        len(registers) * 2,
        *registers,
    )


def _unpack_registers_response(sdu: bytes, n_registers: int) -> list[int]:
    _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
    if byte_count != n_registers * 2:
        raise ProtocolReadError(
            f"Invalid byte count : {byte_count}, expected {n_registers * 2}"
        )
    return list(struct.unpack(ENDIAN + f"{n_registers}H", sdu[2:]))


# Read holding registers - 0x03
@dataclass
class ReadHoldingRegistersRequestSDU(ModbusRequestSDU):
    """Read holding registers request"""

    function_code = FunctionCode.READ_HOLDING_REGISTERS
    start_address: int
    n_registers: int

    def __post_init__(self) -> None:
        _check_read_registers(self.start_address, self.n_registers)

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            self.n_registers,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadHoldingRegistersRequestSDU:
        _, start_address, n_registers = struct.unpack(ENDIAN + "BHH", sdu)
        return ReadHoldingRegistersRequestSDU(
            _pdu_to_dm_address(start_address), n_registers
        )


@dataclass
class ReadHoldingRegistersResponseSDU(
    ModbusResponseSDU[ReadHoldingRegistersRequestSDU]
):
    """Read holding registers response"""

    function_code = FunctionCode.READ_HOLDING_REGISTERS
    registers: list[int]

    def make_sdu(self) -> bytes:
        return _pack_registers_response(self.function_code, self.registers)

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReadHoldingRegistersRequestSDU
    ) -> ReadHoldingRegistersResponseSDU:
        return ReadHoldingRegistersResponseSDU(
            _unpack_registers_response(sdu, request.n_registers)
        )


# Read input registers - 0x04
@dataclass
class ReadInputRegistersRequestSDU(ModbusRequestSDU):
    """Read input registers request"""

    function_code = FunctionCode.READ_INPUT_REGISTERS
    start_address: int
    n_registers: int

    def __post_init__(self) -> None:
        _check_read_registers(self.start_address, self.n_registers)

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            self.n_registers,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadInputRegistersRequestSDU:
        _, start_address, n_registers = struct.unpack(ENDIAN + "BHH", sdu)
        return ReadInputRegistersRequestSDU(
            _pdu_to_dm_address(start_address), n_registers
        )


@dataclass
class ReadInputRegistersResponseSDU(ModbusResponseSDU[ReadInputRegistersRequestSDU]):
    """Read input registers response"""

    function_code = FunctionCode.READ_INPUT_REGISTERS
    registers: list[int]

    def make_sdu(self) -> bytes:
        return _pack_registers_response(self.function_code, self.registers)

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReadInputRegistersRequestSDU
    ) -> ReadInputRegistersResponseSDU:
        return ReadInputRegistersResponseSDU(
            _unpack_registers_response(sdu, request.n_registers)
        )


# Write single coil - 0x05
_COIL_ON_VALUE = 0xFF00
_COIL_OFF_VALUE = 0x0000


def _pack_single_coil(function_code: FunctionCode, address: int, status: bool) -> bytes:
    return struct.pack(
        ENDIAN + "BHH",
        function_code,
        _dm_to_pdu_address(address),
        _COIL_ON_VALUE if status else _COIL_OFF_VALUE,
    )


def _unpack_single_coil(sdu: bytes) -> tuple[int, bool]:
    _, address, value = struct.unpack(ENDIAN + "BHH", sdu)
    if value not in (_COIL_ON_VALUE, _COIL_OFF_VALUE):
        raise ValueError(f"Invalid coil value : {value:04X}")
    return _pdu_to_dm_address(address), value == _COIL_ON_VALUE


@dataclass
class WriteSingleCoilRequestSDU(ModbusRequestSDU):
    """Write single coil request"""

    function_code = FunctionCode.WRITE_SINGLE_COIL
    address: int
    status: bool

    def __post_init__(self) -> None:
        _check_address(self.address)

    def make_sdu(self) -> bytes:
        return _pack_single_coil(self.function_code, self.address, self.status)

    @staticmethod
    def parse_sdu(sdu: bytes) -> WriteSingleCoilRequestSDU:
        return WriteSingleCoilRequestSDU(*_unpack_single_coil(sdu))


@dataclass
class WriteSingleCoilResponseSDU(ModbusResponseSDU[WriteSingleCoilRequestSDU]):
    """Write single coil response, echo of the request"""

    function_code = FunctionCode.WRITE_SINGLE_COIL
    address: int
    status: bool

    def make_sdu(self) -> bytes:
        return _pack_single_coil(self.function_code, self.address, self.status)

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: WriteSingleCoilRequestSDU
    ) -> WriteSingleCoilResponseSDU:
        if sdu != request.make_sdu():
            raise ProtocolReadError(
                f"Response ({sdu!r}) should match query ({request.make_sdu()!r})"
            )
        return WriteSingleCoilResponseSDU(*_unpack_single_coil(sdu))


# Write single register - 0x06
@dataclass
class WriteSingleRegisterRequestSDU(ModbusRequestSDU):
    """Write single register request"""

    function_code = FunctionCode.WRITE_SINGLE_REGISTER
    address: int
    value: int

    def __post_init__(self) -> None:
        _check_address(self.address)
        if not 0 <= self.value <= 0xFFFF:
            raise ValueError(f"Invalid register value : {self.value}")

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.address),
            self.value,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> WriteSingleRegisterRequestSDU:
        _, address, value = struct.unpack(ENDIAN + "BHH", sdu)
        return WriteSingleRegisterRequestSDU(_pdu_to_dm_address(address), value)


@dataclass
class WriteSingleRegisterResponseSDU(
    ModbusResponseSDU[WriteSingleRegisterRequestSDU]
):
    """Write single register response, echo of the request"""

    function_code = FunctionCode.WRITE_SINGLE_REGISTER
    address: int
    value: int

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.address),
            self.value,
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: WriteSingleRegisterRequestSDU
    ) -> WriteSingleRegisterResponseSDU:
        if sdu != request.make_sdu():
            raise ProtocolReadError(
                f"Response ({sdu!r}) should match query ({request.make_sdu()!r})"
            )
        _, address, value = struct.unpack(ENDIAN + "BHH", sdu)
        return WriteSingleRegisterResponseSDU(_pdu_to_dm_address(address), value)


# Read exception status - 0x07 (serial only)
@dataclass
class ReadExceptionStatusRequestSDU(SerialLineOnlySDU):
    """Read exception status request (serial only)"""

    function_code = FunctionCode.READ_EXCEPTION_STATUS

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code)

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadExceptionStatusRequestSDU:
        struct.unpack(ENDIAN + "B", sdu)
        return ReadExceptionStatusRequestSDU()


@dataclass
class ReadExceptionStatusResponseSDU(ModbusResponseSDU[ReadExceptionStatusRequestSDU]):
    """Read exception status response (serial only)"""

    function_code = FunctionCode.READ_EXCEPTION_STATUS
    status: int

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "BB", self.function_code, self.status)

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReadExceptionStatusRequestSDU
    ) -> ReadExceptionStatusResponseSDU:
        _, status = cast(tuple[int, int], struct.unpack(ENDIAN + "BB", sdu))
        return ReadExceptionStatusResponseSDU(status)


# Diagnostics - 0x08 (serial only)
@dataclass
class DiagnosticsRequestSDU(SerialLineOnlySDU):
    """Diagnostics request (serial only)"""

    function_code = FunctionCode.DIAGNOSTICS
    code: DiagnosticsCode
    subfunction_data: bytes
    # Client side only, how to read the answer. Not on the wire
    return_subfunction_bytes: int
    check_response: bool = True

    def make_sdu(self) -> bytes:
        return (
            struct.pack(ENDIAN + "BH", self.function_code, self.code.value)
            + self.subfunction_data
        )

    @staticmethod
    def parse_sdu(sdu: bytes) -> DiagnosticsRequestSDU:
        _, subfunction = struct.unpack(ENDIAN + "BH", sdu[:3])
        subfunction_data = sdu[3:]
        # Most sub-functions answer with as many bytes as they were given
        return DiagnosticsRequestSDU(
            DiagnosticsCode(subfunction), subfunction_data, len(subfunction_data)
        )


@dataclass
class DiagnosticsResponseSDU(ModbusResponseSDU[DiagnosticsRequestSDU]):
    """Diagnostics response (serial only)"""

    function_code = FunctionCode.DIAGNOSTICS
    code: DiagnosticsCode
    data: bytes

    def make_sdu(self) -> bytes:
        return (
            struct.pack(ENDIAN + "BH", self.function_code, self.code.value) + self.data
        )

    @staticmethod
    def parse_sdu(sdu: bytes, request: DiagnosticsRequestSDU) -> DiagnosticsResponseSDU:
        n = request.return_subfunction_bytes
        returned_function, returned_subfunction, data = cast(
            tuple[int, int, bytes],
            struct.unpack(ENDIAN + f"BH{n}s", sdu),
        )

        if request.check_response:
            if returned_function != request.function_code:
                raise ProtocolReadError(
                    f"Invalid returned function code : {returned_function}"
                )
            if returned_subfunction != request.code.value:
                raise ProtocolReadError(
                    f"Invalid returned subfunction code : {returned_subfunction}"
                )

        return DiagnosticsResponseSDU(request.code, data)


# Get comm event counter - 0x0B (serial only)
@dataclass
class GetCommEventCounterRequestSDU(SerialLineOnlySDU):
    """Get communication event counter request (serial only)"""

    function_code = FunctionCode.GET_COMM_EVENT_COUNTER

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code)

    @staticmethod
    def parse_sdu(sdu: bytes) -> GetCommEventCounterRequestSDU:
        struct.unpack(ENDIAN + "B", sdu)
        return GetCommEventCounterRequestSDU()


@dataclass
class GetCommEventCounterResponseSDU(ModbusResponseSDU[GetCommEventCounterRequestSDU]):
    """Get communication event counter response (serial only)"""

    function_code = FunctionCode.GET_COMM_EVENT_COUNTER
    status: int
    event_count: int

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BHH", self.function_code, self.status, self.event_count
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: GetCommEventCounterRequestSDU
    ) -> GetCommEventCounterResponseSDU:
        _, status, event_count = struct.unpack(ENDIAN + "BHH", sdu)
        return GetCommEventCounterResponseSDU(status, event_count)


# Get comm event log - 0x0C (serial only)
@dataclass
class GetCommEventLogRequestSDU(SerialLineOnlySDU):
    """Get communication event log request (serial only)"""

    function_code = FunctionCode.GET_COMM_EVENT_LOG

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code)

    @staticmethod
    def parse_sdu(sdu: bytes) -> GetCommEventLogRequestSDU:
        struct.unpack(ENDIAN + "B", sdu)
        return GetCommEventLogRequestSDU()


@dataclass
class GetCommEventLogResponseSDU(ModbusResponseSDU[GetCommEventLogRequestSDU]):
    """Get communication event log response (serial only)"""

    function_code = FunctionCode.GET_COMM_EVENT_LOG
    status: int
    event_count: int
    message_count: int
    events: bytes

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + f"BBHHH{len(self.events)}s",
            self.function_code,
            6 + len(self.events),
            self.status,
            self.event_count,
            self.message_count,
            self.events,
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: GetCommEventLogRequestSDU
    ) -> GetCommEventLogResponseSDU:
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        status, event_count, message_count = struct.unpack(ENDIAN + "HHH", sdu[2:8])
        events = sdu[8 : 8 + (byte_count - 6)]
        return GetCommEventLogResponseSDU(status, event_count, message_count, events)


# Write multiple coils - 0x0F
@dataclass
class WriteMultipleCoilsRequestSDU(ModbusRequestSDU):
    """Write multiple coils request"""

    function_code = FunctionCode.WRITE_MULTIPLE_COILS
    start_address: int
    values: list[bool]

    def __post_init__(self) -> None:
        number_of_coils = len(self.values)
        _check_discrete_input_output_count(number_of_coils)
        _check_address(self.start_address, MAX_ADDRESS - number_of_coils + 1)

    def make_sdu(self) -> bytes:
        number_of_coils = len(self.values)
        byte_count = ceil(number_of_coils / 8)
        sdu = struct.pack(
            ENDIAN + f"BHHB{byte_count}s",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            number_of_coils,
            byte_count,
            bool_list_to_bytes(self.values),
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> WriteMultipleCoilsRequestSDU:
        _, start_address, number_of_coils, byte_count = struct.unpack(
            ENDIAN + "BHHB", sdu[:6]
        )
        if byte_count != ceil(number_of_coils / 8):
            raise ValueError(
                f"Invalid byte count : {byte_count} for {number_of_coils} coils"
            )
        coil_bytes = struct.unpack(ENDIAN + f"{byte_count}s", sdu[6:])[0]
        return WriteMultipleCoilsRequestSDU(
            _pdu_to_dm_address(start_address),
            bytes_to_bool_list(coil_bytes, number_of_coils),
        )


@dataclass
class WriteMultipleCoilsResponseSDU(ModbusResponseSDU[WriteMultipleCoilsRequestSDU]):
    """Write multiple coils response"""

    function_code = FunctionCode.WRITE_MULTIPLE_COILS
    start_address: int
    number_of_coils: int

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            self.number_of_coils,
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: WriteMultipleCoilsRequestSDU
    ) -> WriteMultipleCoilsResponseSDU:
        _, start_address, coils_written = struct.unpack(ENDIAN + "BHH", sdu)
        if coils_written != len(request.values):
            raise ProtocolReadError(
                f"Number of coils written ({coils_written}) doesn't match expected "
                f"value : {len(request.values)}"
            )
        if start_address != _dm_to_pdu_address(request.start_address):
            raise ProtocolReadError(
                f"Start address mismatch : {start_address} != "
                f"{_dm_to_pdu_address(request.start_address)}"
            )
        return WriteMultipleCoilsResponseSDU(
            _pdu_to_dm_address(start_address), coils_written
        )


# Write multiple registers - 0x10
@dataclass
class WriteMultipleRegistersRequestSDU(ModbusRequestSDU):
    """Write multiple registers request"""

    function_code = FunctionCode.WRITE_MULTIPLE_REGISTERS
    start_address: int
    values: list[int]

    def __post_init__(self) -> None:
        max_number_of_registers = (AVAILABLE_PDU_SIZE - 6) // 2

        if len(self.values) == 0:
            raise ValueError("Empty register list")

        if len(self.values) > max_number_of_registers:
            raise ValueError(
                f"Cannot set more than {max_number_of_registers} registers at a time"
            )

        _check_address(self.start_address, MAX_ADDRESS - len(self.values) + 1)

    def make_sdu(self) -> bytes:
        byte_count = 2 * len(self.values)
        sdu = struct.pack(
            ENDIAN + f"BHHB{byte_count // 2}H",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            byte_count // 2,
            byte_count,
            *self.values,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> WriteMultipleRegistersRequestSDU:
        _, start_address, number_of_registers, byte_count = struct.unpack(
            ENDIAN + "BHHB", sdu[:6]
        )
        if byte_count != 2 * number_of_registers:
            raise ValueError(
                f"Invalid byte count : {byte_count} for {number_of_registers} registers"
            )
        values = list(struct.unpack(ENDIAN + f"{number_of_registers}H", sdu[6:]))
        return WriteMultipleRegistersRequestSDU(
            _pdu_to_dm_address(start_address), values
        )


@dataclass
class WriteMultipleRegistersResponseSDU(
    ModbusResponseSDU[WriteMultipleRegistersRequestSDU]
):
    """Write multiple registers response"""

    function_code = FunctionCode.WRITE_MULTIPLE_REGISTERS
    start_address: int
    number_of_registers: int

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BHH",
            self.function_code,
            _dm_to_pdu_address(self.start_address),
            self.number_of_registers,
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: WriteMultipleRegistersRequestSDU
    ) -> WriteMultipleRegistersResponseSDU:
        _, start_address, registers_written = struct.unpack(ENDIAN + "BHH", sdu)
        if registers_written != len(request.values):
            raise ProtocolReadError(
                f"Number of registers written ({registers_written}) doesn't match "
                f"expected value : {len(request.values)}"
            )
        if start_address != _dm_to_pdu_address(request.start_address):
            raise ProtocolReadError(
                f"Start address mismatch : {start_address} != "
                f"{_dm_to_pdu_address(request.start_address)}"
            )
        return WriteMultipleRegistersResponseSDU(
            _pdu_to_dm_address(start_address), registers_written
        )


# Report server ID - 0x11 (serial only)
@dataclass
class ReportServerIdRequestSDU(SerialLineOnlySDU):
    """Report server ID request (serial only)"""

    function_code = FunctionCode.REPORT_SERVER_ID
    # Client side only, how to cut the answer (device specific). Not on the wire
    server_id_length: int
    additional_data_length: int

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code)

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReportServerIdRequestSDU:
        struct.unpack(ENDIAN + "B", sdu)
        # The lengths aren't on the wire, a server doesn't need them
        return ReportServerIdRequestSDU(server_id_length=0, additional_data_length=0)


@dataclass
class ReportServerIdResponseSDU(ModbusResponseSDU[ReportServerIdRequestSDU]):
    """Report server ID response (serial only)"""

    function_code = FunctionCode.REPORT_SERVER_ID
    server_id: bytes
    run_indicator_status: bool
    additional_data: bytes

    _RUN_INDICATOR_ON = 0xFF
    _RUN_INDICATOR_OFF = 0x00

    def make_sdu(self) -> bytes:
        byte_count = len(self.server_id) + 1 + len(self.additional_data)
        return (
            struct.pack(ENDIAN + "BB", self.function_code, byte_count)
            + self.server_id
            + struct.pack(
                ENDIAN + "B",
                (
                    self._RUN_INDICATOR_ON
                    if self.run_indicator_status
                    else self._RUN_INDICATOR_OFF
                ),
            )
            + self.additional_data
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReportServerIdRequestSDU
    ) -> ReportServerIdResponseSDU:
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        expected = request.server_id_length + 1 + request.additional_data_length
        if byte_count != expected:
            raise ProtocolReadError(
                f"Invalid byte count : {byte_count}, expected {expected}"
            )
        start = 2
        end = start + request.server_id_length
        server_id = sdu[start:end]
        run_indicator_status = sdu[end] == ReportServerIdResponseSDU._RUN_INDICATOR_ON
        additional_data = sdu[end + 1 : end + 1 + request.additional_data_length]
        return ReportServerIdResponseSDU(
            server_id, run_indicator_status, additional_data
        )


# Read file record - 0x14
_FILE_RECORD_REFERENCE_TYPE = 6


@dataclass
class ReadFileRecordRequestSDU(ModbusRequestSDU):
    """Read file record request, records are (file number, record number, length)"""

    function_code = FunctionCode.READ_FILE_RECORD
    records: list[tuple[int, int, int]]

    def __post_init__(self) -> None:
        size_limit = 253
        query_size = 2 + 7 * len(self.records)
        response_size = 2 + len(self.records) + sum(2 * r[2] for r in self.records)
        if query_size > size_limit:
            raise ValueError(f"Number of records is too high : {len(self.records)}")
        if response_size > size_limit:
            raise ValueError(
                f"Sum of records lengths is too high : {sum(r[2] for r in self.records)}"
            )

    def make_sdu(self) -> bytes:
        sub_req_buffer = b""
        for file_number, record_number, record_length in self.records:
            sub_req_buffer += struct.pack(
                ENDIAN + "BHHH",
                _FILE_RECORD_REFERENCE_TYPE,
                file_number,
                record_number,
                record_length,
            )

        byte_count = len(sub_req_buffer)
        sdu = struct.pack(
            ENDIAN + f"BB{byte_count}s",
            self.function_code,
            byte_count,
            sub_req_buffer,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadFileRecordRequestSDU:
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        if byte_count % 7 != 0 or len(sdu) != 2 + byte_count:
            raise ValueError(f"Invalid byte count : {byte_count}")
        records: list[tuple[int, int, int]] = []
        for (
            reference_type,
            file_number,
            record_number,
            record_length,
        ) in struct.iter_unpack(ENDIAN + "BHHH", sdu[2:]):
            if reference_type != _FILE_RECORD_REFERENCE_TYPE:
                raise ValueError(f"Invalid reference type : {reference_type}")
            records.append((file_number, record_number, record_length))
        return ReadFileRecordRequestSDU(records)


@dataclass
class ReadFileRecordResponseSDU(ModbusResponseSDU[ReadFileRecordRequestSDU]):
    """Read file record response"""

    function_code = FunctionCode.READ_FILE_RECORD
    records_data: list[bytes]

    def make_sdu(self) -> bytes:
        sub_resp_buffer = b""
        for data in self.records_data:
            sub_resp_buffer += (
                struct.pack(ENDIAN + "BB", len(data) + 1, _FILE_RECORD_REFERENCE_TYPE)
                + data
            )
        return (
            struct.pack(ENDIAN + "BB", self.function_code, len(sub_resp_buffer))
            + sub_resp_buffer
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReadFileRecordRequestSDU
    ) -> ReadFileRecordResponseSDU:
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        records_data: list[bytes] = []
        offset = 2
        end = 2 + byte_count
        while offset < end:
            length = sdu[offset]
            reference_type = sdu[offset + 1]
            if reference_type != _FILE_RECORD_REFERENCE_TYPE:
                raise ProtocolReadError(f"Invalid reference type : {reference_type}")
            data_start = offset + 2
            data_end = data_start + length - 1
            records_data.append(sdu[data_start:data_end])
            offset = data_end

        return ReadFileRecordResponseSDU(records_data)


# Write file record - 0x15
def _pack_write_file_record(
    function_code: FunctionCode, records: list[tuple[int, int, bytes]]
) -> bytes:
    sub_req_buffer = b""

    for file_number, record_number, data in records:
        sub_req_buffer += struct.pack(
            ENDIAN + f"BHHH{len(data)}s",
            _FILE_RECORD_REFERENCE_TYPE,
            file_number,
            record_number,
            len(data) // 2,
            data,
        )

    return struct.pack(
        ENDIAN + f"BB{len(sub_req_buffer)}s",
        function_code,
        len(sub_req_buffer),
        sub_req_buffer,
    )


def _unpack_write_file_record(sdu: bytes) -> list[tuple[int, int, bytes]]:
    _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
    if len(sdu) != 2 + byte_count:
        raise ValueError(f"Invalid byte count : {byte_count}")
    records: list[tuple[int, int, bytes]] = []
    offset = 2
    while offset < len(sdu):
        reference_type, file_number, record_number, record_length = struct.unpack(
            ENDIAN + "BHHH", sdu[offset : offset + 7]
        )
        if reference_type != _FILE_RECORD_REFERENCE_TYPE:
            raise ValueError(f"Invalid reference type : {reference_type}")
        data_start = offset + 7
        data_end = data_start + 2 * record_length
        if data_end > len(sdu):
            raise ValueError(f"Record data exceeds the frame : {record_length}")
        records.append((file_number, record_number, sdu[data_start:data_end]))
        offset = data_end
    return records


@dataclass
class WriteFileRecordRequestSDU(ModbusRequestSDU):
    """Write file record request, records are (file number, record number, data)"""

    function_code = FunctionCode.WRITE_FILE_RECORD
    records: list[tuple[int, int, bytes]]

    def __post_init__(self) -> None:
        if isinstance(self.records, tuple):
            self.records = [self.records]
        elif not isinstance(self.records, list):
            raise TypeError(f"Invalid records type : {self.records}")

    def make_sdu(self) -> bytes:
        return _pack_write_file_record(self.function_code, self.records)

    @staticmethod
    def parse_sdu(sdu: bytes) -> WriteFileRecordRequestSDU:
        return WriteFileRecordRequestSDU(_unpack_write_file_record(sdu))


@dataclass
class WriteFileRecordResponseSDU(ModbusResponseSDU[WriteFileRecordRequestSDU]):
    """Write file record response, echo of the request"""

    function_code = FunctionCode.WRITE_FILE_RECORD
    records: list[tuple[int, int, bytes]]

    def make_sdu(self) -> bytes:
        return _pack_write_file_record(self.function_code, self.records)

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: WriteFileRecordRequestSDU
    ) -> WriteFileRecordResponseSDU:
        if sdu != request.make_sdu():
            raise ProtocolReadError("Response different from query")
        return WriteFileRecordResponseSDU(_unpack_write_file_record(sdu))


# Mask write register - 0x16
@dataclass
class MaskWriteRegisterRequestSDU(ModbusRequestSDU):
    """Mask write register request"""

    function_code = FunctionCode.MASK_WRITE_REGISTER
    address: int
    and_mask: int
    or_mask: int

    def __post_init__(self) -> None:
        _check_address(self.address)

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHHH",
            self.function_code,
            _dm_to_pdu_address(self.address),
            self.and_mask,
            self.or_mask,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> MaskWriteRegisterRequestSDU:
        _, address, and_mask, or_mask = struct.unpack(ENDIAN + "BHHH", sdu)
        return MaskWriteRegisterRequestSDU(
            _pdu_to_dm_address(address), and_mask, or_mask
        )


@dataclass
class MaskWriteRegisterResponseSDU(ModbusResponseSDU[MaskWriteRegisterRequestSDU]):
    """Mask write register response, echo of the request"""

    function_code = FunctionCode.MASK_WRITE_REGISTER
    address: int
    and_mask: int
    or_mask: int

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BHHH",
            self.function_code,
            _dm_to_pdu_address(self.address),
            self.and_mask,
            self.or_mask,
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: MaskWriteRegisterRequestSDU
    ) -> MaskWriteRegisterResponseSDU:
        if sdu != request.make_sdu():
            raise ProtocolReadError(
                f"Response ({sdu!r}) should match query ({request.make_sdu()!r})"
            )
        _, address, and_mask, or_mask = struct.unpack(ENDIAN + "BHHH", sdu)
        return MaskWriteRegisterResponseSDU(
            _pdu_to_dm_address(address), and_mask, or_mask
        )


# Read/write multiple registers - 0x17
@dataclass
class ReadWriteMultipleRegistersRequestSDU(ModbusRequestSDU):
    """Read/write multiple registers request"""

    function_code = FunctionCode.READ_WRITE_MULTIPLE_REGISTERS
    read_starting_address: int
    number_of_read_registers: int
    write_starting_address: int
    write_values: list[int]

    def __post_init__(self) -> None:
        max_number_read_registers = (AVAILABLE_PDU_SIZE - 2) // 2
        max_numbers_write_registers = (AVAILABLE_PDU_SIZE - 10) // 2

        if not 1 <= self.number_of_read_registers <= max_number_read_registers:
            raise ValueError(
                f"Invalid number of read registers : {self.number_of_read_registers}"
            )

        if not 1 <= len(self.write_values) <= max_numbers_write_registers:
            raise ValueError(
                f"Invalid number of write registers : {len(self.write_values)}"
            )

        _check_address(
            self.read_starting_address,
            MAX_ADDRESS - self.number_of_read_registers + 1,
        )
        _check_address(
            self.write_starting_address, MAX_ADDRESS - len(self.write_values) + 1
        )

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + f"BHHHHB{len(self.write_values)}H",
            self.function_code,
            _dm_to_pdu_address(self.read_starting_address),
            self.number_of_read_registers,
            _dm_to_pdu_address(self.write_starting_address),
            len(self.write_values),
            len(self.write_values) * 2,
            *self.write_values,
        )
        return sdu

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadWriteMultipleRegistersRequestSDU:
        (
            _,
            read_starting_address,
            number_of_read_registers,
            write_starting_address,
            number_of_write_registers,
            byte_count,
        ) = struct.unpack(ENDIAN + "BHHHHB", sdu[:10])
        if byte_count != 2 * number_of_write_registers:
            raise ValueError(
                f"Invalid byte count : {byte_count} for "
                f"{number_of_write_registers} registers"
            )
        write_values = list(
            struct.unpack(ENDIAN + f"{number_of_write_registers}H", sdu[10:])
        )
        return ReadWriteMultipleRegistersRequestSDU(
            _pdu_to_dm_address(read_starting_address),
            number_of_read_registers,
            _pdu_to_dm_address(write_starting_address),
            write_values,
        )


@dataclass
class ReadWriteMultipleRegistersResponseSDU(
    ModbusResponseSDU[ReadWriteMultipleRegistersRequestSDU]
):
    """Read/write multiple registers response"""

    function_code = FunctionCode.READ_WRITE_MULTIPLE_REGISTERS
    read_values: list[int]

    def make_sdu(self) -> bytes:
        return _pack_registers_response(self.function_code, self.read_values)

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReadWriteMultipleRegistersRequestSDU
    ) -> ReadWriteMultipleRegistersResponseSDU:
        return ReadWriteMultipleRegistersResponseSDU(
            _unpack_registers_response(sdu, request.number_of_read_registers)
        )


# Read FIFO queue - 0x18
@dataclass
class ReadFifoQueueRequestSDU(ModbusRequestSDU):
    """Read FIFO queue request"""

    function_code = FunctionCode.READ_FIFO_QUEUE
    fifo_address: int

    def __post_init__(self) -> None:
        _check_address(self.fifo_address)

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BH",
            self.function_code,
            _dm_to_pdu_address(self.fifo_address),
        )

    @staticmethod
    def parse_sdu(sdu: bytes) -> ReadFifoQueueRequestSDU:
        _, fifo_address = struct.unpack(ENDIAN + "BH", sdu)
        return ReadFifoQueueRequestSDU(_pdu_to_dm_address(fifo_address))


@dataclass
class ReadFifoQueueResponseSDU(ModbusResponseSDU[ReadFifoQueueRequestSDU]):
    """Read FIFO queue response"""

    function_code = FunctionCode.READ_FIFO_QUEUE
    values: list[int]

    def make_sdu(self) -> bytes:
        fifo_count = len(self.values)
        return struct.pack(
            ENDIAN + f"BHH{fifo_count}H",
            self.function_code,
            2 + 2 * fifo_count,  # byte count includes the FIFO count
            fifo_count,
            *self.values,
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: ReadFifoQueueRequestSDU
    ) -> ReadFifoQueueResponseSDU:
        _, byte_count = struct.unpack(ENDIAN + "BH", sdu[:3])
        fifo_count = struct.unpack(ENDIAN + "H", sdu[3:5])[0]
        register_count = byte_count // 2 - 1
        if fifo_count != register_count:
            raise ProtocolReadError(
                f"FIFO count mismatch : {fifo_count} != {register_count}"
            )
        values = list(struct.unpack(ENDIAN + f"{register_count}H", sdu[5:]))
        return ReadFifoQueueResponseSDU(values)


# Encapsulated interface transport - 0x2B
@dataclass
class EncapsulatedInterfaceTransportRequestSDU(ModbusRequestSDU):
    """Encapsulated interface transport request"""

    function_code = FunctionCode.ENCAPSULATED_INTERFACE_TRANSPORT
    mei_type: int
    mei_data: bytes
    # Client side only, MEI specific exception messages. Not on the wire
    extra_exceptions: dict[int, str] | None = None

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + f"BB{len(self.mei_data)}s",
            self.function_code,
            self.mei_type,
            self.mei_data,
        )

    @staticmethod
    def parse_sdu(sdu: bytes) -> EncapsulatedInterfaceTransportRequestSDU:
        _, mei_type = struct.unpack(ENDIAN + "BB", sdu[:2])
        return EncapsulatedInterfaceTransportRequestSDU(mei_type, sdu[2:])


@dataclass
class EncapsulatedInterfaceTransportResponseSDU(
    ModbusResponseSDU[EncapsulatedInterfaceTransportRequestSDU]
):
    """Encapsulated interface transport response"""

    function_code = FunctionCode.ENCAPSULATED_INTERFACE_TRANSPORT
    mei_type: int
    data: bytes

    def make_sdu(self) -> bytes:
        return (
            struct.pack(ENDIAN + "BB", self.function_code, self.mei_type) + self.data
        )

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: EncapsulatedInterfaceTransportRequestSDU
    ) -> EncapsulatedInterfaceTransportResponseSDU:
        _, mei_type = struct.unpack(ENDIAN + "BB", sdu[:2])
        return EncapsulatedInterfaceTransportResponseSDU(mei_type, sdu[2:])


DEFAULT_ENCODING = "utf-8"
DEFAULT_PADDING = "\0"

# byte_order vs word_order
#
# byte_order : Order by the individual bytes inside a modbus register
# word_order : Order of the different registers to constitute a multi-register value
#
# Example : Integer 0x12345678 (A=0x12 B=0x34 C=56 D=78)
#
# | byte_order | word_order | Result |
# | -----------|------------|--------|
# | 'big'      | 'big'      | ABCD   |
# | 'little'   | 'big'      | BADC   |
# | 'big'      | 'little'   | CDAB   |
# | 'little'   | 'little'   | DCBA   |


class ModbusMultiRegisterValue:
    _buffer: bytes

    # ENDIAN_SYMBOL = {Endian.BIG: ">", Endian.LITTLE: "<"}
    # Formats based on the number of registers (half the number of bytes)
    INT_FORMAT = {
        1: "h",
        2: "i",
        4: "q",
    }
    UINT_FORMAT = {
        1: "H",
        2: "I",  # or 'L'
        4: "Q",
    }
    FLOAT_FORMAT = {2: "f", 4: "d"}

    def __init__(
        self,
        buffer: bytes,
        *,
        word_order: Endian | str,
        byte_order: Endian | str,
    ) -> None:
        self._word_order = Endian(word_order)
        self._byte_order = Endian(byte_order)

        self._buffer = buffer

    @staticmethod
    def from_registers(
        register_values: list[int], byte_order: Endian | str, word_order: Endian | str
    ) -> ModbusMultiRegisterValue:
        direction = 1 if Endian(word_order) == Endian.BIG else -1
        buffer = b"".join(
            [
                x.to_bytes(2, byteorder=Endian(byte_order).value)
                for x in register_values[::direction]
            ]
        )
        return ModbusMultiRegisterValue(
            buffer, word_order=word_order, byte_order=byte_order
        )

    def to_registers(self) -> list[int]:
        direction = 1 if self._word_order == Endian.BIG else -1
        registers = [
            int.from_bytes(
                self._buffer[2 * i : 2 * i + 2], byteorder=self._byte_order.value
            )
            for i in range(len(self._buffer) // 2)
        ]
        return registers[::direction]

    def to_int(self) -> int:
        n = len(self._buffer) // 2
        try:
            fmt = self.INT_FORMAT[n]
        except KeyError as e:
            raise ValueError(f"Buffer of size {n} cannot be converted to int") from e

        output = cast(int, struct.unpack(f">{fmt}", self._buffer)[0])

        return output

    def to_uint(self) -> int:
        n = len(self._buffer) // 2
        try:
            fmt = self.UINT_FORMAT[n]
        except KeyError as e:
            raise ValueError(f"Buffer of size {n} cannot be converted to uint") from e

        output = cast(int, struct.unpack(f">{fmt}", self._buffer)[0])
        return output

    def to_float(self) -> float:
        n = len(self._buffer) // 2
        try:
            fmt = self.FLOAT_FORMAT[n]
        except KeyError as e:
            raise ValueError(f"Buffer of size {n} cannot be converted to float") from e

        output = cast(int, struct.unpack(f">{fmt}", self._buffer)[0])
        return output

    def to_string(
        self, encoding: str = DEFAULT_ENCODING, padding: str = DEFAULT_PADDING
    ) -> str:
        data = self.to_array()
        # Cast
        decoded_data = data.decode(encoding)
        return decoded_data.strip(padding)

    def to_array(self) -> bytes:
        return self._buffer

    @staticmethod
    def from_int(
        value: int,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        return ModbusMultiRegisterValue(
            struct.pack(">" + ModbusMultiRegisterValue.INT_FORMAT[n_registers], value),
            word_order=word_order,
            byte_order=byte_order,
        )

    @staticmethod
    def from_uint(
        value: int,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        return ModbusMultiRegisterValue(
            struct.pack(">" + ModbusMultiRegisterValue.UINT_FORMAT[n_registers], value),
            word_order=word_order,
            byte_order=byte_order,
        )

    @staticmethod
    def from_float(
        value: float,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        return ModbusMultiRegisterValue(
            struct.pack(
                ">" + ModbusMultiRegisterValue.FLOAT_FORMAT[n_registers], value
            ),
            word_order=word_order,
            byte_order=byte_order,
        )

    @staticmethod
    def from_string(
        value: str,
        n_registers: int,
        padding: str = DEFAULT_PADDING,
        encoding: str = DEFAULT_ENCODING,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        buffer = value.encode(encoding)
        buffer_size = n_registers * 2
        if len(buffer) > buffer_size:
            raise ValueError(
                f"String '{value}' cannot fit in {n_registers} registers ({buffer_size} bytes)"
            )

        padding_bytes = padding.encode(encoding)
        buffer += padding_bytes * (buffer_size - len(buffer))
        return ModbusMultiRegisterValue(
            buffer, word_order=word_order, byte_order=byte_order
        )

    @staticmethod
    def from_array(
        array: bytes,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        if len(array) != 2 * n_registers:
            raise ValueError(
                f"Cannot fit '{array!r}' ({len(array)}) into {n_registers} registers ({2*n_registers})"
            )
        return ModbusMultiRegisterValue(
            array, word_order=word_order, byte_order=byte_order
        )



_SDU_PAIRS: list[tuple[type[ModbusRequestSDU], type[ModbusResponseSDU[Any]]]] = [
    (ReadCoilsRequestSDU, ReadCoilsResponseSDU),
    (ReadDiscreteInputsRequestSDU, ReadDiscreteInputsResponseSDU),
    (ReadHoldingRegistersRequestSDU, ReadHoldingRegistersResponseSDU),
    (ReadInputRegistersRequestSDU, ReadInputRegistersResponseSDU),
    (WriteSingleCoilRequestSDU, WriteSingleCoilResponseSDU),
    (WriteSingleRegisterRequestSDU, WriteSingleRegisterResponseSDU),
    (ReadExceptionStatusRequestSDU, ReadExceptionStatusResponseSDU),
    (DiagnosticsRequestSDU, DiagnosticsResponseSDU),
    (GetCommEventCounterRequestSDU, GetCommEventCounterResponseSDU),
    (GetCommEventLogRequestSDU, GetCommEventLogResponseSDU),
    (WriteMultipleCoilsRequestSDU, WriteMultipleCoilsResponseSDU),
    (WriteMultipleRegistersRequestSDU, WriteMultipleRegistersResponseSDU),
    (ReportServerIdRequestSDU, ReportServerIdResponseSDU),
    (ReadFileRecordRequestSDU, ReadFileRecordResponseSDU),
    (WriteFileRecordRequestSDU, WriteFileRecordResponseSDU),
    (MaskWriteRegisterRequestSDU, MaskWriteRegisterResponseSDU),
    (ReadWriteMultipleRegistersRequestSDU, ReadWriteMultipleRegistersResponseSDU),
    (ReadFifoQueueRequestSDU, ReadFifoQueueResponseSDU),
    (EncapsulatedInterfaceTransportRequestSDU, EncapsulatedInterfaceTransportResponseSDU),
]

REQUESTS = {req.function_code: req for req, _ in _SDU_PAIRS}
RESPONSES = {resp.function_code: resp for _, resp in _SDU_PAIRS}

MBAP_LENGTH = 6  # transaction id, protocol id, length : the fixed part of the header

class ModbusBackend(ProtocolBackend[bytes, ModbusSDU]):
    """
    Builds and parses the Modbus PDU around the SDU of each request

    Two things make this more than an encode/decode pair, and both are why the backend
    keeps state :

    * the response cannot be parsed on its own. Reading 10 coils and reading 3 gives
      the same bytes on the wire, only the request says how to read them, so the SDU
      that was written is kept and used to parse what comes back
    * the frame length lives in the header. FragmentSC() hands the raw fragments over
      and the assembly happens here, which is also what makes coalesced answers work

    Parameters
    ----------
    modbus_type : ModbusType
    slave_address : int or None
        Required for RTU and ASCII, unused by TCP
    silence : float
        Silence that ends an RTU frame, in seconds. See rtu_silence
    """

    def __init__(self) -> None:
        self._transaction_id = 0
        self._last_sdu: ModbusRequestSDU | None = None
        self._buffer = b""

    # ┌──────────┐
    # │ Encoding │
    # └──────────┘

    @abstractmethod
    def encode(self, payload: ModbusSDU) -> list[bytes]: ...

    # ┌───────────┐
    # │ Assembly  │
    # └───────────┘

    @abstractmethod
    def push(
        self, frame: AdapterReadFrame[bytes]
    ) -> BackendOutput[bytes, ModbusSDU]: ...

    @abstractmethod
    def _parse(self, pdu: bytes) -> ModbusSDU: ...

    def _parse_sdu(self, sdu: bytes) -> ModbusResponseSDU[Any]:
        """
        Parse the SDU of a response with the request that was last written

        An exception response is returned as an ExceptionResponseSDU, not raised, it is
        up to the caller to decide what to do with it
        """
        request = self._last_sdu
        if request is None:
            raise ProtocolReadError("Cannot read without a prior write")
        if sdu == b"":
            raise ProtocolReadError("Empty Modbus response")

        try:
            if ExceptionResponseSDU.is_exception(sdu):
                return ExceptionResponseSDU.parse_sdu(sdu, request)
            if sdu[0] != request.function_code:
                raise ProtocolReadError(
                    f"Function code mismatch : got {sdu[0]}, "
                    f"expected {request.function_code}"
                )
            return RESPONSES[request.function_code].parse_sdu(sdu, request)
        except (struct.error, IndexError) as e:
            raise ProtocolReadError(f"Malformed Modbus response : {sdu!r}") from e

    @property
    def in_progress(self) -> bool:
        return len(self._buffer) > 0

    def reset(self) -> None:
        self._buffer = b""

    @property
    def default_timeout(self) -> TimeoutType:
        return 1.0

class ModbusTCPBackend(ModbusBackend):

    @property
    def stop_conditions(self) -> list[StopCondition]:
        # The MBAP header carries the length, the backend cuts the frames itself
        return [FragmentSC()]

    def _parse(self, pdu: bytes) -> ModbusResponseSDU[Any]:
        """Check the MBAP header, return the SDU"""
        if len(pdu) < MBAP_LENGTH + 1:  # header + unit id
            raise ProtocolReadError(f"Modbus TCP frame is too short : {pdu!r}")
        (protocol_id,) = struct.unpack(ENDIAN + "H", pdu[2:4])
        if protocol_id != _PROTOCO_ID:
            raise ProtocolReadError(f"Invalid Modbus TCP protocol id : {protocol_id}")

        return self._parse_sdu(pdu[MBAP_LENGTH + 1 :])

    def push(self, frame: AdapterReadFrame[bytes]) -> BackendOutput[bytes, ModbusSDU]:
        self._buffer += frame.data
        payloads: list[ModbusSDU] = []

        while len(self._buffer) >= MBAP_LENGTH:
            (length,) = struct.unpack(ENDIAN + "H", self._buffer[4:MBAP_LENGTH])
            total = MBAP_LENGTH + length
            if len(self._buffer) < total:
                break  # the body hasn't arrived yet
            payloads.append(self._parse(self._buffer[:total]))
            self._buffer = self._buffer[total:]

        return BackendOutput(payloads=payloads)

    def encode(self, payload: ModbusSDU) -> list[bytes]:
        if not isinstance(payload, ModbusRequestSDU):
            raise RuntimeError("Can only encode ModbusRequestSDU")
        if isinstance(payload, SerialLineOnlySDU):
            raise ProtocolError("This function cannot be used with Modbus TCP")

        sdu = payload.make_sdu()

        length = len(sdu) + 1  # unit_id is included
        output = (
            struct.pack(
                ENDIAN + "HHHB",
                self._transaction_id,
                _PROTOCO_ID,
                length,
                _UNIT_ID,
            )
            + sdu
        )

        self._transaction_id = (self._transaction_id + 1) % 0x10000
        # Kept for parse_sdu, the answer alone doesn't say how to read itself
        self._last_sdu = payload
        return [output]
    
class ModbusSerialBackend(ModbusBackend, ABC):

    def __init__(self, slave_address: int) -> None:
        super().__init__()
        self._slave_address = slave_address

    def push(self, frame: AdapterReadFrame[bytes]) -> BackendOutput[bytes, ModbusSDU]:
        # RTU and ASCII are framed by the adapter (silence, trailer), one frame is
        # one response
        return BackendOutput(payloads=[self._parse(frame.data)])


class ModbusASCIIBackend(ModbusSerialBackend):

    @property
    def stop_conditions(self) -> list[StopCondition]:
        # Every ASCII frame ends with CRLF
        return [Termination(_ASCII_TRAILER)]

    def _parse(self, pdu: bytes) -> ModbusResponseSDU[Any]:
        """Decode the hex, check the LRC and the slave address, return the SDU"""
        if not pdu.startswith(_ASCII_HEADER) or not pdu.endswith(_ASCII_TRAILER):
            raise ProtocolReadError(f"Malformed Modbus ASCII frame : {pdu!r}")

        hex_body = pdu[len(_ASCII_HEADER) : -len(_ASCII_TRAILER)]
        try:
            body = bytes.fromhex(hex_body.decode("ascii"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ProtocolReadError(
                f"Modbus ASCII frame isn't hex : {hex_body!r}"
            ) from e

        if len(body) < 3:  # address + at least a function code + LRC
            raise ProtocolReadError(f"Modbus ASCII frame is too short : {pdu!r}")

        received = body[-1]
        expected = modbus_lrc(body[:-1])
        if received != expected:
            raise ProtocolReadError(
                f"Modbus ASCII LRC mismatch : got {received:02X}, expected {expected:02X}"
            )

        if self._slave_address is not None and body[0] != self._slave_address:
            raise ProtocolReadError(
                f"Modbus ASCII answer came from slave {body[0]}, expected {self._slave_address}"
            )

        data = body[1:-1]

        return self._parse_sdu(data)

    def encode(self, payload: ModbusSDU) -> list[bytes]:
        if not isinstance(payload, ModbusRequestSDU):
            raise RuntimeError("Can only encode ModbusRequestSDU")
        sdu = payload.make_sdu()

        output = _ascii_frame(self._slave_address or 0, sdu)

        self._transaction_id = (self._transaction_id + 1) % 0x10000
        # Kept for parse_sdu, the answer alone doesn't say how to read itself
        self._last_sdu = payload
        return [output]


class ModbusRTUBackend(ModbusSerialBackend):

    def __init__(
        self, slave_address: int, baudrate: int  # = rtu_silence(None),
    ) -> None:
        super().__init__(slave_address)

        # Silence that ends an RTU frame, in seconds
        # 3.5 character (11 bits) times below 19200, fixed 1.75ms above
        self._silence = 1.75e-3 if baudrate > 19200 else (3.5 * 11 / baudrate)

    @property
    def stop_conditions(self) -> list[StopCondition]:
        # An RTU frame ends on a silence on the line
        return [Continuation(self._silence)]

    def _parse(self, pdu: bytes) -> ModbusResponseSDU[Any]:
        """Check the CRC and the slave address, return the SDU"""
        if len(pdu) < 4:  # address + at least a function code + CRC
            raise ProtocolReadError(f"Modbus RTU frame is too short : {pdu!r}")

        (received,) = struct.unpack("<H", pdu[-2:])
        expected = modbus_crc(pdu[:-2])
        if received != expected:
            raise ProtocolReadError(
                f"Modbus RTU CRC mismatch : got {received:04X}, expected {expected:04X}"
            )

        if self._slave_address is not None and pdu[0] != self._slave_address:
            raise ProtocolReadError(
                f"Modbus RTU answer came from slave {pdu[0]}, expected {self._slave_address}"
            )

        data = pdu[1:-2]

        return self._parse_sdu(data)

    def encode(self, payload: ModbusSDU) -> list[bytes]:
        if not isinstance(payload, ModbusRequestSDU):
            raise RuntimeError("Can only encode ModbusRequestSDU")
        sdu = payload.make_sdu()

        frame = struct.pack(ENDIAN + "B", self._slave_address) + sdu
        output = frame + struct.pack("<H", modbus_crc(frame))

        self._transaction_id = (self._transaction_id + 1) % 0x10000
        # Kept for parse_sdu, the answer alone doesn't say how to read itself
        self._last_sdu = payload
        return [output]


def _serial_backend(
    serial_type: str, slave_address: int | None, baudrate: int | None
) -> ModbusBackend:
    """Check the serial parameters and pick the RTU or ASCII backend"""
    if slave_address is None:
        raise ValueError("slave_address must be set for Modbus RTU and ASCII")
    if not 1 <= slave_address <= 247:
        raise ValueError(f"Invalid slave address : {slave_address}, expected 1 to 247")
    if baudrate is None:
        raise ValueError("Baudrate hasn't been defined")
    try:
        _type = ModbusSerialType(serial_type.upper())
    except ValueError as e:
        raise ValueError(f"Invalid modbus serial type : {serial_type}") from e
    if _type == ModbusSerialType.ASCII:
        return ModbusASCIIBackend(slave_address)
    return ModbusRTUBackend(slave_address, baudrate)


ResponseT = TypeVar("ResponseT", bound=ModbusResponseSDU[Any])


class ModbusCommon:
    """Value conversions shared by Modbus and AsyncModbus"""

    @staticmethod
    def _check_response(
        request: ModbusRequestSDU, response: ModbusSDU, response_type: type[ResponseT]
    ) -> ResponseT:
        """Raise the exception response as a ModbusError, check the response type"""
        if isinstance(response, ExceptionResponseSDU):
            description = response.description
            if (
                isinstance(request, EncapsulatedInterfaceTransportRequestSDU)
                and request.extra_exceptions is not None
                and response.exception_code in request.extra_exceptions
            ):
                description = request.extra_exceptions[response.exception_code]
            raise ModbusError(f"{response.exception_code:02X} : {description}")
        if not isinstance(response, response_type):
            raise ProtocolReadError(
                f"Unexpected response {response!r}, expected {response_type.__name__}"
            )
        return response


# pylint: disable=too-many-public-methods
class Modbus(Protocol[ModbusBackend, bytes, ModbusSDU], ModbusCommon):
    """
    Modbus protocol, TCP over IP and RTU or ASCII over a serial port

    Parameters
    ----------
    adapter : Adapter
        IP gives Modbus TCP, SerialPort gives Modbus RTU or ASCII. The flavour is
        decided by the adapter, not by _type
    timeout : float, None or ...
        Time to wait for a complete response, 1 s by default
    serial_type : {'RTU', 'ASCII'}
        Serial flavour, ignored with an IP adapter. 'RTU' by default
    slave_address : int or None
        1 to 247, required for RTU and ASCII, unused by TCP
    alias : str
    """

    def __init__(
        self,
        adapter: Adapter[Any, bytes],
        *,
        timeout: TimeoutParameterType = ...,
        serial_type: str = ModbusSerialType.RTU.value,
        slave_address: int | None = None,
        alias: str = "",
    ) -> None:
        backend: ModbusBackend
        if isinstance(adapter, IP):
            adapter.set_default_port(MODBUS_TCP_DEFAULT_PORT)
            backend = ModbusTCPBackend()
        elif isinstance(adapter, SerialPort):
            backend = _serial_backend(
                serial_type, slave_address, adapter.descriptor.baudrate
            )
        else:
            raise ValueError(f"Invalid adapter : {adapter}")

        super().__init__(
            adapter,
            backend,
            timeout,
            alias,
        )

    def _query(
        self, request: ModbusRequestSDU, response_type: type[ResponseT]
    ) -> ResponseT:
        return self._check_response(request, self.query(request), response_type)

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    # Read Coils - 0x01
    def read_coils(self, start_address: int, number_of_coils: int) -> list[bool]:
        """
        Read a defined number of coils starting at a set address

        Parameters
        ----------
        start_address : int
        number_of_coils : int

        Returns
        -------
        coils : list
        """
        payload = ReadCoilsRequestSDU(
            start_address=start_address, number_of_coils=number_of_coils
        )

        output = self._query(payload, ReadCoilsResponseSDU)

        return output.coils

    # This is a wrapper for the read_coils method
    def read_single_coil(self, address: int) -> bool:
        """
        Read a single coil at a specified address.
        This is a wrapper for the read_coils method with the number of coils set to 1

        Parameters
        ----------
        address : int

        Returns
        -------
        coil : bool
        """
        coil = self.read_coils(start_address=address, number_of_coils=1)[0]
        return coil

    # Read Discrete inputs - 0x02
    def read_discrete_inputs(
        self, start_address: int, number_of_inputs: int
    ) -> list[bool]:
        """
        Read a defined number of discrete inputs at a set starting address

        Parameters
        ----------
        start_address : int
        number_of_inputs : int

        Returns
        -------
        inputs : list
        List of booleans
        """

        payload = ReadDiscreteInputsRequestSDU(
            start_address=start_address, number_of_inputs=number_of_inputs
        )

        output = self._query(payload, ReadDiscreteInputsResponseSDU)

        return output.inputs

    # Read Holding Registers - 0x03
    def read_holding_registers(self, start_address: int, n_registers: int) -> list[int]:
        """
        Reads a defined number of registers starting at a set address

        Parameters
        ----------
        start_address : int
        n_registers : int
            1 to 125

        Returns
        -------
        registers : list
        """

        payload = ReadHoldingRegistersRequestSDU(
            start_address=start_address, n_registers=n_registers
        )

        output = self._query(payload, ReadHoldingRegistersResponseSDU)

        return output.registers

    def read_multi_register_value(
        self,
        address: int,
        n_registers: int,
        *,
        byte_order: Endian | str = Endian.BIG,
        word_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        """
        Read an integer, a float, or a string over multiple registers

        Parameters
        ----------
        address : int
            Address of the first register
        n_registers : int
            Number of registers (half the number of bytes)
        value_type : str
            Type to which the value will be cast
                'int' : signed integer
                'uint' : unsigned integer
                'float' : float or double
                'string' : string
                'array' : Bytes array
            Each type will be adapted based on the number of bytes (_bytes parameter)
        byte_order : str
            Byte order, 'big' means the high bytes will come first, 'little' means the low bytes
            will come first
            Byte order inside a register (2 bytes) is always big as per
            Modbus specification (4.2 Data Encoding)
        encoding : str
            String encoding (if used). UTF-8 by default
        padding : int | None
            String padding, None to return the raw string
        Returns
        -------
        data : any
        """
        # Read N registers
        registers = self.read_holding_registers(
            start_address=address, n_registers=n_registers
        )

        return ModbusMultiRegisterValue.from_registers(
            registers, byte_order, word_order
        )

    def write_multi_register_value(
        self, address: int, value: ModbusMultiRegisterValue
    ) -> None:
        """
        Write an integer, a float, or a string over multiple registers

        Parameters
        ----------
        address : int
            Address of the first register
        n_registers : int
            Number of registers (half the number of bytes)
        value_type : str | bytes | int
            Type to which the value will be cast
                'int' : signed integer
                'uint' : unsigned integer
                'float' : float or double
                'string' : string
                'array' : Bytes array
        value : any
            The value to write, can be any of the following : str, int, float, str, bytearray
        byte_order : str
            Byte order, 'big' means the high bytes will come first, 'little' means the low
            bytes will come first
            Byte order inside a register (2 bytes) is always big as per
            Modbus specification (4.2 Data Encoding)
        encoding : str
            String encoding (if used)
        padding : int
            Padding in case the value (str / bytes) is not long enough
        Returns
        -------
        data : any
        """
        registers = value.to_registers()
        self.write_multiple_registers(start_address=address, values=registers)

    # Read Input Registers - 0x04
    def read_input_registers(self, start_address: int, n_registers: int) -> list[int]:
        """
        Reads a defined number of input registers starting at a set address

        Parameters
        ----------
        start_address : int
        n_registers : int
            1 to 125

        Returns
        -------
        registers : list
            List of integers
        """
        payload = ReadInputRegistersRequestSDU(
            start_address=start_address, n_registers=n_registers
        )

        output = self._query(payload, ReadInputRegistersResponseSDU)

        return output.registers

    # Write Single coil - 0x05
    def write_single_coil(self, address: int, status: bool) -> None:
        """
        Write a single output to either ON or OFF

        Parameters
        ----------
        address : int
        status : bool
        """
        payload = WriteSingleCoilRequestSDU(address=address, status=status)

        self._query(payload, WriteSingleCoilResponseSDU)

    # Write Single Register - 0x06
    def write_single_register(self, address: int, value: int) -> None:
        """
        Write a single register

        Parameters
        ----------
        address : int
        value : int
            value between 0x0000 and 0xFFFF
        """
        payload = WriteSingleRegisterRequestSDU(
            address=address,
            value=value,
        )

        self._query(payload, WriteSingleRegisterResponseSDU)

    def read_single_register(self, address: int) -> int:
        """
        Read a single register

        Parameters
        ----------
        address : int

        Returns
        -------
        value : int
        """
        return self.read_holding_registers(address, 1)[0]

    # Read Exception Status - 0x07
    def read_exception_status(self) -> int:
        """
        Read exeption status

        Returns
        -------
        exceptions : int
        """
        payload = ReadExceptionStatusRequestSDU()

        output = self._query(payload, ReadExceptionStatusResponseSDU)

        return output.status

    # Diagnostics - 0x08
    def diagnostics_return_query_data(self, data: int = 0x1234) -> bool:
        """
        Run "Return Query Data" diagnostic

        A query is sent and should be return identical

        Parameters
        ----------
        data : int
            data to send (16 bits integer)

        Returns
        -------
        success : bool
        """
        subfunction_data = struct.pack(ENDIAN + "H", data)
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_QUERY_DATA,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return output.data == subfunction_data

    # TODO : Check how this function interracts with Listen Only mode
    def diagnostics_restart_communications_option(
        self, clear_communications_event_log: bool = False
    ) -> None:
        """
        Initialize and restart serial line port. Brings the device out of Listen Only Mode

        Parameters
        ----------
        clear_communications_event_log : bool
            False by default
        """
        subfunction_data = struct.pack(
            ENDIAN + "H", 0xFF00 if clear_communications_event_log else 0x0000
        )
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        self._query(payload, DiagnosticsResponseSDU)

    def diagnostics_return_diagnostic_register(self) -> int:
        """
        Return 16 bit diagnostic register

        Returns
        -------
        register : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_change_ascii_input_delimiter(self, char: bytes | str) -> None:
        """
        Change the ASCII input delimiter to specified value

        Parameters
        ----------
        char : bytes or str
            Single character
        """
        if len(char) != 1:
            raise ValueError(f"Invalid char length : {len(char)}")
        if isinstance(char, str):
            char = char.encode("ASCII")

        subfunction_data = struct.pack("cB", char, 0)
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.CHANGE_ASCII_INPUT_DELIMITER,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        self._query(payload, DiagnosticsResponseSDU)

    def diagnostics_force_listen_only_mode(self) -> None:
        """
        Forces the addressed remote device to its Listen Only Mode for MODBUS communications.
        This isolates it from the other devices on the network, allowing them to continue
        communicating without interruption from the addressed remote device. No response is
        returned.
        When the remote device enters its Listen Only Mode, all active communication controls are
        turned off. The Ready watchdog timer is allowed to expire, locking the controls off.
        While the device is in this mode, any MODBUS messages addressed to it or broadcast
        are monitored, but no actions will be taken and no responses will be sent.
        The only function that will be processed after the mode is entered will be the Restart
        Communications Option function (function code 8, sub-function 1).
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.FORCE_LISTEN_ONLY_MODE,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
            check_response=False,
        )

        self.write(payload)

    def diagnostics_clear_counters_and_diagnostic_register(self) -> None:
        """
        Clear all counters and the diagnostic register
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        self._query(payload, DiagnosticsResponseSDU)

    def diagnostics_return_bus_message_count(self) -> int:
        """
        Return the number of messages that the remote device has detection on the communications
        system since its last restat, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_bus_communication_error_count(self) -> int:
        """
        Return the number of messages that the remote device has detection on the communications
        system since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_bus_exception_error_count(self) -> int:
        """
        Return the number of Modbus exceptions responses returned by the remote device since
        its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_server_no_response_count(self) -> int:
        """
        Return the number of messages addressed to the remote device for which it has returned
        no response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_server_nak_count(self) -> int:
        """
        Return the number of messages addressed to the remote device for which it returned
        a negative acnowledge (NAK) exception response since its last restart, clear counters
        operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_SERVER_NAK_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_server_busy_count(self) -> int:
        """
        Return the number of messages addressed to the remote device for which it returned a
        server device busy exception response since its last restart, clear counters operation,
        or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_SERVER_BUSY_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_bus_character_overrun_count(self) -> int:
        """
        Return the number of messages addressed to the remote device that it could not handle
        due to a character overrun condition since its last restart, clear counters operation,
        or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_clear_overrun_counter_and_flag(self) -> None:
        """
        Clear the overrun error counter and reset the error flag
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.CLEAR_OVERRUN_COUNTER_AND_FLAG,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        self._query(payload, DiagnosticsResponseSDU)

    # Get Comm Event Counter - 0x0B
    def get_comm_event_counter(self) -> tuple[int, int]:
        """
        Retrieve status word and event count from the remote device's communication event counter

        Returns
        -------
        status : int
        event_count : int
        """
        payload = GetCommEventCounterRequestSDU()

        output = self._query(payload, GetCommEventCounterResponseSDU)

        return output.status, output.event_count

    # Get Comm Event Log - 0x0C
    def get_comm_event_log(self) -> tuple[int, int, int, bytes]:
        """
        Retrieve status word, event count, message count and a field of event bytes from
        the remote device

        Status word and event count are identical to those returned by get_comm_event_counter()

        Returns
        -------
        status : int
        event_count : int
        message_count : int
            Number of messages processed since its last restart, clear counters operation,
            or power-up
            Identical to diagnostics_return_bus_message_count()
        events : bytes
            0-64 bytes, each corresponding to the status of one Modbus send or receive
            operation for the remote device. Byte 0 is the most recent event
        """
        payload = GetCommEventLogRequestSDU()

        output = self._query(payload, GetCommEventLogResponseSDU)

        return output.status, output.event_count, output.message_count, output.events

    # Write Multiple Coils - 0x0F
    def write_multiple_coils(self, start_address: int, values: list[bool]) -> None:
        """
        Write multiple coil values

        Parameters
        ----------
        start_address : int
        value : list
            Bool values
        """
        payload = WriteMultipleCoilsRequestSDU(
            start_address=start_address,
            values=values,
        )

        self._query(payload, WriteMultipleCoilsResponseSDU)

    # Write Multiple Registers - 0x10
    def write_multiple_registers(self, start_address: int, values: list[int]) -> None:
        """
        Write multiple registers

        Parameters
        ----------
        start_address : int
        values : list
            List of integers

        """
        payload = WriteMultipleRegistersRequestSDU(
            start_address=start_address,
            values=values,
        )

        self._query(payload, WriteMultipleRegistersResponseSDU)

    # Report Server ID - 0x11
    def report_server_id(
        self, server_id_length: int, additional_data_length: int
    ) -> tuple[bytes, bool, bytes]:
        """
        Read description of the type, current status and other information specific to
        a remote device

        Parameters
        ----------
        server_id_length : int
            Length of server id field (bytes)
        additional_data_length : int
            Length of additional data (bytes), 0 if none
        Returns
        -------
        server_id : bytes
        run_indicator_status : bool
        additional_data : bytes
        """
        payload = ReportServerIdRequestSDU(
            server_id_length=server_id_length,
            additional_data_length=additional_data_length,
        )

        output = self._query(payload, ReportServerIdResponseSDU)

        return output.server_id, output.run_indicator_status, output.additional_data

    # Read File Record - 0x14
    def read_file_record(self, records: list[tuple[int, int, int]]) -> list[bytes]:
        """
        Perform a single or multiple file record read

        Total response length cannot exceed 253 bytes, meaning the number of records
        and their length is limited.


        Query equation : 2 + 7*N <= 253
        Response equation : 2 + N*2 + sum(Li*2) <= 253

        Parameters
        ----------
        records : list
            List of tuples : (file_number, record_number, record_length)

        Returns
        -------
        records_data : list
            List of bytes
        """
        payload = ReadFileRecordRequestSDU(records=records)

        output = self._query(payload, ReadFileRecordResponseSDU)

        return output.records_data

    # Write File Record - 0x15
    def write_file_record(self, records: list[tuple[int, int, bytes]]) -> None:
        """
        Perform a single or multiple file record write

        Total query and response length cannot exceed 253 bytes, meaning the number of
        records and their length is limited.

        Query equation : 2 + 7*N + sum(Li*2) <= 253
        Response equation : identical

        File number can be between 0x0001 and 0xFFFF but lots of legacy equipment will
        not support file number above 0x000A (10)

        Parameters
        ----------
        records : list
            List of tuples : (file_number, record_number, data)
        """
        payload = WriteFileRecordRequestSDU(records=records)

        self._query(payload, WriteFileRecordResponseSDU)

    # Mask Write Register - 0x16
    def mask_write_register(self, address: int, and_mask: int, or_mask: int) -> None:
        """
        This function is used to modify the contents of a holding register using a
        combination of AND and OR masks applied to the current contents of the register.

        The algorithm is :

        New value = (old value & and_mask) | (or_mask & (~and_mask))

        Parameters
        ----------
        address : int
            0x0000 to 0xFFFF
        and_mask : int
            0x0000 to 0xFFFF
        or_mask : int
            0x0000 to 0xFFFF
        """
        payload = MaskWriteRegisterRequestSDU(
            address=address,
            and_mask=and_mask,
            or_mask=or_mask,
        )

        self._query(payload, MaskWriteRegisterResponseSDU)

    # Read/Write Multiple Registers - 0x17
    def read_write_multiple_registers(
        self,
        read_starting_address: int,
        number_of_read_registers: int,
        write_starting_address: int,
        write_values: list[int],
    ) -> list[int]:
        """
        Do a write, then a read operation, each on a specific set of registers.

        Parameters
        ----------
        read_starting_address : int
        number_of_read_registers : int
        write_starting_address : int
        write_values : list
            List of registers values

        Returns
        -------
        read_values : list
        """
        payload = ReadWriteMultipleRegistersRequestSDU(
            read_starting_address=read_starting_address,
            number_of_read_registers=number_of_read_registers,
            write_starting_address=write_starting_address,
            write_values=write_values,
        )

        output = self._query(payload, ReadWriteMultipleRegistersResponseSDU)
        return output.read_values

    # Read FIFO Queue - 0x18
    def read_fifo_queue(self, fifo_address: int) -> list[int]:
        """
        Read the contents of a First-In-First-Out (FIFO) queue of registers

        Parameters
        ----------
        fifo_address : int

        Returns
        -------
        registers : list
        """
        payload = ReadFifoQueueRequestSDU(fifo_address=fifo_address)

        output = self._query(payload, ReadFifoQueueResponseSDU)
        return output.values

    # Encapsulate Interface Transport - 0x2B
    def encapsulated_interface_transport(
        self,
        mei_type: int,
        mei_data: bytes,
        extra_exceptions: dict[int, str] | None = None,
    ) -> bytes:
        """
        The MODBUS Encapsulated Interface (MEI) Transport is a mechanism for tunneling
        service requests and method invocations

        Parameters
        ----------
        mei_type : int
        mei_data : bytes

        Returns
        -------
        returned_mei_data : bytes
        """
        payload = EncapsulatedInterfaceTransportRequestSDU(
            mei_type=mei_type,
            mei_data=mei_data,
            extra_exceptions=extra_exceptions,
        )

        output = self._query(payload, EncapsulatedInterfaceTransportResponseSDU)

        return output.data


# pylint: disable=too-many-public-methods
class AsyncModbus(AsyncProtocol[ModbusBackend, bytes, ModbusSDU], ModbusCommon):
    """
    Async Modbus protocol, same parameters as Modbus
    """

    def __init__(
        self,
        adapter: AsyncAdapter[Any, bytes],
        *,
        timeout: TimeoutParameterType = ...,
        serial_type: str = ModbusSerialType.RTU.value,
        slave_address: int | None = None,
        alias: str = "",
    ) -> None:
        backend: ModbusBackend
        if isinstance(adapter, AsyncIP):
            adapter.set_default_port(MODBUS_TCP_DEFAULT_PORT)
            backend = ModbusTCPBackend()
        elif isinstance(adapter, AsyncSerialPort):
            backend = _serial_backend(
                serial_type, slave_address, adapter.descriptor.baudrate
            )
        else:
            raise ValueError(f"Invalid adapter : {adapter}")

        super().__init__(
            adapter,
            backend,
            timeout,
            alias,
        )

    async def _query(
        self, request: ModbusRequestSDU, response_type: type[ResponseT]
    ) -> ResponseT:
        return self._check_response(request, await self.query(request), response_type)

    # Read Coils - 0x01
    async def read_coils(self, start_address: int, number_of_coils: int) -> list[bool]:
        """
        Asynchronously read a defined number of coils starting at a set address

        Parameters
        ----------
        start_address : int
        number_of_coils : int

        Returns
        -------
        coils : list
        """

        payload = ReadCoilsRequestSDU(
            start_address=start_address, number_of_coils=number_of_coils
        )

        output = await self._query(payload, ReadCoilsResponseSDU)

        return output.coils

    # This is a wrapper for the read_coils method
    async def read_single_coil(self, address: int) -> bool:
        """
        Asynchronously read a single coil at a specified address.
        This is a wrapper for the read_coils method with the number of coils set to 1

        Parameters
        ----------
        address : int

        Returns
        -------
        coil : bool
        """
        coil = (await self.read_coils(start_address=address, number_of_coils=1))[0]
        return coil

    # Read Discrete inputs - 0x02
    async def read_discrete_inputs(
        self, start_address: int, number_of_inputs: int
    ) -> list[bool]:
        """
        Read a defined number of discrete inputs at a set starting address

        Parameters
        ----------
        start_address : int
        number_of_inputs : int

        Returns
        -------
        inputs : list
        List of booleans
        """

        payload = ReadDiscreteInputsRequestSDU(
            start_address=start_address, number_of_inputs=number_of_inputs
        )

        output = await self._query(payload, ReadDiscreteInputsResponseSDU)

        return output.inputs

    # Read Holding Registers - 0x03
    async def read_holding_registers(
        self, start_address: int, n_registers: int
    ) -> list[int]:
        """
        Asynchronously Reads a defined number of registers starting at a set address

        Parameters
        ----------
        start_address : int
        n_registers : int
            1 to 125

        Returns
        -------
        registers : list
        """

        payload = ReadHoldingRegistersRequestSDU(
            start_address=start_address, n_registers=n_registers
        )

        output = await self._query(payload, ReadHoldingRegistersResponseSDU)

        return output.registers

    async def read_multi_register_value(
        self,
        address: int,
        n_registers: int,
        *,
        byte_order: Endian | str = Endian.BIG,
        word_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        """
        Asynchronously read an integer, a float, or a string over multiple registers

        Parameters
        ----------
        address : int
            Address of the first register
        n_registers : int
            Number of registers (half the number of bytes)
        value_type : str
            Type to which the value will be cast
                'int' : signed integer
                'uint' : unsigned integer
                'float' : float or double
                'string' : string
                'array' : Bytes array
            Each type will be adapted based on the number of bytes (_bytes parameter)
        byte_order : str
            Byte order, 'big' means the high bytes will come first, 'little' means the low bytes
            will come first
            Byte order inside a register (2 bytes) is always big as per
            Modbus specification (4.2 Data Encoding)
        encoding : str
            String encoding (if used). UTF-8 by default
        padding : int | None
            String padding, None to return the raw string
        Returns
        -------
        data : any
        """
        # Read N registers
        registers = await self.read_holding_registers(
            start_address=address, n_registers=n_registers
        )

        return ModbusMultiRegisterValue.from_registers(
            registers, byte_order, word_order
        )

    async def write_multi_register_value(
        self, address: int, value: ModbusMultiRegisterValue
    ) -> None:
        """
        Asynchronously write an integer, a float, or a string over multiple registers

        Parameters
        ----------
        address : int
            Address of the first register
        n_registers : int
            Number of registers (half the number of bytes)
        value_type : str | bytes | int
            Type to which the value will be cast
                'int' : signed integer
                'uint' : unsigned integer
                'float' : float or double
                'string' : string
                'array' : Bytes array
        value : any
            The value to write, can be any of the following : str, int, float, str, bytearray
        byte_order : str
            Byte order, 'big' means the high bytes will come first, 'little' means the low
            bytes will come first
            Byte order inside a register (2 bytes) is always big as per
            Modbus specification (4.2 Data Encoding)
        encoding : str
            String encoding (if used)
        padding : int
            Padding in case the value (str / bytes) is not long enough
        Returns
        -------
        data : any
        """
        registers = value.to_registers()
        await self.write_multiple_registers(start_address=address, values=registers)

    # Read Input Registers - 0x04
    async def read_input_registers(
        self, start_address: int, n_registers: int
    ) -> list[int]:
        """
        Asynchronously read a defined number of input registers starting at a set address

        Parameters
        ----------
        start_address : int
        n_registers : int
            1 to 125

        Returns
        -------
        registers : list
            List of integers
        """
        payload = ReadInputRegistersRequestSDU(
            start_address=start_address,
            n_registers=n_registers,
        )

        output = await self._query(payload, ReadInputRegistersResponseSDU)

        return output.registers

    # Write Single coil - 0x05
    async def write_single_coil(self, address: int, status: bool) -> None:
        """
        Asynchronously write a single output to either ON or OFF

        Parameters
        ----------
        address : int
        status : bool
        """
        payload = WriteSingleCoilRequestSDU(address=address, status=status)

        await self._query(payload, WriteSingleCoilResponseSDU)

    # Write Single Register - 0x06
    async def write_single_register(self, address: int, value: int) -> None:
        """
        Asynchronously write a single register

        Parameters
        ----------
        address : int
        value : int
            value between 0x0000 and 0xFFFF
        """
        payload = WriteSingleRegisterRequestSDU(
            address=address,
            value=value,
        )

        await self._query(payload, WriteSingleRegisterResponseSDU)

    async def read_single_register(self, address: int) -> int:
        """
        Read a single register

        Parameters
        ----------
        address : int

        Returns
        -------
        value : int
        """
        return (await self.read_holding_registers(address, 1))[0]

    # Read Exception Status - 0x07
    async def read_exception_status(self) -> int:
        """
        Asynchronously read exeption status

        Returns
        -------
        exceptions : int
        """
        payload = ReadExceptionStatusRequestSDU()

        output = await self._query(payload, ReadExceptionStatusResponseSDU)

        return output.status

    async def diagnostics_return_query_data(self, data: int = 0x1234) -> bool:
        """
        Asynchronously run "Return Query Data" diagnostic

        A query is sent and should be return identical

        Parameters
        ----------
        data : int
            data to send (16 bits integer)

        Returns
        -------
        success : bool
        """
        subfunction_data = struct.pack(ENDIAN + "H", data)
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_QUERY_DATA,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return output.data == subfunction_data

    async def diagnostics_restart_communications_option(
        self, clear_communications_event_log: bool = False
    ) -> None:
        """
        Asynchronously initialize and restart serial line port.
        Brings the device out of Listen Only Mode

        Parameters
        ----------
        clear_communications_event_log : bool
            False by default
        """
        subfunction_data = struct.pack(
            ENDIAN + "H", 0xFF00 if clear_communications_event_log else 0x0000
        )
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        await self._query(payload, DiagnosticsResponseSDU)

    async def diagnostics_return_diagnostic_register(self) -> int:
        """
        Asynchronously return 16 bit diagnostic register

        Returns
        -------
        register : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_change_ascii_input_delimiter(self, char: bytes | str) -> None:
        """
        Asynchronously change the ASCII input delimiter to specified value

        Parameters
        ----------
        char : bytes or str
            Single character
        """
        if len(char) != 1:
            raise ValueError(f"Invalid char length : {len(char)}")
        if isinstance(char, str):
            char = char.encode("ASCII")

        subfunction_data = struct.pack("cB", char, 0)
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.CHANGE_ASCII_INPUT_DELIMITER,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        await self._query(payload, DiagnosticsResponseSDU)

    async def diagnostics_force_listen_only_mode(self) -> None:
        """
        Asynchronously forces the addressed remote device to its Listen Only Mode for
        MODBUS communications.
        This isolates it from the other devices on the network, allowing them to continue
        communicating without interruption from the addressed remote device. No response is
        returned.
        When the remote device enters its Listen Only Mode, all active communication controls are
        turned off. The Ready watchdog timer is allowed to expire, locking the controls off.
        While the device is in this mode, any MODBUS messages addressed to it or broadcast
        are monitored, but no actions will be taken and no responses will be sent.
        The only function that will be processed after the mode is entered will be the Restart
        Communications Option function (function code 8, sub-function 1).
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.FORCE_LISTEN_ONLY_MODE,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
            check_response=False,
        )

        await self.write(payload)

    async def diagnostics_clear_counters_and_diagnostic_register(self) -> None:
        """
        Asynchronously clear all counters and the diagnostic register
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        await self._query(payload, DiagnosticsResponseSDU)

    async def diagnostics_return_bus_message_count(self) -> int:
        """
        Asynchronously return the number of messages that the remote device has detection on the
        communications system since its last restat, clear counters operation, or power-up
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_return_bus_communication_error_count(self) -> int:
        """
        Asynchronously return the number of messages that the remote device has detection on the
        communications system since its last restart, clear counters operation, or power-up
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_return_bus_exception_error_count(self) -> int:
        """
        Asynchronously return the number of Modbus exceptions responses returned by the remote
        device since its last restart, clear counters operation, or power-up
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_return_server_no_response_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device for which it
        has returned no response since its last restart, clear counters operation, or power-up
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_return_server_nak_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device for which it
        returned a negative acnowledge (NAK) exception response since its last restart,
        clear counters operation, or power-up
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_SERVER_NAK_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_return_server_busy_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device for which it
        returned a server device busy exception response since its last restart, clear counters
        operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_SERVER_BUSY_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_return_bus_character_overrun_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device that it could
        not handle due to a character overrun condition since its last restart, clear counters
        operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = await self._query(payload, DiagnosticsResponseSDU)

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def diagnostics_clear_overrun_counter_and_flag(self) -> None:
        """
        Asynchronously clear the overrun error counter and reset the error flag
        """
        payload = DiagnosticsRequestSDU(
            code=DiagnosticsCode.CLEAR_OVERRUN_COUNTER_AND_FLAG,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        await self._query(payload, DiagnosticsResponseSDU)

    # Get Comm Event Counter - 0x0B
    async def get_comm_event_counter(self) -> tuple[int, int]:
        """
        Asynchronously retrieve status word and event count from the remote device's
        communication event counter
        """
        payload = GetCommEventCounterRequestSDU()

        output = await self._query(payload, GetCommEventCounterResponseSDU)

        return output.status, output.event_count

    # Get Comm Event Log - 0x0C
    async def get_comm_event_log(self) -> tuple[int, int, int, bytes]:
        """
        Retrieve status word, event count, message count and a field of event bytes from
        the remote device

        Status word and event count are identical to those returned by get_comm_event_counter()

        Returns
        -------
        status : int
        event_count : int
        message_count : int
            Number of messages processed since its last restart, clear counters operation,
            or power-up
            Identical to diagnostics_return_bus_message_count()
        events : bytes
            0-64 bytes, each corresponding to the status of one Modbus send or receive
            operation for the remote device. Byte 0 is the most recent event
        """
        payload = GetCommEventLogRequestSDU()

        output = await self._query(payload, GetCommEventLogResponseSDU)

        return output.status, output.event_count, output.message_count, output.events

    # Write Multiple Coils - 0x0F
    async def write_multiple_coils(
        self, start_address: int, values: list[bool]
    ) -> None:
        """
        Write multiple coil values

        Parameters
        ----------
        start_address : int
        value : list
            Bool values
        """
        payload = WriteMultipleCoilsRequestSDU(
            start_address=start_address,
            values=values,
        )

        await self._query(payload, WriteMultipleCoilsResponseSDU)

    # Write Multiple Registers - 0x10
    async def write_multiple_registers(
        self, start_address: int, values: list[int]
    ) -> None:
        """
        Write multiple registers

        Parameters
        ----------
        start_address : int
        values : list
            List of integers

        """
        payload = WriteMultipleRegistersRequestSDU(
            start_address=start_address,
            values=values,
        )

        await self._query(payload, WriteMultipleRegistersResponseSDU)

    # Report Server ID - 0x11
    async def report_server_id(
        self, server_id_length: int, additional_data_length: int
    ) -> tuple[bytes, bool, bytes]:
        """
        Asynchronously read description of the type, current status and other information specific
        to a remote device
        """
        payload = ReportServerIdRequestSDU(
            server_id_length=server_id_length,
            additional_data_length=additional_data_length,
        )

        output = await self._query(payload, ReportServerIdResponseSDU)

        return output.server_id, output.run_indicator_status, output.additional_data

    # Read File Record - 0x14
    async def read_file_record(
        self, records: list[tuple[int, int, int]]
    ) -> list[bytes]:
        """
        Perform a single or multiple file record read

        Total response length cannot exceed 253 bytes, meaning the number of records
        and their length is limited.


        Query equation : 2 + 7*N <= 253
        Response equation : 2 + N*2 + sum(Li*2) <= 253

        Parameters
        ----------
        records : list
            List of tuples : (file_number, record_number, record_length)

        Returns
        -------
        records_data : list
            List of bytes
        """
        payload = ReadFileRecordRequestSDU(records=records)

        output = await self._query(payload, ReadFileRecordResponseSDU)

        return output.records_data

    # Write File Record - 0x15
    async def write_file_record(self, records: list[tuple[int, int, bytes]]) -> None:
        """
        Perform a single or multiple file record write

        Total query and response length cannot exceed 253 bytes, meaning the number of
        records and their length is limited.

        Query equation : 2 + 7*N + sum(Li*2) <= 253
        Response equation : identical

        File number can be between 0x0001 and 0xFFFF but lots of legacy equipment will
        not support file number above 0x000A (10)

        Parameters
        ----------
        records : list
            List of tuples : (file_number, record_number, data)
        """
        payload = WriteFileRecordRequestSDU(records=records)

        await self._query(payload, WriteFileRecordResponseSDU)

    # Mask Write Register - 0x16
    async def mask_write_register(
        self, address: int, and_mask: int, or_mask: int
    ) -> None:
        """
        This function is used to modify the contents of a holding register using a
        combination of AND and OR masks applied to the current contents of the register.

        The algorithm is :

        New value = (old value & and_mask) | (or_mask & (~and_mask))

        Parameters
        ----------
        address : int
            0x0000 to 0xFFFF
        and_mask : int
            0x0000 to 0xFFFF
        or_mask : int
            0x0000 to 0xFFFF
        """
        payload = MaskWriteRegisterRequestSDU(
            address=address,
            and_mask=and_mask,
            or_mask=or_mask,
        )

        await self._query(payload, MaskWriteRegisterResponseSDU)

    # Read/Write Multiple Registers - 0x17
    async def read_write_multiple_registers(
        self,
        read_starting_address: int,
        number_of_read_registers: int,
        write_starting_address: int,
        write_values: list[int],
    ) -> list[int]:
        """
        Asynchronously do a write, then a read operation, each on a specific set of registers.
        """
        payload = ReadWriteMultipleRegistersRequestSDU(
            read_starting_address=read_starting_address,
            number_of_read_registers=number_of_read_registers,
            write_starting_address=write_starting_address,
            write_values=write_values,
        )

        output = await self._query(payload, ReadWriteMultipleRegistersResponseSDU)

        return output.read_values

    # Read FIFO Queue - 0x18
    async def read_fifo_queue(self, fifo_address: int) -> list[int]:
        """
        Asynchronously read the contents of a First-In-First-Out (FIFO) queue of registers
        """
        payload = ReadFifoQueueRequestSDU(fifo_address=fifo_address)

        output = await self._query(payload, ReadFifoQueueResponseSDU)

        return output.values

    # Encapsulate Interface Transport - 0x2B
    async def encapsulated_interface_transport(
        self,
        mei_type: int,
        mei_data: bytes,
        extra_exceptions: dict[int, str] | None = None,
    ) -> bytes:
        """
        Asynchronously use the MODBUS Encapsulated Interface (MEI) Transport
        """
        payload = EncapsulatedInterfaceTransportRequestSDU(
            mei_type=mei_type,
            mei_data=mei_data,
            extra_exceptions=extra_exceptions,
        )

        output = await self._query(payload, EncapsulatedInterfaceTransportResponseSDU)

        return output.data
