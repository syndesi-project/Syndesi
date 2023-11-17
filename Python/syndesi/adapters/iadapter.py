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
from .stop_conditions import StopCondition, Timeout
from time import time

DEFAULT_STOP_CONDITION = Timeout(response=1, continuation=100e-3, total=None)

class IAdapter(ABC):
    class Status(Enum):
        DISCONNECTED = 0
        CONNECTED = 1
    def __init__(self, stop_condition : StopCondition = DEFAULT_STOP_CONDITION):
        self._read_queue = TimedQueue()
        self._thread : Union[Thread, None] = None
        self._status = self.Status.DISCONNECTED
        self._stop_condition = stop_condition
        # Buffer for data that has been pulled from the queue but
        # not used because of termination or length stop condition
        self._deferred_buffer = b''

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

    # @abstractmethod
    # def _set_timeout(self, timeout):
    #     """
    #     Sets the communication timeout

    #     Parameters
    #     ----------
    #     timeout : float
    #         Timeout in seconds
    #     """
    #     pass
    
    def read(self, **kwargs) -> bytes:
        """
        Read data from the device

        A custom stop-condition can be set by passing it to stop_condition
        or using the simplified API with timeout/response=
        """
        if self._status == self.Status.DISCONNECTED:
            self.open()

        self._start_thread()

        last_read = time()
        timeout = self._stop_condition.initiate_read()

        # Could it be possible to use the deferred buffer to store the partial termination ??
        # If so it would be very clean
        # Study this !
        #

        # Start with the deferred buffer
        if len(self._deferred_buffer) > 0:
            stop, _, output, self._deferred_buffer = self._stop_condition.evaluate(self._deferred_buffer)
        else:
            stop = False
            output = b''
        # If everything is used up, read the queue
        if not stop:
            while True:
                (timestamp, fragment) = self._read_queue.get(timeout)
                if len(self._deferred_buffer) > 0:
                    fragment = self._deferred_buffer + fragment
                if fragment is None:
                    break # Timeout is reached while trying to read the queue
                time_delta = timestamp - last_read
                last_read = timestamp
                if timeout is not None and time_delta > timeout:
                    break
                stop, timeout, kept_fragment, self._deferred_buffer = self._stop_condition.evaluate(fragment)
                output += kept_fragment
                if stop:
                    break
        return output

    def query(self, data : bytes, timeout=None, continuation_timeout=None) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        pass