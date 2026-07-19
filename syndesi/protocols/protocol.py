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
from typing import Any, Generic, TypeVar

from syndesi.adapters.adapterworker import (
    AdapterClosedEvent,
    AdapterEvent,
    AdapterFrameEvent,
)
from syndesi.adapters.stop_conditions import StopCondition
from syndesi.adapters.utils import TimeoutParameterType
from syndesi.component import Component, Event, ReadFrame, ReadScope

from ..adapters.adapter import Adapter
from ..adapters.bytesadapter import BytesAdapter
from ..tools.log_settings import LoggerAlias

ProtocolFrameT = TypeVar("ProtocolFrameT")

AdapterT = TypeVar("AdapterT", bound=Adapter[Any])

@dataclass
class ProtocolReadFrame(Generic[ProtocolFrameT], ReadFrame[ProtocolFrameT]):
    """Adapter signal containing received data"""

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

    frame: ProtocolReadFrame[ProtocolFrameT]

class Protocol(Generic[AdapterT, ProtocolFrameT], Component[ProtocolFrameT]):
    """
    Base class for protocol layers.

    The first generic parameter describes the adapter type expected by the
    protocol (for example ``BytesAdapter`` or a more specific adapter class).
    The second parameter describes the protocol payload type.
    """

    def __init__(
        self,
        adapter: AdapterT,
        timeout: TimeoutParameterType = ...,
    ) -> None:
        super().__init__(LoggerAlias.PROTOCOL)
        self.adapter = adapter # adapter is public as it is used in ui

        self._frame_id = 0

        self.adapter.register_event_callback(self._on_event)

        if timeout is not ...:
            self.adapter.set_default_timeout(timeout)

        if timeout is ...:
            self.adapter.set_timeout(self.default_timeout())
        else:
            self.adapter.set_timeout(timeout)

        self._event_callbacks : list[Callable[[ProtocolEvent], None]] = []

    def _next_frame_id(self) -> int:
        output = self._frame_id
        self._frame_id += 1
        return output

    @staticmethod
    @abstractmethod
    def default_timeout() -> float | None:
        """Default timeout"""

    def _on_event(self, event: AdapterEvent) -> None:
        for callback in self._event_callbacks:
            output_event: ProtocolEvent | None = None
            if isinstance(event, AdapterClosedEvent):
                output_event = ProtocolDisconnectedEvent()
            if isinstance(event, AdapterFrameEvent):
                output_event = ProtocolFrameEvent(
                    frame=self._adapter_to_protocol(event.frame)
                )

            if output_event is not None:
                callback(output_event)

    @abstractmethod
    def _adapter_to_protocol(
        self, adapter_frame: ReadFrame[Any]
    ) -> ProtocolReadFrame[ProtocolFrameT]: ...

    @abstractmethod
    def _protocol_to_adapter(
        self, protocol_payload: ProtocolFrameT
    ) -> Any: ...

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
        self.adapter.open()

    async def aopen(self) -> None:
        """
        Open protocol communication with the target (async)
        """
        await self.adapter.aopen()

    # ==== close ====

    def close(self) -> None:
        """
        Close protocol communication with the target (blocking)
        """
        self.adapter.close()

    async def aclose(self) -> None:
        """
        Close protocol communication with the target (async)
        """
        await self.adapter.aclose()

    # ==== read_detailed ====

    async def aread_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
        adapter_frame = await self.adapter.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return self._adapter_to_protocol(adapter_frame)

    def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
        adapter_frame = self.adapter.read_detailed(
            timeout=timeout, scope=scope, stop_conditions=stop_conditions
        )
        return self._adapter_to_protocol(adapter_frame)

    # ==== read ====

    async def aread(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolFrameT:
        frame = await self.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.data

    def read(
        self,
        timeout: TimeoutParameterType = ...,
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
        self.adapter.flush_read()

    async def aflush_read(self) -> None:
        """
        Clear read buffer (async)
        """
        await self.adapter.aflush_read()

    # ==== write ====

    async def awrite(self, data: ProtocolFrameT) -> None:
        await self.adapter.awrite(self._protocol_to_adapter(data))

    def write(self, data: ProtocolFrameT) -> None:
        self.adapter.write(self._protocol_to_adapter(data))


class BytesProtocol(Protocol[BytesAdapter, ProtocolFrameT], Generic[ProtocolFrameT]):
    """Convenience base class for protocols that operate on byte-oriented adapters."""

    pass

    # ==== query_detailed ====

    async def aquery_detailed(
        self,
        payload: ProtocolFrameT,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
        await self.aflush_read()
        await self.awrite(payload)
        return await self.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )

    def query_detailed(
        self,
        payload: ProtocolFrameT,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
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
        return self.adapter.is_open()
