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
# This is a limitation as it is to this day not possible to communicate "raw"
# with a device through USB yet
#
# An adapter is meant to work with bytes objects but it can accept strings.
# Strings will automatically be converted to bytes using utf-8 encoding

from abc import abstractmethod, ABC
from .timed_queue import TimedQueue
from threading import Thread
from typing import Union
from enum import Enum
from .stop_conditions import StopCondition
from .timeout import Timeout, TimeoutException
from typing import Union
from ..tools.types import is_number
from ..tools.logger import AdapterLogger

DEFAULT_TIMEOUT = Timeout(response=1, continuation=100e-3, total=None)
DEFAUT_STOP_CONDITION = None

class IAdapter(ABC):

    class Status(Enum):
        DISCONNECTED = 0
        CONNECTED = 1

    def __init__(self,
        timeout : Union[float, Timeout] = DEFAULT_TIMEOUT,
        stop_condition : Union[StopCondition, None] = DEFAUT_STOP_CONDITION,
        log_level : int = 0):
        """
        IAdapter instance

        Parameters
        ----------
        timeout : float or Timeout instance
            Default timeout is Timeout(response=1, continuation=0.1, total=None)
        stop_condition : StopCondition or None
            Default to None
        log : int
            0 : basic logging
            1 : detailed logging
            2 : complete logging
        """

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

        self._logger = AdapterLogger('adapter')
        self._logger.set_log_level(log_level)
        self._logger.log_status('Initializing adapter', 0)

    def flushRead(self):
        """
        Flush the input buffer
        """
        self._read_queue.clear()
        self._previous_read_buffer = b''

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
    def write(self, data : Union[bytes, str]):
        """
        Send data to the device

        Parameters
        ----------
        data : bytes or str
        """
        pass

    @abstractmethod
    def _start_thread(self):
        """
        Initiate the read thread
        """
        pass
    
    def read(self, timeout=None, stop_condition=None) -> bytes:
        """
        Read data from the device

        Parameters
        ----------
        timeout : Timeout or None
            Set a custom timeout, if None (default), the adapter timeout is used
        stop_condition : StopCondition or None
            Set a custom stop condition, if None (Default), the adapater stop condition is used
        """
        if self._status == self.Status.DISCONNECTED:
            self.open()

        # Use adapter values if no custom value is specified
        if timeout is None:
            timeout = self._timeout
        
        if stop_condition is None:
            stop_condition = self._stop_condition

        # If the adapter is closed, open it
        if self._status == self.Status.DISCONNECTED:
            self.open()

        if self._thread is None or not self._thread.is_alive():
            self._start_thread()

        timeout_ms = timeout.initiate_read(len(self._previous_read_buffer) > 0)

        if stop_condition is not None:
            stop_condition.initiate_read()

        deferred_buffer = b''

        # Start with the deferred buffer
        if len(self._previous_read_buffer) > 0 and stop_condition is not None:
            stop, output, self._previous_read_buffer = stop_condition.evaluate(self._previous_read_buffer)
        else:
            stop = False
            output = b''
        # If everything is used up, read the queue
        if not stop:
            while True:
                (timestamp, fragment) = self._read_queue.get(timeout_ms)

                # 1) Evaluate the timeout
                stop, timeout_ms = timeout.evaluate(timestamp)
                if stop:
                    data_strategy, origin = timeout.dataStrategy()
                    if data_strategy == Timeout.OnTimeoutStrategy.DISCARD:
                        # Trash everything
                        output = b''
                    elif data_strategy == Timeout.OnTimeoutStrategy.RETURN:
                        # Return the data that has been read up to this point
                        output += deferred_buffer
                        if fragment is not None:
                            output += fragment
                    elif data_strategy == Timeout.OnTimeoutStrategy.STORE:
                        # Store the data
                        self._previous_read_buffer = output
                        output = b''
                    elif data_strategy == Timeout.OnTimeoutStrategy.ERROR:
                        raise TimeoutException(origin)
                    break
                
                
                # Add the deferred buffer
                if len(deferred_buffer) > 0:
                    fragment = deferred_buffer + fragment

                # 2) Evaluate the stop condition
                if stop_condition is not None:
                    stop, kept_fragment, deferred_buffer = stop_condition.evaluate(fragment)
                    output += kept_fragment
                    if stop:
                        self._previous_read_buffer = deferred_buffer
                else:
                    output += fragment
                if stop:
                    break
            if self._logger:
                self._logger.log_read(output, self._previous_read_buffer)

        return output

    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        pass

    def __del__(self):
        self.close()