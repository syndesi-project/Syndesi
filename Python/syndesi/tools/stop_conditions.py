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
        self._start_time = None
        self._response_start = None
        # Time at which the evaluation command is run
        self._eval_time = None

    def initiate_read(self):
        if self._start_time is not None:
            # It hasn't been set by an other StopCondition istance
            self._start_time = time.now()

    def initiate_continuation(self):
        self._response_start = time.now()

    def evaluate(self, data : bytearray) -> Tuple[bool, int]:
        # Will be implemented by each stop condition
        pass

    def _check_init(self):
        if self._start_time is None:
            raise RuntimeError("Cannot evaluate stop condition if initiate_read wasn't called first")


    def __or__(self, sc):
        assert isinstance(sc, StopCondition), f"Cannot do or operator between StopCondition and {type(sc)}"
        return StopConditionOperation(self, sc, operation=StopConditionOperation.OR)
    
    def __and__(self, sc):
        assert isinstance(sc, StopCondition), f"Cannot do and operator between StopCondition and {type(sc)}"
        return StopConditionOperation(self, sc, operation=StopConditionOperation.AND)

class StopConditionOperation(Enum):
    OR = 0
    AND = 1

class StopConditionExpression(StopCondition):
    def __init__(self, A : StopCondition, B : StopCondition, operation : StopConditionOperation) -> None:
        super().__init__()
        self._A = A
        self._B = B
        self._operation = operation

    def evaluate(self, data: bytearray) -> Tuple[bool, int]:
        if self._eval_time is None:
            # First function to be called
            self._eval_time = time()
        super()._check_init()
        a_evaluation._eval_time = self._eval_time
        b_evaluation._eval_time = self._eval_time
        a_evaluation = self._A.evaluate(data)
        b_evaluation = self._B.evaluate(data)
        if self._operation == StopConditionOperation.OR:
            return a_evaluation or b_evaluation
        elif self._operation == StopConditionOperation.AND:
            return a_evaluation and b_evaluation
        self._eval_time = None
    
    def initiate_read(self):
        super().initiate_read()
        self._A._start_time = self._start_time
        self._A.initiate_read()
        self._B._start_time = self._start_time
        self._B.initiate_read()

class Timeout(StopCondition):
    DEFAULT_CONTINUATION_TIMEOUT = 5e-3
    DEFAULT_TOTAL_TIMEOUT = 5

    class State(Enum):
        WAIT_FOR_RESPONSE = 0
        CONTINUATION = 1

    def __init__(self, response, continuation=DEFAULT_CONTINUATION_TIMEOUT, total=DEFAULT_TOTAL_TIMEOUT) -> None:
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

    def initiate_read(self):
        super().initiate_read()
        self._state = self.State.WAIT_FOR_RESPONSE

    def evaluate(self, data: bytearray) -> Tuple[bool, int]:
        if self._eval_time is None:
            # First to be called
            self._eval_time = time()
        super()._check_init()
        
        # Always return False and 0 as the timeout will never
        # tell directly that time is up, it will notify it asynchronously (somehow)
        # It isn't able to tell when to crop either as communication isn't real-time enough
        return False, 0

        # TODO : Find a way for the timeout to asynchronously tell the adapter that
        # a timeout has been reached and return
    

class Termination(StopCondition):
    def __init__(self, sequence : Union[bytes, bytearray]) -> None:
        """
        Stop reading once the desired sequence is detected

        Parameters
        ----------
        sequence : bytes
        """
        super().__init__()
        self._sequence = sequence

    def evaluate(self, data: bytearray) -> Tuple[bool, int]:
        super()._check_init()
        try:
            pos = data.index(self._sequence)
        except ValueError:
            # Sequence not found
            return False, 0
        else:
            return True, len(data) - pos + len(self._sequence)


class Length(StopCondition):
    def __init__(self, N : int, allow_exceed : bool = False) -> None:
        """
        Stop condition when the desired number of bytes is reached or passed
        
        Parameters
        ----------
        N : int
            Number of bytes
        allow_exceed : bool
            Allow exceeding of the specified length, if False, the excess bytes
            are left in the read buffer
        """
        super().__init__()
        self._N = N
        self._allow_exceed = allow_exceed
        self._counter = 0

    def initiate_read(self):
        super().initiate_read()
        self._counter = 0

    def evaluate(self, data: bytearray) -> Tuple[bool, int]:
        super()._check_init()
        if len(data) >= self._N:
            return True, len(data) - self._N
        else:
            return False, 0
        