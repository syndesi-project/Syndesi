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
        self._start = None
        self._response_start = None

    def initiate_read(self):
        self._start = time.now()
        # Time
        pass

    def initiate_continuation(self):
        self._response_start = time.now()

    def evaluate(self, data : bytes) -> Tuple[bool, int]:
        # Will be implemented by each stop condition
        pass

    def _check_init(self):
        if self._start is None:
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

    def evaluate(self, data: bytes) -> Tuple[bool, int]:
        super()._check_init()
        a_evaluation = self._A.evaluate(data, continuation)
        b_evaluation = self._B.evaluate(data, continuation)
        if self._operation == StopConditionOperation.OR:
            return a_evaluation or b_evaluation
        elif self._operation == StopConditionOperation.AND:
            return a_evaluation and b_evaluation

class Timeout(StopCondition):
    DEFAULT_CONTINUATION_TIMEOUT = 5e-3
    DEFAULT_TOTAL_TIMEOUT = 5
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

        self._response = response
        self._continuation = continuation
        self._total = total

    def evaluate(self, data: bytes) -> Tuple[bool, int]:
        super()._check_init()
        t = time.now()
        if self._total is not None:
            # First check if the total timeout is reached
            if t - self._start >= self._total:
                return True, 0
        if self._continuation is not None:
            if t - self._response_start

            # TODO : Find a way to alert whenever a single byte is receivedd
    

class Termination(StopCondition):
    def __init__(self, sequence : Union[bytes, bytes]) -> None:
        """
        Stop reading once the desired sequence is detected

        Parameters
        ----------
        sequence : bytes
        """
        super().__init__()
        self._sequence = sequence

    def evaluate(self, data: bytes) -> Tuple[bool, int]:
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

    def evaluate(self, data: bytes) -> Tuple[bool, int]:
        super()._check_init()
        if len(data) >= self._N:
            return True, len(data) - self._N
        else:
            return False, 0
        