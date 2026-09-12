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
import weakref
from types import EllipsisType
from typing import Generic, TypeVar, cast

from ..endpoint import AsyncEndpoint, Endpoint
from ..tools.errors import AdapterConfigurationError
from .backend import AdapterBackend, Descriptor
from .engine import Engine
from .framer import Framer, SupportsStopConditions
from .stop_conditions import StopCondition
from .utils import TimeoutParameterType, TimeoutType

DescriptorT = TypeVar("DescriptorT", bound=Descriptor)
DataT = TypeVar("DataT")


def _as_list(stop_conditions: StopCondition | list[StopCondition]) -> list[StopCondition]:
    if isinstance(stop_conditions, StopCondition):
        return [stop_conditions]
    return list(stop_conditions)


def _build_engine(
    backend: AdapterBackend[DescriptorT, DataT],
    framer: Framer[DataT],
    timeout: TimeoutParameterType,
    stop_conditions: StopCondition | list[StopCondition] | EllipsisType,
    alias: str,
) -> Engine[DescriptorT, DataT]:
    """
    Build the engine of an adapter

    ``...`` keeps the backend timeout and the framer stop-conditions. The user
    stop-conditions are set on the framer before the engine exists, so the reactor
    never sees them change
    """
    if stop_conditions is not ...:
        if not isinstance(framer, SupportsStopConditions):
            raise AdapterConfigurationError(
                f"{type(framer).__name__} doesn't use stop-conditions"
            )
        framer.stop_conditions = _as_list(stop_conditions)

    return Engine(
        backend,
        framer,
        timeout=backend.default_timeout if timeout is ... else timeout,
        alias=alias,
    )


class Adapter(Endpoint[DataT], Generic[DescriptorT, DataT]):
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
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._descriptor = backend.descriptor
        self._is_default_timeout = timeout is ...
        self._is_default_stop_condition = stop_conditions is ...

        engine = _build_engine(backend, framer, timeout, stop_conditions, alias)
        # The reactor holds the engine, stop it once the adapter is unreachable
        weakref.finalize(self, engine.stop)
        super().__init__(engine, auto_open=auto_open and backend.descriptor.is_initialized())

    def __str__(self) -> str:
        return str(self._descriptor)

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def engine(self) -> Engine[DescriptorT, DataT]:
        """
        Non-blocking side of the adapter, every method returns a future

        Neither sync nor async, protocols sit on it
        """
        return cast("Engine[DescriptorT, DataT]", self._engine)

    @property
    def descriptor(self) -> DescriptorT:
        """Parameters of the target (address, port, baudrate, ...)"""
        return self._descriptor

    @property
    def has_default_timeout(self) -> bool:
        """True if no timeout was given at construction, a protocol then sets its own"""
        return self._is_default_timeout

    @property
    def stop_conditions(self) -> list[StopCondition]:
        """Stop-conditions of the framer"""
        return self.engine.stop_conditions

    def set_stop_conditions(self, stop_conditions: StopCondition | list[StopCondition]) -> None:
        """Set the stop-conditions of the framer"""
        self.engine.set_stop_conditions(_as_list(stop_conditions)).result()

    def set_default_timeout(self, timeout: TimeoutType) -> None:
        """Set the timeout, unless one was given at construction"""
        if self._is_default_timeout:
            self.set_timeout(timeout)

    def set_default_stop_conditions(
        self, stop_conditions: StopCondition | list[StopCondition]
    ) -> None:
        """Set the stop-conditions, unless some were given at construction"""
        if self._is_default_stop_condition:
            self.set_stop_conditions(stop_conditions)


class AsyncAdapter(AsyncEndpoint[DataT], Generic[DescriptorT, DataT]):
    """
    Async adapter, same parameters as Adapter

    auto_open submits the open without waiting for it, see AsyncEndpoint
    """

    def __init__(
        self,
        backend: AdapterBackend[DescriptorT, DataT],
        framer: Framer[DataT],
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._descriptor = backend.descriptor
        self._is_default_timeout = timeout is ...
        self._is_default_stop_condition = stop_conditions is ...

        engine = _build_engine(backend, framer, timeout, stop_conditions, alias)
        # The reactor holds the engine, stop it once the adapter is unreachable
        weakref.finalize(self, engine.stop)
        super().__init__(engine, auto_open=auto_open and backend.descriptor.is_initialized())

    def __str__(self) -> str:
        return str(self._descriptor)

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def engine(self) -> Engine[DescriptorT, DataT]:
        """
        Non-blocking side of the adapter, every method returns a future

        Neither sync nor async, protocols sit on it
        """
        return cast("Engine[DescriptorT, DataT]", self._engine)

    @property
    def descriptor(self) -> DescriptorT:
        """Parameters of the target (address, port, baudrate, ...)"""
        return self._descriptor

    @property
    def has_default_timeout(self) -> bool:
        """True if no timeout was given at construction, a protocol then sets its own"""
        return self._is_default_timeout

    @property
    def stop_conditions(self) -> list[StopCondition]:
        """Stop-conditions of the framer"""
        return self.engine.stop_conditions

    async def set_stop_conditions(
        self, stop_conditions: StopCondition | list[StopCondition]
    ) -> None:
        """Set the stop-conditions of the framer"""
        await asyncio.wrap_future(self.engine.set_stop_conditions(_as_list(stop_conditions)))

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
