from .iadapter import IAdapter
import serial
from ..tools.types import to_bytes
from .stop_conditions import *
from .timeout import Timeout
from .timed_queue import TimedQueue
from threading import Thread, Event
from typing import Union

class SerialPort(IAdapter):
    def __init__(self,  
                port : str,
                baudrate : int,
                timeout : Union[Timeout, float],
                stop_condition : StopCondition = None):
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        super().__init__(timeout=timeout, stop_condition=stop_condition)
        self._port = serial.Serial(port=port, baudrate=baudrate)
        if self._port.isOpen():
            self._status = self.Status.CONNECTED
        else:
            self._status = self.Status.DISCONNECTED
        
        self._stop_event = Event()


    def flushRead(self):
        self._port.flush()

    def open(self):
        self._port.open()

    def close(self):
        self._stop_event.set()
        self._port.close()
            
    def write(self, data : bytes):
        data = to_bytes(data)
        if self._status == self.Status.DISCONNECTED:
            self.open()
        self._port.write(data)

    def _start_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = Thread(target=self._read_thread, daemon=True, args=(self._port, self._read_queue, self._stop_event))
            self._thread.start()

    def _read_thread(self, port : serial.Serial , read_queue : TimedQueue, stop_event : Event):
        while not stop_event.is_set():
            byte = port.read(1)
            if not byte:
                break
            read_queue.put(byte)

    def query(self, data : Union[bytes, str]):
        self.flushRead()
        self.write(data)
        return self.read()