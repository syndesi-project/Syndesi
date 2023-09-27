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
        self._port = serial.Serial(port=port, baudrate=baudrate)
        self._stop_condition = stop_condition
        
        self._thread = Thread(target=self._read_thread, daemon=True, args=(self._port, self._read_queue))

    def flushRead(self):
        self._port.flush()

    def open(self):
        self._port.open()

    def close(self):
        self._port.close()
            
    def write(self, data : bytes):
        assert_byte_instance(data)
        self._port.write(data)

    def _read_thread(self, port : serial.Serial , read_queue : TimedQueue):
        while True:
            byte = port.read(1)
            if not byte:
                break
            read_queue.put(byte)
    
    def read(self):
        if not self._thread.is_alive():
            self._thread.start()

        timeout = self._stop_condition.initiate_read()
        self._port.timeout = timeout

        buffer = b''
        while True:
            (_, byte) = self._read_queue.get(timeout)

        # TODO : Implement timeout strategy
        return self._port.read_all()

    def query(self, data : bytes):
        self.flushRead()
        self.write(data)
        return self.read()