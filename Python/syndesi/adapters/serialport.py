from .iadapter import IAdapter
import serial
from ..tools.types import assert_byte_instance
from .stop_conditions import *
from .timed_queue import TimedQueue
from threading import Thread

class Serial(IAdapter):
    def __init__(self, port : str, baudrate : int, stop_condition : StopCondition):
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        super().__init__(stop_condition)
        self._port = serial.Serial(port=port, baudrate=baudrate)
        
        self._thread = Thread(target=self._read_thread, daemon=True, args=(self._port, self._read_queue))

    def flushRead(self):
        self._port.flush()

    def open(self):
        self._port.open()

    def close(self):
        self._port.close()
            
    def write(self, data : bytes):
        assert_byte_instance(data)
        if self._status == self.Status.DISCONNECTED:
            self.open()
        self._port.write(data)

    def _set_timeout(self, timeout):
        return self._port.tim

    def _read_thread(self, port : serial.Serial , read_queue : TimedQueue):
        while True:
            byte = port.read(1)
            if not byte:
                break
            read_queue.put(byte)

    def query(self, data : bytes):
        self.flushRead()
        self.write(data)
        return self.read()