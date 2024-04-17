from .adapter import Adapter
import serial
from ..tools.types import to_bytes
from .stop_conditions import *
from .timeout import Timeout
from .timed_queue import TimedQueue
from threading import Thread
from typing import Union
import select

# From pyserial - serialposix.py
import fcntl
import termios
import struct
if hasattr(termios, 'TIOCINQ'):
    TIOCINQ = termios.TIOCINQ
else:
    TIOCINQ = getattr(termios, 'FIONREAD', 0x541B)
TIOCM_zero_str = struct.pack('I', 0)
import os

DEFAULT_TIMEOUT = Timeout(response=0.5, continuation=10e-3, total=None)

class SerialPort(Adapter):
    def __init__(self,  
                port : str,
                baudrate : int,
                timeout : Union[Timeout, float] = DEFAULT_TIMEOUT,
                stop_condition : StopCondition = None):
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        super().__init__(timeout=timeout, stop_condition=stop_condition)
        self._logger.info("Setting up SerialPort adapter")
        self._port = serial.Serial(port=port, baudrate=baudrate)
        if self._port.isOpen():
            self._status = self.Status.CONNECTED
        else:
            self._status = self.Status.DISCONNECTED
        
        self._stop_event_pipe, self._stop_event_pipe_write = os.pipe()

    def flushRead(self):
        self._port.flush()

    def open(self):
        self._port.open()
        # Flush the input buffer
        buf = b'0'
        while buf:
            buf = os.read(self._port.fd)
        self._logger.info("Adapter opened !")

    def close(self):
        if self._thread.is_alive():
            os.write(self._stop_event_pipe_write, b'1')
            self._thread.join()
        self._port.close()
        self._logger.info("Adapter closed !")
            
    def write(self, data : bytes):
        data = to_bytes(data)
        if self._status == self.Status.DISCONNECTED:
            self.open()
        write_start = time()
        self._port.write(data)
        write_duration = time() - write_start
        self._logger.debug(f"Written [{write_duration*1e3:.3f}ms]: {repr(data)}")

    def _start_thread(self):
        self._logger.debug("Starting read thread...")
        if self._thread is None or not self._thread.is_alive():
            self._thread = Thread(target=self._read_thread, daemon=True, args=(self._port, self._read_queue, self._stop_event_pipe))
            self._thread.start()

    def _read_thread(self, port : serial.Serial , read_queue : TimedQueue, stop_event_pipe):
        while True:
            # It looks like using the raw implementation of port.in_waiting and port.read is better, there's no more warnings
            # Equivalent of port.in_waiting :
            in_waiting = struct.unpack('I', fcntl.ioctl(port.fd, TIOCINQ, TIOCM_zero_str))[0]
            if in_waiting == 0:
                ready, _, _ = select.select([port.fd, stop_event_pipe], [], [], None)
                if stop_event_pipe in ready:
                    # Stop
                    break
            # Else, read as many bytes as possible
            fragment = os.read(port.fd, 1000) # simplified version of port.read()
            if fragment:
                read_queue.put(fragment)

    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None, return_metrics : bool = False):
        self.flushRead()
        self.write(data)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)