# File : modbus.py
# Author : Sébastien Deriaz
# License : GPL
#
#
# Modbus TCP and Modbus RTU implementation

import struct
from enum import Enum
from math import ceil
from typing import cast
from unittest.mock import DEFAULT

from ..adapters.adapter import Adapter
from ..adapters.ip import IP
from ..adapters.serialport import SerialPort
from ..adapters.stop_condition import Continuation, Length
from ..adapters.timeout import Timeout
from .protocol import Protocol

MODBUS_TCP_DEFAULT_PORT = 502

MAX_ADDRESS = 0xFFFF
MIN_ADDRESS = 0x0001

MAX_DISCRETE_INPUTS = (
    0x07B0  # 1968. This is to ensure the total PDU length is 255 at most.
)
# This value has been checked and going up to 1976 seems to work but sticking to the
# spec is safer

# Specification says 125, but write_multiple_registers would exceed the allow number of bytes in that case
# MAX_NUMBER_OF_REGISTERS = 123

ExceptionCodesType = dict[int, str]


class Endian(Enum):
    BIG = "big"
    LITTLE = "little"


endian_symbol = {Endian.BIG: ">", Endian.LITTLE: "<"}


ENDIAN = endian_symbol[Endian.BIG]

# TCP
# 7 bytes + PDU
# RTU
# 1 byte + PDU + 2 bytes
# Worst case is 255 - 7 bytes = 248 bytes

# Size limitation only apply to Modbus RTU
AVAILABLE_PDU_SIZE = 255 - 3


class ModbusType(Enum):
    RTU = "RTU"
    ASCII = "ASCII"
    TCP = "TCP"


class FunctionCode(Enum):
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
    CANOPEN_GENERAL_REFERENCE_REQUEST_AND_RESPONSE_PDU = 0x0D
    READ_DEVICE_IDENTIFICATION = 0x0E


class DeviceIndentificationObjects(Enum):
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
    byte_count = ceil(len(lst) / 8)
    result: bytes = sum([2**i * int(v) for i, v in enumerate(lst)]).to_bytes(
        byte_count, byteorder="little"
    )
    return result


def bytes_to_bool_list(_bytes: bytes, N: int) -> list[bool]:
    return [
        True if c == "1" else False for c in "".join([f"{x:08b}"[::-1] for x in _bytes])
    ][:N]


class TypeCast(Enum):
    INT = "int"
    UINT = "uint"
    FLOAT = "float"
    STRING = "str"
    ARRAY = "array"

    def is_number(self) -> bool:
        return self in [TypeCast.INT, TypeCast.UINT, TypeCast.FLOAT]


def struct_format(type: TypeCast, length: int) -> str:
    if type == TypeCast.INT:
        if length == 1:
            return "b"
        elif length == 2:
            return "h"
        elif length == 4:
            return "i"  # or 'l'
        elif length == 8:
            return "q"
    elif type == TypeCast.UINT:
        if length == 1:
            return "B"
        elif length == 2:
            return "H"
        elif length == 4:
            return "I"  # or 'L'
        elif length == 8:
            return "Q"
    elif type == TypeCast.FLOAT:
        if length == 4:
            return "f"
        elif length == 8:
            return "d"
    elif type == TypeCast.STRING or type == TypeCast.ARRAY:
        return f"{length}s"
    else:
        raise ValueError(f"Unknown cast type : {type}")
    raise ValueError(f"Invalid type cast / length combination : {type} / {length}")


class ModbusException(Exception):
    pass


class Modbus(Protocol):
    _ASCII_HEADER = b":"
    _ASCII_TRAILER = b"\r\n"

    def __init__(
        self,
        adapter: Adapter,
        timeout: Timeout = DEFAULT,
        _type: str = ModbusType.RTU.value,
        slave_address: int | None = None,
    ) -> None:
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
        super().__init__(adapter, timeout)
        self._logger.debug("Initializing Modbus protocol...")

        if isinstance(adapter, IP):
            self._adapter: IP
            self._adapter.set_default_port(MODBUS_TCP_DEFAULT_PORT)
            self._modbus_type = ModbusType.TCP
        elif isinstance(adapter, SerialPort):
            self._modbus_type = ModbusType(_type)
            assert slave_address is not None, "slave_address must be set"
            raise NotImplementedError("Serialport (Modbus RTU) is not supported yet")
        else:
            raise ValueError("Invalid adapter")

        self._slave_address = slave_address

        self._transaction_id = 0

        # Connect the adapter if it wasn't done already
        self._adapter.connect()

    def _dm_to_pdu_address(self, dm_address: int) -> int:
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

    def _pdu_to_dm_address(self, pdu_address: int) -> int:
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

    def _crc(self, _bytes: bytes) -> int:
        # TODO : Implement
        return 0

    def _make_pdu(self, _bytes: bytes) -> bytes:
        """
        Return PDU generated from bytes data
        """
        PROTOCOL_ID = 0
        UNIT_ID = 0

        if self._modbus_type == ModbusType.TCP:
            # Return raw data
            # output = _bytes
            # Temporary :
            length = len(_bytes) + 1  # unit_id is included
            output = (
                struct.pack(
                    ENDIAN + "HHHB", self._transaction_id, PROTOCOL_ID, length, UNIT_ID
                )
                + _bytes
            )
            self._transaction_id += 1
        else:
            # Add slave address and error check
            error_check = self._crc(_bytes)
            output = (
                struct.pack(ENDIAN + "B", self._slave_address)
                + _bytes
                + struct.pack(ENDIAN + "H", error_check)
            )
            if self._modbus_type.ASCII:
                # Add header and trailer
                output = self._ASCII_HEADER + output + self._ASCII_TRAILER

        return output

    def _raise_if_error(
        self, response: bytes, exception_codes: ExceptionCodesType
    ) -> None:
        if response == b"":
            raise RuntimeError("Empty response")
        if response[0] & 0x80:
            # There is an error
            code = response[1]
            if code not in exception_codes:
                raise RuntimeError(f"Unexpected modbus error code: {code}")
            else:
                raise ModbusException(f"{code:02X} : {exception_codes[code]}")

    def _is_error(self, response: bytes) -> bool:
        raise NotImplementedError()

    def _error_code(self, response: bytes) -> int:
        return response[1]

    def _parse_pdu(self, _pdu: bytes | None) -> bytes:
        """
        Return data from PDU
        """
        if _pdu is None:
            raise RuntimeError("Failed to read modbus data")
        if self._modbus_type == ModbusType.TCP:
            # Return raw data
            # data = _pdu
            data = _pdu[7:]

        else:
            if self._modbus_type.ASCII:
                # Remove header and trailer
                _pdu = _pdu[len(self._ASCII_HEADER) : -len(self._ASCII_TRAILER)]
            # Remove slave address and CRC and check CRC

            data = _pdu[1:-2]
            # Check CRC
            # error_check = _pdu[-2:]
            # TODO : Check here and raise exception

        return data

    def _length(self, pdu_length: int) -> int:
        dummy_pdu = self._make_pdu(b"")
        return len(dummy_pdu) + pdu_length

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

        EXCEPTIONS: ExceptionCodesType = {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of outputs",
            4: "Couldn't read coils",
        }

        assert (
            1 <= number_of_coils <= MAX_DISCRETE_INPUTS
        ), f"Invalid number of coils : {number_of_coils}"
        assert (
            MIN_ADDRESS <= start_address <= MAX_ADDRESS - number_of_coils + 1
        ), f"Invalid start address : {start_address}"

        query = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.READ_COILS.value,
            self._dm_to_pdu_address(start_address),
            number_of_coils,
        )

        n_coil_bytes = ceil(number_of_coils / 8)
        pdu: bytes | None = self._adapter.query(
            self._make_pdu(query),
            # timeout=Timeout(continuation=1),
            stop_conditions=[
                Length(self._length(n_coil_bytes + 2)),
                Continuation(time=1),
            ],  # TODO : convert to multiple stop conditions here
        )
        response = self._parse_pdu(pdu)
        self._raise_if_error(response, exception_codes=EXCEPTIONS)

        _, _, coil_bytes = struct.unpack(ENDIAN + f"BB{n_coil_bytes}s", response)
        coils = bytes_to_bool_list(coil_bytes, number_of_coils)
        return coils

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

        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of inputs",
            4: "Couldn't read inputs",
        }

        assert (
            1 <= number_of_inputs <= MAX_DISCRETE_INPUTS
        ), f"Invalid number of inputs : {number_of_inputs}"
        assert (
            MIN_ADDRESS <= start_address <= MAX_ADDRESS - number_of_inputs + 1
        ), f"Invalid start address : {start_address}"

        query = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.READ_DISCRETE_INPUTS.value,
            self._dm_to_pdu_address(start_address),
            number_of_inputs,
        )
        byte_count = ceil(
            number_of_inputs / 8
        )  # pre-calculate the number of returned coil value bytes
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query),
                stop_conditions=Length(self._length(byte_count + 2)),
            )
        )
        self._raise_if_error(response, exception_codes=EXCEPTIONS)
        _, _, data = struct.unpack(ENDIAN + f"BB{byte_count}s", response)
        inputs = bytes_to_bool_list(data, number_of_inputs)
        return inputs

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
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of registers",
            4: "Couldn't read registers",
        }
        # Specification says 125, but the size would be exceeded over TCP. So 123 is safer
        MAX_NUMBER_OF_REGISTERS = (AVAILABLE_PDU_SIZE - 2) // 2

        assert (
            MIN_ADDRESS <= start_address <= MAX_ADDRESS - number_of_registers + 1
        ), f"Invalid start address : {start_address}"

        assert (
            1 <= number_of_registers <= MAX_NUMBER_OF_REGISTERS
        ), f"Invalid number of registers : {number_of_registers}"
        query = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.READ_HOLDING_REGISTERS.value,
            self._dm_to_pdu_address(start_address),
            number_of_registers,
        )
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query),
                stop_conditions=Length(self._length(2 + number_of_registers * 2)),
            )
        )
        self._raise_if_error(response, exception_codes=EXCEPTIONS)
        _, _, registers_data = struct.unpack(
            ENDIAN + f"BB{number_of_registers * 2}s", response
        )
        registers = list(
            struct.unpack(ENDIAN + "H" * number_of_registers, registers_data)
        )
        return registers

    def read_multi_register_value(
        self,
        address: int,
        n_registers: int,
        value_type: str,
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
            Byte order, 'big' means the high bytes will come first, 'little' means the low bytes will come first
            Byte order inside a register (2 bytes) is always big as per Modbus specification (4.2 Data Encoding)
        encoding : str
            String encoding (if used). UTF-8 by default
        padding : int | None
            String padding, None to return the raw string
        Returns
        -------
        data : any
        """
        type_cast = TypeCast(value_type)
        _byte_order = Endian(byte_order)
        if type_cast.is_number():
            _word_order = Endian(word_order)
        else:
            _word_order = Endian.BIG
        # Read N registers
        registers = self.read_holding_registers(
            start_address=address, number_of_registers=n_registers
        )
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

    def write_multi_register_value(
        self,
        address: int,
        n_registers: int,
        value_type: str,
        value: str | bytes | int | float,
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
            Byte order, 'big' means the high bytes will come first, 'little' means the low bytes will come first
            Byte order inside a register (2 bytes) is always big as per Modbus specification (4.2 Data Encoding)
        encoding : str
            String encoding (if used)
        padding : int
            Padding in case the value (str / bytes) is not long enough
        Returns
        -------
        data : any
        """
        _type = TypeCast(value_type)
        n_bytes = n_registers * 2
        if _type.is_number():
            _word_order = Endian(word_order)
        else:
            _word_order = Endian.BIG
        _byte_order = Endian(byte_order)

        array = b""
        if _type == TypeCast.INT or _type == TypeCast.UINT or _type == TypeCast.FLOAT:
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
        self.write_multiple_registers(start_address=address, values=registers)

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
        # Same implementation as read_holding_registers
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid Start or end addresses",
            3: "Invalid quantity of registers",
            4: "Couldn't read registers",
        }

        MAX_NUMBER_OF_REGISTERS = (AVAILABLE_PDU_SIZE - 2) // 2

        assert (
            1 <= number_of_registers <= MAX_NUMBER_OF_REGISTERS
        ), f"Invalid number of registers : {number_of_registers}"
        query = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.READ_INPUT_REGISTERS.value,
            self._dm_to_pdu_address(start_address),
            number_of_registers,
        )
        response = self._parse_pdu(
            self._adapter.query(self._make_pdu(self._make_pdu(query)))
        )
        self._raise_if_error(response, exception_codes=EXCEPTIONS)
        _, _, registers_data = struct.unpack(
            ENDIAN + f"BB{number_of_registers * 2}", response
        )
        registers = list(
            struct.unpack(ENDIAN + "2s" * number_of_registers, registers_data)
        )
        return registers

    # Write Single coil - 0x05
    def write_single_coil(self, address: int, enabled: bool) -> None:
        """
        Write a single output to either ON or OFF

        Parameters
        ----------
        address : int
        enabled : bool
        """
        ON_VALUE = 0xFF00
        OFF_VALUE = 0x0000
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid address",
            3: "Invalid value",
            4: "Couldn't set coil output",
        }
        assert MIN_ADDRESS <= address <= MAX_ADDRESS, f"Invalid address : {address}"

        query = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.WRITE_SINGLE_COIL.value,
            self._dm_to_pdu_address(address),
            ON_VALUE if enabled else OFF_VALUE,
        )
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query), stop_conditions=Length(self._length(len(query)))
            )
        )
        self._raise_if_error(response, EXCEPTIONS)
        assert (
            query == response
        ), f"Write single coil response should match query {query!r} != {response!r}"

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
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid address",
            3: "Invalid register value",
            4: "Couldn't write register",
        }

        assert MIN_ADDRESS <= address <= MAX_ADDRESS, f"Invalid address : {address}"

        query = struct.pack(
            ENDIAN + "BHH",
            FunctionCode.WRITE_SINGLE_REGISTER.value,
            self._dm_to_pdu_address(address),
            value,
        )
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query), stop_conditions=Length(self._length(len(query)))
            )
        )
        self._raise_if_error(response, EXCEPTIONS)
        assert (
            query == response
        ), f"Response ({response!r}) should match query ({query!r})"

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
    def read_exception_status(self) -> int:  # TODO : Check the return type
        """
        Read exeption status

        Returns
        -------
        exceptions : int
        """
        EXCEPTIONS = {
            1: "Function code not supported",
            4: "Couldn't read exception status",
        }
        if self._modbus_type == ModbusType.TCP:
            raise RuntimeError("read_exception_status cannot be used with Modbus TCP")
        query = struct.pack(ENDIAN + "B", FunctionCode.READ_EXCEPTION_STATUS.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        _, exception_status = cast(
            tuple[int, int], struct.unpack(ENDIAN + "BB", response)
        )  # TODO : Check this
        return exception_status

    # Diagnostics - 0x08
    # One function for each to simplify parameters and returns
    def _diagnostics(
        self,
        code: DiagnosticsCode,
        subfunction_data: bytes,
        return_subfunction_bytes: int,
        check_response: bool = True,
    ) -> bytes:
        """
        Diagnostics wrapper function

        Parameters
        ----------
        code : DiagnosticsCode
        check_response : bool
            Check response function code and subfunction code for equality with query
            True by default

        Returns
        -------
        response
        """

        EXCEPTIONS = {
            1: "Unsuported function code or sub-function code",
            3: "Invalid data value",
            4: "Diagnostic error",
        }

        query = (
            struct.pack(ENDIAN + "BH", FunctionCode.DIAGNOSTICS.value, code)
            + subfunction_data
        )
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))

        self._raise_if_error(response, EXCEPTIONS)

        returned_function, returned_subfunction_integer, subfunction_returned_data = (
            cast(
                tuple[int, int, bytes],
                struct.unpack(ENDIAN + f"BH{return_subfunction_bytes}s", response),
            )
        )
        if check_response:
            returned_subfunction = DiagnosticsCode(returned_subfunction_integer)
            assert (
                returned_function == FunctionCode.DIAGNOSTICS.value
            ), f"Invalid returned function code : {returned_function}"
            assert returned_subfunction == code
        return subfunction_returned_data

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
        try:
            response = self._diagnostics(
                DiagnosticsCode.RETURN_QUERY_DATA, subfunction_data, 2
            )
            return response == subfunction_data
        except AssertionError:
            return False

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
        self._diagnostics(
            DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION, subfunction_data, 2
        )

    def diagnostics_return_diagnostic_register(self) -> int:
        """
        Return 16 bit diagnostic register

        Returns
        -------
        register : int
        """
        returned_data = self._diagnostics(
            DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER, b"\x00\x00", 2
        )
        return int(struct.unpack("H", returned_data)[0])

    def diagnostics_change_ascii_input_delimiter(self, char: bytes) -> None:
        """
        Change the ASCII input delimiter to specified value

        Parameters
        ----------
        char : bytes or str
            Single character
        """
        assert len(char) == 1, f"Invalid char length : {len(char)}"
        if isinstance(char, str):
            char = char.encode("ASCII")

        subfunction_data = struct.pack("cB", char, 0)
        self._diagnostics(
            DiagnosticsCode.CHANGE_ASCII_INPUT_DELIMITER, subfunction_data, 2
        )

    def diagnostics_force_listen_only_mode(self) -> None:
        """
        Forces the addressed remote device to its Listen Only Mode for MODBUS communications.
        This isolates it from the other devices on the network, allowing them to continue
        communicating without interruption from the addressed remote device. No response is
        returned.
        When the remote device enters its Listen Only Mode, all active communication controls are
        turned off. The Ready watchdog timer is allowed to expire, locking the controls off. While the
        device is in this mode, any MODBUS messages addressed to it or broadcast are monitored,
        but no actions will be taken and no responses will be sent.
        The only function that will be processed after the mode is entered will be the Restart
        Communications Option function (function code 8, sub-function 1).
        """
        self._diagnostics(
            DiagnosticsCode.FORCE_LISTEN_ONLY_MODE, b"\x00\x00", 0, check_response=False
        )

    def diagnostics_clear_counters_and_diagnostic_register(self) -> None:
        """
        Clear all counters and the diagnostic register
        """
        self._diagnostics(
            DiagnosticsCode.CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER, b"\x00\x00", 0
        )

    def diagnostics_return_bus_message_count(self) -> int:
        """
        Return the number of messages that the remote device has detection on the communications system since its last restat, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(
            DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT, b"\x00\x00", 2
        )
        count = int(struct.unpack("H", response)[0])
        return count

    def diagnostics_return_bus_communication_error_count(self) -> int:
        """
        Return the number of messages that the remote device has detection on the communications system since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(
            DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT, b"\x00\x00", 2
        )
        count = int(struct.unpack("H", response)[0])
        return count

    def diagnostics_return_bus_exception_error_count(self) -> int:
        """
        Return the number of Modbus exceptions responses returned by the remote device since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(
            DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT, b"\x00\x00", 2
        )
        count = int(struct.unpack("H", response)[0])
        return count

    def diagnostics_return_server_no_response_count(self) -> int:
        """
        Return the number of messages addressed to the remote device for which it has returned no response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(
            DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT, b"\x00\x00", 2
        )
        count = int(struct.unpack("H", response)[0])
        return count

    def diagnostics_return_server_nak_count(self) -> int:
        """
        Return the number of messages addressed to the remote device for which it returned a negative acnowledge (NAK) exception response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(
            DiagnosticsCode.RETURN_SERVER_NAK_COUNT, b"\x00\x00", 2
        )
        count = int(struct.unpack("H", response)[0])
        return count

    def diagnostics_return_server_busy_count(self) -> int:
        """
        Return the number of messages addressed to the remote device for which it returned a server device busy exception response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(
            DiagnosticsCode.RETURN_SERVER_BUSY_COUNT, b"\x00\x00", 2
        )
        count = int(struct.unpack("H", response)[0])
        return count

    def diagnostics_return_bus_character_overrun_count(self) -> int:
        """
        Return the number of messages addressed to the remote device that it could not handle due to a character overrun condition since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(
            DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT, b"\x00\x00", 2
        )
        count = int(struct.unpack("H", response)[0])
        return count

    def diagnostics_clear_overrun_counter_and_flag(self) -> None:
        """
        Clear the overrun error counter and reset the error flag
        """
        self._diagnostics(
            DiagnosticsCode.CLEAR_OVERRUN_COUNTER_AND_FLAG, b"\x00\x00", 0
        )

    # Get Comm Event Counter - 0x0B
    def get_comm_event_counter(self) -> tuple[int, int]:
        """
        Retrieve status word and event count from the remote device's communication event counter

        Returns
        -------
        status : int
        event_count : int
        """
        EXCEPTIONS = {
            1: "Function code not supported",
            4: "Couldn't get comm event counter",
        }
        query = struct.pack(ENDIAN + "B", FunctionCode.GET_COMM_EVENT_COUNTER.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        _, status, event_count = struct.unpack(ENDIAN + "BHH", response)
        return status, event_count

    # Get Comm Event Log - 0x0C
    def get_comm_event_log(self) -> tuple[int, int, int, bytes]:
        """
        Retrieve status word, event count, message count and a field of event bytes from the remote device

        Status word and event count are identical to those returned by get_comm_event_counter()

        Returns
        -------
        status : int
        event_count : int
        message_count : int
            Number of messages processed since its last restart, clear counters operation, or power-up
            Identical to diagnostics_return_bus_message_count()
        events : bytes
            0-64 bytes, each corresponding to the status of one Modbus send or receive operation for
            the remote device. Byte 0 is the most recent event
        """

        EXCEPTIONS = {
            1: "Function code not supported",
            4: "Couldn't get comm event log",
        }
        query = struct.pack(ENDIAN + "B", FunctionCode.GET_COMM_EVENT_LOG.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        _, byte_count, status, event_count, message_count = struct.unpack(
            "BBHHH", response
        )
        events = struct.unpack(ENDIAN + f"8x{byte_count - 6}B", response)[0]

        return status, event_count, message_count, events

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
        # TODO : Check behavior against page 29 of the modbus spec (endianness of values)
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid start and/or end addresses",
            3: "Invalid number of outputs and/or byte count",
            4: "Couldn't write outputs",
        }

        number_of_coils = len(values)
        assert (
            1 <= number_of_coils <= MAX_DISCRETE_INPUTS
        ), f"Invalid number of coils : {number_of_coils}"
        assert (
            1 <= start_address <= MAX_ADDRESS - number_of_coils + 1
        ), f"Invalid start address : {start_address}"
        byte_count = ceil(number_of_coils / 8)

        query = struct.pack(
            ENDIAN + f"BHHB{byte_count}s",
            FunctionCode.WRITE_MULTIPLE_COILS.value,
            self._dm_to_pdu_address(start_address),
            number_of_coils,
            byte_count,
            bool_list_to_bytes(values),
        )
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query), stop_conditions=Length(self._length(5))
            )
        )
        self._raise_if_error(response, EXCEPTIONS)

        _, _, coils_written = struct.unpack(ENDIAN + "BHH", response)
        if coils_written != number_of_coils:
            raise RuntimeError(
                f"Number of coils written ({coils_written}) doesn't match expected value : {number_of_coils}"
            )

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
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid start and/or end addresses",
            3: "Invalid number of outputs and/or byte count",
            4: "Couldn't write outputs",
        }
        byte_count = 2 * len(values)

        # Specs says 123, but it would exceed 255 bytes over TCP. So 121 is safer
        MAX_NUMBER_OF_REGISTERS = (AVAILABLE_PDU_SIZE - 6) // 2

        assert len(values) > 0, "Empty register list"
        assert (
            len(values) <= MAX_NUMBER_OF_REGISTERS
        ), f"Cannot set more than {MAX_NUMBER_OF_REGISTERS} registers at a time"
        assert (
            MIN_ADDRESS <= start_address <= MAX_ADDRESS - len(values) + 1
        ), f"Invalid address : {start_address}"

        query = struct.pack(
            ENDIAN + f"BHHB{byte_count // 2}H",
            FunctionCode.WRITE_MULTIPLE_REGISTERS.value,
            self._dm_to_pdu_address(start_address),
            byte_count // 2,
            byte_count,
            *values,
        )
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query), stop_conditions=Length(self._length(5))
            )
        )
        self._raise_if_error(response, EXCEPTIONS)

        _, _, coils_written = struct.unpack(ENDIAN + "BHH", response)
        if coils_written != byte_count // 2:
            raise RuntimeError(
                f"Number of coils written ({coils_written}) doesn't match expected value : {byte_count // 2}"
            )

    # Report Server ID - 0x11
    def report_server_id(
        self, server_id_length: int, additional_data_length: int
    ) -> tuple[bytes, bool, bytes]:
        """
        Read description of the type, current status and other information specific to a remote device

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
        EXCEPTIONS = {1: "Function code not supported", 4: "Couldn't report slave ID"}
        query = struct.pack(ENDIAN + "B", FunctionCode.REPORT_SERVER_ID.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        server_id, run_indicator_status, additional_data = struct.unpack(
            ENDIAN + f"{server_id_length}sB{additional_data_length}s", response
        )
        return server_id, run_indicator_status == 0xFF, additional_data

    # Read File Record - 0x14
    def read_file_record(self, records: list[tuple[int, int, int]]) -> list[bytes]:
        """
        Perform a single or multiple file record read

        Total response length cannot exceed 253 bytes, meaning the number of records and their length is limited.


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
        SIZE_LIMIT = 253
        REFERENCE_TYPE = 6
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid parameters",
            3: "Invalid byte count",
            4: "Couldn't read records",
        }

        assert isinstance(records, list)

        query_size = 2 + 7 * len(records)
        response_size = 2 + len(records) + sum(2 * r[2] for r in records)
        if query_size > SIZE_LIMIT:
            raise ValueError(f"Number of records is too high : {len(records)}")
        if response_size > SIZE_LIMIT:
            raise ValueError(
                f"Sum of records lenghts is too high : {sum([r[2] for r in records])}"
            )

        sub_req_buffer = b""
        for file_number, record_number, record_length in records:
            sub_req_buffer += struct.pack(
                ENDIAN + "BHHH",
                REFERENCE_TYPE,
                file_number,
                record_number,
                record_length,
            )

        byte_count = len(sub_req_buffer)

        query = struct.pack(
            ENDIAN + f"BB{byte_count}s",
            FunctionCode.READ_FILE_RECORD,
            byte_count,
            sub_req_buffer,
        )
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        # Parse the response
        # start at position 2
        records_data = []
        i = 2
        while True:
            length = response[i]
            i += 1
            # Ignore teh reference type
            # Read the record data
            records_data.append(response[i : i + length])
            i += length

        return records_data

    # Write File Record - 0x15
    def write_file_record(self, records: list[tuple[int, int, bytes]]) -> None:
        """
        Perform a single or multiple file record write

        Total query and response length cannot exceed 253 bytes, meaning the number of records and their length is limited.

        Query equation : 2 + 7*N + sum(Li*2) <= 253
        Response equation : identical

        File number can be between 0x0001 and 0xFFFF but lots of legacy equipment will not support file number above 0x000A (10)

        Parameters
        ----------
        records : list
            List of tuples : (file_number, record_number, data)
        """
        REFERENCE_TYPE = 6
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid parameters",
            3: "Invalid byte count",
            4: "Couldn't write records",
        }

        if isinstance(records, tuple):
            records = [records]
        elif not isinstance(records, list):
            raise TypeError(f"Invalid records type : {records}")

        sub_req_buffer = b""

        for file_number, record_number, data in records:
            sub_req_buffer += struct.pack(
                ENDIAN + f"BHHH{len(data)}s",
                REFERENCE_TYPE,
                file_number,
                record_number,
                len(data) // 2,
                data,
            )

        query = struct.pack(
            ENDIAN + f"BB{len(sub_req_buffer)}s",
            FunctionCode.WRITE_FILE_RECORD,
            len(sub_req_buffer),
            sub_req_buffer,
        )
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        assert response == query

    # Mask Write Register - 0x16
    def mask_write_register(self, address: int, and_mask: int, or_mask: int) -> None:
        """
        This function is used to modify the contents of a holding register using a combination of AND and OR masks applied to the current contents of the register.

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
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid register address",
            3: "Invalid AND/OR mask",
            4: "Couldn't write register",
        }
        assert MIN_ADDRESS <= address <= MAX_ADDRESS, f"Invalid address : {address}"

        query = struct.pack(
            ENDIAN + "BHHH",
            FunctionCode.MASK_WRITE_REGISTER.value,
            self._dm_to_pdu_address(address),
            and_mask,
            or_mask,
        )
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query), stop_conditions=Length(self._length(len(query)))
            )
        )
        self._raise_if_error(response, EXCEPTIONS)
        assert (
            response == query
        ), f"Response ({response!r}) should match query ({query!r})"

    # Read/Write Multiple Registers - 0x17
    def read_write_multiple_registers(
        self,
        read_starting_address: int,
        number_of_read_registers: int,
        write_starting_address: int,
        write_values: list[bytes],
    ) -> list[bytes]:
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
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid read/write start/end address",
            3: "Invalid quantity of read/write and/or byte count",
            4: "Couldn't read and/or write registers",
        }

        MAX_NUMBER_READ_REGISTERS = (AVAILABLE_PDU_SIZE - 2) // 2
        MAX_NUMBER_WRITE_REGISTERS = (AVAILABLE_PDU_SIZE - 10) // 2

        assert (
            1 <= number_of_read_registers <= MAX_NUMBER_READ_REGISTERS
        ), f"Invalid number of read registers : {number_of_read_registers}"
        assert (
            MIN_ADDRESS
            <= read_starting_address
            <= MAX_ADDRESS - number_of_read_registers + 1
        ), f"Invalid read start address : {read_starting_address}"

        assert (
            1 <= len(write_values) <= MAX_NUMBER_WRITE_REGISTERS
        ), f"Invalid number of write registers  : {len(write_values)}"
        assert (
            MIN_ADDRESS <= write_starting_address <= MAX_ADDRESS - len(write_values) + 1
        ), f"Invalid write start address (writing {len(write_values)} registers) : {write_starting_address}"

        query = struct.pack(
            ENDIAN + f"BHHHHB{len(write_values)}H",
            FunctionCode.READ_WRITE_MULTIPLE_REGISTERS.value,
            read_starting_address,
            number_of_read_registers,
            write_starting_address,
            len(write_values),
            len(write_values) * 2,
            *write_values,
        )
        response = self._parse_pdu(
            self._adapter.query(
                self._make_pdu(query),
                stop_conditions=Length(self._length(2 + number_of_read_registers * 2)),
            )
        )
        self._raise_if_error(response, EXCEPTIONS)
        # Parse response
        output = struct.unpack(ENDIAN + f"BB{number_of_read_registers}H", response)
        # _, _, read_values
        read_values = list(output[2:])
        return read_values

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
        EXCEPTIONS = {
            1: "Function code not supported",
            2: "Invalid FIFO address",
            3: "Invalid FIFO count (>31)",
            4: "Couldn't read FIFO queue",
        }
        query = struct.pack(ENDIAN + "BH", FunctionCode.READ_FIFO_QUEUE, fifo_address)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        byte_count = int(struct.unpack(ENDIAN + "xH", response)[0])
        register_count = byte_count // 2 - 1

        values = cast(
            list[int], struct.unpack(ENDIAN + f"{register_count}H", response[5:])[0]
        )  # Ignore the FIFO count

        return values

    # Encapsulate Interface Transport - 0x2B
    def encapsulated_interface_transport(
        self,
        mei_type: int,
        mei_data: bytes,
        extra_exceptions: dict[int, str] | None = None,
    ) -> bytes:
        """
        The MODBUS Encapsulated Interface (MEI) Transport is a mechanism for tunneling service requests and method invocations

        Parameters
        ----------
        mei_type : int
        mei_data : bytes

        Returns
        -------
        returned_mei_data : bytes
        """
        EXCEPTIONS = {
            1: "Function code not supported",
        }
        if extra_exceptions is not None:
            EXCEPTIONS.update(extra_exceptions)

        query = struct.pack(
            ENDIAN + f"BB{len(mei_data)}s",
            FunctionCode.ENCAPSULATED_INTERFACE_TRANSPORT,
            mei_type,
            mei_data,
        )
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        return response[2:]
