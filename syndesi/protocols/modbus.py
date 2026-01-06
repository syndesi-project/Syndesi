# File : modbus.py
# Author : Sébastien Deriaz
# License : GPL
"""
Modbus TCP and Modbus RTU implementation
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
# The PDU is built and parsed by the Modbus class, each data block (SDU)
# is constructed by its corresponding ModbusRequestSDU class. SDUs are parsed
# by ModbusResponseSDU classes

# pylint: disable=too-many-lines

from __future__ import annotations

import struct
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from math import ceil
from types import EllipsisType
from typing import cast

from syndesi.adapters.adapter_worker import AdapterEvent
from syndesi.component import AdapterFrame

from ..adapters.adapter import Adapter
from ..adapters.ip import IP
from ..adapters.serialport import SerialPort
from ..adapters.timeout import Timeout
from ..tools.errors import ProtocolError, ProtocolReadError
from .protocol import Protocol, ProtocolFrame

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


class Endian(Enum):
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
    if dm_address == 0:
        raise ValueError("Address 0 is not valid in Modbus data model")

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


class ModbusType(Enum):
    """
    Modbus type

    - TCP : Modbus over TCP
    - RTU : Modbus over serial
    - ASCII : Modbus using text based encoding
    """

    RTU = "RTU"
    ASCII = "ASCII"
    TCP = "TCP"


class FunctionCode(Enum):
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
    FORCE_LISTEN_ONLY_MODE = 0x05
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


class TypeCast(Enum):
    """
    Type of cast when storing values in modbus registers
    """

    INT = "int"
    UINT = "uint"
    FLOAT = "float"
    STRING = "str"
    ARRAY = "array"

    def is_number(self) -> bool:
        """
        Return True if the type is a number
        """
        return self in [TypeCast.INT, TypeCast.UINT, TypeCast.FLOAT]


def struct_format(_type: TypeCast, length: int) -> str:
    """
    Convert typecast+length to python struct character
    """
    struct_characters = {
        (TypeCast.INT, 1): "b",
        (TypeCast.INT, 2): "h",
        (TypeCast.INT, 4): "i",
        (TypeCast.INT, 8): "q",
        (TypeCast.UINT, 1): "B",
        (TypeCast.UINT, 2): "H",
        (TypeCast.UINT, 4): "I",  # or 'L'
        (TypeCast.UINT, 8): "Q",
        (TypeCast.FLOAT, 4): "f",
        (TypeCast.FLOAT, 8): "d",
    }

    if _type in [TypeCast.STRING, TypeCast.ARRAY]:
        return f"{length}s"
    try:
        return struct_characters[_type, length]
    except KeyError:
        pass
    raise ValueError(f"Invalid type cast / length combination : {_type} / {length}")


class ModbusError(Exception):
    """
    Generic modbus exception
    """


def modbus_crc(_bytes: bytes) -> int:
    """Calculate modbus CRC from the given buffer"""
    # TODO : Implement
    return 0


def _raise_if_error(sdu: bytes, exceptions: dict[int, str]) -> None:
    if sdu == b"":
        raise ModbusError("Empty response")
    if sdu[0] & 0x80:
        # There is an error
        code = sdu[1]
        if code not in exceptions:
            raise ModbusError(f"Unexpected modbus error code: {code}")
        raise ModbusError(f"{code:02X} : {exceptions[code]}")


class ModbusSDU:
    """
    Modbus Service Data Unit

    Subclasses of this contain either request or response fields to a modbus
    frame
    """

    def make_sdu(self) -> bytes:
        """Generate a bytes array containing the SDU"""
        raise ProtocolError("make_sdu() is not supported for this SDU")

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        """Generate a ModbusSDU instance from a given sdu buffer"""
        raise ProtocolError("parse_sdu() is not supported for this SDU")

    def exceptions(self) -> dict[int, str]:
        """Return a dictionary of exceptions based on their integer code"""
        return {}

    def _check_for_error(self, sdu: bytes) -> None:
        """Check the given sdu buffer for an exception"""
        _raise_if_error(sdu, self.exceptions())


class ModbusRequestSDU(ModbusSDU):
    """
    Base class for modbus request SDUs (Service Data Unit)
    """

    @abstractmethod
    def function_code(self) -> FunctionCode:
        """Return the function code of this modbus request"""

    @classmethod
    def expected_length(cls, pdu_length: int, modbus_type: ModbusType) -> int:
        """
        Return the length of the modbus SDU based on the length of the PDU and modbus type

        Parameters
        ----------
        pdu_length : int
        modbus_type : ModbusType
        """
        if modbus_type == ModbusType.TCP:
            output = pdu_length + 8
        else:
            output = 1 + pdu_length + 2
            if modbus_type == ModbusType.ASCII:
                # Add header and trailer
                output += len(_ASCII_HEADER) + len(_ASCII_TRAILER)
        return output

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        raise NotImplementedError()


# class ModbusResponseSDU(ModbusSDU):
#     def make_sdu(self) -> bytes:
#         """Generate a bytes array containing the SDU"""
#         raise NotImplementedError("make_sdu() not implemented for this SDU")


class SerialLineOnlySDU(ModbusRequestSDU):
    """
    Marker class for serial line only Modbus function codes
    """

    @abstractmethod
    def exceptions(self) -> dict[int, str]: ...


# Read Coils - 0x01
@dataclass
class ReadCoilsSDU(ModbusRequestSDU):
    """Read coils request."""

    start_address: int
    number_of_coils: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        coils: list[bool]

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_COILS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of outputs",
            4: "Couldn't read coils",
        }

    def __post_init__(self) -> None:
        _check_discrete_input_output_count(self.number_of_coils)
        _check_address(self.start_address, MAX_ADDRESS - self.number_of_coils + 1)

    def make_sdu(self) -> bytes:
        data = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.READ_COILS.value,
            _dm_to_pdu_address(self.start_address),
            self.number_of_coils,
        )

        return data

    def parse_sdu(self, sdu: bytes) -> Response:
        super()._check_for_error(sdu)
        _, n_bytes = struct.unpack(ENDIAN + "BB", sdu[:2])
        coil_bytes = struct.unpack(ENDIAN + f"{n_bytes}s", sdu[2:])[0]
        coils = bytes_to_bool_list(coil_bytes, self.number_of_coils)
        return self.Response(coils)


# Read discrete inputs - 0x02
@dataclass
class ReadDiscreteInputs(ModbusRequestSDU):
    """Read discrete inputs request."""

    start_address: int
    number_of_inputs: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        inputs: list[bool]

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_DISCRETE_INPUTS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of inputs",
            4: "Couldn't read inputs",
        }

    def __post_init__(self) -> None:
        _check_discrete_input_output_count(self.number_of_inputs)
        _check_address(self.start_address, MAX_ADDRESS - self.number_of_inputs + 1)

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code().value,
            _dm_to_pdu_address(self.start_address),
            self.number_of_inputs,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)

        byte_count = ceil(
            self.number_of_inputs / 8
        )  # pre-calculate the number of returned coil value bytes

        _, _, data = struct.unpack(ENDIAN + f"BB{byte_count}s", sdu)
        inputs = bytes_to_bool_list(data, self.number_of_inputs)

        return self.Response(inputs)


# Read discrete inputs - 0x03
@dataclass
class ReadHoldingRegisters(ModbusRequestSDU):
    """Read holding registers request."""

    start_address: int
    number_of_registers: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        registers: list[int]

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_HOLDING_REGISTERS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of registers",
            4: "Couldn't read registers",
        }

    def __post_init__(self) -> None:
        _check_address(self.start_address, MAX_ADDRESS - self.number_of_registers + 1)

        max_number_of_registers = (AVAILABLE_PDU_SIZE - 2) // 2

        if not 1 <= self.number_of_registers <= max_number_of_registers:
            raise ValueError(
                f"Invalid number of registers : {self.number_of_registers}"
            )

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code().value,
            _dm_to_pdu_address(self.start_address),
            self.number_of_registers,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)

        _, _, registers_data = struct.unpack(
            ENDIAN + f"BB{self.number_of_registers * 2}s", sdu
        )
        registers = list(
            struct.unpack(ENDIAN + "H" * self.number_of_registers, registers_data)
        )

        return self.Response(registers)


# Write Single coil - 0x05
@dataclass
class WriteSingleCoilSDU(ModbusRequestSDU):
    """Write single coil request."""

    address: int
    status: bool

    _ON_VALUE = 0xFF00
    _OFF_VALUE = 0x0000

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

    def function_code(self) -> FunctionCode:
        return FunctionCode.WRITE_SINGLE_COIL

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid address",
            3: "Invalid value",
            4: "Couldn't set coil output",
        }

    def __post_init__(self) -> None:
        _check_address(self.address)

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.WRITE_SINGLE_COIL.value,
            _dm_to_pdu_address(self.address),
            self._ON_VALUE if self.status else self._OFF_VALUE,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        return self.Response()


@dataclass
class ReadInputRegistersSDU(ModbusRequestSDU):
    """Read input registers request."""

    start_address: int
    number_of_registers: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        registers: list[int]

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_INPUT_REGISTERS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of registers",
            4: "Couldn't read registers",
        }

    def __post_init__(self) -> None:
        _check_address(self.start_address, MAX_ADDRESS - self.number_of_registers + 1)

        max_number_of_registers = (AVAILABLE_PDU_SIZE - 2) // 2

        if not 1 <= self.number_of_registers <= max_number_of_registers:
            raise ValueError(
                f"Invalid number of registers : {self.number_of_registers}"
            )

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code().value,
            _dm_to_pdu_address(self.start_address),
            self.number_of_registers,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)

        _, _, registers_data = struct.unpack(
            ENDIAN + f"BB{self.number_of_registers * 2}s", sdu
        )
        registers = list(
            struct.unpack(ENDIAN + "H" * self.number_of_registers, registers_data)
        )

        return self.Response(registers)


@dataclass
class WriteSingleRegisterSDU(ModbusRequestSDU):
    """Write single register request."""

    address: int
    value: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

    def function_code(self) -> FunctionCode:
        return FunctionCode.WRITE_SINGLE_REGISTER

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid address",
            3: "Invalid register value",
            4: "Couldn't write register",
        }

    def __post_init__(self) -> None:
        _check_address(self.address)
        if not 0 <= self.value <= 0xFFFF:
            raise ValueError(f"Invalid register value : {self.value}")

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHH",
            self.function_code().value,
            _dm_to_pdu_address(self.address),
            self.value,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        if sdu != self.make_sdu():
            raise ProtocolReadError(
                f"Response ({sdu!r}) should match query ({self.make_sdu()!r})"
            )
        return self.Response()


@dataclass
class ReadExceptionStatusSDU(SerialLineOnlySDU):
    """Read exception status request (serial only)."""

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        status: int

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_EXCEPTION_STATUS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            4: "Couldn't read exception status",
        }

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code().value)

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        _, status = cast(tuple[int, int], struct.unpack(ENDIAN + "BB", sdu))
        return self.Response(status)


@dataclass
class DiagnosticsSDU(SerialLineOnlySDU):
    """Diagnostics request (serial only)."""

    code: DiagnosticsCode
    subfunction_data: bytes
    return_subfunction_bytes: int
    check_response: bool = True

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        data: bytes

    def function_code(self) -> FunctionCode:
        return FunctionCode.DIAGNOSTICS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Unsuported function code or sub-function code",
            3: "Invalid data value",
            4: "Diagnostic error",
        }

    def make_sdu(self) -> bytes:
        return (
            struct.pack(ENDIAN + "BH", self.function_code().value, self.code.value)
            + self.subfunction_data
        )

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)

        if self.return_subfunction_bytes == 0:
            returned_function, returned_subfunction_integer = struct.unpack(
                ENDIAN + "BH", sdu
            )
            subfunction_returned_data = b""
        else:
            (
                returned_function,
                returned_subfunction_integer,
                subfunction_returned_data,
            ) = cast(
                tuple[int, int, bytes],
                struct.unpack(ENDIAN + f"BH{self.return_subfunction_bytes}s", sdu),
            )

        if self.check_response:
            returned_subfunction = DiagnosticsCode(returned_subfunction_integer)

            if returned_function != self.function_code().value:
                raise ProtocolReadError(
                    f"Invalid returned function code : {returned_function}"
                )
            if returned_subfunction != self.code:
                raise ProtocolReadError(
                    f"Invalid returned subfunction code : {returned_subfunction}"
                )

        return self.Response(subfunction_returned_data)


@dataclass
class GetCommEventCounterSDU(SerialLineOnlySDU):
    """Get communication event counter request (serial only)."""

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        status: int
        event_count: int

    def function_code(self) -> FunctionCode:
        return FunctionCode.GET_COMM_EVENT_COUNTER

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            4: "Couldn't get comm event counter",
        }

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code().value)

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        _, status, event_count = struct.unpack(ENDIAN + "BHH", sdu)
        return self.Response(status, event_count)


@dataclass
class GetCommEventLogSDU(SerialLineOnlySDU):
    """Get communication event log request (serial only)."""

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        status: int
        event_count: int
        message_count: int
        events: bytes

    def function_code(self) -> FunctionCode:
        return FunctionCode.GET_COMM_EVENT_LOG

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            4: "Couldn't get comm event log",
        }

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code().value)

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        status, event_count, message_count = struct.unpack(ENDIAN + "HHH", sdu[2:8])
        events = sdu[8 : 8 + (byte_count - 6)]
        return self.Response(status, event_count, message_count, events)


@dataclass
class WriteMultipleCoilsSDU(ModbusRequestSDU):
    """Write multiple coils request."""

    start_address: int
    values: list[bool]

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

    def function_code(self) -> FunctionCode:
        return FunctionCode.WRITE_MULTIPLE_COILS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid start and/or end addresses",
            3: "Invalid number of outputs and/or byte count",
            4: "Couldn't write outputs",
        }

    def __post_init__(self) -> None:
        number_of_coils = len(self.values)
        _check_discrete_input_output_count(number_of_coils)
        _check_address(self.start_address, MAX_ADDRESS - number_of_coils + 1)

    def make_sdu(self) -> bytes:
        number_of_coils = len(self.values)
        byte_count = ceil(number_of_coils / 8)
        sdu = struct.pack(
            ENDIAN + f"BHHB{byte_count}s",
            self.function_code().value,
            _dm_to_pdu_address(self.start_address),
            number_of_coils,
            byte_count,
            bool_list_to_bytes(self.values),
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)

        _, start_address, coils_written = struct.unpack(ENDIAN + "BHH", sdu)
        if coils_written != len(self.values):
            raise ProtocolError(
                f"Number of coils written ({coils_written}) doesn't match expected "
                f"value : {len(self.values)}"
            )
        if start_address != _dm_to_pdu_address(self.start_address):
            raise ProtocolReadError(
                f"Start address mismatch : {start_address} != "
                "{_dm_to_pdu_address(self.start_address)}"
            )
        return self.Response()


@dataclass
class WriteMultipleRegistersSDU(ModbusRequestSDU):
    """Write multiple registers request."""

    start_address: int
    values: list[int]

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

    def function_code(self) -> FunctionCode:
        return FunctionCode.WRITE_MULTIPLE_REGISTERS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid start and/or end addresses",
            3: "Invalid number of outputs and/or byte count",
            4: "Couldn't write outputs",
        }

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
            self.function_code().value,
            _dm_to_pdu_address(self.start_address),
            byte_count // 2,
            byte_count,
            *self.values,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)

        _, start_address, registers_written = struct.unpack(ENDIAN + "BHH", sdu)
        if registers_written != len(self.values):
            raise ProtocolError(
                f"Number of registers written ({registers_written}) doesn't match expected "
                f"value : {len(self.values)}"
            )
        if start_address != _dm_to_pdu_address(self.start_address):
            raise ProtocolReadError(
                f"Start address mismatch : {start_address} != "
                "{_dm_to_pdu_address(self.start_address)}"
            )
        return self.Response()


@dataclass
class ReportServerIdSDU(SerialLineOnlySDU):
    """Report server ID request (serial only)."""

    server_id_length: int
    additional_data_length: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        server_id: bytes
        run_indicator_status: bool
        additional_data: bytes

    def function_code(self) -> FunctionCode:
        return FunctionCode.REPORT_SERVER_ID

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            4: "Couldn't report slave ID",
        }

    def make_sdu(self) -> bytes:
        return struct.pack(ENDIAN + "B", self.function_code().value)

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        expected = self.server_id_length + 1 + self.additional_data_length
        if byte_count != expected:
            raise ProtocolReadError(
                f"Invalid byte count : {byte_count}, expected {expected}"
            )
        start = 2
        end = start + self.server_id_length
        server_id = sdu[start:end]
        run_indicator_status = sdu[end] == 0xFF
        additional_data = sdu[end + 1 : end + 1 + self.additional_data_length]
        return self.Response(server_id, run_indicator_status, additional_data)


@dataclass
class ReadFileRecordSDU(ModbusRequestSDU):
    """Read file record request."""

    records: list[tuple[int, int, int]]

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        records_data: list[bytes]

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_FILE_RECORD

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid parameters",
            3: "Invalid byte count",
            4: "Couldn't read records",
        }

    def __post_init__(self) -> None:
        size_limit = 253
        query_size = 2 + 7 * len(self.records)
        response_size = 2 + len(self.records) + sum(2 * r[2] for r in self.records)
        if query_size > size_limit:
            raise ValueError(f"Number of records is too high : {len(self.records)}")
        if response_size > size_limit:
            raise ValueError(
                f"Sum of records lenghts is too high : {sum(r[2] for r in self.records)}"
            )

    def make_sdu(self) -> bytes:
        reference_type = 6
        sub_req_buffer = b""
        for file_number, record_number, record_length in self.records:
            sub_req_buffer += struct.pack(
                ENDIAN + "BHHH",
                reference_type,
                file_number,
                record_number,
                record_length,
            )

        byte_count = len(sub_req_buffer)
        sdu = struct.pack(
            ENDIAN + f"BB{byte_count}s",
            self.function_code().value,
            byte_count,
            sub_req_buffer,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        records_data: list[bytes] = []
        offset = 2
        end = 2 + byte_count
        while offset < end:
            length = sdu[offset]
            reference_type = sdu[offset + 1]
            if reference_type != 6:
                raise ProtocolReadError(f"Invalid reference type : {reference_type}")
            data_start = offset + 2
            data_end = data_start + length - 1
            records_data.append(sdu[data_start:data_end])
            offset = data_end

        return self.Response(records_data)


@dataclass
class WriteFileRecordSDU(ModbusRequestSDU):
    """Write file record request."""

    records: list[tuple[int, int, bytes]]

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

    def function_code(self) -> FunctionCode:
        return FunctionCode.WRITE_FILE_RECORD

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid parameters",
            3: "Invalid byte count",
            4: "Couldn't write records",
        }

    def __post_init__(self) -> None:
        if isinstance(self.records, tuple):
            self.records = [self.records]
        elif not isinstance(self.records, list):
            raise TypeError(f"Invalid records type : {self.records}")

    def make_sdu(self) -> bytes:
        reference_type = 6
        sub_req_buffer = b""

        for file_number, record_number, data in self.records:
            sub_req_buffer += struct.pack(
                ENDIAN + f"BHHH{len(data)}s",
                reference_type,
                file_number,
                record_number,
                len(data) // 2,
                data,
            )

        sdu = struct.pack(
            ENDIAN + f"BB{len(sub_req_buffer)}s",
            self.function_code().value,
            len(sub_req_buffer),
            sub_req_buffer,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        if sdu != self.make_sdu():
            raise ProtocolReadError("Response different from query")
        return self.Response()


@dataclass
class MaskWriteRegisterSDU(ModbusRequestSDU):
    """Mask write register request."""

    address: int
    and_mask: int
    or_mask: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

    def function_code(self) -> FunctionCode:
        return FunctionCode.MASK_WRITE_REGISTER

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid register address",
            3: "Invalid AND/OR mask",
            4: "Couldn't write register",
        }

    def __post_init__(self) -> None:
        _check_address(self.address)

    def make_sdu(self) -> bytes:
        sdu = struct.pack(
            ENDIAN + "BHHH",
            self.function_code().value,
            _dm_to_pdu_address(self.address),
            self.and_mask,
            self.or_mask,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        if sdu != self.make_sdu():
            raise ProtocolReadError(
                f"Response ({sdu!r}) should match query ({self.make_sdu()!r})"
            )
        return self.Response()


@dataclass
class ReadWriteMultipleRegistersSDU(ModbusRequestSDU):
    """Read/write multiple registers request."""

    read_starting_address: int
    number_of_read_registers: int
    write_starting_address: int
    write_values: list[int]

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        read_values: list[int]

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_WRITE_MULTIPLE_REGISTERS

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid read/write start/end address",
            3: "Invalid quantity of read/write and/or byte count",
            4: "Couldn't read and/or write registers",
        }

    def __post_init__(self) -> None:
        max_number_read_registers = (AVAILABLE_PDU_SIZE - 2) // 2
        max_numbers_write_registers = (AVAILABLE_PDU_SIZE - 10) // 2

        if not 1 <= self.number_of_read_registers <= max_number_read_registers:
            raise ValueError(
                f"Invalid number of read registers : {self.number_of_read_registers}"
            )

        if not 1 <= len(self.write_values) <= max_numbers_write_registers:
            raise ValueError(
                f"Invalid number of write registers : {self.number_of_read_registers}"
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
            self.function_code().value,
            _dm_to_pdu_address(self.read_starting_address),
            self.number_of_read_registers,
            _dm_to_pdu_address(self.write_starting_address),
            len(self.write_values),
            len(self.write_values) * 2,
            *self.write_values,
        )
        return sdu

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        _, byte_count = struct.unpack(ENDIAN + "BB", sdu[:2])
        expected = self.number_of_read_registers * 2
        if byte_count != expected:
            raise ProtocolReadError(
                f"Invalid byte count : {byte_count}, expected {expected}"
            )
        read_values = list(
            struct.unpack(ENDIAN + f"{self.number_of_read_registers}H", sdu[2:])
        )
        return self.Response(read_values)


@dataclass
class ReadFifoQueueSDU(ModbusRequestSDU):
    """Read FIFO queue request."""

    fifo_address: int

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        values: list[int]

    def function_code(self) -> FunctionCode:
        return FunctionCode.READ_FIFO_QUEUE

    def exceptions(self) -> dict[int, str]:
        return {
            1: "Function code not supported",
            2: "Invalid FIFO address",
            3: "Invalid FIFO count (>31)",
            4: "Couldn't read FIFO queue",
        }

    def __post_init__(self) -> None:
        _check_address(self.fifo_address)

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + "BH",
            self.function_code().value,
            _dm_to_pdu_address(self.fifo_address),
        )

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        _, byte_count = struct.unpack(ENDIAN + "BH", sdu[:3])
        fifo_count = struct.unpack(ENDIAN + "H", sdu[3:5])[0]
        register_count = byte_count // 2 - 1
        if fifo_count != register_count:
            raise ProtocolReadError(
                f"FIFO count mismatch : {fifo_count} != {register_count}"
            )
        values = list(struct.unpack(ENDIAN + f"{register_count}H", sdu[5:]))
        return self.Response(values)


@dataclass
class EncapsulatedInterfaceTransportSDU(ModbusRequestSDU):
    """Encapsulated interface transport request."""

    mei_type: int
    mei_data: bytes
    extra_exceptions: dict[int, str] | None = None

    @dataclass
    class Response(ModbusSDU):
        """Response data."""

        data: bytes

    def function_code(self) -> FunctionCode:
        return FunctionCode.ENCAPSULATED_INTERFACE_TRANSPORT

    def exceptions(self) -> dict[int, str]:
        exceptions = {1: "Function code not supported"}
        if self.extra_exceptions is not None:
            exceptions.update(self.extra_exceptions)
        return exceptions

    def make_sdu(self) -> bytes:
        return struct.pack(
            ENDIAN + f"BB{len(self.mei_data)}s",
            self.function_code().value,
            self.mei_type,
            self.mei_data,
        )

    def parse_sdu(self, sdu: bytes) -> ModbusSDU:
        self._check_for_error(sdu)
        return self.Response(sdu[2:])


class ModbusFrame(ProtocolFrame[ModbusSDU]):
    """Modbus frame containing a ModbusSDU"""

    payload: ModbusSDU

    def __str__(self) -> str:
        return f"ModbusFrame({self.payload})"


# pylint: disable=too-many-public-methods
class Modbus(Protocol[ModbusSDU]):
    """
    Modbus protocol

    Parameters
    ----------
    adapter : Adapter
        SerialPort or IP
    timeout : Timeout
    _type : str
        Only used with SerialPort adapter
        'RTU' : Modbus RTU (default)
        'ASCII' : Modbus ASCII
    """

    def __init__(
        self,
        adapter: Adapter,
        timeout: Timeout | None | EllipsisType = ...,
        _type: str = ModbusType.RTU.value,
        slave_address: int | None = None,
    ) -> None:
        super().__init__(adapter, timeout)
        self._logger.debug("Initializing Modbus protocol...")

        if isinstance(adapter, IP):
            self._adapter: IP
            self._adapter.set_default_port(MODBUS_TCP_DEFAULT_PORT)
            self._modbus_type = ModbusType.TCP
        elif isinstance(adapter, SerialPort):
            self._modbus_type = ModbusType(_type)
            if slave_address is None:
                raise ValueError("slave_address must be set")
            raise NotImplementedError("Serialport (Modbus RTU) is not supported yet")
        else:
            raise ValueError("Invalid adapter")

        self._slave_address = slave_address

        self._last_sdu: ModbusSDU | None = None
        self._transaction_id = 0

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=1, action="error")

    def _on_event(self, event: AdapterEvent) -> None: ...

    def _protocol_to_adapter(self, protocol_payload: ModbusSDU) -> bytes:
        if isinstance(protocol_payload, SerialLineOnlySDU):
            if self._modbus_type == ModbusType.TCP:
                raise ProtocolError("This function cannot be used with Modbus TCP")

        sdu = protocol_payload.make_sdu()

        if self._modbus_type == ModbusType.TCP:
            # Return raw data
            length = len(sdu) + 1  # unit_id is included
            output = (
                struct.pack(
                    ENDIAN + "HHHB", self._transaction_id, _PROTOCO_ID, length, _UNIT_ID
                )
                + sdu
            )
        else:
            # Add slave address and error check
            error_check = modbus_crc(sdu)
            output = (
                struct.pack(ENDIAN + "B", self._slave_address)
                + sdu
                + struct.pack(ENDIAN + "H", error_check)
            )
            if self._modbus_type == ModbusType.ASCII:
                # Add header and trailer
                output = _ASCII_HEADER + output + _ASCII_TRAILER

        self._transaction_id += 1

        self._last_sdu = protocol_payload
        return output

    def _adapter_to_protocol(
        self, adapter_frame: AdapterFrame
    ) -> ProtocolFrame[ModbusSDU]:
        pdu = adapter_frame.get_payload()

        if self._modbus_type == ModbusType.TCP:
            # transaction_id, protocol_id, length, unit_id = struct.unpack(
            #     "HHHB",
            #     pdu[:7]
            # )
            data = pdu[7:]
            # len(data) should match length variable
        else:
            if self._modbus_type == ModbusType.ASCII:
                # Remove header and trailer
                pdu = pdu[len(_ASCII_HEADER) : -len(_ASCII_TRAILER)]
            # Remove slave address and CRC and check CRC

            # slave_address = pdu[0]
            data = pdu[1:-2]
            # crc = pdu[-2:] # TODO : Check CRC

        if self._last_sdu is None:
            raise ModbusError("Cannot read without prior write")

        # It is necessary to know the previous SDU because some information cannot
        # be parsed from the response only (like the number of coils from a read_coils
        # command)
        sdu = self._last_sdu.parse_sdu(data)

        return ModbusFrame(
            stop_timestamp=adapter_frame.stop_timestamp,
            stop_condition_type=adapter_frame.stop_condition_type,
            previous_read_buffer_used=adapter_frame.previous_read_buffer_used,
            response_delay=adapter_frame.response_delay,
            payload=sdu,
        )

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
        payload = ReadCoilsSDU(
            start_address=start_address, number_of_coils=number_of_coils
        )

        output = cast(ReadCoilsSDU.Response, self.query(payload))

        return output.coils

    async def aread_coils(self, start_address: int, number_of_coils: int) -> list[bool]:
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

        payload = ReadCoilsSDU(
            start_address=start_address, number_of_coils=number_of_coils
        )

        output = cast(ReadCoilsSDU.Response, await self.aquery(payload))

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

    async def aread_single_coil(self, address: int) -> bool:
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
        coil = (await self.aread_coils(start_address=address, number_of_coils=1))[0]
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

        payload = ReadDiscreteInputs(
            start_address=start_address, number_of_inputs=number_of_inputs
        )

        output = cast(ReadDiscreteInputs.Response, self.query(payload))

        return output.inputs

    async def aread_discrete_inputs(
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

        payload = ReadDiscreteInputs(
            start_address=start_address, number_of_inputs=number_of_inputs
        )

        output = cast(ReadDiscreteInputs.Response, await self.aquery(payload))

        return output.inputs

    # Read Holding Registers - 0x03
    def read_holding_registers(
        self, start_address: int, number_of_registers: int
    ) -> list[int]:
        """
        Reads a defined number of registers starting at a set address

        Parameters
        ----------
        start_address : int
        number_of_registers : int
            1 to 125

        Returns
        -------
        registers : list
        """

        payload = ReadHoldingRegisters(
            start_address=start_address, number_of_registers=number_of_registers
        )

        output = cast(ReadHoldingRegisters.Response, self.query(payload))

        return output.registers

    async def aread_holding_registers(
        self, start_address: int, number_of_registers: int
    ) -> list[int]:
        """
        Asynchronously Reads a defined number of registers starting at a set address

        Parameters
        ----------
        start_address : int
        number_of_registers : int
            1 to 125

        Returns
        -------
        registers : list
        """

        payload = ReadHoldingRegisters(
            start_address=start_address, number_of_registers=number_of_registers
        )

        output = cast(ReadHoldingRegisters.Response, await self.aquery(payload))

        return output.registers

    def _parse_multi_register_value(
        self,
        n_registers: int,
        registers: list[int],
        value_type: str,
        *,
        byte_order: str = Endian.BIG.value,
        word_order: str = Endian.BIG.value,
        encoding: str = "utf-8",
        padding: int | None = 0,
    ) -> str | bytes | int | float:

        type_cast = TypeCast(value_type)
        _byte_order = Endian(byte_order)
        if type_cast.is_number():
            _word_order = Endian(word_order)
        else:
            _word_order = Endian.BIG
        # Create a buffer
        to_bytes_endian = Endian.BIG if _byte_order == _word_order else Endian.LITTLE
        buffer = b"".join(
            [x.to_bytes(2, byteorder=to_bytes_endian.value) for x in registers]
        )
        # Use struct_format to convert to the corresponding value directly
        # Swap the buffer accordingly
        data: bytes | int | float = struct.unpack(
            endian_symbol[_word_order] + struct_format(type_cast, n_registers * 2),
            buffer,
        )[0]

        # If data is a string, do additionnal processing
        output: bytes | int | float | str
        if type_cast == TypeCast.STRING:
            data = cast(bytes, data)
            # If null termination is enabled, remove any \0
            if padding is not None and padding in data:
                data = data[: data.index(padding)]
            # Cast
            output = data.decode(encoding)
        else:
            output = data

        return output

    def read_multi_register_value(
        self,
        address: int,
        n_registers: int,
        value_type: str,
        *,
        byte_order: str = Endian.BIG.value,
        word_order: str = Endian.BIG.value,
        encoding: str = "utf-8",
        padding: int | None = 0,
    ) -> str | bytes | int | float:
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
            start_address=address, number_of_registers=n_registers
        )

        return self._parse_multi_register_value(
            n_registers=n_registers,
            registers=registers,
            value_type=value_type,
            byte_order=byte_order,
            word_order=word_order,
            encoding=encoding,
            padding=padding,
        )

    async def aread_multi_register_value(
        self,
        address: int,
        n_registers: int,
        value_type: str,
        *,
        byte_order: str = Endian.BIG.value,
        word_order: str = Endian.BIG.value,
        encoding: str = "utf-8",
        padding: int | None = 0,
    ) -> str | bytes | int | float:
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
        registers = await self.aread_holding_registers(
            start_address=address, number_of_registers=n_registers
        )

        return self._parse_multi_register_value(
            n_registers=n_registers,
            registers=registers,
            value_type=value_type,
            byte_order=byte_order,
            word_order=word_order,
            encoding=encoding,
            padding=padding,
        )

    def _make_multi_register_value(
        self,
        n_registers: int,
        value_type: str,
        value: str | bytes | int | float,
        *,
        byte_order: str = Endian.BIG.value,
        word_order: str = Endian.BIG.value,
        encoding: str = "utf-8",
        padding: int = 0,
    ) -> list[int]:
        _type = TypeCast(value_type)
        n_bytes = n_registers * 2
        if _type.is_number():
            _word_order = Endian(word_order)
        else:
            _word_order = Endian.BIG
        _byte_order = Endian(byte_order)

        array = b""
        if _type in [TypeCast.INT, TypeCast.UINT, TypeCast.FLOAT]:
            # Make one big array using word_order endian
            array = struct.pack(
                endian_symbol[_word_order] + struct_format(_type, n_bytes), value
            )

        elif _type == TypeCast.ARRAY:
            if isinstance(value, bytes):
                if len(value) > n_registers * 2:
                    raise ValueError(
                        f"Cannot store {len(value)} bytes array in {n_registers} registers"
                    )
            else:
                raise ValueError(f"Invalid value type : {type(value)}")

            array = value
        elif _type == TypeCast.STRING:
            if isinstance(value, str):
                array = value.encode(encoding)
            else:
                raise ValueError(f"Invalid value type : {type(value)}")

            if len(array) < n_bytes:
                # Padding
                array = array + padding.to_bytes(1, byteorder="big") * (
                    n_bytes - len(value)
                )

        if len(array) != n_registers * 2:
            raise ValueError(
                f"Cannot store a {len(array)} bytes array in {n_registers} registers"
            )

        unpack_endian = Endian.BIG if _byte_order == _word_order else Endian.LITTLE
        registers = [
            struct.unpack(endian_symbol[unpack_endian] + "H", array[2 * i : 2 * i + 2])[
                0
            ]
            for i in range(len(array) // 2)
        ]

        return registers

    def write_multi_register_value(
        self,
        address: int,
        n_registers: int,
        value_type: str,
        value: str | bytes | int | float,
        *,
        byte_order: str = Endian.BIG.value,
        word_order: str = Endian.BIG.value,
        encoding: str = "utf-8",
        padding: int = 0,
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

        registers = self._make_multi_register_value(
            n_registers=n_registers,
            value_type=value_type,
            value=value,
            byte_order=byte_order,
            word_order=word_order,
            encoding=encoding,
            padding=padding,
        )

        self.write_multiple_registers(start_address=address, values=registers)

    async def awrite_multi_register_value(
        self,
        address: int,
        n_registers: int,
        value_type: str,
        value: str | bytes | int | float,
        *,
        byte_order: str = Endian.BIG.value,
        word_order: str = Endian.BIG.value,
        encoding: str = "utf-8",
        padding: int = 0,
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

        registers = self._make_multi_register_value(
            n_registers=n_registers,
            value_type=value_type,
            value=value,
            byte_order=byte_order,
            word_order=word_order,
            encoding=encoding,
            padding=padding,
        )

        await self.awrite_multiple_registers(start_address=address, values=registers)

    # Read Input Registers - 0x04
    def read_input_registers(
        self, start_address: int, number_of_registers: int
    ) -> list[int]:
        """
        Reads a defined number of input registers starting at a set address

        Parameters
        ----------
        start_address : int
        number_of_registers : int
            1 to 125

        Returns
        -------
        registers : list
            List of integers
        """
        payload = ReadInputRegistersSDU(
            start_address=start_address,
            number_of_registers=number_of_registers,
        )

        output = cast(ReadInputRegistersSDU.Response, self.query(payload))

        return output.registers

    async def aread_input_registers(
        self, start_address: int, number_of_registers: int
    ) -> list[int]:
        """
        Asynchronously read a defined number of input registers starting at a set address

        Parameters
        ----------
        start_address : int
        number_of_registers : int
            1 to 125

        Returns
        -------
        registers : list
            List of integers
        """
        payload = ReadInputRegistersSDU(
            start_address=start_address,
            number_of_registers=number_of_registers,
        )

        output = cast(ReadInputRegistersSDU.Response, await self.aquery(payload))

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
        payload = WriteSingleCoilSDU(address=address, status=status)

        self.query(payload)

    async def awrite_single_coil(self, address: int, status: bool) -> None:
        """
        Asynchronously write a single output to either ON or OFF

        Parameters
        ----------
        address : int
        status : bool
        """
        payload = WriteSingleCoilSDU(address=address, status=status)

        await self.aquery(payload)

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
        payload = WriteSingleRegisterSDU(
            address=address,
            value=value,
        )

        self.query(payload)

    async def awrite_single_register(self, address: int, value: int) -> None:
        """
        Asynchronously write a single register

        Parameters
        ----------
        address : int
        value : int
            value between 0x0000 and 0xFFFF
        """
        payload = WriteSingleRegisterSDU(
            address=address,
            value=value,
        )

        await self.aquery(payload)

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
        payload = ReadExceptionStatusSDU()

        output = cast(ReadExceptionStatusSDU.Response, self.query(payload))

        return output.status

    async def aread_exception_status(self) -> int:
        """
        Asynchronously read exeption status

        Returns
        -------
        exceptions : int
        """
        payload = ReadExceptionStatusSDU()

        output = cast(ReadExceptionStatusSDU.Response, await self.aquery(payload))

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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_QUERY_DATA,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return output.data == subfunction_data

    async def adiagnostics_return_query_data(self, data: int = 0x1234) -> bool:
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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_QUERY_DATA,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        self.query(payload)

    async def adiagnostics_restart_communications_option(
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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        await self.aquery(payload)

    def diagnostics_return_diagnostic_register(self) -> int:
        """
        Return 16 bit diagnostic register

        Returns
        -------
        register : int
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_diagnostic_register(self) -> int:
        """
        Asynchronously return 16 bit diagnostic register

        Returns
        -------
        register : int
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.CHANGE_ASCII_INPUT_DELIMITER,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        self.query(payload)

    async def adiagnostics_change_ascii_input_delimiter(
        self, char: bytes | str
    ) -> None:
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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.CHANGE_ASCII_INPUT_DELIMITER,
            subfunction_data=subfunction_data,
            return_subfunction_bytes=2,
        )

        await self.aquery(payload)

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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.FORCE_LISTEN_ONLY_MODE,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
            check_response=False,
        )

        self.query(payload)

    async def adiagnostics_force_listen_only_mode(self) -> None:
        """
        Asynchronously force the addressed remote device to its Listen Only Mode
        for MODBUS communications.
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.FORCE_LISTEN_ONLY_MODE,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
            check_response=False,
        )

        await self.aquery(payload)

    def diagnostics_clear_counters_and_diagnostic_register(self) -> None:
        """
        Clear all counters and the diagnostic register
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
        )

        self.query(payload)

    async def adiagnostics_clear_counters_and_diagnostic_register(self) -> None:
        """
        Asynchronously clear all counters and the diagnostic register
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
        )

        await self.aquery(payload)

    def diagnostics_return_bus_message_count(self) -> int:
        """
        Return the number of messages that the remote device has detection on the communications
        system since its last restat, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_bus_message_count(self) -> int:
        """
        Asynchronously return the number of messages that the remote device has detection on the
        communications system since its last restat, clear counters operation, or power-up
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_bus_communication_error_count(self) -> int:
        """
        Return the number of messages that the remote device has detection on the communications
        system since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_bus_communication_error_count(self) -> int:
        """
        Asynchronously return the number of messages that the remote device has detection on the
        communications system since its last restart, clear counters operation, or power-up
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_bus_exception_error_count(self) -> int:
        """
        Return the number of Modbus exceptions responses returned by the remote device since
        its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_bus_exception_error_count(self) -> int:
        """
        Asynchronously return the number of Modbus exceptions responses returned by the remote
        device since its last restart, clear counters operation, or power-up
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_return_server_no_response_count(self) -> int:
        """
        Return the number of messages addressed to the remote device for which it has returned
        no response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_server_no_response_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device for which it
        has returned no response since its last restart, clear counters operation, or power-up
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_SERVER_NAK_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_server_nak_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device for which it
        returned a negative acnowledge (NAK) exception response since its last restart,
        clear counters operation, or power-up
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_SERVER_NAK_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_SERVER_BUSY_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_server_busy_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device for which it
        returned a server device busy exception response since its last restart, clear counters
        operation, or power-up
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_SERVER_BUSY_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

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
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, self.query(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    async def adiagnostics_return_bus_character_overrun_count(self) -> int:
        """
        Asynchronously return the number of messages addressed to the remote device that it could
        not handle due to a character overrun condition since its last restart, clear counters
        operation, or power-up
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=2,
        )

        output = cast(DiagnosticsSDU.Response, await self.aquery(payload))

        return int(struct.unpack(ENDIAN + "H", output.data)[0])

    def diagnostics_clear_overrun_counter_and_flag(self) -> None:
        """
        Clear the overrun error counter and reset the error flag
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.CLEAR_OVERRUN_COUNTER_AND_FLAG,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
        )

        self.query(payload)

    async def adiagnostics_clear_overrun_counter_and_flag(self) -> None:
        """
        Asynchronously clear the overrun error counter and reset the error flag
        """
        payload = DiagnosticsSDU(
            code=DiagnosticsCode.CLEAR_OVERRUN_COUNTER_AND_FLAG,
            subfunction_data=b"\x00\x00",
            return_subfunction_bytes=0,
        )

        await self.aquery(payload)

    # Get Comm Event Counter - 0x0B
    def get_comm_event_counter(self) -> tuple[int, int]:
        """
        Retrieve status word and event count from the remote device's communication event counter

        Returns
        -------
        status : int
        event_count : int
        """
        payload = GetCommEventCounterSDU()

        output = cast(GetCommEventCounterSDU.Response, self.query(payload))

        return output.status, output.event_count

    async def aget_comm_event_counter(self) -> tuple[int, int]:
        """
        Asynchronously retrieve status word and event count from the remote device's
        communication event counter
        """
        payload = GetCommEventCounterSDU()

        output = cast(GetCommEventCounterSDU.Response, await self.aquery(payload))

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
        payload = GetCommEventLogSDU()

        output = cast(GetCommEventLogSDU.Response, self.query(payload))

        return output.status, output.event_count, output.message_count, output.events

    async def aget_comm_event_log(self) -> tuple[int, int, int, bytes]:
        """
        Asynchronously retrieve status word, event count, message count and a field of event bytes
        from the remote device
        """
        payload = GetCommEventLogSDU()

        output = cast(GetCommEventLogSDU.Response, await self.aquery(payload))

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
        payload = WriteMultipleCoilsSDU(
            start_address=start_address,
            values=values,
        )

        self.query(payload)

    async def awrite_multiple_coils(
        self, start_address: int, values: list[bool]
    ) -> None:
        """
        Asynchronously write multiple coil values
        """
        payload = WriteMultipleCoilsSDU(
            start_address=start_address,
            values=values,
        )

        await self.aquery(payload)

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
        payload = WriteMultipleRegistersSDU(
            start_address=start_address,
            values=values,
        )

        self.query(payload)

    async def awrite_multiple_registers(
        self, start_address: int, values: list[int]
    ) -> None:
        """
        Asynchronously write multiple registers
        """
        payload = WriteMultipleRegistersSDU(
            start_address=start_address,
            values=values,
        )

        await self.aquery(payload)

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
        payload = ReportServerIdSDU(
            server_id_length=server_id_length,
            additional_data_length=additional_data_length,
        )

        output = cast(ReportServerIdSDU.Response, self.query(payload))

        return output.server_id, output.run_indicator_status, output.additional_data

    async def areport_server_id(
        self, server_id_length: int, additional_data_length: int
    ) -> tuple[bytes, bool, bytes]:
        """
        Asynchronously read description of the type, current status and other information specific
        to a remote device
        """
        payload = ReportServerIdSDU(
            server_id_length=server_id_length,
            additional_data_length=additional_data_length,
        )

        output = cast(ReportServerIdSDU.Response, await self.aquery(payload))

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
        payload = ReadFileRecordSDU(records=records)

        output = cast(ReadFileRecordSDU.Response, self.query(payload))

        return output.records_data

    async def aread_file_record(
        self, records: list[tuple[int, int, int]]
    ) -> list[bytes]:
        """
        Asynchronously perform a single or multiple file record read
        """
        payload = ReadFileRecordSDU(records=records)

        output = cast(ReadFileRecordSDU.Response, await self.aquery(payload))

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
        payload = WriteFileRecordSDU(records=records)

        self.query(payload)

    async def awrite_file_record(self, records: list[tuple[int, int, bytes]]) -> None:
        """
        Asynchronously perform a single or multiple file record write
        """
        payload = WriteFileRecordSDU(records=records)

        await self.aquery(payload)

    # Mask Write Register - 0x16
    async def amask_write_register(
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
        payload = MaskWriteRegisterSDU(
            address=address,
            and_mask=and_mask,
            or_mask=or_mask,
        )

        await self.aquery(payload)

    def mask_write_register(self, address: int, and_mask: int, or_mask: int) -> None:
        """
        This function is used to modify the contents of a holding register using a
        combination of AND and OR masks applied to the current contents of the register.
        """
        payload = MaskWriteRegisterSDU(
            address=address,
            and_mask=and_mask,
            or_mask=or_mask,
        )

        self.query(payload)

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
        payload = ReadWriteMultipleRegistersSDU(
            read_starting_address=read_starting_address,
            number_of_read_registers=number_of_read_registers,
            write_starting_address=write_starting_address,
            write_values=write_values,
        )

        output = cast(ReadWriteMultipleRegistersSDU.Response, self.query(payload))

        return output.read_values

    async def aread_write_multiple_registers(
        self,
        read_starting_address: int,
        number_of_read_registers: int,
        write_starting_address: int,
        write_values: list[int],
    ) -> list[int]:
        """
        Asynchronously do a write, then a read operation, each on a specific set of registers.
        """
        payload = ReadWriteMultipleRegistersSDU(
            read_starting_address=read_starting_address,
            number_of_read_registers=number_of_read_registers,
            write_starting_address=write_starting_address,
            write_values=write_values,
        )

        output = cast(
            ReadWriteMultipleRegistersSDU.Response, await self.aquery(payload)
        )

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
        payload = ReadFifoQueueSDU(fifo_address=fifo_address)

        output = cast(ReadFifoQueueSDU.Response, self.query(payload))

        return output.values

    async def aread_fifo_queue(self, fifo_address: int) -> list[int]:
        """
        Asynchronously read the contents of a First-In-First-Out (FIFO) queue of registers
        """
        payload = ReadFifoQueueSDU(fifo_address=fifo_address)

        output = cast(ReadFifoQueueSDU.Response, await self.aquery(payload))

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
        payload = EncapsulatedInterfaceTransportSDU(
            mei_type=mei_type,
            mei_data=mei_data,
            extra_exceptions=extra_exceptions,
        )

        output = cast(EncapsulatedInterfaceTransportSDU.Response, self.query(payload))

        return output.data

    async def aencapsulated_interface_transport(
        self,
        mei_type: int,
        mei_data: bytes,
        extra_exceptions: dict[int, str] | None = None,
    ) -> bytes:
        """
        Asynchronously use the MODBUS Encapsulated Interface (MEI) Transport
        """
        payload = EncapsulatedInterfaceTransportSDU(
            mei_type=mei_type,
            mei_data=mei_data,
            extra_exceptions=extra_exceptions,
        )

        output = cast(
            EncapsulatedInterfaceTransportSDU.Response, await self.aquery(payload)
        )

        return output.data
