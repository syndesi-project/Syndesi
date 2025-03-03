from ..adapters import Adapter, Timeout, SerialPort, IP
from . import Protocol
from ..adapters.auto import auto_adapter
from ..tools.log import LoggerAlias
from enum import Enum
from math import log2, floor
from abc import abstractmethod, abstractproperty
import struct
from .secs1 import Secs1
from .hsms import HSMS

class AnnotationStandard(Enum):
    SEMI = 0
    SML = 1

ASCII_CHARACTERS = [chr(x) for x in range(128)]
ASCII_QUOTEABLE_CHARACTERS = set([c for c in ASCII_CHARACTERS if c.isprintable() and c != '"'])


ANNOTATION_STANDARD = AnnotationStandard.SML

# Stream categories
STREAM_CATEGORIES = {
    1 : 'Equipment Status',
    2 : 'Equipment Control',
    3 : 'Material Status',
    4 : 'Material Control',
    5 : 'Alarm Handling',
    6 : 'Data Collection',
    7 : 'Recipe Management',
    8 : 'Control Program Transfer',
    9 : 'System Errors',
    10 : 'Terminal Services',
    # 11 : Not used,
    12 : 'Wafer Mapping',
    13 : 'Unformatted Data Set Transfers'
}

# Functions
# | Stream(s) | Functions |    Status    |
# |-----------|-----------|--------------|
# |    0      |  0 to 255 |   Reserved   |
# |  1 to 63  |  0 to 63  |   Reserved   |
# | 64 to 127 |     0     |   Reserved   |
# |  1 to 63  | 64 to 255 | User defined |
# | 64 to 127 |  1 to 255 | User defined |

# Function 0 has a special meaning : reply to an aborted primary message

class DataItemType(Enum):
    LIST    = 0b000000
    BINARY  = 0b001000
    BOOLEAN = 0b001001
    ASCII   = 0b010000
    JIS8    = 0b010001
    INT64   = 0b011000
    INT8    = 0b011001
    INT16   = 0b011010
    INT32   = 0b011100
    FLOAT64 = 0b100000
    FLOAT32 = 0b100100
    UINT64  = 0b101000
    UINT8   = 0b101001
    UINT16  = 0b101010
    UINT32  = 0b101100

DATAITEM_TYPE_SYMBOL = {
    DataItemType.LIST : 'L',
    DataItemType.BINARY : 'B',
    DataItemType.BOOLEAN : 'BOOLEAN',
    DataItemType.ASCII : 'A',
    DataItemType.JIS8 : 'J',
    DataItemType.INT64 : 'I8',
    DataItemType.INT8 : 'I1',
    DataItemType.INT16 : 'I2',
    DataItemType.INT32 : 'I4',
    DataItemType.FLOAT64 : 'F8',
    DataItemType.FLOAT32 : 'F4',
    DataItemType.UINT64 : 'U8',
    DataItemType.UINT8 : 'U1',
    DataItemType.UINT16 : 'U2',
    DataItemType.UINT32 : 'U3',
}

N_BYTES = {
    DataItemType.INT8 : 1,
    DataItemType.INT16 : 2,
    DataItemType.INT32 : 4,
    DataItemType.INT64 : 8,
    DataItemType.UINT8 : 1,
    DataItemType.UINT16 : 2,
    DataItemType.UINT32 : 4,
    DataItemType.UINT64 : 8,
    DataItemType.FLOAT32 : 4,
    DataItemType.FLOAT64 : 8
}

# In case of list, dataitems are nested, format+length is repeated

# Zero length items for each type is possible, check for that

def decode_dataitem(dataitem_array : bytes):
    # read the format code
    format_header = dataitem_array[0]
    _type = DataItemType(format_header >> 2)
    number_of_length_bytes = format_header & 0b11
    length = int.from_bytes((dataitem_array[1:1+number_of_length_bytes]), 'big', signed=False)
    expected_length_total = 1 + number_of_length_bytes + length
    assert len(dataitem_array) >= expected_length_total, f"Invalid dataitem array size, expected {expected_length}, received {len(dataitem_array)}"
    data = dataitem_array[1+number_of_length_bytes:1+number_of_length_bytes+length]
    remaining = dataitem_array[1+number_of_length_bytes+length:]

    match _type:
        case DataItemType.LIST:
            data_item = DIList.from_bytes(data)
        case DataItemType.BINARY:
            data_item = DIBinary.from_bytes(data)
        case DataItemType.BOOLEAN:
            data_item = DIBinary.from_bytes(data)
        case DataItemType.ASCII:
            data_item = DIAscii.from_bytes(data)
        case DataItemType.JIS8:
            data_item = DIJIS8.from_bytes(data)
        case DataItemType.INT8 | DataItemType.INT16 | DataItemType.INT32 | DataItemType.INT64:
            data_item = DIInt.from_bytes(data, size=N_BYTES[_type])
        case DataItemType.UINT8 | DataItemType.UINT16 | DataItemType.UINT32 | DataItemType.UINT64:
            data_item = DIUInt.from_bytes(data, size=N_BYTES[_type])
        case DataItemType.FLOAT32 | DataItemType.FLOAT64:
            data_item = DIFloat.from_bytes(data, size=N_BYTES[_type])
        case _:
            raise ValueError(f'Cannot decode data item array : {dataitem_array}')

    return data_item, remaining

class DataItem:
    _TYPE : DataItemType = None
    def __init__(self, data) -> None:
        self.data = data

    def _encode_wrapper(self, item_array):
        length = len(item_array)
        if length == 0:
            # Empty item
            number_of_length_bytes = 0
        else:
            number_of_length_bytes = floor(log2(length) / 8)+1

        format_header = bytes([(self._TYPE.value << 2) + number_of_length_bytes])
        
        if length == 0:
            length_bytes = b''
        else:
            length_bytes = length.to_bytes(number_of_length_bytes, byteorder='big', signed=False)

        return format_header + length_bytes + item_array

    @abstractmethod
    def from_bytes(data):
        pass

    @abstractmethod
    def encode(self):
        pass

def indent(string, indent : int):
    return '\n'.join([' '*indent + line for line in string.split('\n')])

class DIList(DataItem):
    _TYPE = DataItemType.LIST
    
    def __init__(self, dataitems : list) -> None:
        super().__init__(dataitems)

    def encode(self):
        # Encode all of the items
        encoded_items = [dataitem.encode() for dataitem in self.data]
        items_array = b''.join(encoded_items)

        return self._encode_wrapper(items_array)

    def from_bytes(data):
        # Parse individual elements
        dataitems = []
        remaining = data
        while len(remaining) > 0:
            data_item, remaining = decode_dataitem(remaining)
            dataitems.append(data_item)
        return DIList(dataitems)

    def __str__(self) -> str:
        INDENT = 4
        if len(self.data) == 0:
            # Empty list
            string = f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]}>'
        else:
            string = f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]} [{len(self.data)}]\n'
            for dataitem in self.data:
                string += indent(str(dataitem), INDENT) + '\n'
            string += '>'
        return string

class DIAscii(DataItem):
    _TYPE = DataItemType.ASCII
    def __init__(self, data : str = ...) -> None:
        # If data is bytes, store it as string (easier for the user)
        # and convert it when necessary
        if data is ...:
            super().__init__(None)
        elif isinstance(data, str):
            # Allow for unencoded str
            super().__init__(data)
        elif isinstance(data, bytes):
            super().__init__(data.decode('ASCII'))
        else:
            raise TypeError('Data must be bytes or string')

    def encode(self):
        if self.data is None:
            data_array = b''
        else:
            data_array = self.data.encode('ASCII')
        return self._encode_wrapper(data_array)

    def from_bytes(data):
        return DIAscii(data)

    def __str__(self) -> str:
        # Special characters cannot be printed out in quotes
        # Multi-line is not supported for the moment
        string = ''
        if self.data is not None:
            if self.data == '':
                # Special case, not specified, return an empty string
                string = ' ""'
            else:
                string += ' '
                quoted = False
                for c in self.data:
                    if c in ASCII_QUOTEABLE_CHARACTERS:
                        if not quoted:
                            if len(string) > 0:
                                string += ' '
                            string += '"'
                        quoted = True

                        string += c
                    else:
                        if quoted:
                            string += '" '
                        string += f'0x{ord(c):02X}'
                        quoted = False
                if quoted:
                    string += '"'
        return f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]}{string}>'

class DIBinary(DataItem):
    _TYPE = DataItemType.BINARY

    def __init__(self, data : bool = ...) -> None:
        if data is ...:
            data = None
        else:
            assert isinstance(data, bytes), 'Data must be bytes'
        super().__init__(data)
    
    def encode(self):
        if self.data is None:
            data_array = b''
        else:
            data_array = self.data
        return self._encode_wrapper(data_array)

    def from_bytes(data):
        return DIBinary(data)

    def __str__(self) -> str:
        if self.data is None:
            return f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]}>'
        binary_values = ''.join(f'{x:02X}' for x in self.data)
        return f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]} 0x{binary_values}>'

class DIBoolean(DataItem):
    _TYPE = DataItemType.BOOLEAN

    def __init__(self, value : bool = ...) -> None:
        if value is ...:
            data = None
        elif value:
            data = 0x01
        else:
            data = 0x00
        super().__init__(data)
    
    def encode(self):
        if self.data is None:
            encoded_data = b''
        else:
            encoded_data = struct.pack('>?', self.data)
        return self._encode_wrapper(encoded_data)

    def from_bytes(data):
        return DIBoolean(data)
    
    def __str__(self) -> str:
        if self.data is None:
            string = ''
        else:
            string = str(self.data)
        return f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]}{string}>'

class DIJIS8(DataItem):
    _TYPE = DataItemType.JIS8
    def __init__(self, data) -> None:
        raise NotImplementedError()

class DIInt(DataItem):
    signed = True
    def __init__(self, value : int = ..., size : int = ...) -> None:
        if size is ...:
            raise ValueError('Size must be specified even if the dataitem is empty')
        if value is ...:
            # Empty
            value = None
        else:
            assert isinstance(value, int), "Value must be an integer"
            if size not in [1, 2, 4, 8]:
                raise ValueError(f'Invalid size : {size}')

        self._size = size
        
        if self.signed:
            self._TYPE = {
                1 : DataItemType.INT8,
                2 : DataItemType.INT16,
                4 : DataItemType.INT32,
                8 : DataItemType.INT64
            }[self._size]
        else:
            self._TYPE = {
                1 : DataItemType.UINT8,
                2 : DataItemType.UINT16,
                4 : DataItemType.UINT32, 
                8 : DataItemType.UINT64
            }[self._size]
        super().__init__(value)
    
    def encode(self):
        if self.data is None:
            encoded_data = b''
        else:
            encoded_data = self.data.to_bytes(self._size, byteorder='big', signed=self.signed)
        return self._encode_wrapper(encoded_data)

    def from_bytes(data, size):
        return DIInt(int.from_bytes(data, 'big', signed=True), size)

    def __str__(self) -> str:
        string = ''
        if self.data is not None:
            string = f' {self.data}'
        return f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]}{string}>'

class DIUInt(DIInt):
    signed = False

    def from_bytes(data, size : int):
        return DIUInt(int.from_bytes(data, 'big', signed=False), size)
    
class DIFloat(DataItem):
    def __init__(self, value : float = None, size : float = None) -> None:
        if size is None:
            raise ValueError('size must be specified, even if the value is empty')
        if value is not None:
            assert isinstance(value, float), f"Value must be float, not {type(value)}"
            if size not in [4, 8]:
                raise ValueError(f'Invalid size : {size}')
        self._size = size
        self._TYPE = {
            4 : DataItemType.FLOAT32,
            8 : DataItemType.FLOAT64
        }[self._size]
        super().__init__(value)

    def encode(self):
        if self.data is None:
            encoded_data = b''
        else:    
            pack_symbol = 'f' if self._size == 4 else 'd'
            encoded_data = struct.pack(f'>{pack_symbol}', self.data)
        return self._encode_wrapper(encoded_data)

    def from_bytes(data, size):
        if len(data) == 0:
            value = None
        elif size in [4, 8]:
            unpack_symbol = 'f' if size == 4 else 'd'
            value = struct.unpack(f'>{unpack_symbol}', data)[0]
        else:
            raise ValueError(f'Invalid float data length : {size}')
        
        return DIFloat(value, size)

    def __str__(self):
        string = ''
        if self.data is not None:
            string = f' {self.data}'
        return f'<{DATAITEM_TYPE_SYMBOL[self._TYPE]}{string}>'

class Secs2Message:
    def __init__(self, stream : int, function : int, data_item : DataItem = ...) -> None:
        self.stream = stream
        self.function = function
        
        assert isinstance(data_item, DataItem) or data_item is ..., "data_item must be a data_item or shouldn't be set"
        #assert all([isinstance(_type, DataItemType) for _type in dataitems]), "dataitems must be a list of tuple with the first element an instance of DataItemType"
        self.dataitem = data_item

    def decode(stream : int, function : int, data : bytes):
        return Secs2Message(stream, function, decode_dataitem(data))

    def encode(self):
        return self.dataitem.encode()

    def __str__(self) -> str:
        return f'S{self.function}S{self.stream}\n' + str(self.dataitem) + '    .' # TODO : Check the position of the dot

# T3 : Reply timeout (-> response)
# T4 : Inter-Block Timeout (-> continuation ?)

# Interleaving : managing multiple transactions when they start/end inbetween each other
class Secs2(Protocol):
    def __init__(self, adapter : Adapter, source_id : int, timeout : Timeout = ...) -> None:
        super().__init__(adapter, timeout)
        if isinstance(adapter, SerialPort):
            self._prot = Secs1(adapter, timeout)
        elif isinstance(adapter, IP):
            self._prot = HSMS(adapter, source_id)
        else:
            raise ValueError(f'Invalid adapter : {type(adapter)}')

    def write(self, device_id : int, message : Secs2Message):
        assert message.stream % 2 == 1, "SECS-II primary message stream must be odd"
        self._prot.write(device_id, message.stream, message.function, message)

    def query(self, device_id : int, message : Secs2Message):
        stream, function, data_out = self._prot.query(device_id, message.stream, message.function, message.encode())
        return Secs2Message.decode(stream, function, data_out)

    def read(self, device_id) -> Secs2Message:
        stream, function, data_out = self._prot.read(device_id)

    def hello(self):
        """
        Say hello to the equipment
        """
        message = Secs2Message(1, 1)
        self.query(message)