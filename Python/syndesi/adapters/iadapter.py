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
# An adapter is meant to work with bytes objects but it can accept strings.
# Strings will automatically be converted to bytes using utf-8 encoding

from abc import abstractmethod, ABC
from .timed_queue import TimedQueue
from threading import Thread
from typing import Union
from enum import Enum
from .stop_conditions import StopCondition
from .timeout import Timeout, TimeoutException
from time import time
from typing import Union
from ..tools.types import is_number
import logging

DEFAULT_TIMEOUT = Timeout(response=1, continuation=100e-3, total=None)
DEFAUT_STOP_CONDITION = None

class IAdapter(ABC):
    TIMEOUT_ARGUMENT = 'timeout'

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

    @abstractmethod
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
        if timeout is None:
            read_timeout = self._timeout
        else:
            read_timeout = timeout
        
        if stop_condition is not None:
            


        if self._status == self.Status.DISCONNECTED:
            self.open()

        self._start_thread()

        timeout = self._timeout.initiate_read(len(self._previous_read_buffer) > 0)
        if self._stop_condition is not None:
            self._stop_condition.initiate_read()

        deferred_buffer = b''

        # Start with the deferred buffer
        if len(self._previous_read_buffer) > 0:
            stop, output, self._previous_read_buffer = self._stop_condition.evaluate(self._previous_read_buffer)
        else:
            stop = False
            output = b''
        # If everything is used up, read the queue
        if not stop:
            while True:
                (timestamp, fragment) = self._read_queue.get(timeout)

                # 1) Evaluate the timeout
                stop, timeout = self._timeout.evaluate(timestamp)
                if stop:
                    data_strategy, origin = self._timeout.dataStrategy()
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
                if self._stop_condition is not None:
                    stop, kept_fragment, deferred_buffer = self._stop_condition.evaluate(fragment)
                    output += kept_fragment
                    if stop:
                        self._previous_read_buffer = deferred_buffer
                else:
                    output += fragment
                if stop:
                    break
        return output

    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        pass