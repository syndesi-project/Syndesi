# File : reader_thread.py
# Author : Sébastien Deriaz
# License : GPL
"""
Makes data coming from another thread selectable

The reactor only watches file descriptors. A transport that has none (pyvisa, pyserial
on Windows, anything provided by a bridge) gets its data from another thread, which puts
it in a FragmentQueue : the queue simulates the file descriptor with a socketpair, so
that the reactor sees that data like any other

The fragment timestamp is taken when the data is put in the queue, not when the reactor
picks it up : the stop-conditions work on those timestamps, so a queueing delay must not
end up in them
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
    """Data received from the transport, or the error that ended it"""

    data: DataT | None
    timestamp: float
    error: AdapterError | None = None


class FragmentQueue(Generic[DataT]):
    """
    A simulated file descriptor : any thread puts data in, the reactor reads fragments out

    put() and put_error() are thread safe. selectable() and read() are the two
    AdapterBackend methods of the same name, a backend only forwards them
    """

    QUEUE_MAX = 1024

    def __init__(self) -> None:
        self._logger = logging.getLogger(LoggerAlias.ADAPTER.value)
        self._items: queue.Queue[_Item[DataT]] = queue.Queue(maxsize=self.QUEUE_MAX)
        self._wakeup_r, self._wakeup_w = socket.socketpair()
        self._wakeup_r.setblocking(False)
        self._wakeup_w.setblocking(False)

    def put(self, data: DataT) -> None:
        """Hand data to the reactor, timestamped now"""
        self._put(_Item(data, time.time()))

    def put_error(self, error: AdapterError) -> None:
        """Hand an error to the reactor, the adapter closes when it reads it"""
        self._put(_Item(None, time.time(), error=error))

    def close(self) -> None:
        """Release the socketpair. Data put afterwards is dropped"""
        self._wakeup_r.close()
        self._wakeup_w.close()

    def selectable(self) -> HasFileno:
        """End of the socketpair the reactor watches"""
        return self._wakeup_r

    def read(self, fragment_timestamp: float) -> Fragment[DataT]:
        """
        Return the next fragment

        fragment_timestamp is ignored : the timestamp taken by put() is closer to the
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
            raise AdapterReadError("Fragment queue reported data but had none") from e

        if item.error is not None:
            raise item.error
        if item.data is None:
            raise AdapterReadError("Fragment queue produced no data")
        return Fragment(item.data, item.timestamp)

    def _put(self, item: _Item[DataT]) -> None:
        """Queue one item and wake the reactor, one byte per item to stay in step"""
        try:
            self._items.put(item, block=False)
        except queue.Full:
            self._logger.warning("Fragment queue is full, dropping a fragment")
            return
        try:
            self._wakeup_w.send(_WAKEUP_BYTE)
        except OSError:
            pass


class ThreadedReader(Generic[DataT]):
    """
    Runs a blocking read in a thread and puts its results in a FragmentQueue

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

    def __init__(self, read_once: Callable[[], DataT | None], name: str) -> None:
        self._read_once = read_once
        self._queue: FragmentQueue[DataT] = FragmentQueue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        """Start reading"""
        self._thread.start()

    def stop(self) -> None:
        """Stop reading and release the queue. The reader cannot be restarted"""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self.JOIN_TIMEOUT)
        self._queue.close()

    def selectable(self) -> HasFileno | None:
        """See FragmentQueue.selectable"""
        return self._queue.selectable()

    def read(self, fragment_timestamp: float) -> Fragment[DataT]:
        """See FragmentQueue.read"""
        return self._queue.read(fragment_timestamp)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                data = self._read_once()
            except AdapterError as e:
                self._queue.put_error(e)
                return
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._queue.put_error(AdapterReadError(str(e)))
                return

            if data is not None:
                self._queue.put(data)
