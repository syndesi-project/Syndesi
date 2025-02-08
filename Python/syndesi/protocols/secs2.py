from ..adapters import Adapter
from ..adapters import Timeout
from ..adapters.auto import auto_adapter
import logging
from ..tools.log import LoggerAlias
from enum import Enum


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


# In case of list, dataitems are nested, format+length is repeated


class DataItem:
    def __init__(self, type : DataItemType, contents) -> None:
        self.type = type
        self.contents = contents

    def encode(self):
        # Byte 0 : format code + number of bytes in length
        # Byte(s) 1-n : length
        # Bytes (n+1)... : data
        pass

class Secs2Message:
    def __init__(self, stream : int, function : int) -> None:
        self.stream = stream
        self.function = function

    def encode(self):
        ...

    def __str__(self):
        # TODO : Implement print here
        # Use either SEMI format or SML format (or both ?)
        ...


# T3 : Reply timeout (-> response)
# T4 : Inter-Block Timeout (-> continuation ?)

# Interleaving : managing multiple transactions when they start/end inbetween each other
class Secs2:
    def __init__(self, adapter : Adapter, timeout : Timeout = ...) -> None:
        self._adapter = auto_adapter(adapter)
        if timeout != ...:
            self._adapter.set_default_timeout(timeout)
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)

    def flushRead(self):
        self._adapter.flushRead()

    def send(self, data):
        pass

    def query(self, data, timeout : Timeout = ...):
        pass

    def read(self):
        pass

    def hello(self):
        """
        Say hello to the equipment
        """
        message = Secs2Message(1, 1) 
        self.query(message)

