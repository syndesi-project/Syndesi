# timeout.py
# Sébastien Deriaz
# 20.11.2023

from enum import Enum
from typing import Union, Tuple
from time import time


class Timeout():
    class OnTimeoutStrategy(Enum):
        DISCARD = 'discard' # If a timeout is reached, data is discarded
        RETURN = 'return' #  If a timeout is reached, data is returned (timeout acts as a stop condition)
        STORE = 'store' # If a timeout is reached, data is stored and returned on the next read() call
        ERROR = 'error' # If a timeout is reached, raise an error

    class TimeoutType(Enum):
        RESPONSE = 'response'
        CONTINUATION = 'continuation'
        TOTAL = 'total'
        
    class _State(Enum):
        WAIT_FOR_RESPONSE = 0
        CONTINUATION = 1

    def __init__(self, 
        response=...,
        continuation=...,
        total=...,
        on_response=...,
        on_continuation=...,
        on_total=...) -> None:
        """
        A class to manage timeouts

        Timeouts are split in three categories :
        - response timeout : the "standard" timeout, (i.e the time it takes for
            a device to start transmitting data)
        - continuation timeout : the time between reception of
            data units (bytes or blocks of data)
        - total timeout : maximum time from start to end of transmission.
            This timeout can stop a communication mid-way. It is used to
            prevent a host from getting stuck reading a constantly streaming device

        Each timeout is specified in seconds
        
        Actions
        - discard : Discard all of data obtained during the read() call if the specified timeout if reached
        - return : Return all of the data read up to this point when the specified timeout is reached
        - store : Store all of the data read up to this point in a buffer. Data will be available at the next read() call
        - error : Produce an error

        Parameters
        ----------
        response : float
        continuation : float
        total : float
        on_response : str
            Action on response timeout (see Actions), 'discard' by default
        on_continuation : str
            Action on continuation timeout (see Actions), 'return' by default
        on_total : str
            Action on total timeout (see Actions), 'discard' by default
        """
        super().__init__()
        # It is possible to pass a tuple to set response/continuation/total, parse this first if it is the case
        if isinstance(response, (tuple, list)):
            if len(response) >= 3:
                total = response[2]
            if len(response) >= 2:
                continuation = response[1]
            response = response[0]

        # Timeout values (response, continuation and total)
        self._response_set = response is not ...
        self._on_response_set = on_response is not ...
        self._continuation_set = continuation is not ...
        self._on_continuation_set = on_continuation is not ...
        self._total_set = total is not ...
        self._on_total_set = on_total is not ...

        self._response = response
        self._continuation = continuation
        self._total = total
        self._on_response = self.OnTimeoutStrategy(on_response) if self._on_response_set else on_response
        self._on_continuation = self.OnTimeoutStrategy(on_continuation) if self._on_continuation_set else on_continuation
        self._on_total = self.OnTimeoutStrategy(on_total) if self._on_total_set else on_total


        # State machine flags
        self._state = self._State.WAIT_FOR_RESPONSE
        self._queue_timeout_type = self.TimeoutType.RESPONSE
        self._last_data_strategy_origin = self.TimeoutType.RESPONSE

    def initiate_read(self, deferred_buffer : bool = False) -> Union[float, None]:
        """
        Initiate a read sequence.

        The maximum time that should be spent in the next byte read
        is returned

        Returns
        -------
        stop : bool
            Timeout is reached
        keep : bool
            True if data read up to this point should be kept
            False if data should be discarded
        timeout : float or None
            None is there's no timeout
        """
        self._start_time = time()
        if deferred_buffer:
            self._state = self._State.CONTINUATION
            self._data_strategy = self._on_continuation
            self._queue_timeout_type = self.TimeoutType.CONTINUATION
        else:
            self._state = self._State.WAIT_FOR_RESPONSE
            self._data_strategy = self._on_response
            self._queue_timeout_type = self.TimeoutType.RESPONSE
        self._last_timestamp = None

        self.response_time = None
        self.continuation_times = []
        self.total_time = None

        self._output_timeout = None
        
        return self._response

    def evaluate(self, timestamp : float) -> Tuple[bool, Union[float, None]]:
        stop = False

        for setting in [
                'response',
                'continuation',
                'total',
                'on_response',
                'on_continuation',
                'on_total']:
            if getattr(self, '_' + setting) is Ellipsis:
                raise RuntimeError(f'{setting} was not initialized')

        self._data_strategy = None
        self._stop_source_overtime = '###' # When a timeout occurs, store the value that exceeded its value here
        self._stop_source_limit = '###' # And store the limit value here

        # First check if the timestamp is None, that would mean the timeout was reached in the queue
        if timestamp is None:
            # Set the data strategy according to the timeout that was given for the queue before
            match self._queue_timeout_type:
                case self.TimeoutType.RESPONSE:
                    self._data_strategy = self._on_response
                    self._stop_source_limit = self._response
                case self.TimeoutType.CONTINUATION:
                    self._data_strategy = self._on_continuation
                    self._stop_source_limit = self._continuation
                case self.TimeoutType.TOTAL:
                    self._data_strategy = self._on_total
                    self._stop_source_limit = self._total
            self._stop_source_overtime = None # We do not have the exceed time, but None will be printed as '---'
            self._last_data_strategy_origin = self._queue_timeout_type
            stop = True
            
        else:
            # Check total
            if self._total is not None:
                self.total_time = timestamp - self._start_time
                if self.total_time >= self._total:
                    stop = True
                    self._data_strategy = self._on_total
                    self._last_data_strategy_origin = self.TimeoutType.TOTAL
                    self._stop_source_overtime = self.total_time
                    self._stop_source_limit = self._total
            # Check continuation
            elif self._continuation is not None and self._state == self._State.CONTINUATION and self._last_timestamp is not None:
                continuation_time = timestamp - self._last_timestamp
                self.continuation_times.append(continuation_time)
                if continuation_time >= self._continuation:
                    stop = True
                    self._data_strategy = self._on_continuation
                    self._last_data_strategy_origin = self.TimeoutType.CONTINUATION
                    self._stop_source_overtime = continuation_time
                    self._stop_source_limit = self._continuation
            # Check response time
            elif self._response is not None and self._state == self._State.WAIT_FOR_RESPONSE:
                self.response_time = timestamp - self._start_time
                if self.response_time >= self._response:
                    stop = True
                    self._data_strategy = self._on_response
                    self._last_data_strategy_origin = self.TimeoutType.RESPONSE
                    self._stop_source_overtime = self.response_time
                    self._stop_source_limit = self._response

        self._output_timeout = None
        # If we continue
        if not stop:
            # Update the state
            if self._state == self._State.WAIT_FOR_RESPONSE:
                self._state = self._State.CONTINUATION
            self._last_timestamp = timestamp
            # No timeouts were reached, return the next one
            # Return the timeout (state is always CONTINUATION at this stage)
            # Take the smallest between continuation and total
            if self._total is not None and self._continuation is not None:
                c = self._continuation
                t = self._start_time + self._total
                if c < t:
                    self._output_timeout = c
                    self._queue_timeout_type = self.TimeoutType.CONTINUATION
                else:
                    self._output_timeout = t
                    self._queue_timeout_type = self.TimeoutType.TOTAL
            elif self._total is not None:
                self._output_timeout = time() - (self._start_time + self._total)
                self._queue_timeout_type = self.TimeoutType.TOTAL
            elif self._continuation is not None:
                self._output_timeout = self._continuation
                self._queue_timeout_type = self.TimeoutType.CONTINUATION
                

        return stop, self._output_timeout

    def dataStrategy(self):
        """
        Return the data strategy (discard, return, store or error)
        and the timeout origin (response, continuation or total)

        Returns
        -------
        data_strategy : Timeout.DataStrategy
        origin : Timeout.TimeoutType
        
        """
        return self._data_strategy, self._last_data_strategy_origin

    def __str__(self) -> str:
        def _format(value, action):
            if value is None:
                return 'None'
            elif value is Ellipsis:
                return 'not set'
            else:
                return f'{value*1e3:.3f}ms/{action.value if isinstance(action, Enum) else "not set"}'


        response =  'r:' + _format(self._response, self._on_response)
        continuation = 'c:' + _format(self._continuation, self._on_continuation)
        total = 't:' + _format(self._total, self._on_total)
        return f'Timeout({response},{continuation},{total})'

    def __repr__(self) -> str:
        return self.__str__()


class TimeoutException(Exception):
    def __init__(self, type : Timeout.TimeoutType, value : float, limit : float) -> None:
        super().__init__()
        self._type = type
        self._value = value
        self._limit = limit
    
    def __str__(self) -> str:
        try:
            value_string = f'{self._value*1e3:.3f}ms'
        except (ValueError, TypeError):
            value_string = 'not received'

        try:
            limit_string = f'{self._limit*1e3:.3f}ms'
        except (ValueError, TypeError):
            limit_string = 'not received'


        return f'{self._type.value} : {value_string} / {limit_string}'

    def __repr__(self) -> str:
        return self.__str__()



def timeout_fuse(high_priority, low_priority, force : bool = False):
    """
    Fuse two timeout descriptions (Timeout class or float or tuple)
    
    Parameters
    ----------
    high_priority : any
        High priority timeout description
    low_priority : any
        Low priority timeout description
    force : bool
        False : Only fuse uninitialized parameters
        True : Keep high priority if both parameters were initialized
    """
    new_timeout = Timeout()
    
    # 1) Check if any is none, in that case return the other one
    if high_priority is None:
        return low_priority
    if low_priority is None:
        return high_priority

    # 2) Convert each to Timeout class
    high : Timeout
    low : Timeout
    high = high_priority if isinstance(high_priority, Timeout) else Timeout(high_priority)
    low = low_priority if isinstance(low_priority, Timeout) else Timeout(low_priority)

    # 3) If one is the default, take the other
    # 4) Select with parameter to keep based on where it has been set
    for attr in [
        '_response',
        '_on_response',
        '_continuation',
        '_on_continuation',
        '_total',
        '_on_total']:
        H = getattr(high, attr)
        L = getattr(low, attr)

        if H is not Ellipsis and L is not Ellipsis and force:
            raise RuntimeError(f'Parameter {attr.removeprefix("_")} was set twice, set force=True if it should be merged anyway')

        # Use low priority if the default value is used in high priority
        new_timeout.__setattr__(attr, H if H is not Ellipsis else L)
        
    return new_timeout

