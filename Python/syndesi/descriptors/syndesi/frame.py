# Syndesi Frame
#
# Sébastien Deriaz
# 14.11.2022

from enum import Enum
from .sdid import SyndesiID, AddressType
from .payload import Payload
from struct import pack, unpack, calcsize

def _bit_to_bool(buffer, bit):
        return True if buffer & (1 << bit) else False

class NetworkHeader:
    length = 1
    def __init__(self, routing=True, follow=False, error=True):
        """
        Network header
        """
        self.routing = routing
        self.follow = follow
        self.error = error

    def _check_values(self):
        """
        Check values for correct types and values
        """
        assert isinstance(self.routing, bool), f'"routing" has the wrong type {type(self.routing)} instead of bool'
        assert isinstance(self.follow, bool), f'"follow" has the wrong type {type(self.follow)} instead of bool'
        assert isinstance(self.error, bool), f'"error" has the wrong type {type(self.error)} instead of bool'

    def value(self):
        """
        Export network header as byte array
        """
        self._check_values()

        value = self.routing | (self.follow << 1) | (self.error << 2)

        return value
    
    def parse(self, buffer):
        """
        Parse the header from a buffer

        Parameters
        ----------
        buffer : int
        """

        self.routing = _bit_to_bool(buffer, 0)
        self.follow = _bit_to_bool(buffer, 1)
        self.error = _bit_to_bool(buffer, 2)

class ErrorCode(Enum):
    NO_ERROR = 0,
    NO_INTERPETER = 1,
    INVALID_PAYLOAD = 2



class OutboundFrame():
    def __init__(self, payload : Payload, ID : SyndesiID):
        """
        Outbound Frame instance (host -> device)

        Parameters
        ----------
        payload : Payload
            The payload to send
        ID : SyndesiID
            Device's ID
            
        """
        self.ID = ID
        self._payload = payload

    def data(self):
        """
        Return frame raw data
        """
        STRUCT_FORMAT = lambda pl : f'!BH{pl}s'
        # Create network header
        header = NetworkHeader()
        header.follow = False
        header.routing = False
        header.error = False
        # Payload
        payload_buffer = self._payload.value()
        # Frame length
        length = len(payload_buffer) # Length of payload

        buffer = pack(STRUCT_FORMAT(length), header.value(), length, payload_buffer)

        return buffer

class InboundFrame():
    def __init__(self, buffer : bytes, requestFrame : OutboundFrame) -> None:
        """
        Inbound frame instance (device -> host)
        
        Parameters
        ----------
        buffer : bytes
            The buffer to parse
        ID : SyndesiID
            Device's ID
        requestFrame : OutboundFrame
            The frame sent for the request, this is to identify the confirm payload
        """
        self.ID = requestFrame.ID
        self.isErrorFrame = False

        # Parsing

        # Read the header
        HEADER_STRUCT_FORMAT = '!BH'
        header_size = calcsize(HEADER_STRUCT_FORMAT)
        
        header_byte, length_or_error = unpack(HEADER_STRUCT_FORMAT, buffer[:header_size])

        # Header
        self.header = NetworkHeader()
        self.header.parse(header_byte)

        self.isErrorFrame = True if self.header.error else False
        if self.isErrorFrame:
            # Error frame, the rest is the error code
            self.errorCode = ErrorCode(length_or_error)
        else:
            # Read the payload
            payloadBuffer = buffer[header_size:header_size+length_or_error]
            self.payload = requestFrame._payload._reply(payloadBuffer)