# modbus.py
# Sébastien Deriaz
# 16.07.2024
#
#
# Modbus TCP and Modbus RTU implementation
from .protocol import Protocol
from ..adapters import Adapter, IP, SerialPort
from ..adapters.timeout import Timeout
from enum import Enum
import struct
from math import ceil
from typing import List

MODBUS_TCP_DEFAULT_PORT = 502

ENDIAN = '>'

class ModbusType(Enum):
    RTU = 'RTU'
    ASCII = 'ASCII'
    TCP = 'TCP'

class FunctionCode(Enum):
    # Public function codes 1 to 64
    READ_COILS = 0x01
    READ_DISCRETE_INPUTS = 0x02
    READ_HOLDING_REGISTERS = 0x03
    READ_INPUT_REGISTERS = 0x04
    WRITE_SINGLE_COIL = 0x05
    WRITE_SINGLE_REGISTER = 0x06
    READ_EXCEPTION_STATUS = 0x07 # Serial only
    DIAGNOSTICS = 0x08 # Serial only
    GET_COMM_EVENT_COUNTER = 0x0B # Serial only
    GET_COMM_EVENT_LOG = 0x0C # Serial only
    WRITE_MULTIPLE_COILS = 0x0F
    WRITE_MULTIPLE_REGISTERS = 0x10
    REPORT_SERVER_ID = 0x11 # Serial only
    READ_FILE_RECORD = 0x14
    WRITE_FILE_RECORD = 0x15
    MASK_WRITE_REGISTERS = 0x16
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

def list_to_bytes(lst : list):
    byte_count = ceil(len(lst) / 8)
    return sum([2**i * int(v) for i, v in enumerate(lst)]).to_bytes(byte_count, byteorder='little')


def bytes_to_list(_bytes : bytes, N : int):
    return [True if c == '1' else False for c in ''.join([f'{x:08b}'[::-1] for x in _bytes])][:N]

class TypeCast(Enum):
    INT = 'int'
    UINT = 'uint'
    FLOAT = 'float'
    STRING_ASCII = 'string_ascii'
    STRING_UTF8 = 'string_utf8'
    ARRAY = 'array'

def struct_format(type : TypeCast, length : int):
    if type == TypeCast.INT:
        if length == 1:
            return 'b'
        elif length == 2:
            return 'h'
        elif length == 4:
            return 'i' # or 'l'
        elif length == 8:
            return 'q'
    elif type == TypeCast.UINT:
        if length == 1:
            return 'B'
        elif length == 2:
            return 'H'
        elif length == 4:
            return 'I' # or 'L'
        elif length == 8:
            return 'Q'
    elif type == TypeCast.FLOAT:
        if length == 4:
            return 'f'
        elif length == 8:
            return 'd'
    elif type == TypeCast.STRING_ASCII or type == TypeCast.STRING_UTF8 or type == TypeCast.ARRAY:
        return f'{length}s'
    else:
        raise ValueError(f'Unknown cast type : {type}')
    raise ValueError(f'Invalid type cast / length combination : {type} / {length}')


class ModbusException(Exception):
    pass


class Modbus(Protocol):
    ASCII_HEADER = b':'
    ASCII_TRAILER = b'\r\n'

    def __init__(self, adapter: Adapter, timeout: Timeout, _type : str = ModbusType.RTU.value, slave_address : int = None) -> None:
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


        if isinstance(adapter, IP):
            self._adapter.set_default_port(MODBUS_TCP_DEFAULT_PORT)
            self._modbus_type = ModbusType.TCP
        elif isinstance(adapter, SerialPort):
            self._modbus_type = ModbusType(_type)
            assert slave_address is not None, "slave_address must be set"
            raise NotImplementedError("Serialport (Modbus RTU) is not supported yet")
        else:
            raise ValueError('Invalid adapter')

        self._slave_address = slave_address

        self._transaction_id = 0

    def _dm_to_pdu_address(self, dm_address):
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
            raise ValueError('Address 0 is not valid in Modbus data model')

        return dm_address - 1        

    def _pdu_to_dm_address(self, pdu_address):
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
        


    def _crc(self, _bytes):
        # TODO : Implement
        return 0
    
    def _make_pdu(self, _bytes):
        """
        Return PDU generated from bytes data
        """
        PROTOCOL_ID = 0
        UNIT_ID = 0

        if self._modbus_type == ModbusType.TCP:
            # Return raw data
            # output = _bytes
            # Temporary :
            length = len(_bytes) + 1 # unit_id is included
            output = struct.pack(ENDIAN + 'HHHB', self._transaction_id, PROTOCOL_ID, length, UNIT_ID) + _bytes
            self._transaction_id += 1
        else:
            # Add slave address and error check
            error_check = self._crc(_bytes)
            output = struct.pack(ENDIAN + 'B', self._slave_address) + _bytes + struct.pack(ENDIAN + 'H', error_check)
            if self._modbus_type.ASCII:
                # Add header and trailer
                output = self.ASCII_HEADER + output + self.ASCII_TRAILER

        return output

    def _raise_if_error(self, response, exception_codes : dict):
        if response[0] & 0x80:
            # There is an error
            code = response[1]
            if code not in exception_codes:
                raise RuntimeError(f"Unexpected modbus error code: {code}")
            else:
                raise ModbusException(f'{code:02X} : {exception_codes[code]}')

    def _is_error(self, response):
        return 

    def _error_code(self, response):
        return response[1]

    def _parse_pdu(self, _pdu):
        """
        Return data from PDU
        """
        if self._modbus_type == ModbusType.TCP:
            # Return raw data
            # data = _pdu
            data = _pdu[7:]

        else:
            if self._modbus_type.ASCII:
                # Remove header and trailer
                _pdu = _pdu[len(self.ASCII_HEADER):-len(self.ASCII_TRAILER)]
            # Remove slave address and CRC and check CRC

            data = _pdu[1:-2]
            # Check CRC
            error_check = _pdu[-2:]
            # TODO : Check here and raise exception

        return data

    # Read Coils - 0x01
    def read_coils(self, start_address : int, number_of_coils : int):
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
        EXCEPTIONS = {
            1 : 'Function code not supported',
            2 : 'Invalid Start or end addresses',
            3 : 'Invalid quantity of outputs',
            4 : 'Couldn\'t read coils'
        }
        query = struct.pack(ENDIAN + 'BHH', FunctionCode.READ_COILS.value, self._dm_to_pdu_address(start_address), number_of_coils)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query))   )
        self._raise_if_error(response, exception_codes=EXCEPTIONS)
        n_coil_bytes = ceil(number_of_coils / 8)
        _, _, coil_bytes = struct.unpack(ENDIAN + f'BB{n_coil_bytes}s', response)
        coils = bytes_to_list(coil_bytes, number_of_coils)
        return coils

    def read_single_coil(self, address : int):
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
    def read_discrete_inputs(self, start_address : int, number_of_inputs : int):
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
            1 : 'Function code not supported',
            2 : 'Invalid Start or end addresses',
            3 : 'Invalid quantity of inputs',
            4 : 'Couldn\'t read inputs'
        }
        query = struct.pack(ENDIAN + 'BHH', FunctionCode.READ_DISCRETE_INPUTS.value, self._dm_to_pdu_address(start_address), number_of_inputs)
        byte_count = ceil(number_of_inputs / 8) # pre-calculate the number of returned coil value bytes
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, exception_codes=EXCEPTIONS)
        _, _, data = struct.unpack(ENDIAN + f'BB{byte_count}s', response)
        inputs = bytes_to_list(data, number_of_inputs)
        return inputs

    # Read Holding Registers - 0x03
    def read_holding_registers(self, start_address : int, number_of_registers : int):
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
            1 : 'Function code not supported',
            2 : 'Invalid Start or end addresses',
            3 : 'Invalid quantity of registers',
            4 : 'Couldn\'t read registers'
        }
        MAX_NUMBER_OF_REGISTERS = 125
        assert 1 <= number_of_registers <= MAX_NUMBER_OF_REGISTERS, f"Invalid number of registers : {number_of_registers}"
        query = struct.pack(ENDIAN + 'BHH', FunctionCode.READ_HOLDING_REGISTERS.value, self._dm_to_pdu_address(start_address), number_of_registers)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, exception_codes=EXCEPTIONS)
        _, _, registers_data = struct.unpack(ENDIAN + f'BB{number_of_registers*2}', response)
        registers = list(struct.unpack(ENDIAN + '2s' * number_of_registers), registers_data)
        return registers

    def read_multi_register_value(self, 
            address : int,
            _bytes : int,
            _type : str,
            byte_order : str = 'big',
            null_terminated_string : bool = False):
        """
        Read an integer, a float, or a string over multiple registers

        Parameters
        ----------
        address : int
            Address of the first register
        _bytes : int
            Number of bytes (twice the number of registers)
        _type : str
            Type to which the value will be cast
                'int' : signed integer
                'uint' : unsigned integer
                'float' : float or double
                'string_ascii' : ASCII string
                'tring_utf8' : UTF-8 string
                'array' : Bytes array
            Each type will be adapted based on the number of bytes (_bytes parameter) 
        byte_order : str
            Byte order, 'big' means the high bytes will come first, 'little' means the low bytes will come first
            Byte order inside a register (2 bytes) is always big as per Modbus specification (4.2 Data Encoding)
        null_terminated_string : bool
            If True, remove null termination if any (strings only)

        Returns
        -------
        data : any
        """
        _type = TypeCast(_type)
        # Read N registers
        registers = self.read_holding_registers(start_address=self._dm_to_pdu_address(address), number_of_registers=_bytes//2)
        # Create the buffer (2*N bytes)
        buffer = b''.join(registers[::(1 if byte_order == 'big' else -1)])
        # Parse
        data : bytes
        data = struct.unpack(struct_format(_type, _bytes), buffer)
        # If data is a string, do additionnal processing
        if _type == TypeCast.STRING_ASCII or _type == TypeCast.STRING_UTF8:
            # If null termination is enabled, remove any
            if null_terminated_string and b'\0' in data:
                data = data[:data.index(b'\0')]
            # Cast
            if _type == TypeCast.STRING_ASCII:
                data = data.decode('ASCII')
            elif _type == TypeCast.STRING_UTF8:
                data = data.decode('utf-8')

        return data

    # Read Input Registers - 0x04
    def read_input_registers(self, start_address : int, number_of_registers : int):
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
            1 : 'Function code not supported',
            2 : 'Invalid Start or end addresses',
            3 : 'Invalid quantity of registers',
            4 : 'Couldn\'t read registers'
        }
        MAX_NUMBER_OF_REGISTERS = 125
        assert 1 <= number_of_registers <= MAX_NUMBER_OF_REGISTERS, f"Invalid number of registers : {number_of_registers}"
        query = struct.pack(ENDIAN + 'BHH', FunctionCode.READ_INPUT_REGISTERS.value, self._dm_to_pdu_address(start_address), number_of_registers)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(self._make_pdu(query))))
        self._raise_if_error(response, exception_codes=EXCEPTIONS)
        _, _, registers_data = struct.unpack(ENDIAN + f'BB{number_of_registers*2}', response)
        registers = list(struct.unpack(ENDIAN + '2s' * number_of_registers), registers_data)
        return registers

    # Write Single coil - 0x05
    def write_single_coil(self, address : int, enabled : bool):
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
            1 : 'Function code not supported',
            2 : 'Invalid address',
            3 : 'Invalid value',
            4 : 'Couldn\'t set coil output'
        }
        query = struct.pack(ENDIAN + 'BHH', FunctionCode.WRITE_SINGLE_COIL.value, self._dm_to_pdu_address(address), ON_VALUE if enabled else OFF_VALUE)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        assert query == response, f"Write single coil response should match query {query} != {response}"

    # Write Single Register - 0x06
    def write_single_register(self, address : int, value : int):
        """
        Write a single register

        Parameters
        ----------
        address : int
        value : int
            value between 0x0000 and 0xFFFF
        """
        EXCEPTIONS = {
            1 : 'Function code not supported',
            2 : 'Invalid address',
            3 : 'Invalid register value',
            4 : 'Couldn\'t write register'
        }
        query = struct.pack(ENDIAN + 'BHH', FunctionCode.WRITE_SINGLE_REGISTER.value, self._dm_to_pdu_address(address), value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        assert query == response, f"Response ({response}) should match query ({query})"

    # Read Exception Status - 0x07
    def read_exception_status(self):
        """
        Read exeption status

        Returns
        -------
        exceptions : int
        """
        EXCEPTIONS = {
            1 : 'Function code not supported',
            4 : 'Couldn\'t read exception status'
        }
        if self._modbus_type == ModbusType.TCP:
            raise RuntimeError("read_exception_status cannot be used with Modbus TCP")
        query = struct.pack(ENDIAN + 'B', FunctionCode.READ_EXCEPTION_STATUS.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        exception_status = struct.unpack(ENDIAN + 'BB')
        return exception_status

    # Diagnostics - 0x08
    # One function for each to simplify parameters and returns
    def _diagnostics(self, code : DiagnosticsCode, subfunction_data : bytes, return_subfunction_bytes : int, check_response : bool = True):
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
            1 : 'Unsuported function code or sub-function code',
            3 : 'Invalid data value',
            4 : 'Diagnostic error'
        }

        query = struct.pack(ENDIAN + 'BH', FunctionCode.DIAGNOSTICS.value, code) + subfunction_data
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))

        self._raise_if_error(response, EXCEPTIONS)

        returned_function, returned_subfunction, subfunction_returned_data = struct.unpack(ENDIAN + f'BH{return_subfunction_bytes}s', response)
        if check_response:
            assert returned_function == FunctionCode.DIAGNOSTICS.value, f"Invalid returned function code : {returned_function}"
            assert returned_subfunction == code
        return subfunction_returned_data

    def diagnostics_return_query_data(self, data : int = 0x1234):
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
        subfunction_data = struct.pack(ENDIAN + 'H', data)
        try:
            response = self._diagnostics(DiagnosticsCode.RETURN_QUERY_DATA, subfunction_data, 2)
            return response == subfunction_data
        except AssertionError:
            return False


    # TODO : Check how this function interracts with Listen Only mode
    def diagnostics_restart_communications_option(self, clear_communications_event_log : bool = False):
        """
        Initialize and restart serial line port. Brings the device out of Listen Only Mode

        Parameters
        ----------
        clear_communications_event_log : bool
            False by default
        """
        subfunction_data = struct.pack(ENDIAN + 'H', 0xFF00 if clear_communications_event_log else 0x0000)
        self._diagnostics(DiagnosticsCode.RESTART_COMMUNICATIONS_OPTION, subfunction_data, 2)

    def diagnostics_return_diagnostic_register(self):
        """
        Return 16 bit diagnostic register

        Returns
        -------
        register : int
        """
        returned_data = self._diagnostics(DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER, 0, 2)
        return struct.unpack('H', returned_data)

    def diagnostics_change_ascii_input_delimiter(self, char : bytes):
        """
        Change the ASCII input delimiter to specified value

        Parameters
        ----------
        char : bytes or str
            Single character
        """
        assert len(char) == 1, f"Invalid char length : {len(char)}"
        if isinstance(char, str):
            char = char.encode('ASCII')
        
        subfunction_data = struct.pack('cB', char, 0)
        self._diagnostics(DiagnosticsCode.CHANGE_ASCII_INPUT_DELIMITER, subfunction_data, 2)

    def diagnostics_force_listen_only_mode(self):
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
        self._diagnostics(DiagnosticsCode.FORCE_LISTEN_ONLY_MODE, 0, 0, check_response=False)

    def diagnostics_clear_counters_and_diagnostic_register(self):
        """
        Clear all counters and the diagnostic register
        """
        self._diagnostics(DiagnosticsCode.CLEAR_COUNTERS_AND_DIAGNOSTIC_REGISTER, 0, 0)

    def diagnostics_return_bus_message_count(self):
        """
        Return the number of messages that the remote device has detection on the communications system since its last restat, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT, 0, 2)
        count = struct.unpack('H', response)
        return count

    def diagnostics_return_bus_communication_error_count(self):
        """
        Return the number of messages that the remote device has detection on the communications system since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT, 0, 2)
        count = struct.unpack('H', response)
        return count

    def diagnostics_return_bus_exception_error_count(self):
        """
        Return the number of Modbus exceptions responses returned by the remote device since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int        
        """
        response = self._diagnostics(DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT, 0, 2)
        count = struct.unpack('H', response)
        return count

    def diagnostics_return_server_no_response_count(self):
        """
        Return the number of messages addressed to the remote device for which it has returned no response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT, 0, 2)
        count = struct.unpack('H', response)
        return count

    def diagnostics_return_server_nak_count(self):
        """
        Return the number of messages addressed to the remote device for which it returned a negative acnowledge (NAK) exception response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(DiagnosticsCode.RETURN_SERVER_NAK_COUNT, 0, 2)
        count = struct.unpack('H', response)
        return count

    def diagnostics_return_server_busy_count(self):
        """
        Return the number of messages addressed to the remote device for which it returned a server device busy exception response since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(DiagnosticsCode.RETURN_SERVER_BUSY_COUNT, 0, 2)
        count = struct.unpack('H', response)
        return count

    def diagnostics_return_bus_character_overrun_count(self):
        """
        Return the number of messages addressed to the remote device that it could not handle due to a character overrun condition since its last restart, clear counters operation, or power-up

        Returns
        -------
        count : int
        """
        response = self._diagnostics(DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT, 0, 2)
        count = struct.unpack('H', response)
        return count

    def diagnostics_clear_overrun_counter_and_flag(self):
        """
        Clear the overrun error counter and reset the error flag
        """
        self._diagnostics(DiagnosticsCode.CLEAR_OVERRUN_COUNTER_AND_FLAG, 0, 0)


    # Get Comm Event Counter - 0x0B
    def get_comm_event_counter(self):
        """
        Retrieve status word and event count from the remote device's communication event counter

        Returns
        -------
        status : int
        event_count : int
        """
        EXCEPTIONS = {
            1 : 'Function code not supported',
            4 : 'Couldn\'t get comm event counter'
        }
        query = struct.pack(ENDIAN + 'B', FunctionCode.GET_COMM_EVENT_COUNTER.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        _, status, event_count = struct.unpack(ENDIAN + 'BHH')
        return status, event_count

    # Get Comm Event Log - 0x0C
    def get_comm_event_log(self):
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
            1 : 'Function code not supported',
            4 : 'Couldn\'t get comm event log'
        }
        query = struct.pack(ENDIAN + 'B', FunctionCode.GET_COMM_EVENT_LOG.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)
        _, byte_count, status, event_count, message_count = struct.unpack('BBHHH', response)
        events = struct.unpack(ENDIAN + f'8x{byte_count-6}B')

        return status, event_count, message_count, events


    # Write Multiple Coils - 0x0F
    def write_multiple_coils(self, start_address : int, values : List[bool]):
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
            1 : 'Function code not supported',
            2 : 'Invalid start and/or end addresses',
            3 : 'Invalid number of outputs and/or byte count',
            4 : 'Couldn\'t write outputs'
        }

        number_of_coils = len(values)
        byte_count = ceil(number_of_coils / 8)

        query = struct.pack(ENDIAN + f'BHHB{byte_count}s',
            FunctionCode.WRITE_MULTIPLE_COILS.value,
            self._dm_to_pdu_address(start_address),
            number_of_coils,
            byte_count,
            list_to_bytes(values)
            )
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)

        _, _, coils_written = struct.unpack(ENDIAN + 'BHH', response)
        if coils_written != number_of_coils:
            raise RuntimeError(f"Number of coils written ({coils_written}) doesn't match expected value : {number_of_coils}")

    # Write Multiple Registers - 0x10
    def write_multiple_registers(self, start_address : int, values : list):
        """
        Write multiple registers

        Parameters
        ----------
        start_address : int
        values : list
            List of integers

        """
        EXCEPTIONS = {
            1 : 'Function code not supported',
            2 : 'Invalid start and/or end addresses',
            3 : 'Invalid number of outputs and/or byte count',
            4 : 'Couldn\'t write outputs'
        }
        byte_count = 2 * len(values)

        query = struct.pack(ENDIAN + f'BHHB{byte_count // 2}H',
            FunctionCode.WRITE_MULTIPLE_REGISTERS.value,
            self._dm_to_pdu_address(start_address),
            byte_count // 2,
            byte_count,
            values
            )
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        self._raise_if_error(response, EXCEPTIONS)

        _, _, coils_written = struct.unpack(ENDIAN + 'BHH', response)
        if coils_written != byte_count // 2:
            raise RuntimeError(f"Number of coils written ({coils_written}) doesn't match expected value : {byte_count // 2}")
        

    # Report Server ID - 0x11
    def report_server_id(self, server_id_length : int, additional_data_length : int):
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
        EXCEPTIONS = {
            1 : 'Function code not supported',
            4 : 'Couldn\'t report slave ID'
        }
        query = struct.pack(ENDIAN + 'B', FunctionCode.REPORT_SERVER_ID.value)
        response = self._parse_pdu(self._adapter.query(self._make_pdu(query)))
        server_id, run_indicator_status, additional_data = struct.unpack(ENDIAN + f'{server_id_length}sB{additional_data_length}s', response)
        return server_id, run_indicator_status == 0xFF, additional_data

    # Read File Record - 0x14
    def read_file_record(self):
        """
        Perform a file record read
        
        """

    # Write File Record - 0x15
    def write_file_record(self):
        pass

    # Mask Write Register - 0x16
    def mask_write_register(self):
        pass

    # Read/Write Multiple Registers - 0x17
    def read_write_multiple_registers(self):
        pass

    # Read FIFO Queue - 0x18
    def read_fifo_queue(self):
        pass

    # Encapsulate Interface Transport - 0x2B
    def encapsulated_interface_transport(self):
        pass



    

    

    

    

    
