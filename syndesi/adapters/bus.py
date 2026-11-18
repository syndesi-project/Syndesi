# File : bus.py
# Author : Sébastien Deriaz
# License : GPL
"""
Backend shared by the transaction buses (I2C, SPI)

On these buses nothing arrives unrequested : every write is a transaction, and what is
read during it is its answer. The transaction always runs on a bridge, the native buses
included (LinuxI2C, LinuxSPI) :

- the write submits it to the bridge without waiting, and returns its future : the
  engine completes the write when the bridge has done it, or fails it with the bridge
  error (a NACK, ...)
- the answer goes in a FragmentQueue, the simulated file descriptor the reactor watches,
  and becomes a frame like data received on any other adapter. It is queued after the
  write future is done, so that the engine finishes the write before reading its answer
"""

from __future__ import annotations

from abc import abstractmethod
from concurrent.futures import Future
from typing import TypeVar

from ..bridges.bridge import Bridge
from ..tools.errors import AdapterReadError, AdapterWriteError
from .engine import AdapterBackend, Descriptor
from .reader_thread import FragmentQueue
from .utils import Fragment, HasFileno, TimeoutType

DescriptorT = TypeVar("DescriptorT", bound=Descriptor)


class BusBackend(AdapterBackend[DescriptorT, bytes]):
    """
    Runs each write as a transaction on a bridge, see the module docstring

    A bus only implements transfer()

    Parameters
    ----------
    bridge : Bridge
    descriptor : Descriptor
    """

    def __init__(self, bridge: Bridge, descriptor: DescriptorT) -> None:
        super().__init__(descriptor)
        self.bridge = bridge
        self._answers: FragmentQueue[bytes] | None = None

    @abstractmethod
    def transfer(self, data: bytes) -> bytes:
        """
        Run one transaction and return what was read during it, b"" if nothing

        Runs on the bridge thread
        """

    def selectable(self) -> HasFileno | None:
        return None if self._answers is None else self._answers.selectable()

    def open(self, timeout: float | None) -> None:
        # The bus itself belongs to the bridge, shared with the other devices on it
        del timeout
        self._answers = FragmentQueue()

    def close(self) -> None:
        if self._answers is not None:
            self._answers.close()
            self._answers = None

    def write(self, data: bytes) -> Future[None]:
        if self._answers is None:
            raise AdapterWriteError(f"{self.descriptor} is not open")
        # The queue of this opening : an answer coming after a close is dropped with it
        answers = self._answers
        written: Future[None] = Future()

        def transaction_done(transaction: Future[bytes]) -> None:
            """Bridge thread : the write is done first, then its answer is handed over"""
            if transaction.cancelled():
                written.cancel()
                return
            error = transaction.exception()
            if error is not None:
                written.set_exception(error)
                return
            written.set_result(None)
            received = transaction.result()
            if received:
                answers.put(received)

        self.bridge.run(self.transfer, data).add_done_callback(transaction_done)
        return written

    def read(self, fragment_timestamp: float) -> Fragment[bytes]:
        if self._answers is None:
            raise AdapterReadError(f"{self.descriptor} is not open")
        return self._answers.read(fragment_timestamp)

    @property
    def default_timeout(self) -> TimeoutType:
        # The answer is already there when the write completes, only the reactor delays it
        return 2.0
