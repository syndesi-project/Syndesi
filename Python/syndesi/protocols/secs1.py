from ..adapters import Adapter
from ..adapters import Timeout
from ..adapters.auto import auto_adapter
import logging
from ..tools.log import LoggerAlias


# Handshake codes are (supposedly) sent raw, without anything around them
class HandshakeCode:
    ENQ = 0x05 # Ready to send
    EOT = 0x04 # Ready to receive
    ACK = 0x06 # Correct reception
    NAK = 0x15 # Incorrect reception

HANDSHAKE_CODES_DESCRIPTIONS = {
    HandshakeCode.ENQ : 'Ready to send',
    HandshakeCode.EOT : 'Ready to receive',
    HandshakeCode.ACK : 'Correct reception',
    HandshakeCode.NAK : 'Incorrect reception'
}

# T1 : Inter-Character timeout (-> continuation)
# T2 : Protocol timeout (time between ENQ and EOT -> total ?)
# RTY : Retry limit
# Master/slave : Resolve contention

class Secs1:
    def __init__(self, adapter : Adapter, device_id : int, timeout : Timeout = ...) -> None:
        """
        SECS-I (Block Transfer Protocol) instance
        """
        self._device_id = device_id # TODO : Maybe the device_id shouldn't be set here ? Maybe it should be set in SECS-II ? or in the send_message ? idk
        self._adapter = auto_adapter(adapter)
        if timeout != ...:
            self._adapter.set_default_timeout(timeout)
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)

    def flushRead(self):
        self._adapter.flushRead()

    


    def send_message(self, stream : int, function : int, data : bytes, expect_reply = bool):
        # Each block is
        # - Length (1 byte)
        # - Data bytes (10 to 254)
        #   - Header (10 bytes)
        #     - Device ID (2 bytes)
        #     - Message ID (2 bytes)
        #       - MSB is "W-bit" (sender of primary message is expecting a reply)
        #       - Upper byte is stream
        #       - Lower byte is function
        #     - Block number (2 bytes)
        #       - MSB is "E-bit", 0 indicates there are blocks to follow, 1 means it is the last/only block
        #     - System bytes (4 bytes), should be the same bytes for the reply
        #       - SourceID (2 bytes), sender ID
        #       - transactionID (2 bytes), incremental ?
        #   - Data structure (0 to 244 bytes)
        # - Checksum (2 bytes)
        pass
    
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
        pass

    def query(self, data, timeout : Timeout = ...):
        pass

    def read(self):
        pass