# File : stop_condition.py
# Author : Sébastien Deriaz
# License : GPL
#
# A stop-condition describes when a communication with a device should
# be stopped based on the data received (length, contents, termination, etc...)
# A stop-condition can also format the data if necessary (remove termination for example)

import time

from syndesi.adapters.stop_condition import (
    Continuation,
    Length,
    StopCondition,
    StopConditionType,
    Termination,
    Total,
)

from ...tools.backend_api import Fragment


def termination_in_data(termination: bytes, data: bytes) -> tuple[int | None, int]:
    """
    Return the position (if it exists) and length of the termination (or part of it) inside data
    """
    p = None
    L = len(termination)
    # First check if the full termination is somewhere. If that's the case, data will be split
    try:
        p = data.index(termination)
        # If found, return that
    except ValueError:
        # If not, we'll try to find if part of the sequence is at the end, in that case
        # we'll return the length of the sequence that was found
        L -= 1
        while L > 0:
            if data[-L:] == termination[:L]:
                p = len(data) - L  # - 1
                break
            L -= 1

    return p, L


class StopConditionBackend:
    def __init__(self) -> None:
        pass

    def initiate_read(self) -> None:
        raise NotImplementedError()

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        raise NotImplementedError()

    def type(self) -> StopConditionType:
        raise NotImplementedError()

    def flush_read(self) -> None:
        raise NotImplementedError()


class TerminationBackend(StopConditionBackend):
    def __init__(self, sequence: bytes) -> None:
        super().__init__()
        self._sequence = sequence
        self._sequence_found_length = 0

    def initiate_read(self) -> None:
        # Termination
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
        deferred = Fragment(b"", None)

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
                deferred = Fragment(b"", None)

            kept = raw_fragment[:position]

        return stop, kept, deferred, None

    def type(self) -> StopConditionType:
        return StopConditionType.TERMINATION


class LengthBackend(StopConditionBackend):
    def __init__(self, N: int) -> None:
        super().__init__()
        self._N = N
        self._counter = 0

    def initiate_read(self) -> None:
        # Length
        self._counter = 0

    def flush_read(self) -> None:
        self._counter = 0

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        remaining_bytes = self._N - self._counter
        kept_fragment = raw_fragment[:remaining_bytes]
        deferred_fragment = raw_fragment[remaining_bytes:]
        self._counter += len(kept_fragment.data)
        remaining_bytes = self._N - self._counter
        # TODO : remaining_bytes <= 0 ? Alongside above TODO maybe
        return remaining_bytes == 0, kept_fragment, deferred_fragment, None

    def type(self) -> StopConditionType:
        return StopConditionType.LENGTH


class ContinuationBackend(StopConditionBackend):
    def __init__(self, time: float) -> None:
        super().__init__()
        self._continuation = time
        self._last_fragment: float | None = None

    def initiate_read(self) -> None:
        self._last_fragment = time.time()

    def flush_read(self) -> None:
        self._last_fragment = None

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        deferred = Fragment(b"", None)
        kept = raw_fragment

        if raw_fragment.timestamp is None:
            raise RuntimeError("Cannot evaluate fragment with no timestamp")
        # last_fragment can be none if no data was ever received
        if self._last_fragment is not None:
            continuation_timestamp = self._last_fragment + self._continuation
            stop = continuation_timestamp <= raw_fragment.timestamp
            next_event_timeout = continuation_timestamp
        else:
            stop = False
            next_event_timeout = None

        return stop, kept, deferred, next_event_timeout

    def type(self) -> StopConditionType:
        return StopConditionType.TIMEOUT


class TotalBackend(StopConditionBackend):
    def __init__(self, time: float) -> None:
        super().__init__()
        self._total = time
        self._start_time: float | None = None

    def initiate_read(self) -> None:
        self._start_time = time.time()

    def flush_read(self) -> None:
        self._start_time = None

    def evaluate(
        self, raw_fragment: Fragment
    ) -> tuple[bool, Fragment, Fragment, float | None]:
        kept = raw_fragment
        deferred = Fragment(b"", None)

        if raw_fragment.timestamp is None:
            raise RuntimeError("Cannot evaluate fragment with no timestamp")

        if self._start_time is None:
            raise RuntimeError("Invalid start time")
        total_timestamp = self._start_time + self._total
        stop = total_timestamp <= raw_fragment.timestamp

        return stop, kept, deferred, total_timestamp

    def type(self) -> StopConditionType:
        return StopConditionType.TIMEOUT


def stop_condition_to_backend(stop_condition: StopCondition) -> StopConditionBackend:
    if isinstance(stop_condition, Termination):
        return TerminationBackend(stop_condition.sequence)
    elif isinstance(stop_condition, Length):
        return LengthBackend(stop_condition.N)
    elif isinstance(stop_condition, Continuation):
        return ContinuationBackend(stop_condition.continuation)
    elif isinstance(stop_condition, Total):
        return TotalBackend(stop_condition.total)
    else:
        raise RuntimeError(f"Invalid stop condition : {stop_condition}")
