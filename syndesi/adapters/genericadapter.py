# File : adapter.py
# Author : Sébastien Deriaz
# License : GPL
"""
Adapter and AdapterWorker class descriptions.

The Adapter class is used with generic data type and no stop-conditions
"""
from __future__ import annotations

import time
from abc import ABC
from typing import Generic, TypeVar

from syndesi.adapters.utils import Fragment
from syndesi.component import ReadFrame

from .adapter import Adapter
from .adapterworker import AdapterWorker
from .utils import TimeoutType

DataT = TypeVar("DataT")

class GenericAdapterWorker(Generic[DataT], AdapterWorker[DataT], ABC):
    """
    Adapter worker with bytes and fragment support
    """

    # ┌──────────────────────────────┐
    # │ Worker: fragment/frame logic │
    # └──────────────────────────────┘

    def _worker_manage_fragment(self, fragment: Fragment[DataT]) -> None:
        # pylint: disable=too-many-branches, too-many-statements

        if self._last_write_timestamp is not None:
            response_delay = fragment.timestamp - self._last_write_timestamp
        else:
            response_delay = float("nan")

        self._worker_logger.debug("New fragment %+.3f %s", response_delay, fragment)

        stop_timestamp = fragment.timestamp

        frame: ReadFrame[DataT] = ReadFrame(
            data=fragment.data,
            id=self._next_frame_id(),
            stop_timestamp=stop_timestamp,
            previous_read_buffer_used=False,
            response_delay=response_delay,
        )
        self._worker_logger.debug("Frame %s", repr(frame.data))
        self._worker_deliver_frame(frame)

    # ┌───────────────────┐
    # │ Worker: main loop │
    # └───────────────────┘

    def _select_timeout(self) -> float | None:
        now = time.time()
        # Refresh next stop-condition timeout from current fragment state
        select_timeout = None
        if (
            self._pending_read is not None
            and self._pending_read.response_deadline is not None
        ):
            select_timeout = max(0.0, self._pending_read.response_deadline - now)

        return select_timeout

    def _on_select_timeout(self, timestamp: float) -> None:
        if self._pending_read is not None:
            dl = self._pending_read.response_deadline
            if dl is not None and timestamp >= dl:
                self._worker_fail_pending_read_timeout()

class GenericAdapter(Generic[DataT], Adapter[DataT]):
    """
    Adapter with generic data and no stop-conditions

    Parameters
    ----------
    descriptor : Descriptor
    timeout : float | int | None | ...
    alias : str
    auto_open : bool
    """

    def __init__(
        self,
        *,
        timeout: TimeoutType,
        alias: str,
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            worker=GenericAdapterWorker(self),
            timeout=timeout,
            alias=alias,
            auto_open=auto_open,
        )
