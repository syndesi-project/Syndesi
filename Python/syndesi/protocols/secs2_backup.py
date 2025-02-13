from ..adapters import Adapter, Timeout
from ..protocols import Protocol
from ..adapters.auto import auto_adapter
from ..tools.log import LoggerAlias
from enum import Enum
from math import log2, floor

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

class DataItem:
    def __init__(self, type : DataItemType, contents) -> None:
        self.type = type
        if isinstance(contents, str) and type == DataItemType.ASCII:
            # Allow for unencoded str
            self.contents = contents.encode('ASCII')
        else:
            self.contents = contents

    def encode(self):
        # Byte 0 : format code + number of bytes in length
        # Byte(s) 1-n : length
        # Bytes (n+1)... : data
        match self.type:
            case DataItemType.LIST:
                # Data must be a list of DataItem
                assert isinstance(self.contents, list) and (len(self.contents) == 0 or isinstance(self.contents[0], DataItem)), "Data must be a list of DataItem"
                data_array = sum([el.encode() for el in self.contents])
            case DataItemType.BINARY:
                assert isinstance(self.contents, bytes), 'Contents type must be bytes'
                return self.contents
            case DataItemType.BOOLEAN:
                data_array = b'\x01' if self.contents else b'\x00'
            case DataItemType.ASCII:
                assert isinstance(self.contents, bytes), 'Contents must be bytes or string'
                data_array = self.contents
            case DataItemType.JIS8:
                raise NotImplementedError()
            case DataItemType.UINT64 | DataItemType.UINT32 | DataItemType.UINT16 | DataItemType.UINT8 | DataItemType.INT64 | DataItemType.INT32 | DataItemType.INT16 | DataItemType.INT8:
                signed = self.type in [DataItemType.INT64 | DataItemType.INT32 | DataItemType.INT16 | DataItemType.INT8]
                    
                assert isinstance(self.contents, int), "Data must be an integer"
                length = {
                    DataItemType.INT8 : 1,
                    DataItemType.INT16 : 2,
                    DataItemType.INT32 : 4,
                    DataItemType.INT64 : 8,
                    DataItemType.UINT8 : 1,
                    DataItemType.UINT16 : 2,
                    DataItemType.UINT32 : 4,
                    DataItemType.UINT64 : 8
                }[self.type]
                data_array = self.contents.to_bytes(length, 'big', signed=signed)
            case DataItemType.FLOAT32 | DataItem.FLOAT64:
                pass
        length = len(data_array)
        number_of_length_bytes = floor(log2(length) / 8)
        assert number_of_length_bytes <= 3, f"Error while calculating length bytes (data : {length})"
        array = ((self.type) << 2) + number_of_length_bytes + length.to_bytes(number_of_length_bytes, byteorder='big')

        return array

    def __str__(self) -> str:
        match self.type:
            case DataItemType.LIST:
                pass

            case DataItemType.BINARY:
                string = '0x' + ''.join(f'{x:02X}' for x in self.contents)
            case DataItemType.BOOLEAN:
                pass
            case DataItemType.ASCII:
                # Special characters cannot be printed out in quotes
                # For the moment, multi-line is not supported
                string = ''
                quoted = False
                for c in self.contents:
                    c = chr(c)
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

            case DataItemType.JIS8:
                pass
            #case DataItemType.
        return string

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

