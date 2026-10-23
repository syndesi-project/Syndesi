# File : common.py
# Author : Sébastien Deriaz
# License : GPL
"""
Modbus constants, codes and errors, shared by every part of the implementation
"""

from __future__ import annotations

from enum import Enum, IntEnum, StrEnum
from math import ceil

from ...tools.errors import SyndesiError

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


class ModbusAddressError(ValueError):
    """An address, or a range of addresses, is outside of the data model"""


def _check_address(address: int, max_address: int | None = None) -> None:
    if not MIN_ADDRESS <= address <= MAX_ADDRESS:
        raise ModbusAddressError(
            f"Invalid address : {address}, it must be in the range "
            f"[{MIN_ADDRESS},{MAX_ADDRESS}]"
        )

    if max_address is not None:
        if address > max_address:
            raise ModbusAddressError(
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


class ModbusError(SyndesiError):
    """
    Generic modbus exception
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


def _exception_description(exception_code: int) -> str:
    if exception_code in _EXCEPTION_DESCRIPTIONS:
        return _EXCEPTION_DESCRIPTIONS[ExceptionCode(exception_code)]
    return "Unknown exception code"


class ModbusException(ModbusError):
    """
    Modbus exception, the error a server answers with

    Raised by a client that receives an exception response, and by a server handler
    to answer with one

    Parameters
    ----------
    exception_code : ExceptionCode or int
    description : str or None
        None for the standard description of the exception code
    """

    def __init__(self, exception_code: int, description: str | None = None) -> None:
        self.exception_code = exception_code
        if description is None:
            description = _exception_description(exception_code)
        super().__init__(f"{exception_code:02X} : {description}")
