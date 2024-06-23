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
#

from abc import abstractmethod, ABC
from .timed_queue import TimedQueue
from threading import Thread
from typing import Union
from enum import Enum
from .stop_conditions import StopCondition, Termination, Length
from .timeout import Timeout, TimeoutException, timeout_fuse
from typing import Union
from ..tools.types import is_number
from ..tools.log import LoggerAlias
import logging
from time import time
from dataclasses import dataclass
from ..tools.others import DEFAULT

DEFAULT_TIMEOUT = Timeout(response=1, continuation=100e-3, total=None)
DEFAULT_STOP_CONDITION = None


class AdapterDisconnected(Exception):
    pass

STOP_DESIGNATORS = {
    'timeout' : {
        Timeout.TimeoutType.RESPONSE : 'TR',
        Timeout.TimeoutType.CONTINUATION : 'TC',
        Timeout.TimeoutType.TOTAL : 'TT'
    },
    'stop_condition' : {
        Termination : 'ST',
        Length : 'SL'
    },
    'previous-read-buffer' : 'RB'
}

class Origin(Enum):
    TIMEOUT = 'timeout'
    STOP_CONDITION = 'stop_condition'

@dataclass
class ReturnMetrics:
    read_duration : float
    origin : Origin
    timeout_type : Timeout.TimeoutType
    stop_condition : StopCondition
    previous_read_buffer_used : bool
    n_fragments : int
    response_time : float
    continuation_times : list
    total_time : float

class Adapter(ABC):
    class Status(Enum):
        DISCONNECTED = 0
        CONNECTED = 1

    def __init__(self, alias : str = '', stop_condition : Union[StopCondition, None] = DEFAULT, timeout : Union[float, Timeout] = DEFAULT) -> None:
        """
        Adapter instance

        Parameters
        ----------
        alias : str
            The alias is used to identify the class in the logs
        timeout : float or Timeout instance
            Default timeout is Timeout(response=1, continuation=0.1, total=None)
        stop_condition : StopCondition or None
            Default to None
        """
        super().__init__()
        self._alias = alias

        self._default_stop_condition = stop_condition == DEFAULT
        if self._default_stop_condition:
            self._stop_condition = DEFAULT_STOP_CONDITION
        else:
            self._stop_condition = stop_condition
        self._read_queue = TimedQueue()
        self._thread : Union[Thread, None] = None
        self._status = self.Status.DISCONNECTED
        self._logger = logging.getLogger(LoggerAlias.ADAPTER.value)

        # Buffer for data that has been pulled from the queue but
        # not used because of termination or length stop condition
        self._previous_read_buffer = b''

        self._default_timeout = timeout == DEFAULT
        if self._default_timeout:
            self._timeout = DEFAULT_TIMEOUT
        else:
            if is_number(timeout):
                self._timeout = Timeout(response=timeout, continuation=100e-3)
            elif isinstance(timeout, Timeout):
                self._timeout = timeout
            else:
                raise ValueError(f"Invalid timeout type : {type(timeout)}")

    def set_default_timeout(self, default_timeout : Union[Timeout, tuple, float]):
        """
        Set the default timeout for this adapter. If a previous timeout has been set, it will be fused

        Parameters
        ----------
        default_timeout : Timeout or tuple or float
        """
        if self._default_timeout:
            self._timeout = default_timeout
        else:
            self._timeout = timeout_fuse(self._timeout, default_timeout)

    def set_default_stop_condition(self, stop_condition):
        """
        Set the default stop condition for this adapter.

        Parameters
        ----------
        stop_condition : StopCondition
        """
        if self._default_stop_condition:
            self._stop_condition = stop_condition

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
    
    # TODO : Return None or b'' when read thread is killed while reading
    # This is to detect if a server socket has been closed


    def read(self, timeout=None, stop_condition=None, return_metrics : bool = False) -> bytes:
        """
        Read data from the device

        Parameters
        ----------
        timeout : Timeout or None
            Set a custom timeout, if None (default), the adapter timeout is used
        stop_condition : StopCondition or None
            Set a custom stop condition, if None (Default), the adapater stop condition is used
        return_metrics : ReturnMetrics class
        """
        read_start = time()
        if self._status == self.Status.DISCONNECTED:
            self.open()

        # Use adapter values if no custom value is specified
        if timeout is None:
            timeout = self._timeout
        elif isinstance(timeout, float):
            timeout = Timeout(timeout)
        
        
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
        # TODO : Check if data could be lost here, like the data is put in the previous_read_buffer and is never
        # read back again because there's no stop condition
        if len(self._previous_read_buffer) > 0 and stop_condition is not None:
            stop, output, self._previous_read_buffer = stop_condition.evaluate(self._previous_read_buffer)
            previous_read_buffer_used = True
        else:
            stop = False
            output = b''
            previous_read_buffer_used = False
        
        n_fragments = 0
        # If everything is used up, read the queue
        if not stop:
            while True:
                (timestamp, fragment) = self._read_queue.get(timeout_ms)
                n_fragments += 1

                if fragment == b'':
                    raise AdapterDisconnected()

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
                else:
                    origin = None
                    
                
                
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
            
            if origin is not None:
                # The stop originates from the timeout
                designator = STOP_DESIGNATORS['timeout'][origin]
            else:
                designator = STOP_DESIGNATORS['stop_condition'][type(stop_condition)]
        else:
            designator = STOP_DESIGNATORS['previous-read-buffer']
        
        read_duration = time() - read_start
        if self._previous_read_buffer:
            self._logger.debug(f'Read [{designator}, {read_duration*1e3:.3f}ms] : {output} , previous read buffer : {self._previous_read_buffer}')
        else:
            self._logger.debug(f'Read [{designator}, {read_duration*1e3:.3f}ms] : {output}')

        if return_metrics:
            return output, ReturnMetrics(
                read_duration=read_duration,
                origin=Origin.TIMEOUT if origin is not None else Origin.STOP_CONDITION,
                timeout_type=origin if origin is not None else None,
                stop_condition=type(stop_condition) if origin is None else None,
                previous_read_buffer_used=previous_read_buffer_used,
                n_fragments=n_fragments,
                response_time=timeout.response_time,
                continuation_times=timeout.continuation_times,
                total_time=timeout.total_time
            )
        else:
            return output

    @abstractmethod
    def _start_thread(self):
        pass

    def __del__(self):
        self.close()

    @abstractmethod
    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None, return_metrics : bool = False) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        pass
    