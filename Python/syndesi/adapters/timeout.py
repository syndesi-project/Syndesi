# timeout.py
# Sébastien Deriaz
# 20.11.2023

from enum import Enum
from typing import Union, Tuple
from time import time
from ..tools.others import is_default_argument


class Timeout():
    class OnTimeoutStrategy(Enum):
        DISCARD = 'discard' # If a timeout is reached, data is discarded
        RETURN = 'return' #  If a timeout is reached, data is returned (timeout acts as a stop condition)
        STORE = 'store' # If a timeout is reached, data is stored and returned on the next read() call
        ERROR = 'error' # If a timeout is reached, raise an error

    class TimeoutType(Enum):
        RESPONSE = 0
        CONTINUATION = 1
        TOTAL = 2
        
    class _State(Enum):
        WAIT_FOR_RESPONSE = 0
        CONTINUATION = 1

    DEFAULT_CONTINUATION = 5e-3
    DEFAULT_TOTAL = None
    DEFAULT_ON_RESPONSE = OnTimeoutStrategy.DISCARD
    DEFAULT_ON_CONTINUATION = OnTimeoutStrategy.RETURN
    DEFAULT_ON_TOTAL = OnTimeoutStrategy.RETURN

    def __init__(self, 
        response,
        continuation=None,
        total=None,
        on_response=None,
        on_continuation=None,
        on_total=None) -> None:
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
        if isinstance(response, tuple):
            if len(response) >= 3:
                total = response[2]
            if len(response) >= 2:
                continuation = response[1]
            response = response[0]

        self._defaults = {
            '_response' : False,
            '_continuation' : continuation is None,
            '_total' : total is None,
            '_on_response' : on_response is None,
            '_on_continuation' : on_continuation is None,
            '_on_total' : on_total is None
        }

        # Set default values
        if continuation is None:
            continuation = self.DEFAULT_CONTINUATION
        if total is None:
            total = self.DEFAULT_TOTAL
        if on_response is None:
            on_response = self.DEFAULT_ON_RESPONSE
        if on_continuation is None:
            on_continuation = self.DEFAULT_ON_CONTINUATION
        if on_total is None:
            on_total = self.DEFAULT_ON_TOTAL

        # Timeout values (response, continuation and total)
        self._response = response
        self._continuation = continuation
        self._total = total
        self._on_response = self.OnTimeoutStrategy(on_response)
        self._on_continuation = self.OnTimeoutStrategy(on_continuation)
        self._on_total = self.OnTimeoutStrategy(on_total)

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
        self._data_strategy = None

        # First check if the timestamp is None, that would mean the timeout was reached in the queue
        if timestamp is None:
            # Set the data strategy according to the timeout that was given for the queue before
            match self._queue_timeout_type:
                case self.TimeoutType.RESPONSE:
                    self._data_strategy = self._on_response
                    self.response_time = self._output_timeout # This is a test
                case self.TimeoutType.CONTINUATION:
                    self._data_strategy = self._on_continuation
                    self.continuation_times.append(self._output_timeout) # This is a test
                case self.TimeoutType.TOTAL:
                    self.total_time = self._output_timeout # This is a test
                    self._data_strategy = self._on_total
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
            # Check continuation
            # elif
            if self._continuation is not None and self._state == self._State.CONTINUATION and self._last_timestamp is not None:
                continuation_time = timestamp - self._last_timestamp
                self.continuation_times.append(continuation_time)
                if continuation_time >= self._continuation:
                    stop = True
                    self._data_strategy = self._on_continuation
                    self._last_data_strategy_origin = self.TimeoutType.CONTINUATION
            # Check response time
            # elif
            if self._response is not None and self._state == self._State.WAIT_FOR_RESPONSE:
                self.response_time = timestamp - self._start_time
                if self.response_time >= self._response:
                    stop = True
                    self._data_strategy = self._on_response
                    self._last_data_strategy_origin = self.TimeoutType.RESPONSE

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


class TimeoutException(Exception):
    def __init__(self, type : Timeout.TimeoutType) -> None:
        super().__init__()
        self._type = type


def timeout_fuse(high_priority, low_priority):
    """
    Fuse two timeout descriptions (Timeout class or float or tuple)
    
    Parameters
    ----------
    high_priority : any
        High priority timeout description
    low_priority : any
        Low priority timeout description
    """
    # 1) Check if any is none, in that case return the other one
    if high_priority is None:
        return low_priority
    if low_priority is None:
        return high_priority

    # 2) Convert each to Timeout class
    high = high_priority if isinstance(high_priority, Timeout) else Timeout(high_priority)
    low = low_priority if isinstance(low_priority, Timeout) else Timeout(low_priority)

    # 3) If one is the default, take the other
    if is_default_argument(high):
        return low
    if is_default_argument(low):
        return high
    
    new_attr = {}
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
        # Use low priority if the default value is used in high priority
        new_attr[attr.removeprefix('_')] = L if high._defaults[attr] else H
        
    return Timeout(**new_attr)

