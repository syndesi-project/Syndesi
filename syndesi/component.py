# File : component.py
# Author : Sébastien Deriaz
# License : GPL
"""
Component is the base of the main syndesi classes : Adapters, Protocols and Drivers
"""

import logging
from abc import ABC, abstractmethod
from concurrent.futures import Future
from dataclasses import dataclass
from enum import StrEnum
from types import EllipsisType
from typing import Any, Callable, Generic, TypeVar

from syndesi.adapters.stop_conditions import StopConditionType
from syndesi.adapters.timeout import Timeout, TimeoutType
from syndesi.tools.errors import AdapterOpenError, AdapterReadError, WorkerThreadError

from .tools.log_settings import LoggerAlias


class Event:
    """Generic event, used to move information asynchronously from the adapter worker thread"""


class Descriptor(ABC):
    """
    Descriptor base class. A descriptor is a string to define the main parameters
    of an adapter (ip address, port, baudrate, etc...)
    """

    DETECTION_PATTERN = ""

    def __init__(self) -> None:
        return None

    @staticmethod
    @abstractmethod
    def from_string(string: str) -> "Descriptor":
        """
        Create a Descriptor class from a string
        """

    @abstractmethod
    def is_initialized(self) -> bool:
        """Return True if the descriptor is initialized"""

DataT = TypeVar("DataT")

@dataclass
class Frame(Generic[DataT]):
    """
    A complete frame of data
    """

    data: DataT
    stop_timestamp: float
    previous_read_buffer_used: bool
    response_delay: float
    stop_condition_type: StopConditionType = StopConditionType.FRAGMENT
    first_fragment_timestamp: float = float("nan")

    def __str__(self) -> str:
        return f"Frame({self.data})"


class EmptyFrame(AdapterReadError):
    """A special exception to indicate an empty frame as return"""


ThreadReturn = TypeVar("ThreadReturn")


class ThreadCommand(Future[ThreadReturn]):
    """
    Command object completed by the worker thread.

    - .future is a concurrent.futures.Future => compatible with asyncio.wrap_future
    - .result() raises WorkerThreadError on command-timeout (worker not responding),
      not on device read timeouts (those are handled in the worker and surfaced as Adapter* errors).
    """

    def result(self, timeout: float | None = None) -> ThreadReturn:
        """
        Return the result of the thread command
        """
        try:
            return super().result(timeout=timeout)
        except TimeoutError:
            raise WorkerThreadError(
                f"No response from worker thread to {type(self).__name__} within {timeout}s"
            ) from None


class ReadScope(StrEnum):
    """
    Read scope

    NEXT : Only read data after the start of the read() call
    BUFFERED : Return any data that was present before the read() call
    """

    NEXT = "next"
    BUFFERED = "buffered"


class Component(ABC, Generic[DataT]):
    """Syndesi Component

    A Component is the elementary class of Syndesi. It is the base
    of all classes the user will be using
    """

    def __init__(self, logger_alias: LoggerAlias) -> None:
        self._logger = logging.getLogger(logger_alias.value)

    # ==== open ====

    @abstractmethod
    def open(self) -> None:
        """Open the component"""

    @abstractmethod
    async def aopen(self) -> None:
        """Asynchronously open the component"""

    # ==== try_open ====

    async def atry_open(self) -> bool:
        """
        Async try to open communication with the device
        Return True if sucessful and False otherwise

        Returns
        -------
        success : bool
        """
        try:
            await self.aopen()
            return True
        except AdapterOpenError:
            return False

    def try_open(self) -> bool:
        """
        Try to open communication with the device
        Return True if sucessful and False otherwise

        Returns
        -------
        success : bool
        """
        try:
            self.open()
        except AdapterOpenError:
            return False
        return True

    # ==== close ====

    @abstractmethod
    def close(self) -> None:
        """Close the component"""

    @abstractmethod
    async def aclose(self) -> None:
        """Asynchronously close the component"""

    # ==== read_detailed ====

    @abstractmethod
    async def aread_detailed(
        self,
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[DataT]:
        """Asynchronously read data from the component and return a Frame object"""

    @abstractmethod
    def read_detailed(
        self,
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[DataT]:
        """Read data from the component and return a Frame object"""

    # ==== read ====

    @abstractmethod
    async def aread(
        self,
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> DataT:
        """Asynchronously read data from the component"""

    @abstractmethod
    def read(
        self,
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> DataT:
        """Read data from the component"""

    # ==== flush_read ====

    @abstractmethod
    async def aflush_read(self) -> None:
        """Clear input buffer"""

    @abstractmethod
    def flush_read(self) -> None:
        """Clear input buffer"""

    # ==== write ====

    @abstractmethod
    async def awrite(self, data: DataT) -> None:
        """Asynchronously write data to the component"""

    @abstractmethod
    def write(self, data: DataT) -> None:
        """Synchronously write data to the component"""

    # ==== query_detailed ====

    @abstractmethod
    async def aquery_detailed(
        self,
        payload: DataT,
        timeout: Timeout | None | EllipsisType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[DataT]:
        """
        Asynchronously query the component and return a Frame object
        """

    @abstractmethod
    def query_detailed(
        self,
        payload: DataT,
        timeout: Timeout | None | EllipsisType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[DataT]:
        """
        Synchronously query the component and return a Frame object
        """

    # ==== query ====

    async def aquery(
        self,
        payload: DataT,
        timeout: Timeout | None | EllipsisType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> DataT:
        """Asynchronously query the component"""
        output_frame = await self.aquery_detailed(
            payload=payload,
            timeout=timeout,
            scope=scope,
        )
        return output_frame.data

    def query(
        self,
        payload: DataT,
        timeout: Timeout | None | EllipsisType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> DataT:
        """Query the component"""
        output_frame = self.query_detailed(
            payload=payload,
            timeout=timeout,
            scope=scope,
        )
        return output_frame.data

    # ==== Other ====

    @abstractmethod
    def is_open(self) -> bool:
        """Return True if the component is open"""

    @abstractmethod
    def register_event_callback(self, event_callback: Callable[[Any], None]) -> None:
        """
        Register an event callback
        
        Parameters
        ----------
        event_callback : Callable[[Event], None]
        """

    @abstractmethod
    def clear_event_callbacks(self) -> None:
        """Remove all event callbacks"""
