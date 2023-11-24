# timeout.py
# Sébastien Deriaz
# 20.11.2023

from enum import Enum
from typing import Union, Tuple
from time import time

class Timeout():
    DEFAULT_CONTINUATION_TIMEOUT = 5e-3

    class DataStrategy(Enum):
        DISCARD = 0 # If a timeout is reached, everything is trashed
        RETURN = 1 # If a timeout is reached, data is returned (timeout acts as a stop condition)
        STORE = 2 # If a timeout is reached, data is stored and returned on the next read() call
    class _State(Enum):
        WAIT_FOR_RESPONSE = 0
        CONTINUATION = 1

    def __init__(self, response, continuation=DEFAULT_CONTINUATION_TIMEOUT, total=None, data_strategy=DataStrategy.DISCARD) -> None:
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

        Parameters
        ----------
        response : float
        continuation : float
        total : float
        data_strategy : Mode
            Strategy of data processing upon timeout event.
            - DataStrategy.DISCARD : All of the data received after a timeout event is discarded
            - DataStrategy.RETAIN : All of the data received after a timeout event is retained and
                will be read on the next read() call
        """
        super().__init__()
        self._state = self._State.WAIT_FOR_RESPONSE
        self._response = response
        self._continuation = continuation
        self._total = total
        self._data_strategy = data_strategy

    def initiate_read(self) -> Union[float, None]:
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
        print(f"Initiate read")
        self._start_time = time()
        self._state = self._State.WAIT_FOR_RESPONSE
        self._last_eval_time = None
        return self._response

    def evaluate(self, timestamp : float) -> Tuple[bool, Union[float, None]]:
        self._eval_time = time()
        stop = False

        # Check total
        if self._total is not None:
            if self._eval_time - self._start_time >= self._total:
                stop = True
        # Check continuation
        if self._continuation is not None and self._state == self._State.CONTINUATION and self._last_eval_time is not None:
            if self._eval_time - self._last_eval_time >= self._continuation:
                stop = True
        
        # Check response time
        if self._response is not None and self._state == self._State.WAIT_FOR_RESPONSE:
            response_time = self._eval_time - self._start_time
            if response_time >= self._response:
                stop = True

        # Update the state
        if self._state == self._State.WAIT_FOR_RESPONSE:
            self._state = self._State.CONTINUATION

        timeout = None

        if not stop:
            self._last_eval_time = self._eval_time
            self._eval_time = None
            # No timeouts were reached, return the next one
            # Return the timeout (state is always CONTINUATION at this stage)
            # Take the smallest between continuation and total
            if self._total is not None and self._continuation is not None:
                timeout = min((self._start_time + self._total) - time(), self._continuation)
            elif self._total is not None:
                timeout = time() - (self._start_time + self._total)
            elif self._continuation is not None:
                timeout = self._continuation
                

        return stop, self._data_strategy == self.DataStrategy.DISCARD, timeout