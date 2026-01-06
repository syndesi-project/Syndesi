# File : stop_condition.py
# Author : Sébastien Deriaz
# License : GPL

"""
Stop-condition module

This is the frontend of the stop-conditions, the part that is imported by the user
"""

# from abc import abstractmethod
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum


@dataclass
class Fragment:
    """
    Fragment class, holds a piece of data (bytes) and the time at which it was received
    """

    data: bytes
    timestamp: float

    def __str__(self) -> str:
        return f"{self.data!r}@{self.timestamp}"

    def __repr__(self) -> str:
        return f"Fragment({self.data!r}@{self.timestamp})"

    def __getitem__(self, key: slice) -> "Fragment":
        # if self.data is None:
        #     raise IndexError('Cannot index invalid fragment')
        return Fragment(self.data[key], self.timestamp)


class StopConditionType(Enum):
    """
    Stop-condition type
    """

    TERMINATION = "termination"
    LENGTH = "length"
    CONTINUATION = "continuation"
    TOTAL = "total"
    FRAGMENT = "fragment"


class StopCondition:
    """
    Stop-condition base class, cannot be used on its own
    """

    # @abstractmethod
    # def type(self) -> StopConditionType:
    #     pass

    @abstractmethod
    def initiate_read(self, timestamp: float) -> None:
        """
        Prepare the stop-condition for the next read
        """

    @abstractmethod
    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        """
        Evaluate incoming fragment and return read information for the next fragment
        """

    @abstractmethod
    def type(self) -> StopConditionType:
        """
        Helper function to determine the which type of stop-condition generated a stop
        """

    @abstractmethod
    def flush_read(self) -> None:
        """
        Reset read operation
        """


class Termination(StopCondition):
    """
    Termination stop-condition, used to stop when a specified sequence is received

    Parameters
    ----------
    sequence : bytes | str
    """

    def __init__(self, sequence: bytes | str) -> None:
        super().__init__()
        if isinstance(sequence, str):
            self._sequence = sequence.encode("utf-8")
        else:
            self._sequence = sequence
        self._sequence_found_length = 0

    # TYPE = StopConditionType.TERMINATION

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
        return f"Termination({repr(self._sequence)})"

    def __repr__(self) -> str:
        return self.__str__()

    def initiate_read(self, timestamp: float) -> None:
        self._sequence_found_length = 0

    def flush_read(self) -> None:
        self._sequence_found_length = 0

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        if raw_fragment.data is None:
            raise RuntimeError("Trying to evaluate an invalid fragment")

        position, length = termination_in_data(
            self._sequence[self._sequence_found_length :], raw_fragment.data
        )
        stop = False
        deferred = Fragment(b"", raw_fragment.timestamp)

        if position is None:
            # Nothing was found, keep everything
            kept = raw_fragment
        else:
            self._sequence_found_length += length

            if self._sequence_found_length == len(self._sequence):
                # The sequence was found entirely
                deferred = raw_fragment[position + length :]
                self._sequence_found_length = 0
                stop = True
            elif position + length == len(raw_fragment.data):
                # Part of the sequence was found at the end
                # Return what's before the sequence
                deferred = Fragment(b"", raw_fragment.timestamp)

            kept = raw_fragment[: position + length]

        return stop, kept, deferred, None

    def type(self) -> StopConditionType:
        return StopConditionType.TERMINATION


class Length(StopCondition):
    """
    Length stop-condition, used to stop when the specified number of bytes (or more) have been read

    Parameters
    ----------
    n : int
        Number of bytes
    """

    # TYPE = StopConditionType.LENGTH
    def __init__(self, n: int) -> None:
        super().__init__()
        self._n = n
        self._counter = 0

    def __str__(self) -> str:
        return f"Length({self._n})"

    def __repr__(self) -> str:
        return self.__str__()

    def initiate_read(self, timestamp: float) -> None:
        # Length
        self._counter = 0

    def type(self) -> StopConditionType:
        return StopConditionType.LENGTH

    def flush_read(self) -> None:
        self._counter = 0

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        remaining_bytes = self._n - self._counter
        kept_fragment = raw_fragment[:remaining_bytes]
        deferred_fragment = raw_fragment[remaining_bytes:]
        self._counter += len(kept_fragment.data)
        remaining_bytes = self._n - self._counter
        # TODO : remaining_bytes <= 0 ? Alongside above TODO maybe
        return remaining_bytes == 0, kept_fragment, deferred_fragment, None


class Continuation(StopCondition):
    """
    Continuation stop-condition, used to stop reading when data has already been received
    and nothing has been received since then for the specified amount of time

    Parameters
    ----------
    continuation : float
    """

    def __init__(self, continuation: float) -> None:
        super().__init__()
        self.continuation = continuation
        self._last_fragment: float | None = None

    def __str__(self) -> str:
        return f"Continuation({self.continuation})"

    def __repr__(self) -> str:
        return self.__str__()

    def initiate_read(self, timestamp: float) -> None:
        self._last_fragment = timestamp

    def flush_read(self) -> None:
        self._last_fragment = None

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        deferred = Fragment(b"", raw_fragment.timestamp)
        kept = raw_fragment

        # if raw_fragment.timestamp is None:
        #    raise RuntimeError("Cannot evaluate fragment with no timestamp")
        # last_fragment can be none if no data was ever received
        if self._last_fragment is not None:
            continuation_timestamp = self._last_fragment + self.continuation
            stop = continuation_timestamp <= raw_fragment.timestamp
            next_event_timeout = continuation_timestamp
        else:
            stop = False
            next_event_timeout = None

        return stop, kept, deferred, next_event_timeout

    def type(self) -> StopConditionType:
        return StopConditionType.CONTINUATION


class Total(StopCondition):
    """
    Total stop-condition, used to stop reading when data has already been received
    and the total read time exceeds the specified amount

    """

    def __init__(self, total: float) -> None:
        super().__init__()
        self.total = total
        self._start_time: float | None = None

    def __str__(self) -> str:
        return f"Total({self.total})"

    def __repr__(self) -> str:
        return self.__str__()

    def initiate_read(self, timestamp: float) -> None:
        self._start_time = timestamp

    def flush_read(self) -> None:
        self._start_time = None

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        kept = raw_fragment
        deferred = Fragment(b"", raw_fragment.timestamp)

        # if raw_fragment.timestamp is None:
        #     raise RuntimeError("Cannot evaluate fragment with no timestamp")

        if self._start_time is None:
            raise RuntimeError("Invalid start time")
        total_timestamp = self._start_time + self.total
        stop = total_timestamp <= raw_fragment.timestamp

        return stop, kept, deferred, total_timestamp

    def type(self) -> StopConditionType:
        return StopConditionType.TOTAL


class FragmentStopCondition(StopCondition):
    """
    Fragment stop-condition, used to stop on each piece of data received by the
    adapter

    """

    def __init__(self) -> None: ...

    def __str__(self) -> str:
        return "FragmentStopCondition()"

    def __repr__(self) -> str:
        return self.__str__()

    def initiate_read(self, timestamp: float) -> None:
        pass

    def flush_read(self) -> None:
        pass

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:

        return True, raw_fragment, Fragment(b"", raw_fragment.timestamp), None

    def type(self) -> StopConditionType:
        return StopConditionType.FRAGMENT


def termination_in_data(termination: bytes, data: bytes) -> tuple[int | None, int]:
    """
    Return the position (if it exists) and length of the termination (or part of it) inside data
    """
    p = None
    length = len(termination)
    # First check if the full termination is somewhere. If that's the case, data will be split
    try:
        p = data.index(termination)
        # If found, return that
    except ValueError:
        # If not, we'll try to find if part of the sequence is at the end, in that case
        # we'll return the length of the sequence that was found
        length -= 1
        while length > 0:
            if data[-length:] == termination[:length]:
                p = len(data) - length  # - 1
                break
            length -= 1

    return p, length
