# File : stop_condition.py
# Author : Sébastien Deriaz
# License : GPL

import json
from abc import abstractmethod
from enum import Enum

class StopConditionType(Enum):
    TERMINATION = 'termination'
    LENGTH = 'length'
    TIMEOUT = 'timeout'
    #CONTINUATION = 'continuation'
    #TOTAL = 'total'




class StopCondition:
    @abstractmethod
    def type(self) -> StopConditionType:
        pass


    def __init__(self) -> None:
        """
        A condition to stop reading from a device

        Cannot be used on its own
        """

    # @abstractmethod
    # def compose_json(self) -> str:
    #     raise NotImplementedError

    # def compose(self) -> dict:
    #     raise NotImplementedError


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

    # def compose_json(self) -> str:
    #     data = {
    #         JsonKey.TYPE.value: StopConditionType.TERMINATION.value,
    #         JsonKey.TERMINATION_SEQUENCE.value: self._sequence.decode("utf-8"),
    #     }
    #     return json.dumps(data)
    
    # def compose(self) -> dict:
    #     return {
    #         StopConditionDescriptorKey.TYPE.value: StopConditionType.TERMINATION.value,
    #         StopConditionDescriptorKey.TERMINATION_SEQUENCE.value: self.sequence.decode("utf-8"),
    #     }

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

    # def compose_json(self) -> str:
    #     data = {
    #         JsonKey.TYPE.value: StopConditionType.LENGTH.value,
    #         JsonKey.LENGTH_N.value: self._N,
    #     }
    #     return json.dumps(data)

    # def compose(self) -> dict:
    #     return {
    #         StopConditionDescriptorKey.TYPE.value: StopConditionType.LENGTH.value,
    #         StopConditionDescriptorKey.LENGTH_N.value: self.N,
    #     }

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"Length({self.N})"
    
    def type(self) -> StopConditionType:
        return StopConditionType.LENGTH


class Continuation(StopCondition):
    def __init__(self, time : float) -> None:
        super().__init__()
        self.continuation = time
    
    def type(self) -> StopConditionType:
        return StopConditionType.TIMEOUT

class Total(StopCondition):
    def __init__(self, time : float) -> None:
        super().__init__()
        self.total = time
    
    def type(self) -> StopConditionType:
        return StopConditionType.TIMEOUT
    


# class TimeoutStopCondition(StopCondition):
#     def __init__(
#         self, continuation: float | None = None, total: float | None = None
#     ) -> None:
#         super().__init__()
#         self.continuation = continuation
#         self.total = total

#     # def compose_json(self) -> str:
#     #     data = {
#     #         JsonKey.TYPE.value: StopConditionType.TIMEOUT.value,
#     #         JsonKey.TIMEOUT_CONTINUATION.value: self.continuation,
#     #         JsonKey.TIMEOUT_TOTAL.value: self.total,
#     #     }
#     #     return json.dumps(data)

#     # def compose(self) -> dict:
#     #     return {
#     #         StopConditionDescriptorKey.TYPE.value: StopConditionType.TIMEOUT.value,
#     #         StopConditionDescriptorKey.TIMEOUT_CONTINUATION.value: self.continuation,
#     #         StopConditionDescriptorKey.TIMEOUT_TOTAL.value: self.total,
#     #     }

#     def __repr__(self) -> str:
#         return super().__repr__()

#     def __str__(self) -> str:
#         return super().__str__()
    
#     def type(self) -> StopConditionType:
#         return StopConditionType.TIMEOUT
