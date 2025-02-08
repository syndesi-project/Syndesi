from ..adapters import Adapter
from ..adapters import Timeout
from ..adapters.auto import auto_adapter
import logging
from ..tools.log import LoggerAlias


class HandshakeCode:
    ENQ = 0x05 # Ready to send
    EOT = 0x04 # Ready to receive
    ACK = 0x06 # Correct reception
    NAK = 0x15 # Incorrect reception


# T1 : Inter-Character timeout (-> continuation)
# T2 : Protocol timeout (time between ENQ and EOT -> total ?)
# RTY : Retry limit
# Master/slave : Resolve contention

class Secs1:
    def __init__(self, adapter : Adapter, timeout : Timeout = ...) -> None:
        self._adapter = auto_adapter(adapter)
        if timeout != ...:
            self._adapter.set_default_timeout(timeout)
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)

    def flushRead(self):
        self._adapter.flushRead()

    def write(self, data):
        # Length (cheksum not included), 10 to 254
        # Data Bytes
        #  10 byte header
        #    DeviceID (upper and lower, MSB of upper is 1 E->H or 0 H->E).
        #    MessageID
        #      MSB of first byte is W (reply expected)
        #      Rest of first byte is stream
        #      Second byte is function
        #    BlockNumber
        #      MSB of first byte is E (last block of message)
        #    SystemBytes
        #      first 2 bytes : sourceID, random ?
        #      last 2 bytes : transactionID, random ?
        #  data structure (secs2 message), can be nothing
        # checksum (2 bytes)
        # 
        # 
        # 
        # 
        pass

    def query(self, data, timeout : Timeout = ...):
        pass

    def read(self):
        pass