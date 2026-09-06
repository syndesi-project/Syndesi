# File : adapter.py
# Author : Sébastien Deriaz
# License : GPL

"""
Adapters provide a common abstraction for the media layers (physical + data link + network)

The user calls methods of the Adapter class synchronously.

An adapter's read/write data type is defined by its DataT generic parameter
(e.g. BytesAdapter subclasses read/write bytes). No implicit str<->bytes
conversion is performed; protocols such as Delimited handle encoding instead.

Each adapter contains a worker thread that monitors the low-level communication layers.
This approach allows for precise time management (when each fragment is sent/received) and allows
for asynchronous events (fragment received).

Async facade:
- aopen/awrite/aread/aread_detailed simply await the SAME underlying worker-thread commands
  using asyncio.wrap_future (no extra threads are spawned).
"""

import asyncio
import threading
import weakref
from types import EllipsisType
from typing import Any, Generic, TypeVar, get_args, get_origin

from syndesi.adapters.stop_conditions import StopCondition
from syndesi.tools.errors import AdapterError

from ..component import AsyncComponent, Component, ComponentCommon, ReadFrame, ReadScope
from ..tools.log_settings import LoggerAlias
from .adapterworker import (
    AdapterWorker,
    AdapterWorkerInterface,
)
from .utils import TimeoutParameterType, TimeoutType

DataT = TypeVar("DataT")

class AdapterCommon(Generic[DataT], ComponentCommon[DataT], AdapterWorkerInterface[DataT]):
    """
    This is a generic class from which all adapters (sync and async) should inherit.
    It provides basic functionnalities common to each
    """
    def __init__(
            self,
            worker: AdapterWorker[DataT],
            timeout: TimeoutParameterType,
            alias: str,
            auto_open: bool,
            logger_alias: LoggerAlias
        ) -> None:
        ComponentCommon.__init__(self, logger_alias)
        AdapterWorkerInterface.__init__(self, worker, timeout, alias, auto_open)

        weakref.finalize(self, self._cleanup)


    def open(self) -> None:
        """
        Open adapter communication with the target (blocking)
        """
        # If timeout is None, wait indefinitely
        # If timeout is not None, add a small amount (IMMEDIATE_COMMAND)
        # To let the worker setup and respond. The "real" timeout is used in the _worker_open
        # method
        timeout : float | None
        if self.timeout is None:
            timeout = None
        else:
            timeout = self.timeout + self.WorkerTimeout.IMMEDIATE_COMMAND.value

        output = self._open_future().result(timeout)
        return output



    def close(self) -> None:
        """
        Close adapter communication with the target (blocking)
        """
        self._close_future().result(self.WorkerTimeout.CLOSE.value)

    @property
    def timeout(self) -> TimeoutType:
        """Return the adapter's timeout. The timeout is used:
            * To set the opening time
            * Define the maximum time before a fragment is received when reading"""
        return self._worker.timeout

    def _cleanup(self) -> None:
        try:
            if self.is_open:
                self.close()
        except AdapterError:
            pass
        self._stop()

class Adapter(Generic[DataT], AdapterCommon[DataT], Component[DataT]):
    """
    Adapter class

    An adapter manages communication with a hardware device.
    """    

    def __init__(
        self,
        *,
        worker: AdapterWorker[DataT],
        timeout: TimeoutParameterType,
        alias: str,
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            worker=worker,
            timeout=timeout,
            alias=alias,
            auto_open=auto_open,
            logger_alias=LoggerAlias.ADAPTER
        )

        self._sync_io_lock = threading.Lock()

        if self.descriptor.is_initialized() and self._auto_open:
            self.open()

    # ┌──────────────────────────┐
    # │ Defaults / configuration │
    # └──────────────────────────┘

    def __str__(self) -> str:
        return str(self.descriptor)

    def __repr__(self) -> str:
        return self.__str__()

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ReadFrame[DataT]:
        with self._sync_io_lock:
            result = self._read_detailed_future(
                timeout=timeout, scope=ReadScope(scope), stop_conditions=stop_conditions
            ).result(self.WorkerTimeout.READ.value)
        return result

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> DataT:
        frame = self.read_detailed(
            timeout=timeout, scope=scope, stop_conditions=stop_conditions
        )
        return frame.data

    def clear_read_buffer(self) -> None:
        """
        Clear buffered completed frames and reset current fragment assembly (blocking)
        """
        with self._sync_io_lock:
            self._clear_read_buffer_future().result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)    

    def write(self, data: DataT) -> None:
        with self._sync_io_lock:
            self._write_future(data).result(self.WorkerTimeout.WRITE.value)

    def query_detailed(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...
    ) -> ReadFrame[DataT]:

        with self._sync_io_lock:
            self._write_future(payload).result(self.WorkerTimeout.WRITE.value)
            output = self._read_detailed_future(
                timeout=timeout,
                scope=ReadScope.LAST_WRITE,
                stop_conditions=stop_conditions
            ).result(self.WorkerTimeout.READ.value)
        return output

def find_adapter_data_type(obj : type[Adapter[Any]] | Adapter[Any]) -> Any:
    """
    Supports:
    - Adapter[bytes]
    - class MyAdapter(Adapter[bytes]): ...
    - MyAdapter() instance

    Returns the concrete DataT, or None if it cannot be determined.
    """

    # Case 1: direct parametrized generic, e.g. Adapter[bytes]
    if get_origin(obj) is Adapter:
        args = get_args(obj)
        return args[0] if args else None

    # Normalize class / instance
    cls = obj if isinstance(obj, type) else type(obj)

    # Case 2: subclass, e.g. class MyAdapter(Adapter[bytes])
    bases = getattr(cls, "__orig_bases__", cls.__bases__)
    for base in bases:
        if get_origin(base) is Adapter:
            args = get_args(base)
            return args[0] if args else None

    return None

class AsyncAdapter(Generic[DataT], AdapterCommon[DataT], AsyncComponent[DataT]):
    """
    AsyncAdapter class

    An adapter manages communication with a hardware device.
    """

    def __init__(
            self,
            *,
            worker: AdapterWorker[DataT],
            timeout: TimeoutParameterType,
            alias: str,
            auto_open: bool = False,
        ) -> None:
        AsyncComponent.__init__(self, LoggerAlias.ADAPTER)
        AdapterWorkerInterface.__init__(self, worker, timeout, alias, auto_open)

        self._logger.info(f"Setting up {self.descriptor} adapter ")

        self._async_io_lock = asyncio.Lock()

        if self.descriptor.is_initialized() and self._auto_open:
            self.open()

    async def open_async(self) -> None:
        """
        Open adapter communication with the target (async)
        """
        await asyncio.wrap_future(self._open_future())

    async def close_async(self) -> None:
        """
        Close adapter communication with the target (async)
        """
        await asyncio.wrap_future(self._close_future())

    async def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ReadFrame[DataT]:
        async with self._async_io_lock:
            return await asyncio.wrap_future(
                self._read_detailed_future(
                    timeout=timeout, scope=ReadScope(scope), stop_conditions=stop_conditions
                )
            )

    async def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> DataT:
        frame = await self.read_detailed(
            timeout=timeout, scope=scope, stop_conditions=stop_conditions
        )
        return frame.data

    async def clear_read_buffer(self) -> None:
        """
        Clear buffered completed frames and reset current fragment assembly (async)
        """
        async with self._async_io_lock:
            await asyncio.wrap_future(self._clear_read_buffer_future())

    async def write(self, data: DataT) -> None:
        async with self._async_io_lock:
            await asyncio.wrap_future(self._write_future(data))

    async def query_detailed(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        ) -> ReadFrame[DataT]:
        async with self._async_io_lock:
            await asyncio.wrap_future(self._write_future(payload))
            return await asyncio.wrap_future(
                self._read_detailed_future(
                    timeout=timeout,
                    scope=ReadScope.LAST_WRITE,
                    stop_conditions=stop_conditions
                )
            )