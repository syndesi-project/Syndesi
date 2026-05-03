# File : bytesadapter.py
# Author : Sébastien Deriaz
# License : GPL
"""
Bytes adapter and worker
"""
from __future__ import annotations

import time
from abc import abstractmethod
from collections import deque
from types import EllipsisType

from ..component import Descriptor, Frame
from .adapter import Adapter
from .adapterworker import (
    AdapterWorker,
    AdapterWorkerInterface,
    GetStopConditionsCommand,
    SetStopConditionsCommand,
)
from .stop_conditions import (
    BytesFragment,
    Continuation,
    StopCondition,
    StopConditionType,
    Total,
)
from .tracehub import tracehub
from .utils import nmin, TimeoutType


def fuse_fragments(fragments: list[BytesFragment]) -> bytes:
    """
    Merge fragments data into a single bytes object
    """

    output = b""
    for fragment in fragments:
        output += fragment.data
    return output


# pylint: disable=too-many-instance-attributes
class BytesAdapterWorker(AdapterWorker[bytes]):
    """
    Adapter worker with bytes and fragment support
    """

    # How many completed frames we keep for BUFFERED reads
    def __init__(self, adapter_interface: AdapterWorkerInterface[bytes]) -> None:
        super().__init__(adapter_interface)

        # Fragment assembly state
        self._first_fragment_timestamp: float | None = None
        self._first_fragment: bool = True
        self._fragments: list[BytesFragment] = []
        self._previous_buffer: BytesFragment = BytesFragment(b"", time.time())
        self._last_write_timestamp: float | None = None
        self._next_stop_condition_timeout_timestamp: float | None = None
        self._read_start_timestamp: float | None = None
        self._last_fragment_timestamp: float | None = None
        self._frame_buffer: deque[Frame[bytes]] = deque(maxlen=self._FRAME_BUFFER_MAX)
        self._timeout_origin: StopConditionType = StopConditionType.TIMEOUT

    # ┌──────────────────────────────┐
    # │ Worker: fragment/frame logic │
    # └──────────────────────────────┘

    def _worker_manage_fragment(self, fragment: BytesFragment) -> None:
        # pylint: disable=too-many-branches, too-many-statements
        self._last_fragment_timestamp = fragment.timestamp

        if self._last_write_timestamp is not None:
            write_delta = fragment.timestamp - self._last_write_timestamp
            initiate_timestamp = fragment.timestamp
        else:
            write_delta = float("nan")
            initiate_timestamp = time.time()

        suffix = " (first)" if self._first_fragment else ""
        self._worker_logger.debug(
            "New fragment %+.3f %s%s", write_delta, fragment, suffix
        )

        stop_timestamp = float("nan")
        kept = fragment

        while True:
            if self._first_fragment:
                self._first_fragment = False
                self._read_start_timestamp = fragment.timestamp
                self._first_fragment_timestamp = fragment.timestamp

                for stop_condition in self._stop_conditions:
                    stop_condition.initiate_read(initiate_timestamp)

            stop = False
            stop_condition_type: StopConditionType | None = None

            for stop_condition in self._stop_conditions:
                (
                    stop,
                    kept,
                    self._previous_buffer,
                    next_stop_condition_timeout_timestamp,
                ) = stop_condition.evaluate(kept)

                self._next_stop_condition_timeout_timestamp = nmin(
                    next_stop_condition_timeout_timestamp,
                    self._next_stop_condition_timeout_timestamp,
                )
                if stop:
                    stop_condition_type = stop_condition.type()
                    stop_timestamp = kept.timestamp
                    break

            self._fragments.append(kept)

            # If there's no stop, break here
            if stop_condition_type is None:
                # Only upload emit a fragment event if there's no frame
                if self._interface.descriptor is not None:
                    if self._last_write_timestamp is None:
                        write_delta = float("nan")
                    else:
                        write_delta = kept.timestamp - self._last_write_timestamp

                    tracehub.emit_fragment(
                        descriptor=str(self._interface.descriptor),
                        fragment=kept,
                        write_delta=write_delta,
                    )
                break

            # frame complete
            self._first_fragment = True

            if self._last_write_timestamp is None:
                response_delay = float("nan")
            else:
                response_delay = (
                    self._fragments[0].timestamp - self._last_write_timestamp
                )

            frame = Frame(
                data=fuse_fragments(self._fragments),
                first_fragment_timestamp=self._fragments[0].timestamp,
                stop_timestamp=stop_timestamp,
                stop_condition_type=stop_condition_type,
                previous_read_buffer_used=False,
                response_delay=response_delay,
            )
            self._worker_logger.debug(
                "Frame %s (%s)",
                "+".join(repr(f.data) for f in self._fragments),
                stop_condition_type.value if stop_condition_type is not None else "---",
            )
            self._worker_deliver_frame(frame)

            # Reset for next frame
            self._next_stop_condition_timeout_timestamp = None
            self._fragments = []

            if len(self._previous_buffer.data) > 0:
                kept = self._previous_buffer
            else:
                break

    def _worker_on_stop_condition_timeout(self, timestamp: float) -> None:
        """
        Called when a stop-condition timeout expires (Continuation/Total),
        producing a frame if we have accumulated fragments.
        """
        if len(self._fragments) > 0:
            if self._last_write_timestamp is None:
                response_delay = float("nan")
            else:
                response_delay = (
                    self._fragments[0].timestamp - self._last_write_timestamp
                )

            frame = Frame(
                data=fuse_fragments(self._fragments),
                first_fragment_timestamp=self._fragments[0].timestamp,
                stop_timestamp=timestamp,
                stop_condition_type=self._timeout_origin,
                previous_read_buffer_used=False,
                response_delay=response_delay,
            )
            self._worker_deliver_frame(frame)

        self._worker_reset_read()

    def _worker_reset_read(self) -> None:
        self._last_fragment_timestamp = None
        self._first_fragment_timestamp = None
        self._first_fragment = True
        self._last_write_timestamp = None
        self._fragments = []
        self._next_stop_condition_timeout_timestamp = None
        self._timeout_origin = StopConditionType.TIMEOUT

    def _worker_next_timeout_timestamp(self) -> float | None:
        next_timestamp = None

        for stop_condition in self._stop_conditions:
            if isinstance(stop_condition, Continuation):
                if self._last_fragment_timestamp is not None:
                    next_timestamp = nmin(
                        next_timestamp,
                        self._last_fragment_timestamp + stop_condition.continuation,
                    )
                    self._timeout_origin = stop_condition.type()
            elif isinstance(stop_condition, Total):
                if self._first_fragment_timestamp is not None:
                    next_timestamp = nmin(
                        next_timestamp,
                        self._first_fragment_timestamp + stop_condition.total,
                    )
                    self._timeout_origin = stop_condition.type()

        return next_timestamp

    # ┌───────────────────┐
    # │ Worker: main loop │
    # └───────────────────┘

    def _select_timeout(self) -> float | None:
        now = time.time()
        # Refresh next stop-condition timeout from current fragment state
        self._next_stop_condition_timeout_timestamp = (
            self._worker_next_timeout_timestamp()
        )

        # Compute pending read response deadline (only before first qualifying fragment)
        pr_deadline = None
        if self._pending_read is not None and self._first_fragment:
            pr_deadline = self._pending_read.response_deadline

        # Earliest deadline wins
        deadline = nmin(self._next_stop_condition_timeout_timestamp, pr_deadline)
        if deadline is None:
            select_timeout = None
        else:
            select_timeout = max(0.0, deadline - now)

        return select_timeout

    def _on_select_timeout(self, timestamp: float) -> None:
        # 1) pending read response timeout (before qualifying first fragment)
        if self._pending_read is not None and self._first_fragment:
            dl = self._pending_read.response_deadline
            if dl is not None and timestamp >= dl:
                self._worker_fail_pending_read_timeout()
                # do NOT return; stop-condition timeout might also be due

        # 2) stop-condition timeout (Continuation/Total)
        if (
            self._next_stop_condition_timeout_timestamp is not None
            and timestamp >= self._next_stop_condition_timeout_timestamp
        ):
            self._worker_on_stop_condition_timeout(timestamp)


class BytesAdapter(Adapter[bytes]):
    """
    Bytes adapter with stop-conditions

    Parameters
    ----------
    descriptor : Descriptor
    timeout : float | int | None | ...
    stop_conditions : StopCondition | [StopCondition] | ...
    alias : str
    auto_open : bool
    """

    def __init__(
        self,
        timeout: TimeoutType,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType,
        *,
        alias: str,
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            worker=BytesAdapterWorker(self),
            timeout=timeout,
            alias=alias,
            auto_open=auto_open,
        )
        # Default stop conditions
        self._initial_stop_conditions: list[StopCondition]
        if stop_conditions is ...:
            self._is_default_stop_condition = True
            self._initial_stop_conditions = self._default_stop_conditions()
        else:
            self._is_default_stop_condition = False
            if isinstance(stop_conditions, StopCondition):
                self._initial_stop_conditions = [stop_conditions]
            elif isinstance(stop_conditions, list):
                self._initial_stop_conditions = stop_conditions
            else:
                raise ValueError("Invalid stop_conditions")

        self.set_stop_conditions(self._initial_stop_conditions)

    def set_stop_conditions(
        self, stop_conditions: StopCondition | None | list[StopCondition]
    ) -> None:
        """
        Set adapter stop-conditions

        Parameters
        ----------
        stop_conditions : [StopCondition] or None
        """
        if isinstance(stop_conditions, list):
            lst = stop_conditions
        elif isinstance(stop_conditions, StopCondition):
            lst = [stop_conditions]
        elif stop_conditions is None:
            lst = []
        else:
            raise ValueError("Invalid stop_conditions")

        cmd = SetStopConditionsCommand(lst)
        self._worker.send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    @property
    def stop_conditions(self) -> list[StopCondition]:
        """
        Return the list of stop-conditions configured for this adapter
        """
        cmd = GetStopConditionsCommand()
        self._worker.send_command(cmd)
        stop_conditions = cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)
        return stop_conditions

    def set_default_stop_conditions(self, stop_conditions: list[StopCondition]) -> None:
        """
        Configure adapter default stop-condition. Stop-condition will only be set if none
        has been configured before

        Parameters
        ----------
        stop_conditions : [StopCondition]
        """
        if self._is_default_stop_condition:
            self.set_stop_conditions(stop_conditions)

    @staticmethod
    @abstractmethod
    def _default_stop_conditions() -> list[StopCondition]: ...
