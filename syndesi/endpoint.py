# File : endpoint.py
# Author : Sébastien Deriaz
# License : GPL
"""
Endpoints, the sync and async facades over an engine

An engine returns futures and knows neither sync nor async. An endpoint turns each of
them into a value : Endpoint waits with result(), AsyncEndpoint awaits
asyncio.wrap_future(). This is the only place of Syndesi where sync and async differ

Endpoints hold no logic and are never subclassed to add a transport or a protocol.
Adapters and protocols inherit from them and only add how their engine is built
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Future
from types import EllipsisType, TracebackType
from typing import Generic, Protocol, Self, TypeVar

from .adapters.engine import ReadScope
from .adapters.events import AdapterEvent
from .adapters.framer import ReadFrame
from .adapters.stop_conditions import StopCondition
from .adapters.utils import TimeoutParameterType, TimeoutType
from .tools.errors import AdapterOpenError

DataT = TypeVar("DataT")


class EndpointEngine(Protocol[DataT]):
    """
    What an endpoint needs from its engine, every method returns a future

    Provided by Engine for adapters and by ProtocolEngine for protocols
    """

    @property
    def is_open(self) -> bool:
        """True if communication with the target is open"""

    @property
    def timeout(self) -> TimeoutType:
        """Timeout used by the reads that don't specify one"""

    def open(self) -> Future[None]:
        """Open communication with the target"""

    def close(self) -> Future[None]:
        """Close communication with the target"""

    def set_timeout(self, timeout: TimeoutType) -> Future[None]:
        """Set the timeout used by the reads that don't specify one"""

    def write(self, data: DataT) -> Future[None]:
        """Write data to the target"""

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope = ReadScope.BUFFERED,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> Future[ReadFrame[DataT]]:
        """Read one frame"""

    def clear_buffer(self) -> Future[None]:
        """Drop the buffered frames and the frame being assembled"""

    def register_event_callback(self, callback: Callable[[AdapterEvent], None]) -> Future[None]:
        """Register an event callback"""

    def clear_event_callbacks(self) -> Future[None]:
        """Remove every event callback"""


class Endpoint(Generic[DataT]):
    """
    Sync facade, blocks on every engine future

    Parameters
    ----------
    engine : EndpointEngine
    auto_open : bool
        Open the engine before returning
    """

    def __init__(self, engine: EndpointEngine[DataT], *, auto_open: bool) -> None:
        self._engine = engine
        # Keeps the write and the read of a query together when threads share the endpoint
        self._lock = threading.Lock()

        if auto_open:
            self.open()

    @property
    def is_open(self) -> bool:
        """True if communication with the target is open"""
        return self._engine.is_open

    @property
    def timeout(self) -> TimeoutType:
        """Timeout used by the reads that don't specify one"""
        return self._engine.timeout

    def open(self) -> None:
        """Open communication with the target"""
        self._engine.open().result()

    def try_open(self) -> bool:
        """Open communication with the target, return False if it failed"""
        try:
            self.open()
        except AdapterOpenError:
            return False
        return True

    def close(self) -> None:
        """Close communication with the target"""
        self._engine.close().result()

    def set_timeout(self, timeout: TimeoutType) -> None:
        """Set the timeout used by the reads that don't specify one"""
        self._engine.set_timeout(timeout).result()

    def write(self, data: DataT) -> None:
        """Write data to the target"""
        with self._lock:
            self._engine.write(data).result()

    def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> ReadFrame[DataT]:
        """
        Read one frame

        Parameters
        ----------
        timeout : float, None or ...
            Time to wait for the target to respond, ``...`` for the endpoint timeout
        scope : ReadScope
        stop_conditions : StopCondition, list of StopCondition or ...
            Override the stop-conditions for this read only
        """
        with self._lock:
            return self._engine.read(timeout, ReadScope(scope), stop_conditions).result()

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> DataT:
        """Read one frame and return its data"""
        return self.read_detailed(timeout, scope, stop_conditions).data

    def query_detailed(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> ReadFrame[DataT]:
        """Write payload and read the frame received after it"""
        with self._lock:
            self._engine.write(payload).result()
            return self._engine.read(timeout, ReadScope.LAST_WRITE, stop_conditions).result()

    def query(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> DataT:
        """Write payload and return the data received after it"""
        return self.query_detailed(payload, timeout, stop_conditions).data

    def clear_read_buffer(self) -> None:
        """Drop the buffered frames and the frame being assembled"""
        with self._lock:
            self._engine.clear_buffer().result()

    def register_event_callback(self, callback: Callable[[AdapterEvent], None]) -> None:
        """Register an event callback. It runs on the reactor thread and must not block"""
        self._engine.register_event_callback(callback).result()

    def clear_event_callbacks(self) -> None:
        """Remove every event callback"""
        self._engine.clear_event_callbacks().result()

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class AsyncEndpoint(Generic[DataT]):
    """
    Async facade, awaits every engine future

    Parameters
    ----------
    engine : EndpointEngine
    auto_open : bool
        Submit an open without waiting for it, so no event loop is needed at
        construction. The engine runs commands in order : the open is done before any
        later operation, and if it failed the operations that need it raise its error
    """

    def __init__(self, engine: EndpointEngine[DataT], *, auto_open: bool) -> None:
        self._engine = engine
        # Keeps the write and the read of a query together when tasks share the endpoint
        self._lock = asyncio.Lock()

        if auto_open:
            engine.open()

    @property
    def is_open(self) -> bool:
        """True if communication with the target is open"""
        return self._engine.is_open

    @property
    def timeout(self) -> TimeoutType:
        """Timeout used by the reads that don't specify one"""
        return self._engine.timeout

    async def open(self) -> None:
        """Open communication with the target"""
        await asyncio.wrap_future(self._engine.open())

    async def try_open(self) -> bool:
        """Open communication with the target, return False if it failed"""
        try:
            await self.open()
        except AdapterOpenError:
            return False
        return True

    async def close(self) -> None:
        """Close communication with the target"""
        await asyncio.wrap_future(self._engine.close())

    async def set_timeout(self, timeout: TimeoutType) -> None:
        """Set the timeout used by the reads that don't specify one"""
        await asyncio.wrap_future(self._engine.set_timeout(timeout))

    async def write(self, data: DataT) -> None:
        """Write data to the target"""
        async with self._lock:
            await asyncio.wrap_future(self._engine.write(data))

    async def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> ReadFrame[DataT]:
        """
        Read one frame

        Cancelling the call (task.cancel(), asyncio.wait_for, ...) cancels the read,
        a frame arriving afterwards stays in the buffer for the next one

        Parameters
        ----------
        timeout : float, None or ...
            Time to wait for the target to respond, ``...`` for the endpoint timeout
        scope : ReadScope
        stop_conditions : StopCondition, list of StopCondition or ...
            Override the stop-conditions for this read only
        """
        async with self._lock:
            return await asyncio.wrap_future(
                self._engine.read(timeout, ReadScope(scope), stop_conditions)
            )

    async def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> DataT:
        """Read one frame and return its data"""
        return (await self.read_detailed(timeout, scope, stop_conditions)).data

    async def query_detailed(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> ReadFrame[DataT]:
        """Write payload and read the frame received after it"""
        async with self._lock:
            await asyncio.wrap_future(self._engine.write(payload))
            return await asyncio.wrap_future(
                self._engine.read(timeout, ReadScope.LAST_WRITE, stop_conditions)
            )

    async def query(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> DataT:
        """Write payload and return the data received after it"""
        return (await self.query_detailed(payload, timeout, stop_conditions)).data

    async def clear_read_buffer(self) -> None:
        """Drop the buffered frames and the frame being assembled"""
        async with self._lock:
            await asyncio.wrap_future(self._engine.clear_buffer())

    async def register_event_callback(self, callback: Callable[[AdapterEvent], None]) -> None:
        """Register an event callback. It runs on the reactor thread and must not block"""
        await asyncio.wrap_future(self._engine.register_event_callback(callback))

    async def clear_event_callbacks(self) -> None:
        """Remove every event callback"""
        await asyncio.wrap_future(self._engine.clear_event_callbacks())

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
