# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL
"""
Protocol base class. A protocol applies format of outgoing data and removes format
of incoming data
"""

from abc import abstractmethod
from dataclasses import dataclass
from types import EllipsisType
from typing import Callable, Generic, TypeVar

from syndesi.adapters.adapterworkerbase import (
    AdapterDisconnectedEvent,
    AdapterEvent,
    AdapterFrameEvent,
)
from syndesi.adapters.stop_conditions import StopCondition
from syndesi.component import Component, Event, Frame, ReadScope

from ..adapters.adapterbase import AdapterBase
from ..adapters.timeout import Timeout, TimeoutType
from ..tools.log_settings import LoggerAlias

ProtocolFrameT = TypeVar("ProtocolFrameT")

AdapterDataT = TypeVar("AdapterDataT")
# AdapterT = TypeVar("AdapterT", bound=AdapterBase[AdapterDataT])


@dataclass
class ProtocolFrame(Generic[ProtocolFrameT], Frame[ProtocolFrameT]):
    """
    Adapter signal containing received data
    """

    # payload: ProtocolFrameT

    # @abstractmethod
    def __str__(self) -> str:
        return f"ProtocolFrame({self.data!r})"


class ProtocolEvent(Event):
    """Protocol event"""


class ProtocolDisconnectedEvent(ProtocolEvent):
    """Protocol disconnected event"""


@dataclass
class ProtocolFrameEvent(ProtocolEvent, Generic[ProtocolFrameT]):
    """Protocol frame event"""

    frame: ProtocolFrame[ProtocolFrameT]


ProtocolTimeoutType = Timeout | None | EllipsisType


class Protocol(Generic[ProtocolFrameT, AdapterDataT], Component[ProtocolFrameT]):
    """
    Protocol base class
    """

    def __init__(
        self,
        adapter: AdapterBase[AdapterDataT],
        timeout: ProtocolTimeoutType = ...,
    ) -> None:
        super().__init__(LoggerAlias.PROTOCOL)
        self._adapter = adapter

        self._adapter.register_event_callback(self._on_event)

        if timeout is not ...:
            self._adapter.set_default_timeout(timeout)

        if timeout is ...:
            self._adapter.set_timeout(self._default_timeout())
        else:
            self._adapter.set_timeout(timeout)

        self._event_callbacks : list[Callable[[ProtocolEvent], None]] = []

    @abstractmethod
    def _default_timeout(self) -> Timeout | None:
        pass

    def _on_event(self, event: AdapterEvent) -> None:
        for callback in self._event_callbacks:
            output_event: ProtocolEvent | None = None
            if isinstance(event, AdapterDisconnectedEvent):
                output_event = ProtocolDisconnectedEvent()
            if isinstance(event, AdapterFrameEvent):
                output_event = ProtocolFrameEvent(
                    frame=self._adapter_to_protocol(event.frame)
                )

            if output_event is not None:
                callback(output_event)

    @abstractmethod
    def _adapter_to_protocol(
        self, adapter_frame: Frame[AdapterDataT]
    ) -> ProtocolFrame[ProtocolFrameT]: ...

    @abstractmethod
    def _protocol_to_adapter(
        self, protocol_payload: ProtocolFrameT
    ) -> AdapterDataT: ...

    def register_event_callback(self, event_callback: Callable[[ProtocolEvent], None]) -> None:
        self._event_callbacks.append(event_callback)

    def clear_event_callbacks(self) -> None:
        self._event_callbacks.clear()

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
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolFrame[ProtocolFrameT]:
        adapter_frame = await self._adapter.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return self._adapter_to_protocol(adapter_frame)

    def read_detailed(
        self,
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolFrame[ProtocolFrameT]:
        adapter_frame = self._adapter.read_detailed(
            timeout=timeout, scope=scope, stop_conditions=stop_conditions
        )
        return self._adapter_to_protocol(adapter_frame)

    # ==== read ====

    async def aread(
        self,
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolFrameT:
        frame = await self.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.data

    def read(
        self,
        timeout: TimeoutType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolFrameT:
        frame = self.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.data

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

    async def awrite(self, data: ProtocolFrameT) -> None:
        await self._adapter.awrite(self._protocol_to_adapter(data))

    def write(self, data: ProtocolFrameT) -> None:
        self._adapter.write(self._protocol_to_adapter(data))

    # ==== query_detailed ====

    async def aquery_detailed(
        self,
        payload: ProtocolFrameT,
        timeout: Timeout | None | EllipsisType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolFrame[ProtocolFrameT]:
        await self.aflush_read()
        await self.awrite(payload)
        return await self.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )

    def query_detailed(
        self,
        payload: ProtocolFrameT,
        timeout: Timeout | None | EllipsisType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolFrame[ProtocolFrameT]:
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
