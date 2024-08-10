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

class DiagnosticsSubFunctionCodes(Enum):
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

    def _crc(self, _bytes):
        # TODO : Implement
        return 0
    
    def _make_pdu(self, _bytes):
        """
        Return PDU generated from bytes data
        """
        if self._modbus_type == ModbusType.TCP:
            # Return raw data
            output = _bytes
        else:
            # Add slave address and error check
            error_check = self._crc(_bytes)
            output = struct.pack('B', self._slave_address) + _bytes + struct.pack('H', error_check)
            if self._modbus_type.ASCII:
                # Add header and trailer
                output = self.ASCII_HEADER + output + self.ASCII_TRAILER

        return output

    def _parse_pdu(self, _pdu):
        """
        Return data from PDU
        """
        if self._modbus_type == ModbusType.TCP:
            # Return raw data
            data = _pdu
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
    def read_coils(self, starting_address : int, number_of_coils : int):
        """
        Read a defined number of coils starting at a set address

        Parameters
        ----------
        starting_address : int
        number_of_coils : int
        """
        query = struct.pack('BHH', FunctionCode.READ_COILS, starting_address, number_of_coils)
        response = self._adapter.query(self._make_pdu(query))
        n_coil_bytes = ceil(number_of_coils / 8)
        _, _, coil_bytes = struct.unpack(f'BB{n_coil_bytes}s', response)

        return bytes_to_list(coil_bytes)

    def read_single_coil(self, address : int):
        """
        Read a single coil at a specified address.
        This is a wrapper for the read_coils method with the number of coils set to 1

        Parameters
        ----------
        address : int
        """
        return self.read_coils(starting_address=address, number_of_coils=1)[0]

    # Read Discrete inputs - 0x02
    def read_discrete_inputs(self, start_address : int, number_of_inputs : int):
        """
        Read a defined number of discrete inputs at a set starting address

        Parameters
        ----------
        start_address : int
        number_of_inputs : int
        """
        query = struct.pack('BHH', FunctionCode.READ_DISCRETE_INPUTS, start_address, number_of_inputs)
        byte_count = ceil(number_of_inputs / 8) # pre-calculate the number of returned coil value bytes
        response = self._adapter.query(self._make_pdu(query))
        _, _, data = struct.unpack(f'BB{byte_count}s', response)
        return bytes_to_list(data, number_of_inputs)

    # Read Holding Registers - 0x03
    def read_holding_registers(self, starting_address : int, number_of_registers : int):
        """
        Reads a defined number of registers starting at a set address

        Parameters
        ----------
        starting_address : int
        number_of_registers : int
            1 to 125
        """
        MAX_NUMBER_OF_REGISTERS = 125
        assert 1 <= number_of_registers <= MAX_NUMBER_OF_REGISTERS, f"Invalid number of registers : {number_of_registers}"
        query = struct.pack('BHH', FunctionCode.READ_HOLDING_REGISTERS, starting_address, number_of_registers)
        response = self._adapter.query(self._make_pdu(query))
        _, _, registers = struct.unpack(f'BB{number_of_registers*2}')


    # Read Input Registers - 0x04
    def read_input_registers(self):
        pass

    # Write Single coil - 0x05
    def write_single_coil(self, address : int, enabled : bool):
        query = struct.pack('BHH', FunctionCode.WRITE_SINGLE_COIL, address, 0xFF00 if enabled else 0x0000)
        response = self._adapter.query(query)
        assert query == response, f"Write single coil response should match query {query} != {response}"

    # Write Single Register - 0x06
    def write_single_register(self, address : int, value : int):
        query = struct.pack('BHH', FunctionCode.WRITE_SINGLE_REGISTER, address, value)
        response = self._adapter.query(query)
        assert query == response, f"Response ({response}) should match query ({query})"

    # Read Exception Status - 0x07
    def read_exception_status(self):
        pass

    # Diagnostics - 0x08
    def diagnostics(self):
        pass

    # Get Comm Event Counter - 0x0B
    def get_comm_event_counter(self):
        pass

    # Get Comm Event Log - 0x0C
    def get_comm_event_log(self):
        pass

    # Write Multiple Coils - 0x0F
    def write_multiple_coils(self, starting_address : int, values : List[bool]):
        number_of_coils = len(values)
        byte_count = ceil(number_of_coils / 8)

        query = struct.pack(f'BHHB{byte_count}s',
            FunctionCode.WRITE_MULTIPLE_COILS,
            starting_address,
            number_of_coils,
            byte_count,
            list_to_bytes(values)
            )
        response = self._adapter.query(query)

        _, _, coils_written = struct.unpack('BHH', response)
        if coils_written != number_of_coils:
            raise RuntimeError(f"Number of coils written ({coils_written}) doesn't match expected values ({number_of_coils})")

    # Write Multiple Registers - 0x10
    def write_multiple_registers(self):
        pass

    # Report Server ID - 0x11
    def report_server_id(self):
        pass

    # Read File Record - 0x14
    def read_file_record(self):
        pass

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



    

    

    

    

    
