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
from .stop_conditions import StopCondition, Termination, Length
from .timeout import Timeout, TimeoutException, timeout_fuse
from typing import Union
from ..tools.types import is_number
from ..tools.log import LoggerAlias
import socket
import logging
from time import time
from dataclasses import dataclass

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
    'previous-buffer' : 'PB'
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

    def __init__(self, alias : str = '', stop_condition : Union[StopCondition, None] = ..., timeout : Union[float, Timeout] = ...) -> None:
        """
        Adapter instance

        Parameters
        ----------
        alias : str
            The alias is used to identify the class in the logs
        timeout : float or Timeout instance
            Default timeout is Timeout(response=5, continuation=0.2, total=None)
        stop_condition : StopCondition or None
            Default to None
        """
        super().__init__()

        self._alias = alias

        self.is_default_timeout = timeout is Ellipsis
        if self.is_default_timeout:
            self._timeout = self._default_timeout()
        else:
            self._timeout = timeout_fuse(timeout, self._default_timeout())

        self._default_stop_condition = stop_condition is Ellipsis
        if self._default_stop_condition:
            self._stop_condition = DEFAULT_STOP_CONDITION
        else:
            self._stop_condition = stop_condition

        self._read_queue = TimedQueue()
        self._thread : Union[Thread, None] = None
        self._status = self.Status.DISCONNECTED
        self._logger = logging.getLogger(LoggerAlias.ADAPTER.value)
        self._thread_stop_read, self._thread_stop_write = socket.socketpair()

        # Buffer for data that has been pulled from the queue but
        # not used because of termination or length stop condition
        self._previous_buffer = b''

        if not isinstance(self._timeout, Timeout):
            raise ValueError('Timeout must be defined to initialize an Adapter base class')

    @abstractmethod
    def _default_timeout(self):
        pass

    def set_timeout(self, timeout : Timeout):
        """
        Overwrite timeout

        Parameters
        ----------
        timeout : Timeout
        """
        self._timeout = timeout

    def set_default_timeout(self, default_timeout : Union[Timeout, tuple, float]):
        """
        Set the default timeout for this adapter. If a previous timeout has been set, it will be fused

        Parameters
        ----------
        default_timeout : Timeout or tuple or float
        """
        if self.is_default_timeout:
            self._logger.debug(f'Setting default timeout to {default_timeout}')
            self._timeout = default_timeout
        else:
            log = f'Fusing timeouts {self._timeout}+{default_timeout} -> '
            self._timeout = timeout_fuse(self._timeout, default_timeout)
            self._logger.debug(f'{log}{self._timeout}')

    def set_stop_condition(self, stop_condition):
        """
        Overwrite the stop-condition

        Parameters
        ----------
        stop_condition : StopCondition
        """
        self._stop_condition = stop_condition

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
        self._previous_buffer = b''

    def previous_read_buffer_empty(self):
        """
        Check whether the previous read buffer is empty

        Returns
        -------
        empty : bool
        """
        return self._previous_buffer == b''

    @abstractmethod
    def open(self):
        """
        Start communication with the device
        """
        pass

    def close(self):
        """
        Stop communication with the device
        """
        self._logger.debug('Closing adapter and stopping read thread')
        self._thread_stop_write.send(b'1')

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
    def read(self, timeout : Timeout = ..., stop_condition : StopCondition = ..., return_metrics : bool = False) -> bytes:
        pass
    

    @abstractmethod
    def _start_thread(self):
        self._logger.debug("Starting read thread...")

    def __del__(self):
        self.close()

    def query(self, data : Union[bytes, str], timeout : Timeout = ..., stop_condition : StopCondition = ..., return_metrics : bool = False) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        self.flushRead()
        self.write(data)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)
    

class StreamAdapter(Adapter):
    def read(self, timeout=..., stop_condition=..., return_metrics : bool = False) -> bytes:
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

        # 29.08.24 Change timeout behavior
        if timeout is ...:
            # Use the class timeout
            timeout = self._timeout
        else:
            # Fuse it
            timeout = timeout_fuse(timeout, self._timeout)
        
        if stop_condition is ...:
            stop_condition = self._stop_condition

        # If the adapter is closed, open it
        if self._status == self.Status.DISCONNECTED:
            self.open()

        timeout_ms = timeout.initiate_read(len(self._previous_buffer) > 0)

        if stop_condition is not None:
            stop_condition.initiate_read()


        deferred_buffer = b''

        # Start with the deferred buffer
        # TODO : Check if data could be lost here, like the data is put in the previous_read_buffer and is never
        # read back again because there's no stop condition
        if len(self._previous_buffer) > 0:# and stop_condition is not None:
            self._logger.debug(f'Using previous buffer ({self._previous_buffer})')
            if stop_condition is not None:
                stop, output, self._previous_buffer = stop_condition.evaluate(self._previous_buffer)
            else:
                stop = True
                output = self._previous_buffer
                self._previous_buffer = b''
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

                if isinstance(fragment, AdapterDisconnected):
                    raise fragment

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
                        self._previous_buffer = output
                        output = b''
                    elif data_strategy == Timeout.OnTimeoutStrategy.ERROR:
                        raise TimeoutException(origin, timeout._stop_source_overtime, timeout._stop_source_limit)
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
                        self._previous_buffer = deferred_buffer
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
            designator = STOP_DESIGNATORS['previous-buffer']
        
        read_duration = time() - read_start
        if self._previous_buffer:
            self._logger.debug(f'Read [{designator}, {read_duration*1e3:.3f}ms] : {output} , previous read buffer : {self._previous_buffer}')
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