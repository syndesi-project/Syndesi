# File : framer.py
# Author : Sébastien Deriaz
# License : GPL
"""
Framers assemble the fragments returned by a backend into complete frames

A framer holds no socket and no thread. It is a pure function of the fragments
and timestamps it is given, which makes it testable on its own
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, runtime_checkable

from .stop_conditions import BytesFragment, Continuation, StopCondition, Total
from .utils import Fragment

DataT = TypeVar("DataT")


@dataclass
class Frame(Generic[DataT]):
    """
    A complete frame, as produced by a framer

    The adapter adds the frame id, the response delay and the buffer information
    to build the ReadFrame returned to the user
    """

    data: DataT
    first_fragment_timestamp: float
    stop_timestamp: float
    stop_condition: StopCondition | None = None


class Framer(Generic[DataT], ABC):
    """
    Framer base class, turns a stream of fragments into complete frames
    """

    @abstractmethod
    def push(self, fragment: Fragment[DataT]) -> list[Frame[DataT]]:
        """
        Take a new fragment and return the frames it completes

        Parameters
        ----------
        fragment : Fragment

        Returns
        -------
        frames : list[Frame]
            Empty if the fragment doesn't complete anything
        """

    @abstractmethod
    def next_deadline(self) -> float | None:
        """
        Return the timestamp at which on_deadline must be called

        Returns
        -------
        deadline : float or None
            None if the framer isn't waiting for a deadline
        """

    @abstractmethod
    def on_deadline(self, now: float) -> list[Frame[DataT]]:
        """
        Called when the timestamp returned by next_deadline is reached

        Parameters
        ----------
        now : float

        Returns
        -------
        frames : list[Frame]
        """

    @property
    @abstractmethod
    def in_progress(self) -> bool:
        """
        Return True if a frame is currently being assembled
        """

    @abstractmethod
    def reset(self) -> None:
        """
        Discard the frame currently being assembled
        """


@runtime_checkable
class SupportsStopConditions(Protocol):
    """
    A framer whose behaviour is configured by stop-conditions

    Used by the adapter to read and swap them without knowing the framer type
    """

    stop_conditions: list[StopCondition]


class TrivialFramer(Framer[DataT]):
    """
    Framer without stop-conditions, each fragment is a complete frame

    Used by adapters whose data type is already a complete unit, like IPServer
    """

    def push(self, fragment: Fragment[DataT]) -> list[Frame[DataT]]:
        return [
            Frame(
                data=fragment.data,
                first_fragment_timestamp=fragment.timestamp,
                stop_timestamp=fragment.timestamp,
            )
        ]

    def next_deadline(self) -> float | None:
        return None

    def on_deadline(self, now: float) -> list[Frame[DataT]]:
        return []

    @property
    def in_progress(self) -> bool:
        return False

    def reset(self) -> None:
        pass


class BytesFramer(Framer[bytes]):
    """
    Framer assembling bytes fragments into frames using stop-conditions

    stop_conditions is a plain attribute so that the adapter can swap it for the
    duration of a single read. It must only be swapped on a frame boundary, the
    new conditions are initiated on the next first fragment

    Parameters
    ----------
    stop_conditions : list[StopCondition]
    """

    def __init__(self, stop_conditions: list[StopCondition]) -> None:
        super().__init__()
        self.stop_conditions = stop_conditions
        self._fragments: list[BytesFragment] = []
        self._first_fragment = True
        self._first_fragment_timestamp: float | None = None
        self._last_fragment_timestamp: float | None = None

    # ┌───────────────────┐
    # │ Frame assembly    │
    # └───────────────────┘

    def push(self, fragment: BytesFragment) -> list[Frame[bytes]]:
        frames: list[Frame[bytes]] = []
        kept = fragment

        # A fragment can complete more than one frame, the data left over by a
        # stop-condition is fed back in as the start of the next one
        while True:
            if self._first_fragment:
                self._first_fragment = False
                self._first_fragment_timestamp = kept.timestamp
                for stop_condition in self.stop_conditions:
                    stop_condition.initiate_read(kept.timestamp)

            stop_condition_hit: StopCondition | None = None
            deferred = BytesFragment(b"", kept.timestamp)

            for stop_condition in self.stop_conditions:
                stop, kept, deferred, _ = stop_condition.evaluate(kept)
                if stop:
                    stop_condition_hit = stop_condition
                    break

            self._fragments.append(kept)
            self._last_fragment_timestamp = kept.timestamp

            if stop_condition_hit is None:
                break

            frames.append(self._build_frame(kept.timestamp, stop_condition_hit))

            if len(deferred.data) == 0:
                break
            kept = deferred

        return frames

    def next_deadline(self) -> float | None:
        deadline, _ = self._deadline()
        return deadline

    def on_deadline(self, now: float) -> list[Frame[bytes]]:
        deadline, origin = self._deadline()
        if deadline is None or now < deadline or len(self._fragments) == 0:
            return []
        return [self._build_frame(now, origin)]

    @property
    def in_progress(self) -> bool:
        return len(self._fragments) > 0

    def reset(self) -> None:
        self._clear_assembly()
        for stop_condition in self.stop_conditions:
            stop_condition.clear_read_buffer()

    # ┌───────────────────┐
    # │ Internals         │
    # └───────────────────┘

    def _deadline(self) -> tuple[float | None, StopCondition | None]:
        """
        Return the earliest stop-condition deadline and the condition it comes from

        Only Continuation and Total are time based. Both are relative to the frame
        being assembled, so there is no deadline while the framer is empty
        """
        deadline: float | None = None
        origin: StopCondition | None = None

        for stop_condition in self.stop_conditions:
            candidate: float | None = None
            if isinstance(stop_condition, Continuation):
                if self._last_fragment_timestamp is not None:
                    candidate = self._last_fragment_timestamp + stop_condition.continuation
            elif isinstance(stop_condition, Total):
                if self._first_fragment_timestamp is not None:
                    candidate = self._first_fragment_timestamp + stop_condition.total

            if candidate is not None and (deadline is None or candidate < deadline):
                deadline = candidate
                origin = stop_condition

        return deadline, origin

    def _build_frame(
        self, stop_timestamp: float, stop_condition: StopCondition | None
    ) -> Frame[bytes]:
        frame = Frame(
            data=b"".join(fragment.data for fragment in self._fragments),
            first_fragment_timestamp=self._fragments[0].timestamp,
            stop_timestamp=stop_timestamp,
            stop_condition=stop_condition,
        )
        self._clear_assembly()
        return frame

    def _clear_assembly(self) -> None:
        self._fragments = []
        self._first_fragment = True
        self._first_fragment_timestamp = None
        self._last_fragment_timestamp = None
