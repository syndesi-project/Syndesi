# File : stop_condition.py
# Author : Sébastien Deriaz
# License : GPL

from abc import abstractmethod
from enum import Enum

class StopConditionType(Enum):
    TERMINATION = "termination"
    LENGTH = "length"
    TIMEOUT = "timeout"

class StopCondition:
    @abstractmethod
    def type(self) -> StopConditionType:
        pass

    def __init__(self) -> None:
        """
        A condition to stop reading from a device

        Cannot be used on its own
        """


class Termination(StopCondition):
    def __init__(self, sequence: bytes | str) -> None:
        """
        Stop reading once the desired sequence is detected

        Parameters
        ----------
        sequence : bytes
        """
        self.sequence: bytes
        if isinstance(sequence, str):
            self.sequence = sequence.encode("utf-8")
        elif isinstance(sequence, bytes):
            self.sequence = sequence
        else:
            raise ValueError(f"Invalid termination sequence type : {type(sequence)}")

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"Termination({repr(self.sequence)})"

    def type(self) -> StopConditionType:
        return StopConditionType.TERMINATION


class Length(StopCondition):
    def __init__(self, N: int) -> None:
        """
        Stop condition when the desired number of bytes is reached or passed

        Parameters
        ----------
        N : int
            Number of bytes
        """
        self.N = N

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"Length({self.N})"

    def type(self) -> StopConditionType:
        return StopConditionType.LENGTH


class Continuation(StopCondition):
    def __init__(self, time: float) -> None:
        super().__init__()
        self.continuation = time

    def type(self) -> StopConditionType:
        return StopConditionType.TIMEOUT


class Total(StopCondition):
    def __init__(self, time: float) -> None:
        super().__init__()
        self.total = time

    def type(self) -> StopConditionType:
        return StopConditionType.TIMEOUT
