# adapters.py
# Sébastien Deriaz
# 06.05.2023
#
# Adapters provide a common abstraction for the media layers (physical + data link + network)
# The following classes are provided, which all are derived from the main Adapter class 
#   - IP
#   - Serial
#   - USBVisa
# 
# Note that technically VISA is not part of the media layer, only USB is.
# This is a limitation as it is to this day not possible to communication "raw"
# with a device through USB yet

from abc import abstractmethod, ABC
from enum import Enum
import socket

class IAdapter(ABC):
    @abstractmethod
    def __init__(self, descriptor, *args):
        pass

    @abstractmethod
    def flushRead(self):
        pass

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass
            
    @abstractmethod
    def write(self, data : bytearray):
        pass
    
    @abstractmethod
    def read(self):
        pass

class IP(IAdapter):
    class Status(Enum):
        DISCONNECTED = 0
        CONNECTED = 1
    class Protocol(Enum):
        TCP = 0
        UDP = 1
    def __init__(self, descriptor : str, port = None, transport : Protocol = Protocol.TCP):
        """
        IP stack adapter

        Parameters
        ----------
        descriptor : str
            IP description
        port : int
            port used (optional, can be specified in descriptor)
        transport : Transport
            Transport protocol, TCP or UDP
        """
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(5)
        self._ip = descriptor # TODO : update this
        self._port = port
        self._status = self.Status.DISCONNECTED


    def flushRead(self):
        return super().flushRead()

    def open(self):
        self._socket.connect((self._ip, self._port))
        self._status = self.Status.CONNECTED

    def close(self):
        self._socket.close()
            
    def write(self, data : bytearray):
        if self._status == self.Status.DISCONNECTED:
            self.open()
        self._socket.send(data)

    def read(self):
        if self._status == self.Status.DISCONNECTED:
            self.open()
        
        self._socket.settimeout(5)

        buffer = b''
        while True:
            try:
                recv = self._socket.recv(10)
                self._socket.settimeout(0.05)
                buffer += recv
            except TimeoutError:
                break
        return buffer

class Serial(IAdapter):
    def __init__(self, descriptor : str):
        """
        Serial communication adapter

        Parameters
        ----------
        descriptor : str
            Serial port (COMx or ttyACMx)
        """
        pass

    def flushRead(self):
        pass

    def open(self):
        pass

    def close(self):
        pass
            
    def write(self, data : bytearray):
        pass
    
    def read(self):
        pass

class USBVisa(IAdapter):
    def __init__(self, descriptor : str):
        """
        USB VISA stack adapter

        Parameters
        ----------
        descriptor : str
            IP description
        """
        pass

    def flushRead(self):
        pass

    def open(self):
        pass

    def close(self):
        pass
            
    def write(self, data : bytearray):
        pass
    
    def read(self):
        pass