# File : component.py
# Author : Sébastien Deriaz
# License : GPL
"""
Component is the base of the main syndesi classes : Adapters, Protocols and Drivers
"""

import logging
from abc import ABC, abstractmethod
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import StrEnum
from types import EllipsisType
from typing import Generic, TypeVar

from syndesi.adapters.stop_conditions import Fragment, StopCondition, StopConditionType
from syndesi.adapters.timeout import Timeout
from syndesi.tools.errors import AdapterOpenError, WorkerThreadError

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


T = TypeVar("T")


@dataclass
class Frame(Generic[T]):
    """
    Adapter signal containing received data
    """

    stop_timestamp: float | None
    stop_condition_type: StopConditionType | None  # None if it's a response timeout
    previous_read_buffer_used: bool
    response_delay: float | None

    @abstractmethod
    def get_payload(self) -> T:
        """
        Return frame payload
        """

    @abstractmethod
    def __str__(self) -> str: ...


@dataclass
class AdapterFrame(Frame[bytes]):
    """
    Adapter frame
    """

    fragments: list[Fragment] = field(default_factory=lambda: [])

    def get_payload(self) -> bytes:
        """
        Return all fragement data as a combined bytes array
        """
        return b"".join([f.data for f in self.fragments])

    def __str__(self) -> str:
        return f"AdapterFrame({self.get_payload()!r})"


R = TypeVar("R")


class ThreadCommand(Future[R]):
    """
    Command object completed by the worker thread.

    - .future is a concurrent.futures.Future => compatible with asyncio.wrap_future
    - .result() raises WorkerThreadError on command-timeout (worker not responding),
      not on device read timeouts (those are handled in the worker and surfaced as Adapter* errors).
    """

    def result(self, timeout: float | None = None) -> R:
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


class Component(ABC, Generic[T]):
    """Syndesi Component

    A Component is the elementary class of Syndesi. It is the base
    of all classes the user will be using
    """

    def __init__(self, logger_alias: LoggerAlias) -> None:
        super().__init__()
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
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[T]:
        """Asynchronously read data from the component and return a Frame object"""

    @abstractmethod
    def read_detailed(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[T]:
        """Read data from the component and return a Frame object"""

    # ==== read ====

    @abstractmethod
    async def aread(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> T:
        """Asynchronously read data from the component"""

    @abstractmethod
    def read(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> T:
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
    async def awrite(self, data: T) -> None:
        """Asynchronously write data to the component"""

    @abstractmethod
    def write(self, data: T) -> None:
        """Synchronously write data to the component"""

    # ==== query_detailed ====

    @abstractmethod
    async def aquery_detailed(
        self,
        payload: T,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[T]:
        """
        Asynchronously query the component and return a Frame object
        """

    @abstractmethod
    def query_detailed(
        self,
        payload: T,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> Frame[T]:
        """
        Synchronously query the component and return a Frame object
        """

    # ==== query ====

    async def aquery(
        self,
        payload: T,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> T:
        """Asynchronously query the component"""
        output_frame = await self.aquery_detailed(
            payload=payload,
            timeout=timeout,
            stop_conditions=stop_conditions,
            scope=scope,
        )
        return output_frame.get_payload()

    def query(
        self,
        payload: T,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> T:
        """Query the component"""
        output_frame = self.query_detailed(
            payload=payload,
            timeout=timeout,
            stop_conditions=stop_conditions,
            scope=scope,
        )
        return output_frame.get_payload()

    # ==== Other ====

    @abstractmethod
    def is_open(self) -> bool:
        """Return True if the component is open"""
