# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL
"""
Protocol base class. A protocol applies format of outgoing data and removes format
of incoming data
"""

from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from types import EllipsisType
from typing import Generic, TypeVar

from syndesi.adapters.adapter_worker import AdapterEvent
from syndesi.adapters.stop_conditions import StopCondition
from syndesi.component import AdapterFrame, Component, Event, Frame, ReadScope

from ..adapters.adapter import Adapter
from ..adapters.auto import auto_adapter
from ..adapters.timeout import Timeout
from ..tools.log_settings import LoggerAlias

T = TypeVar("T")


@dataclass
class ProtocolFrame(Frame[T]):
    """
    Adapter signal containing received data
    """

    payload: T

    def get_payload(self) -> T:
        return self.payload

    @abstractmethod
    def __str__(self) -> str:
        return f"ProtocolFrame({self.payload!r})"


class ProtocolEvent(Event):
    """Protocol event"""


class ProtocolDisconnectedEvent(ProtocolEvent):
    """Protocol disconnected event"""


@dataclass
class ProtocolFrameEvent(ProtocolEvent, Generic[T]):
    """Protocol frame event"""

    frame: ProtocolFrame[T]


ProtocolTimeoutType = Timeout | None | EllipsisType


class Protocol(Component[T], Generic[T]):
    """
    Protocol base class
    """

    def __init__(
        self,
        adapter: Adapter,
        timeout: ProtocolTimeoutType = ...,
        event_callback: Callable[[ProtocolEvent], None] | None = None,
    ) -> None:
        super().__init__(LoggerAlias.PROTOCOL)
        # TODO : Convert the callable from AdapterSignal to ProtocolSignal or something similar
        self._adapter = auto_adapter(adapter)
        self._event_callback = event_callback

        self._adapter.set_event_callback(self._on_event)

        if timeout is not ...:
            self._adapter.set_default_timeout(timeout)

        if timeout is ...:
            self._adapter.set_timeout(self._default_timeout())
        else:
            self._adapter.set_timeout(timeout)

    @abstractmethod
    def _default_timeout(self) -> Timeout | None:
        pass

    @abstractmethod
    def _on_event(self, event: AdapterEvent) -> None:
        pass

    @abstractmethod
    def _adapter_to_protocol(self, adapter_frame: AdapterFrame) -> ProtocolFrame[T]: ...

    @abstractmethod
    def _protocol_to_adapter(self, protocol_payload: T) -> bytes: ...

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    # ==== open ====

    def open(self) -> None:
        """
        Open protocol communication with the target (blocking)
        """
        self._adapter.open()

    async def aopen(self) -> None:
        """
        Open protocol communication with the target (async)
        """
        await self._adapter.aopen()

    # ==== close ====

    def close(self) -> None:
        """
        Close protocol communication with the target (blocking)
        """
        self._adapter.close()

    async def aclose(self) -> None:
        """
        Close protocol communication with the target (async)
        """
        await self._adapter.aclose()

    # ==== read_detailed ====

    async def aread_detailed(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> ProtocolFrame[T]:
        adapter_frame = await self._adapter.aread_detailed()
        return self._adapter_to_protocol(adapter_frame)

    def read_detailed(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> ProtocolFrame[T]:
        adapter_frame = self._adapter.read_detailed()
        return self._adapter_to_protocol(adapter_frame)

    # ==== read ====

    async def aread(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> T:
        frame = await self.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.get_payload()

    def read(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> T:
        frame = self.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.get_payload()

    # ==== flush_read ====

    def flush_read(self) -> None:
        """
        Clear read buffer (blocking)
        """
        self._adapter.flush_read()

    async def aflush_read(self) -> None:
        """
        Clear read buffer (async)
        """
        await self._adapter.aflush_read()

    # ==== write ====

    async def awrite(self, data: T) -> None:
        await self._adapter.awrite(self._protocol_to_adapter(data))

    def write(self, data: T) -> None:
        self._adapter.write(self._protocol_to_adapter(data))

    # ==== query_detailed ====

    async def aquery_detailed(
        self,
        payload: T,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> ProtocolFrame[T]:
        await self.aflush_read()
        await self.awrite(payload)
        return await self.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )

    def query_detailed(
        self,
        payload: T,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> ProtocolFrame[T]:
        self.flush_read()
        self.write(payload)
        return self.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )

    # ==== Other ====

    def is_open(self) -> bool:
        """
        Return True if the protocol is opened
        """
        return self._adapter.is_open()
