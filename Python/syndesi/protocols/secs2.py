from ..adapters import Adapter, Timeout
from ..protocols import Protocol
from ..adapters.auto import auto_adapter
from ..tools.log import LoggerAlias
from enum import Enum
from math import log2, floor
from abc import abstractmethod, abstractproperty
import struct
from typing import Self

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

# In case of list, dataitems are nested, format+length is repeated

# Zero length items for each type is possible, check for that

def decode(dataitem_array : bytes):
    # read the format code
    format_header = dataitem_array[0]
    _type = DataItemType(format_header >> 2)
    number_of_length_bytes = format_header & 0b11
    length = int.from_bytes((dataitem_array[1:1+number_of_length_bytes]), 'big', signed=False)
    expected_length = 1 + number_of_length_bytes + length
    assert len(dataitem_array) == expected_length, f"Invalid dataitem array size, expected {expected_length}, received {len(dataitem_array)}"
    data = dataitem_array[1+number_of_length_bytes:]

    match _type:
        case DataItemType.LIST:
            return DIList.from_bytes(data)

class DataItem:
    _SYMBOL : str = None
    _FORMAT_CODE : int = None
    def __init__(self, data) -> None:
        self.data = data

    def _encode_wrapper(self, item_array):
        length = len(item_array)
        number_of_length_bytes = floor(log2(length) / 8)
        format_header = bytes([self._FORMAT_CODE << 2 + number_of_length_bytes])
        length_bytes = number_of_length_bytes.to_bytes(number_of_length_bytes, byteorder='big', signed=False)

        return format_header + length_bytes + item_array

    @abstractmethod
    def from_bytes(data) -> Self:
        pass

    @abstractmethod
    def encode(self):
        pass

def indent(string, indent : int):
    return '\n'.join([' '*indent + line for line in string.split('\n')])

class DIList(DataItem):
    _SYMBOL = 'L'
    
    def __init__(self, dataitems : list) -> None:
        super().__init__(dataitems)

    def encode(self):
        # Encode all of the items
        items_array = sum([dataitem.encode() for dataitem in self.data])

        self._encode_wrapper(items_array)

    def from_bytes(data) -> Self:
        return DIList(data)

    def __str__(self) -> str:
        INDENT = 4
        if len(self.data) == 0:
            # Empty list
            string = f'<{self._SYMBOL}>'
        else:
            string = f'<{self._SYMBOL} [{len(self.data)}]\n'
            for dataitem in self.data:
                string += indent(str(dataitem), INDENT) + '\n'
            string += '>'
        return string

class DIAscii(DataItem):
    _SYMBOL = 'A'
    def __init__(self, data) -> None:
        # If data is bytes, store it as string (easier for the user)
        # and convert it when necessary
        if isinstance(data, str):
            # Allow for unencoded str
            super().__init__(data)
        elif isinstance(data, bytes):
            super().__init__(data.decode('ASCII'))
        else:
            raise TypeError('Data must be bytes or string')

    def encode(self):
        return self._encode_wrapper(self.data.encode('ASCII'))

    def from_bytes(data) -> Self:
        return DIAscii(data)

    def __str__(self) -> str:
        # Special characters cannot be printed out in quotes
        # Multi-line is not supported for the moment
        string = ''
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
        
        return f'<{self._SYMBOL} {string}>'

class DIBinary(DataItem):
    _SYMBOL = 'B'

    def __init__(self, data) -> None:
        assert isinstance(data, bytes), 'Data must be bytes'
        super().__init__(data)
    
    def encode(self):
        return self._encode_wrapper(self.data)

    def __str__(self) -> str:
        binary_values = ''.join(f'{x:02X}' for x in self.data)
        return f'<{self._SYMBOL} 0x{binary_values}>'

class DIBoolean(DataItem):
    _SYMBOL = 'BOOLEAN'

    def __init__(self, value) -> None:
        super().__init__(0x01 if value else 0x00)
    
    def encode(self):
        return self._encode_wrapper(self.data)
    
    def __str__(self) -> str:
        return f'<{self._SYMBOL} {self.data}>'

class DIJIS8(DataItem):
    _SYMBOL = 'J'
    def __init__(self, data) -> None:
        raise NotImplementedError()

class DIInt(DataItem):
    signed = True
    def __init__(self, value : int, size : int) -> None:
        assert isinstance(value, int), "Value must be an integer"
        if size not in [1, 2, 4, 8]:
            raise ValueError(f'Invalid size : {size}')
        self._size = size
        if self.signed:
            self._SYMBOL = f'I{size}'
        else:
            self._SYMBOL = f'U{size}'
        super().__init__(value)
    
    def encode(self):
        self.data : int
        array = self.data.to_bytes(self._size, byteorder='big', signed=self.signed)
        return self._encode_wrapper(array)

    def __str__(self) -> str:
        return f'<{self._SYMBOL} {self.data}>'

class DIUInt(DIInt):
    signed = False
    
class DIFloat(DataItem):
    def __init__(self, value, size) -> None:
        assert isinstance(value, float), "Value must be float"
        if size not in [4, 8]:
            raise ValueError(f'Invalid size : {size}')
        self._size = size
        super().__init__(value)

    def encode(self):
        pack_symbol = 'f' if self._size == 4 else 'd'
        struct.pack(f'>{pack_symbol}', self.data)

class Secs2Message:
    def __init__(self, stream : int, function : int, dataitems : list) -> None:
        self.stream = stream
        self.function = function
        assert all([isinstance(_type, DataItemType) for _type in dataitems]), "dataitems must be a list of tuple with the first element an instance of DataItemType"
        self.dataitems = [DataItem(_type, data) for _type, data in dataitems]

    def encode(self):
        array = b''
        for dataitem in self.dataitems:
            # Create the DataItem
            array += dataitem.encode()

    def __str__(self) -> str:
        output = ''
        if ANNOTATION_STANDARD == AnnotationStandard.SML:
            for dataitem in self.dataitems:
                output += str(dataitem) + '\n'
        else:
            raise NotImplementedError()


# T3 : Reply timeout (-> response)
# T4 : Inter-Block Timeout (-> continuation ?)

# Interleaving : managing multiple transactions when they start/end inbetween each other
class Secs2(Protocol):
    def __init__(self, adapter : Adapter, timeout : Timeout = ...) -> None:
        super().__init__(adapter, timeout)

    def send_message(self, message : Secs2Message):
        assert message.stream % 2 == 1, "SECS-II primary message stream must be odd"

    def query(self, message : Secs2Message):
        self.send_message(message)
        output = self.read()
        return output

    def read(self) -> Secs2Message:
        pass

    def hello(self):
        """
        Say hello to the equipment
        """
        message = Secs2Message(1, 1) 
        self.query(message)

