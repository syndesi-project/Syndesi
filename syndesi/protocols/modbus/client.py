# File : client.py
# Author : Sébastien Deriaz
# License : GPL
"""
Modbus clients (masters), sync and async
"""

# pylint: disable=too-many-lines

from __future__ import annotations

import struct
from typing import Any, TypeVar

from syndesi.adapters.serialport import AsyncSerialPort, SerialPort

from ...adapters.adapter import Adapter, AsyncAdapter
from ...adapters.ip import IP, AsyncIP
from ...adapters.utils import TimeoutParameterType
from ...tools.errors import ProtocolReadError
from ...tools.others import DEFAULT
from ..protocol import (
    AsyncProtocol,
    Protocol,
)
from .backend import (
    ModbusBackend,
    ModbusSerialType,
    ModbusTCPBackend,
    _serial_backend,
)
from .common import (
    ENDIAN,
    MODBUS_TCP_DEFAULT_PORT,
    DiagnosticsCode,
    Endian,
    ModbusException,
)
from .sdu import (
    DiagnosticsRequestSDU,
    DiagnosticsResponseSDU,
    EncapsulatedInterfaceTransportRequestSDU,
    EncapsulatedInterfaceTransportResponseSDU,
    ExceptionResponseSDU,
    GetCommEventCounterRequestSDU,
    GetCommEventCounterResponseSDU,
    GetCommEventLogRequestSDU,
    GetCommEventLogResponseSDU,
    MaskWriteRegisterRequestSDU,
    MaskWriteRegisterResponseSDU,
    ModbusRequestSDU,
    ModbusResponseSDU,
    ModbusSDU,
    ReadCoilsRequestSDU,
    ReadCoilsResponseSDU,
    ReadDiscreteInputsRequestSDU,
    ReadDiscreteInputsResponseSDU,
    ReadExceptionStatusRequestSDU,
    ReadExceptionStatusResponseSDU,
    ReadFifoQueueRequestSDU,
    ReadFifoQueueResponseSDU,
    ReadFileRecordRequestSDU,
    ReadFileRecordResponseSDU,
    ReadHoldingRegistersRequestSDU,
    ReadHoldingRegistersResponseSDU,
    ReadInputRegistersRequestSDU,
    ReadInputRegistersResponseSDU,
    ReadWriteMultipleRegistersRequestSDU,
    ReadWriteMultipleRegistersResponseSDU,
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
from .values import (
    ModbusMultiRegisterValue,
)

ResponseT = TypeVar("ResponseT", bound=ModbusResponseSDU[Any])


class ModbusCommon:
    """Value conversions shared by Modbus and AsyncModbus"""

    @staticmethod
    def _check_response(
        request: ModbusRequestSDU, response: ModbusSDU, response_type: type[ResponseT]
    ) -> ResponseT:
        """Raise the exception response as a ModbusException, check the response type"""
        if isinstance(response, ExceptionResponseSDU):
            description = None
            if (
                isinstance(request, EncapsulatedInterfaceTransportRequestSDU)
                and request.extra_exceptions is not None
            ):
                description = request.extra_exceptions.get(response.exception_code)
            raise ModbusException(response.exception_code, description)
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
    timeout : float, None or DEFAULT
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
        timeout: TimeoutParameterType = DEFAULT,
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
        timeout: TimeoutParameterType = DEFAULT,
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
