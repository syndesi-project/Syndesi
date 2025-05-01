from ..adapters import IP, Adapter
from ..adapters import Timeout
from .protocol import Protocol
from ..adapters.auto import auto_adapter
import logging
from ..tools.log import LoggerAlias
import struct

class SType:
    DATA = 0
    SELECT_REQ = 1
    SELECT_RSP = 2
    DESELECT_REQ = 3
    DESELECT_RSP = 4
    LINKTEST_REQ = 5
    LINKTEST_RSP = 6
    SEPARATE_REQ = 7 

class HSMS(Protocol):
    class Header:
        _FORMAT = '<HBBBB4s'
        _HEADER_SIZE = 10
        def __init__(self, 
            stype : SType,
            system_bytes : bytes,
            device_id : int = ...,
            stream : int = ...,
            function : int = ...,
            w_bit : bool = ...,
            select_status : int = ...):
            self.stype = stype
            self.system_bytes = system_bytes
            if self.stype == SType.DATA:
                assert device_id is not Ellipsis, "device_id must be set if stype is data"
                assert stream is not Ellipsis, "stream must be set if stype is data"
                assert function is not Ellipsis, "function must be set if stype is data"
                assert w_bit is not Ellipsis, "wbit must be set if stype is data"
                self.device_id = device_id
                self.stream = stream
                self.function = function
                self.wbit = w_bit
            else:
                self.device_id = 0xFFFF
                self.wbit = False
                self.stream = 0
                if self.stype == SType.SELECT_REQ:
                    assert select_status is not Ellipsis, "select_status must be set if stype is select_req"
                    self.function = select_status
                else:
                    self.function = 0

        def encode(self) -> bytes:
            return struct.pack(self._FORMAT,
                self.device_id,
                0b10000000 & self.wbit | self.stream,
                self.function,
                0x00,
                self.stype.value,
                self.system_bytes
                )

        def decode(header : bytes):
            device_id, wbit_stream, function, _, stype, system_bytes = struct.unpack(HSMS.Header._FORMAT, header)
            return HSMS.Header(
                    SType(stype),
                    system_bytes,
                    device_id,
                    wbit_stream & 0b01111111,
                    function,
                    wbit_stream & 0b10000000 > 0)


    def __init__(self, adapter : IP, source_id : int, timeout : Timeout = ...) -> None:
        self._adapter = adapter
        if timeout != ...:
            self._adapter.set_default_timeout(timeout)
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)
        self._transaction_id = 0
        self._source_id = source_id

    def flushRead(self):
        self._adapter.flushRead()

    def _encode_message(self, header : Header, message : bytes = b''):
        return struct.pack(f'<I{HSMS.Header._HEADER_SIZE}s', len(message)+HSMS.Header._HEADER_SIZE, header.encode()) + message
    
    def _system_bytes(self):
        array = struct.pack('<HH', self._source_id, self._transaction_id)
        self._transaction_id += 1
        return array
    def _select(self, select_status):
        header = self.Header(
            SType.SELECT_REQ,
            self._system_bytes(),
            select_status=select_status
        )
        response = self._adapter.query(self._encode_message(header))
        received_header = self.Header.decode(response)
        assert received_header.stype == SType.SELECT_RSP

    def _deselect(self):
        header = self.Header(
            SType.DESELECT_REQ,
            self._system_bytes(),
        )
        response = self._adapter.query(self._encode_message(header))
        received_header = self.Header.decode(response)
        assert received_header.stype == SType.DESELECT_REQ

    def _link_test(self):
        header = self.Header(
            SType.LINKTEST_REQ,
            self._system_bytes(),
        )
        response = self._adapter.query(self._encode_message(header))
        received_header = self.Header.decode(response)
        assert received_header.stype == SType.LINKTEST_RSP

    def _separate(self):
        header = self.Header(
            SType.SEPARATE_REQ,
            self._system_bytes()
        )
        self._adapter.write(self._encode_message(header))

    def _data_header(self, device_id, stream, function, w_bit):
        return self.Header(
            SType.DATA,
            self._system_bytes(),
            device_id=device_id,
            stream=stream,
            function=function,
            w_bit=w_bit
        ) 

    def write(self, device_id : int, stream : int, function : int, message : bytes):
        header = self._data_header(device_id, stream, False)
        self._adapter.write(self._encode_message(header, message))    

    def query(self, device_id, stream : int, function : int, message : bytes, timeout : Timeout = ...):
        header = self._data_header(device_id, stream, function, True)
        response = self._adapter.query(self._encode_message(header, message))
        received_header = self.Header.decode(response[:self.Header._HEADER_SIZE])
        received_data = response[self.Header._HEADER_SIZE:]
        assert received_header.stype == SType.DATA
        return received_data

    def read(self):
        response = self._adapter.read()
        #header = self.Header.decode(response[:self.Header._HEADER_SIZE])
        data = response[:self.Header._HEADER_SIZE]
        return data