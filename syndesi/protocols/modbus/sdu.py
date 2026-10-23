# File : sdu.py
# Author : Sébastien Deriaz
# License : GPL
"""
Modbus SDUs (Service Data Units) : one request and one response class per
function code, each able to build and to parse itself, for a client and for a server
"""

# pylint: disable=too-many-lines

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import ceil
from typing import Any, Generic, TypeVar, cast

from ...tools.errors import ProtocolReadError
from .common import (
    AVAILABLE_PDU_SIZE,
    ENDIAN,
    EXCEPTION_FLAG,
    MAX_ADDRESS,
    DiagnosticsCode,
    FunctionCode,
    _check_address,
    _check_discrete_input_output_count,
    _dm_to_pdu_address,
    _exception_description,
    _pdu_to_dm_address,
    bool_list_to_bytes,
    bytes_to_bool_list,
)


class ModbusSDU:
    """
    Modbus Service Data Unit

    Subclasses of this contain either request or response fields to a modbus
    frame
    """

    function_code: int

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
    def make_sdu(self) -> bytes: ...

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
    def parse_sdu(sdu: bytes, request: RequestT) -> ModbusResponseSDU[RequestT]:
        """Generate a ModbusSDU instance from a given sdu buffer"""


class SerialLineOnlySDU(ModbusRequestSDU, ABC):
    """
    Marker class for serial line only Modbus function codes
    """


@dataclass
class ExceptionResponseSDU(ModbusResponseSDU[ModbusRequestSDU]):
    """
    Exception response, the answer to any request the server couldn't handle

    function_code is the one of the request, without the exception flag. exception_code
    is kept as an int, devices are free to use non standard codes
    """

    function_code: int
    exception_code: int

    @property
    def description(self) -> str:
        """Human readable description of the exception code"""
        return _exception_description(self.exception_code)

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
class ReadDiscreteInputsResponseSDU(ModbusResponseSDU[ReadDiscreteInputsRequestSDU]):
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


def _pack_registers_response(
    function_code: FunctionCode, registers: list[int]
) -> bytes:
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
class WriteSingleRegisterResponseSDU(ModbusResponseSDU[WriteSingleRegisterRequestSDU]):
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
        return struct.pack(ENDIAN + "BB", self.function_code, self.mei_type) + self.data

    @staticmethod
    def parse_sdu(
        sdu: bytes, request: EncapsulatedInterfaceTransportRequestSDU
    ) -> EncapsulatedInterfaceTransportResponseSDU:
        _, mei_type = struct.unpack(ENDIAN + "BB", sdu[:2])
        return EncapsulatedInterfaceTransportResponseSDU(mei_type, sdu[2:])


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
    (
        EncapsulatedInterfaceTransportRequestSDU,
        EncapsulatedInterfaceTransportResponseSDU,
    ),
]

REQUESTS = {req.function_code: req for req, _ in _SDU_PAIRS}
RESPONSES = {resp.function_code: resp for _, resp in _SDU_PAIRS}
