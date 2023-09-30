# adapters.py
# Sébastien Deriaz
# 06.05.2023
#
# Adapters provide a common abstraction for the media layers (physical + data link + network)
# The following classes are provided, which all are derived from the main Adapter class 
#   - IP
#   - Serial
#   - VISA
# 
# Note that technically VISA is not part of the media layer, only USB is.
# This is a limitation as it is to this day not possible to communication "raw"
# with a device through USB yet
#
#
#
#
# Timeout system
# We can differentiate two kinds of timeout :
#   - transmission timeout (aka "timeout"): the time it takes for a device to start transmitting what we expect
#   - continuation timeout : the time it takes for a device to continue sending the requested data

from abc import abstractmethod, ABC
from .timed_queue import TimedQueue
from threading import Thread
from typing import Union
from enum import Enum
from .stop_conditions import StopCondition

class IAdapter(ABC):
    class Status(Enum):
        DISCONNECTED = 0
        CONNECTED = 1
    def __init__(self, stop_condition : StopCondition):
        self._read_queue = TimedQueue()
        self._thread : Union[Thread, None] = None
        self._status = self.Status.DISCONNECTED
        self._stop_condition = stop_condition

    def flushRead(self):
        """
        Flush the input buffer
        """
        self._read_queue.clear()

    @abstractmethod
    def open(self):
        """
        Start communication with the device
        """
        pass

    @abstractmethod
    def close(self):
        """
        Stop communication with the device
        """
        pass
            
    @abstractmethod
    def write(self, data : bytes):
        """
        Send data to the device
        """
        pass

    @abstractmethod
    def _start_thread(self):
        """
        Initiate the read thread
        """
        pass

    @abstractmethod
    def _set_timeout(self, timeout):
        """
        Sets the communication timeout

        Parameters
        ----------
        timeout : float
            Timeout in seconds
        """
        pass
    
    def read(self) -> bytes:
        """
        Read data from the device
        """
        if self._status == self.Status.DISCONNECTED:
            self.open()

        self._start_thread()

        timeout = self._stop_condition.initiate_read()
        self._set_timeout(timeout)

        buffer = b''
        while True:
            (_, byte) = self._read_queue.get(timeout)
            if byte is None:
                break
            buffer += byte
            stop, timeout = self._stop_condition.evaluate(byte)
            if stop:
                break
        return buffer

    @abstractmethod
    def query(self, data : bytes, timeout=None, continuation_timeout=None) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        pass