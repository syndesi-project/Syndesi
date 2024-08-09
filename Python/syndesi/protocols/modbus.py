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
    READ_DEVICE_IDENTIFICATION = 0x2B # 2BOE ?

SERIAL_LINE_ONLY_CODES = [
    FunctionCode.DIAGNOSTICS,
    FunctionCode.GET_COMM_EVENT_COUNTER,
    FunctionCode.REPORT_SERVER_ID,
    FunctionCode.READ_EXCEPTION_STATUS,
    ]

def list_to_bytes(lst : list):
    byte_count = ceil(lst / 8)
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

    def read_coils(self, starting_address : int, number_of_coils : int):
        query = struct.pack('BHH', FunctionCode.READ_COILS, starting_address, number_of_coils)
        response = self._adapter.query(self._make_pdu(query))
        n_coil_bytes = ceil(number_of_coils / 8)
        _, _, coil_bytes = struct.unpack(f'BB{n_coil_bytes}s', response)

        return bytes_to_list(coil_bytes)
    def read_coil(self, address : int):
        return self.read_coils(starting_address=address, number_of_coils=1)[0]

    def write_coil(self, address : int, enabled : bool):
        query = struct.pack('BHH', FunctionCode.WRITE_SINGLE_COIL, address, 0xFF00 if enabled else 0x0000)
        response = self._adapter.query(query)
        assert query == response, f"Write single coil response should match query {query} != {response}"

    def write_coils(self, starting_address : int, values : List[bool]):
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

    def read_discrete_inputs(self, start_address : int, number_of_inputs : int):
        query = struct.pack('BHH', FunctionCode.READ_DISCRETE_INPUTS, start_address, number_of_inputs)
        byte_count = ceil(number_of_inputs / 8) # pre-calculate the number of returned coil value bytes
        response = self._adapter.query(query)
        _, _, data = struct.unpack(f'BB{byte_count}s', response)
        return bytes_to_list(data, number_of_inputs)

    def write_register(self, address : int, value : int):
        query = struct.pack('BHH', FunctionCode.WRITE_SINGLE_REGISTER, address, value)
        response = self._adapter.query(query)
        assert query == response, f"Response ({response}) should match query ({query})"
