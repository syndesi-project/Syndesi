# File : adapter.py
# Author : Sébastien Deriaz
# License : GPL
"""
Adapters, the endpoints that talk to a device through a backend

An adapter only builds its engine from a backend and a framer, reading, writing and
waiting are inherited from the endpoint. A transport (IP, SerialPort, ...) is a
constructor that builds its backend and hands it to Adapter or AsyncAdapter

Adapter and AsyncAdapter are duplicated on purpose : they hold no logic, what they
share lives in _build_engine
"""

from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Callable
from types import EllipsisType, TracebackType
from typing import Any, Generic, Self, TypeVar

from syndesi.adapters.events import AdapterEvent

from ..tools.errors import AdapterConfigurationError
from .engine import AdapterBackend, AdapterEngine, Descriptor, ReadScope
from .framer import AdapterReadFrame, Framer, SupportsStopConditions
from .stop_conditions import StopCondition
from .utils import TimeoutParameterType, TimeoutType


def _as_list(
    stop_conditions: StopCondition | list[StopCondition],
) -> list[StopCondition]:
    if isinstance(stop_conditions, StopCondition):
        return [stop_conditions]
    return list(stop_conditions)


def _stop_engine(engine: AdapterEngine[Any, Any]) -> None:
    """Detach an engine from the reactor once its adapter is garbage collected"""
    engine.stop()


DescriptorT = TypeVar("DescriptorT", bound=Descriptor)
DataT = TypeVar("DataT")


class AdapterCommon(Generic[DescriptorT, DataT]):
    """
    What Adapter and AsyncAdapter share : the engine, and the read-only view on it

    Everything that waits lives in the two facades, this class never blocks
    """

    def __init__(
        self,
        backend: AdapterBackend[DescriptorT, DataT],
        framer: Framer[DataT],
        timeout: TimeoutParameterType,
        *,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType,
        alias: str,
    ) -> None:
        super().__init__()

        # Set on the framer before the engine exists, so the reactor never sees them
        # change. ``...`` keeps the ones the transport built its framer with
        if stop_conditions is not ...:
            if not isinstance(framer, SupportsStopConditions):
                raise AdapterConfigurationError(
                    f"{type(framer).__name__} doesn't use stop-conditions"
                )
            framer.set_stop_conditions(_as_list(stop_conditions))

        self._engine = AdapterEngine(
            backend, framer, timeout=timeout, alias=alias
        )
        self._is_default_timeout = timeout is ...
        self._is_default_stop_condition = stop_conditions is ...
        self._alias = alias

        # A free function, not self._cleanup : a bound method keeps a strong reference
        # on self, and the finalizer would never run
        weakref.finalize(self, _stop_engine, self._engine)

    @property
    def is_open(self) -> bool:
        """True if communication with the target is open"""
        return self._engine.is_open

    @property
    def descriptor(self) -> DescriptorT:
        """Parameters of the target (address, port, baudrate, ...)"""
        return self._engine.descriptor

    def __str__(self) -> str:
        return str(self.descriptor)

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def has_default_timeout(self) -> bool:
        """True if no timeout was given at construction, a protocol then sets its own"""
        return self._is_default_timeout

    @property
    def has_default_stop_conditions(self) -> bool:
        """True if no stop-conditions were given at construction"""
        return self._is_default_stop_condition

    @property
    def stop_conditions(self) -> list[StopCondition]:
        """Stop-conditions of the framer"""
        return self._engine.stop_conditions

    @property
    def timeout(self) -> TimeoutType:
        """Timeout used by the reads that don't specify one"""
        return self._engine.timeout

    @property
    def engine(self) -> AdapterEngine[DescriptorT, DataT]:
        """Engine of the adapter, the non-blocking side a protocol builds on"""
        return self._engine


class Adapter(Generic[DescriptorT, DataT], AdapterCommon[DescriptorT, DataT]):
    """
    Sync adapter

    Parameters
    ----------
    backend : AdapterBackend
    framer : Framer
    timeout : float, None or ...
        Time to wait for the target to respond, ``...`` for the backend default
    stop_conditions : StopCondition, list of StopCondition or ...
        When a frame is complete, ``...`` keeps the framer ones
    alias : str
    auto_open : bool
        Open on construction. Skipped while the descriptor is incomplete, a protocol
        may still have to set a default (port, ...)
    """

    def __init__(
        self,
        backend: AdapterBackend[DescriptorT, DataT],
        framer: Framer[DataT],
        timeout: TimeoutParameterType = ...,
        *,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._lock = threading.Lock()

        super().__init__(
            backend,
            framer,
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
        )

        # Sync waits for the open : a failed one is raised here rather than at the first
        # operation. Skipped while the descriptor is incomplete, a protocol may still
        # have to set a default (port, baudrate, ...)
        if auto_open and self.descriptor.is_initialized():
            self.open()

    def set_default_timeout(self, timeout: TimeoutType) -> None:
        """Set the timeout, unless one was given at construction"""
        if self._is_default_timeout:
            self.set_timeout(timeout)

    def open(self) -> None:
        """Open communication with the target"""
        self._engine.open().result()

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
    ) -> AdapterReadFrame[DataT]:
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
            return self._engine.read(
                timeout, ReadScope(scope), stop_conditions
            ).result()

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
    ) -> AdapterReadFrame[DataT]:
        """Write payload and read the frame received after it"""
        with self._lock:
            self._engine.write(payload).result()
            return self._engine.read(
                timeout, ReadScope.LAST_WRITE, stop_conditions
            ).result()

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
            self._engine.clear_buffer() .result()

    def register_event_callback(self, callback: Callable[[AdapterEvent], None]) -> None:
        """Register an event callback. It runs on the reactor thread and must not block"""
        self._engine.register_event_callback(callback).result()

    def clear_event_callbacks(self) -> None:
        """Remove every event callback"""
        self._engine.clear_event_callbacks().result()

    def set_stop_conditions(
        self, stop_conditions: StopCondition | list[StopCondition]
    ) -> None:
        """Set the stop-conditions of the framer"""
        self._engine.set_stop_conditions(_as_list(stop_conditions)).result()

    def set_default_stop_conditions(
        self, stop_conditions: StopCondition | list[StopCondition]
    ) -> None:
        """Set the stop-conditions, unless some were given at construction"""
        if self._is_default_stop_condition:
            self.set_stop_conditions(stop_conditions)

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

class AsyncAdapter(Generic[DescriptorT, DataT], AdapterCommon[DescriptorT, DataT]):
    """
    Async adapter, same parameters as Adapter

    auto_open submits the open without waiting for it, see AsyncEndpoint
    """

    def __init__(
        self,
        backend: AdapterBackend[DescriptorT, DataT],
        framer: Framer[DataT],
        timeout: TimeoutParameterType = ...,
        *,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._lock = asyncio.Lock()

        super().__init__(
            backend,
            framer,
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
        )

        # Async submits the open without waiting : no event loop is needed at
        # construction, and a failed open is raised by the first operation. Use
        # ``async with`` or ``await open()`` to wait for it
        if auto_open and self.descriptor.is_initialized():
            self._engine.open()

    async def set_stop_conditions(
        self, stop_conditions: StopCondition | list[StopCondition]
    ) -> None:
        """Set the stop-conditions of the framer"""
        await asyncio.wrap_future(
            self._engine.set_stop_conditions(_as_list(stop_conditions))
        )

    async def set_default_timeout(self, timeout: TimeoutType) -> None:
        """Set the timeout, unless one was given at construction"""
        if self._is_default_timeout:
            await self.set_timeout(timeout)

    async def set_default_stop_conditions(
        self, stop_conditions: StopCondition | list[StopCondition]
    ) -> None:
        """Set the stop-conditions, unless some were given at construction"""
        if self._is_default_stop_condition:
            await self.set_stop_conditions(stop_conditions)

    async def open(self) -> None:
        """Open communication with the target"""
        await asyncio.wrap_future(self._engine.open())

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
    ) -> AdapterReadFrame[DataT]:
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
    ) -> AdapterReadFrame[DataT]:
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

    async def register_event_callback(
        self, callback: Callable[[AdapterEvent], None]
    ) -> None:
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
