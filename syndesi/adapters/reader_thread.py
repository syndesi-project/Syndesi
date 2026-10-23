# File : reader_thread.py
# Author : Sébastien Deriaz
# License : GPL
"""
Makes a blocking transport selectable

Some transports cannot be watched by select() : pyvisa exposes no file descriptor at
all, and pyserial has no usable fileno() on Windows. A backend for one of those runs
its reads in a thread and wakes the reactor through a socketpair, which is the only
place in Syndesi where a thread per adapter still exists

The fragment timestamp is taken in the thread, right after the data comes in, not when
the reactor picks it up : the stop-conditions work on those timestamps, so a queueing
delay must not end up in them
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from ..tools.errors import AdapterError, AdapterReadError
from ..tools.log_settings import LoggerAlias
from .utils import Fragment, HasFileno

DataT = TypeVar("DataT")

_WAKEUP_BYTE = b"\x00"


@dataclass
class _Item(Generic[DataT]):
    """One read from the transport, or the error that ended it"""

    data: DataT | None
    timestamp: float
    error: AdapterError | None = None


class ThreadedReader(Generic[DataT]):
    """
    Runs a blocking read in a thread and makes its results selectable

    Parameters
    ----------
    read_once : callable
        Blocking read. Returns the data it got, or None if it got nothing this round.
        It must return regularly (a short transport timeout) so that stop() is seen.
        An AdapterError it raises is handed to the reactor on the next read()
    name : str
        Thread name, for debugging
    """

    JOIN_TIMEOUT = 1.0
    QUEUE_MAX = 1024

    def __init__(self, read_once: Callable[[], DataT | None], name: str) -> None:
        self._read_once = read_once
        self._logger = logging.getLogger(LoggerAlias.ADAPTER.value)

        self._items: queue.Queue[_Item[DataT]] = queue.Queue(maxsize=self.QUEUE_MAX)
        self._wakeup_r, self._wakeup_w = socket.socketpair()
        self._wakeup_r.setblocking(False)
        self._wakeup_w.setblocking(False)

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        """Start reading"""
        self._thread.start()

    def stop(self) -> None:
        """Stop reading and release the socketpair. The reader cannot be restarted"""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self.JOIN_TIMEOUT)
        self._wakeup_r.close()
        self._wakeup_w.close()

    def selectable(self) -> HasFileno | None:
        """End of the socketpair the reactor watches"""
        return self._wakeup_r

    def read(self, fragment_timestamp: float) -> Fragment[DataT]:
        """
        Return the next fragment the thread produced

        fragment_timestamp is ignored : the thread's own timestamp is closer to the
        data, and that is the one the stop-conditions must see
        """
        del fragment_timestamp
        try:
            self._wakeup_r.recv(1)
        except OSError:
            pass

        try:
            item = self._items.get(block=False)
        except queue.Empty as e:
            raise AdapterReadError("Reader thread reported data but had none") from e

        if item.error is not None:
            raise item.error
        if item.data is None:
            raise AdapterReadError("Reader thread produced no data")
        return Fragment(item.data, item.timestamp)

    # ┌────────┐
    # │ Thread │
    # └────────┘

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                data = self._read_once()
            except AdapterError as e:
                self._put(_Item(None, time.time(), error=e))
                return
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._put(_Item(None, time.time(), error=AdapterReadError(str(e))))
                return

            if data is not None:
                self._put(_Item(data, time.time()))

    def _put(self, item: _Item[DataT]) -> None:
        """Queue one item and wake the reactor, one byte per item to stay in step"""
        try:
            self._items.put(item, block=False)
        except queue.Full:
            self._logger.warning("Reader thread queue is full, dropping a fragment")
            return
        try:
            self._wakeup_w.send(_WAKEUP_BYTE)
        except OSError:
            pass
