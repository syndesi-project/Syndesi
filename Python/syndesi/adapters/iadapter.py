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
from .timeout import Timeout
from time import time
from typing import Union
from ..tools.types import is_number

DEFAULT_TIMEOUT = Timeout(response=1, continuation=100e-3, total=None)
DEFAUT_STOP_CONDITION = None

class IAdapter(ABC):
    class Status(Enum):
        DISCONNECTED = 0
        CONNECTED = 1
    def __init__(self,
        timeout : Union[float, Timeout] = DEFAULT_TIMEOUT,
        stop_condition : Union[StopCondition, None] = DEFAUT_STOP_CONDITION):

        if is_number(timeout):
            self._timeout = Timeout(response=timeout, continuation=100e-3)
        elif isinstance(timeout, Timeout):
            self._timeout = timeout
        else:
            raise ValueError(f"Invalid timeout type : {type(timeout)}")

        self._stop_condition = stop_condition
        self._read_queue = TimedQueue()
        self._thread : Union[Thread, None] = None
        self._status = self.Status.DISCONNECTED
        # Buffer for data that has been pulled from the queue but
        # not used because of termination or length stop condition
        self._previous_read_buffer = b''

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
    
    def read(self, **kwargs) -> bytes:
        """
        Read data from the device

        A custom stop-condition can be set by passing it to stop_condition
        or using the simplified API with timeout/response=
        """
        if self._status == self.Status.DISCONNECTED:
            self.open()

        self._start_thread()

        timeout = self._timeout.initiate_read()
        if self._stop_condition is not None:
            self._stop_condition.initiate_read()

        deferred_buffer = b''

        # Start with the deferred buffer
        if len(self._previous_read_buffer) > 0:
            print(f"Start with deferred buffer : {self._previous_read_buffer}")
            stop, output, self._previous_read_buffer = self._stop_condition.evaluate(self._previous_read_buffer)
            print(f"Output : {output}, deferred buffer : {self._previous_read_buffer}")
        else:
            stop = False
            output = b''
        # If everything is used up, read the queue
        if not stop:
            while True:
                print(f"Read the queue ({timeout:.3f})...")
                (timestamp, fragment) = self._read_queue.get(timeout)
                # 1) Evaluate the timeout
                if timestamp is None:
                    # Stop directly
                    print(f"Timeout reached while reading the queue")
                    print(f"Output buffer : {output}")
                    break
                
                # Add the deferred buffer
                if len(deferred_buffer) > 0:
                    fragment = deferred_buffer + fragment

                if self._timeout is not None:
                    stop, keep, timeout = self._timeout.evaluate(timestamp)
                    if stop:
                        print("Timeout reached")
                        if self._timeout._data_strategy == Timeout.DataStrategy.DISCARD:
                            # Trash everything
                            output = b''
                        elif self._timeout._data_strategy == Timeout.DataStrategy.RETURN:
                            # Return the data that has been read up to this point
                            output += fragment
                        elif self._timeout._data_strategy == Timeout.DataStrategy.STORE:
                            # Store the data
                            self._previous_read_buffer = output
                            output = b''
                        break

                # 2) Evaluate the stop condition
                if self._stop_condition is not None:
                    print(f"Evaluate fragment : {fragment}")
                    stop, kept_fragment, deferred_buffer = self._stop_condition.evaluate(fragment)
                    print(f"stop : {stop}, Kept fragment : {kept_fragment}, deferred buffer : {deferred_buffer}")
                    output += kept_fragment
                    if stop:
                        self._previous_read_buffer = deferred_buffer
                        print(f"Stop condition reached")
                else:
                    output += fragment
                if stop:
                    break
        print(f"Return {output}")
        return output

    def query(self, data : bytes, timeout=None, continuation_timeout=None) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        pass