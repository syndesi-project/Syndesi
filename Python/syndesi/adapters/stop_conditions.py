from typing import Union, Tuple
from enum import Enum
from time import time

class StopCondition:
    def __init__(self) -> None:
        """
        A condition to stop reading from a device

        Cannot be used on its own
        """
        self._and = None
        self._or = None
        # Time at which the evaluation command is run

    def initiate_read(self) -> Union[float, None]:
        """
        Initiate a read sequence.

        The maximum time that should be spent in the next byte read
        is returned

        Returns
        -------
        timeout : float or None
            None is there's no timeout
        """
        return NotImplementedError()

    def evaluate(self, fragment : bytes) -> Tuple[bool, Union[float, None]]:
        """
        Evaluate the next received byte

        Returns
        -------
        stop : bool
            False if read should continue
            True if read should stop
        timeout : float or None
            timeout for the next byte read
        kept_fragment : bytes
            Part of the fragment kept for future use
        deferred_fragment : bytes
            Part of the fragment that was deferred because of a stop condition
        """
        raise NotImplementedError()

    def __or__(self, sc):
        assert isinstance(sc, StopCondition), f"Cannot do or operator between StopCondition and {type(sc)}"
        return StopConditionOperation(self, sc, operation=StopConditionOperation.OR)
    
    def __and__(self, sc):
        assert isinstance(sc, StopCondition), f"Cannot do and operator between StopCondition and {type(sc)}"
        return StopConditionOperation(self, sc, operation=StopConditionOperation.AND)

    def get_timeout(self) -> Union[float, None]:
        raise NotImplementedError()

class StopConditionOperation(Enum):
    OR = 0
    AND = 1

class StopConditionExpression(StopCondition):
    def __init__(self, A : StopCondition, B : StopCondition, operation : StopConditionOperation) -> None:
        super().__init__()
        self._A = A
        self._B = B
        self._operation = operation

    def evaluate(self, byte : bytes) -> Tuple[bool, Union[float, None]]:
        if self._eval_time is None:
            # First function to be called
            self._eval_time = time()

        self._A._eval_time = self._eval_time
        self._B._eval_time = self._eval_time
        # TODO : finish this
        a_stop, a_timeout = self._A.evaluate(byte)
        b_stop, b_timeout = self._B.evaluate(byte)

        self._eval_time = None
        keep_last = a_keep_last if a_stop else (b_keep_last if b_stop else False)
        if self._operation == StopConditionOperation.OR:
            stop = a_stop or b_stop
            timeout = min(a_timeout, b_timeout)
        elif self._operation == StopConditionOperation.AND:
            stop = a_stop and b_stop
            timeout = max(a_timeout, b_timeout)
        else:
            raise RuntimeError("Invalid operation")
        
        return stop, timeout
    
    def initiate_read(self):
        super().initiate_read()
        self._A._start_time = self._start_time
        self._A.initiate_read()
        self._B._start_time = self._start_time
        self._B.initiate_read()

    def get_timeout(self) -> Union[float, None]:
        timeout_A = self._A.get_timeout()
        timeout_B = self._B.get_timeout()
        if timeout_B is None:
            return timeout_A
        elif timeout_A is None:
            return timeout_B
        elif timeout_A < timeout_B:
            return timeout_A
        else:
            return timeout_B

class Timeout(StopCondition):
    DEFAULT_CONTINUATION_TIMEOUT = 5e-3
    class State(Enum):
        WAIT_FOR_RESPONSE = 0
        CONTINUATION = 1

    def __init__(self, response, continuation=DEFAULT_CONTINUATION_TIMEOUT, total=None) -> None:
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
        """

        self._state = self.State.WAIT_FOR_RESPONSE
        self._response = response
        self._continuation = continuation
        self._total = total
        self._start_time = None
        self._eval_time = None


    def initiate_read(self) -> Union[float, None]:
        """
        Initiate a read sequence.

        The maximum time that should be spent in the next byte read
        is returned

        Returns
        -------
        timeout : float or None
            None is there's no timeout
        """
        if self._start_time is None:
            # It hasn't been set by an other StopCondition instance
            self._start_time = time()
        self._start_time = time()
        self._state = self.State.WAIT_FOR_RESPONSE
        self._last_eval_time = None
        return self._response

    def evaluate(self, data: bytes) -> Tuple[bool, Union[float, None]]:
        if self._eval_time is None:
            self._eval_time = time()
        stop = False
        # Update the state
        if self._state == self.State.WAIT_FOR_RESPONSE:
            self._state = self.State.CONTINUATION

        # Check total
        if self._total is not None:
            if self._eval_time - self._start_time >= self._total:
                stop = True
        # Check continuation
        if self._continuation is not None and self._state == self.State.CONTINUATION and self._last_eval_time is not None:
            if self._eval_time - self._last_eval_time >= self._continuation:
                stop = True
        
        # Check response time
        if self._response is not None and self._state == self.State.WAIT_FOR_RESPONSE:
            if self._eval_time - self._start_time >= self._response:
                stop = True
        if stop:
            return True, None
            
        self._last_eval_time = self._eval_time
        self._eval_time = None
        # No timeouts were reached, return the next one
        timeout = None
        # Return the timeout (state is always CONTINUATION at this stage)
        # Take the smallest between continuation and total
        if self._total is not None and self._continuation is not None:
            timeout = min((self._start_time + self._total) - time(), self._continuation)
        elif self._total is not None:
            timeout = time() - (self._start_time + self._total)
        elif self._continuation is not None:
            timeout = self._continuation
        else:
            timeout = None
        return False, timeout, data, b''

class Termination(StopCondition):
    def __init__(self, sequence : bytes) -> None:
        """
        Stop reading once the desired sequence is detected

        Parameters
        ----------
        sequence : bytes
        """
        super().__init__()
        self._sequence = sequence
        self._sequence_index = 0

    def initiate_read(self):
        super().initiate_read()
        self._sequence_index = 0
        return None

    def evaluate(self, fragment: bytes) -> Tuple[bool, Union[float, None]]:
        #if len(byte) != 1:
        #    raise ValueError(f"Invalid byte length : {len(byte)}")
        try:
            termination_index = fragment.index(self._sequence)
            return True, None, fragment[:termination_index], fragment[termination_index+1:]
        except ValueError:
            # No termination, return everything and continue
            return False, None, fragment, b''

        # TODO : Implement partial sequence detection (if a sequence starts in a fragment and ends in the next one)

        for b in fragment:
            if self._sequence[self._sequence_index] == b:
                # The byte is in the sequence
                self._sequence_index += 1
                if self._sequence_index == len(self._sequence):
                    # We finished the sequence
                    self._sequence_index = 0
                    return True, None
        else:
            self._sequence_index = 0
        return False, None, 

class Length(StopCondition):
    def __init__(self, N : int) -> None:
        """
        Stop condition when the desired number of bytes is reached or passed
        
        Parameters
        ----------
        N : int
            Number of bytes
        """
        super().__init__()
        self._N = N
        self._counter = 0

    def initiate_read(self):
        super().initiate_read()
        self._counter = 0

    def evaluate(self, data: bytes) -> Tuple[bool, Union[float, None]]:
        self._counter += len(data)
        return self._counter >= self._N, None