from .iadapter import IAdapter
import serial
from ..tools.types import assert_byte_instance

class Serial(IAdapter):
    def __init__(self, port : str, baudrate=115200):
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        self._port = serial.Serial(port=port, baudrate=baudrate)

    def flushRead(self):
        self._port.flush()

    def open(self):
        self._port.open()

    def close(self):
        self._port.close()
            
    def write(self, data : bytes):
        assert_byte_instance(data)
        self._port.write(data)
    
    def read(self):
        # TODO : Implement timeout strategy
        return self._port.read_all()

    def query(self, data : bytes):
        self.flushRead()
        self.write(data)
        return self.read()