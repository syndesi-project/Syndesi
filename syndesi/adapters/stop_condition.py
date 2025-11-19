# File : stop_condition.py
# Author : Sébastien Deriaz
# License : GPL

"""
Stop-condition module

This is the frontend of the stop-conditions, the part that is imported by the user
"""

#from abc import abstractmethod
from enum import Enum
from dataclasses import dataclass


class StopConditionType(Enum):
    """
    Stop-condition type
    """
    TERMINATION = "termination"
    LENGTH = "length"
    TIMEOUT = "timeout"

@dataclass
class StopCondition:
    """
    Stop-condition base class, cannot be used on its own
    """
    # @abstractmethod
    # def type(self) -> StopConditionType:
    #     pass

    def __repr__(self) -> str:
        return self.__str__()

@dataclass
class Termination(StopCondition):
    """
    Termination stop-condition, used to stop when a specified sequence is received

    Parameters
    ----------
    sequence : bytes | str
    """
    #TYPE = StopConditionType.TERMINATION
    sequence : bytes | str
    # def __init__(self, sequence: bytes | str) -> None:
    #     """
    #     Instanciate a new Termination class
    #     """
    #     self.sequence: bytes
    #     if isinstance(sequence, str):
    #         self.sequence = sequence.encode("utf-8")
    #     elif isinstance(sequence, bytes):
    #         self.sequence = sequence
    #     else:
    #         raise ValueError(f"Invalid termination sequence type : {type(sequence)}")

    def __str__(self) -> str:
        return f"Termination({repr(self.sequence)})"


@dataclass
class Length(StopCondition):
    """
    Length stop-condition, used to stop when the specified number of bytes (or more) have been read
    
    Parameters
    ----------
    N : int
        Number of bytes
    """
    #TYPE = StopConditionType.LENGTH
    n : int

    def __str__(self) -> str:
        return f"Length({self.n})"

    # def type(self) -> StopConditionType:
    #     return StopConditionType.LENGTH

@dataclass
class Continuation(StopCondition):
    """
    Continuation stop-condition, used to stop reading when data has already been received
    and nothing has been received since then for the specified amount of time

    Parameters
    ----------
    time : float
    """
    #TYPE = StopConditionType.TIMEOUT
    time : float



    # def type(self) -> StopConditionType:
    #     return StopConditionType.TIMEOUT

@dataclass
class Total(StopCondition):
    """
    Total stop-condition, used to stop reading when data has already been received
    and the total read time exceeds the specified amount
    
    """
    #TYPE = StopConditionType.TIMEOUT
    time : float
    # def __init__(self, time: float) -> None:
    #     super().__init__()
    #     self.total = time

    # def type(self) -> StopConditionType:
    #     return StopConditionType.TIMEOUT
